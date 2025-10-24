# -*- coding: utf-8 -*-
"""
ifc_to_canonical.py
End-to-end CLI:
- 讀取 Wendy 的 UIR JSONL（每行一個 entity 包）
- 呼叫 llm_runner.class_mapping / property_extraction
- 規則化單位 (deterministic TE)
- 驗證（必填/範圍/鄰居一致性/AI 置信度）
- 產生 canonical CSV：assets / asset_props / asset_relations / asset_flags
- 報表 stage_report.json
"""

from __future__ import annotations
import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid
import re

# ---------- Setup logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("ifc_to_canonical")

# ---------- Import llm_runner ----------
try:
    from llm_runner import class_mapping as llm_class_map
    from llm_runner import property_extraction as llm_prop_extract
except Exception as e:
    log.error("Cannot import llm_runner: %s", e)
    raise

# =========================
# Config helpers
# =========================
def load_yaml(path: Path) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.warning("YAML load failed for %s: %s", path, e)
        return {}

def ensure_outdir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

# =========================
# Templates
# =========================
def read_text_if_exists(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

# =========================
# Deterministic TE: unit normalization
# =========================

_NUM_UNIT_RE = re.compile(
    r"""(?xi)
    (?P<num>
        [-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)? |
        [-+]?\d+(?:\.\d+)?
    )
    \s*
    (?P<unit>[a-zA-Z°/%³²^/]+)?
    """
)
_DIAM_RE = re.compile(r"(?i)[øØφphi]*\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|in|\"|')")

NAME_ALIASES = {
    # 幾何
    "length":"length","width":"length","height":"length","depth":"length","thickness":"length","diameter":"length","dia":"length","radius":"length",
    "netarea":"area","grossarea":"area","area":"area","netsidearea": "area","crosssectionarea": "area",
    "netvolume":"volume","grossvolume":"volume","volume":"volume",
    # 流量/速度
    "flow":"vol_flow","flow_rate":"vol_flow","q":"vol_flow","airflow":"vol_flow","cfm":"vol_flow","velocity":"velocity",
    # 功率/能量/電
    "power":"power","rated_power":"power","kw":"power","power_kw":"power","btu/h":"power","heat_gain":"power","heat_loss":"power",
    "voltage":"voltage","current":"current","frequency":"frequency","power_factor":"unitless",
    # 溫度/壓力
    "temperature":"temperature","temp":"temperature","setpoint":"temperature",
    "pressure":"pressure","press":"pressure","static_pressure":"pressure",
    # 其他
    "percent":"percent","percentage":"percent","efficiency":"percent","angle":"angle",
    
}
UNIT_CANON = {
    "m":"m","meter":"m","metre":"m",
    "mm":"mm","cm":"cm","in":"in","\"":"in","inch":"in","ft":"ft","'":"ft",
    "m2":"m²","m^2":"m²","m²":"m²","mm2":"mm²","cm2":"cm²","ft2":"ft²","sqft":"ft²","sf":"ft²",
    "m3":"m³","m^3":"m³","m³":"m³","l":"L","liter":"L","litre":"L","ml":"mL","ft3":"ft³","cf":"ft³","cuft":"ft³","gal":"gal","gallon":"gal",
    "w":"W","kw":"kW","hp":"hp","btu/h":"BTU/h","btuh":"BTU/h",
    "pa":"Pa","kpa":"kPa","mpa":"MPa","bar":"bar","psi":"psi",
    "c":"°C","°c":"°C","f":"°F","°f":"°F","k":"K",
    "l/s":"L/s","lps":"L/s","l/sec":"L/s","l/min":"L/min","lpm":"L/min",
    "m3/h":"m³/h","m3/s":"m³/s","m³/h":"m³/h","m³/s":"m³/s","cfm":"CFM","gpm":"GPM",
    "m/s":"m/s","rpm":"RPM","hz":"Hz",
    "%":"%",
}

def _to_float(x) -> Optional[float]:
    if x is None: return None
    if isinstance(x,(int,float)): return float(x)
    s = str(x).strip().replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

def _parse_num_unit_from_string(s: str) -> Tuple[Optional[float], Optional[str]]:
    if not isinstance(s, str):
        return _to_float(s), None
    s = s.strip()
    m = _DIAM_RE.search(s)
    if m:
        v = _to_float(m.group("num"))
        u = UNIT_CANON.get(m.group("unit").lower(), m.group("unit"))
        return v, u
    m = _NUM_UNIT_RE.search(s)
    if not m:
        return _to_float(s), None
    v = _to_float(m.group("num"))
    u = m.group("unit")
    if u:
        u = UNIT_CANON.get(u.lower(), u)
    return v, u

def _canon_kind(name: str) -> str:
    n = (name or "").strip().lower()
    if n in NAME_ALIASES: return NAME_ALIASES[n]
    if n.endswith("_mm") or "(mm)" in n: return "length"
    if n.endswith("_m") or "(m)" in n: return "length"
    if n.endswith("_cm"): return "length"
    if n.endswith("_ft") or "(ft)" in n: return "length"
    if "area" in n: return "area"
    if "volume" in n: return "volume"
    if "pressure" in n: return "pressure"
    if "temperature" in n or "temp" in n: return "temperature"
    if "flow" in n or "cfm" in n: return "vol_flow"
    if "velocity" in n: return "velocity"
    if "power" in n or "btu" in n: return "power"
    if "voltage" in n: return "voltage"
    if "current" in n: return "current"
    if "frequency" in n: return "frequency"
    if "percent" in n or n.endswith("_pct"): return "percent"
    return "unknown"

def normalize_unit(name: str, value, unit: Optional[str], unit_overrides: Dict[str, Any] | None = None):
    """回傳 (value_norm, unit_norm, reason)"""
    kind = _canon_kind(name)
    v, u = None, None

    # overrides: 預設單位（只有在缺單位時才補）
    default_u = None
    if unit_overrides and "defaults" in unit_overrides:
        default_u = unit_overrides["defaults"].get((name or "").strip().lower())

    # parse
    if isinstance(value, str):
        v, parsed_u = _parse_num_unit_from_string(value)
        u = parsed_u or unit or default_u
    else:
        v = _to_float(value)
        u = unit or default_u

    if u:
        u = UNIT_CANON.get((u or "").lower(), u)

    if v is None:
        return None, u, "no_value"

    # Length -> m
    if kind == "length":
        if not u or u == "m": return v, "m", "ok" if u else "assume_m"
        if u == "mm": return v/1000.0, "m", "mm_to_m"
        if u == "cm": return v/100.0, "m", "cm_to_m"
        if u == "in": return v*0.0254, "m", "in_to_m"
        if u == "ft": return v*0.3048, "m", "ft_to_m"
        return v, u, "length_noop"

    # Area -> m²
    if kind == "area":
        if not u or u in ["m²","m2"]: return v, "m²", "ok" if u else "assume_m2"
        if u in ["mm²","mm2"]: return v/1e6, "m²", "mm2_to_m2"
        if u in ["cm²","cm2"]: return v/1e4, "m²", "cm2_to_m2"
        if u in ["ft²","ft2","ft^2","sqft","sf"]: return v*0.09290304, "m²", "ft2_to_m2"
        return v, u, "area_noop"

    # Volume -> m³
    if kind == "volume":
        if not u or u in ["m³","m3"]: return v, "m³", "ok" if u else "assume_m3"
        if u in ["L","l"]: return v/1000.0, "m³", "L_to_m3"
        if u == "mL": return v/1e6, "m³", "mL_to_m3"
        if u in ["ft³","ft3"]: return v*0.0283168466, "m³", "ft3_to_m3"
        if u in ["gal","gallon"]: return v*0.00378541178, "m³", "gal_to_m3"
        return v, u, "volume_noop"

    # Volume flow -> L/s
    if kind == "vol_flow":
        if not u: return v, "L/s", "assume_Lps"
        if u in ["L/s"]: return v, "L/s", "ok"
        if u in ["L/min","lpm"]: return v/60.0, "L/s", "Lpm_to_Lps"
        if u in ["m³/h","m3/h"]: return v*1000/3600.0, "L/s", "m3h_to_Lps"
        if u in ["m³/s","m3/s"]: return v*1000.0, "L/s", "m3s_to_Lps"
        if u == "CFM": return v*0.47194745, "L/s", "cfm_to_Lps"
        if u == "GPM": return v*0.0630902, "L/s", "gpm_to_Lps"
        return v, u, "flow_noop"

    # Temperature -> °C
    if kind == "temperature":
        if not u or u in ["°C","C","c"]: return v, "°C", "ok" if u else "assume_C"
        if u in ["°F","F","f"]: return (v-32)*5.0/9.0, "°C", "F_to_C"
        if u == "K": return v-273.15, "°C", "K_to_C"
        return v, u, "temp_noop"

    # Pressure -> Pa
    if kind == "pressure":
        if not u or u == "Pa": return v, "Pa", "ok" if u else "assume_Pa"
        if u == "kPa": return v*1000.0, "Pa", "kPa_to_Pa"
        if u == "MPa": return v*1e6, "Pa", "MPa_to_Pa"
        if u == "bar": return v*1e5, "Pa", "bar_to_Pa"
        if u == "psi": return v*6894.75729, "Pa", "psi_to_Pa"
        return v, u, "press_noop"

    # Power -> kW
    if kind == "power":
        if not u or u == "kW": return v, "kW", "ok" if u else "assume_kW"
        if u == "W": return v/1000.0, "kW", "W_to_kW"
        if u == "hp": return v*0.745699872, "kW", "hp_to_kW"
        if u == "BTU/h": return v*0.00029307107, "kW", "BTUh_to_kW"
        return v, u, "power_noop"

    # Voltage / Current / Frequency / Percent / Angle
    if kind == "voltage":
        return v, "V" if (not u or str(u).lower()=="v") else u, "ok"
    if kind == "current":
        return v, "A" if (not u or str(u).lower()=="a") else u, "ok"
    if kind == "frequency":
        return v, "Hz" if (not u or str(u).lower()=="hz") else u, "ok"
    if kind == "percent":
        if 0 <= v <= 1 and (u is None or u==""):
            return v*100.0, "%", "fraction_to_percent"
        return v, "%" if not u else u, "ok"
    if kind == "angle":
        return v, "deg" if (not u) else u, "ok"

    return v, u, "noop"

# =========================
# Validation
# =========================

def validate_required(props_flat: Dict[str, Any], required: List[str]) -> List[str]:
    missing = []
    for k in required or []:
        if k not in props_flat or props_flat.get(k) in (None, "", [], {}):
            missing.append(k)
    return missing

def validate_ranges(prop_name: str, value_norm: Optional[float], ranges: Dict[str, Any]) -> Optional[str]:
    if value_norm is None: return None
    r = ranges.get(prop_name) if ranges else None
    if not r: return None
    mn = r.get("min"); mx = r.get("max")
    if mn is not None and value_norm < mn: return f"value {value_norm} < min {mn}"
    if mx is not None and value_norm > mx: return f"value {value_norm} > max {mx}"
    return None

def validate_neighbors(canonical_class: str, neighbors: List[Dict[str, Any]], neighbor_rules: Dict[str, Any]) -> Optional[str]:
    if not canonical_class or not neighbor_rules: return None
    expect = neighbor_rules.get(canonical_class)
    if not expect: return None
    # 簡單檢查：是否至少有一個在期待清單中的 class
    classes = [n.get("class") for n in neighbors or []]
    if not any(c in expect for c in classes):
        return f"expected any of {expect}, got {classes}"
    return None

# =========================
# Helpers
# =========================
def stable_uuid(source: str, local_id: str) -> str:
    name = f"{source}:{local_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

def flatten_known_props(entity_props: Dict[str, Any]) -> Dict[str, Any]:
    flat = {}
    for pset, kv in (entity_props or {}).items():
        if isinstance(kv, dict):
            for k, v in kv.items():
                if k == "id": continue
                flat[str(k)] = v
    return flat

# =========================
# Core
# =========================
def process_one_pack(
    pack: Dict[str, Any],
    class_tmpl: str,
    prop_tmpl: str,
    allowed_classes: List[str],
    top_n: int,
    model_cfg: Dict[str, Any],
    te_cfg: Dict[str, Any],
    rule_required: Dict[str, Any],
    rule_ranges: Dict[str, Any],
    neighbor_rules: Dict[str, Any],
    conf_threshold: float,
    out_rows_assets: List[Dict[str, Any]],
    out_rows_props: List[Dict[str, Any]],
    out_rows_rel: List[Dict[str, Any]],
    out_rows_flags: List[Dict[str, Any]],
) -> None:

    ent = pack.get("entity") or {}
    run_id = pack.get("run_id") or "unknown_run"

    # 來源/本地ID：以 Wendy 的 pack 欄位為準
    source = run_id
    local_id = ent.get("uid") or ent.get("global_id") or ent.get("id") or "unknown"
    asset_id = stable_uuid(source, str(local_id))

    # LLM：class mapping
    cls_out = llm_class_map(pack, class_tmpl, allowed_classes, top_n, model_cfg)
    canonical = cls_out.get("canonical_class")
    class_conf = float(cls_out.get("confidence") or 0.0)
    class_codes = cls_out.get("class_codes") or {}

    # 已有屬性攤平
    known_flat = flatten_known_props(ent.get("properties"))
    # LLM：抽缺屬性（mock 目前返回空）
    new_props = llm_prop_extract(pack, prop_tmpl, canonical, known_flat, top_n, model_cfg)

    # 合併屬性，new_props 覆蓋舊的同名（若有）
    merged_props: Dict[str, Dict[str, Any]] = {}  # name -> {v,u,confidence,source}
    # 先放已知
    for k, v in known_flat.items():
        merged_props[k] = {"v": v, "u": None, "confidence": 1.0, "source": "ifc"}
    # 再放 LLM 新增
    for rec in new_props or []:
        k = str(rec.get("k"))
        if not k: continue
        merged_props[k] = {
            "v": rec.get("v"),
            "u": rec.get("u"),
            "confidence": float(rec.get("confidence") or 0.0),
            "source": "llm",
        }

    # TE：單位正規化
    unit_overrides = load_yaml(Path("rules/unit_overrides.yaml"))
    for name, obj in merged_props.items():
        v_raw = obj.get("v")
        u_raw = obj.get("u")
        v_norm, u_norm, reason = normalize_unit(name, v_raw, u_raw, unit_overrides)
        obj["value_raw"] = v_raw
        obj["unit_raw"] = u_raw
        obj["value_norm"] = v_norm
        obj["unit_norm"] = u_norm
        obj["te_reason"] = reason

    # 寫 assets（1 row）
    out_rows_assets.append({
        "asset_id": asset_id,
        "source": source,
        "local_id": local_id,
        "ifc_class": ent.get("ifc_class"),
        "name": ent.get("name"),
        "canonical_class": canonical,
        "class_confidence": class_conf,
        "class_codes": json.dumps(class_codes, ensure_ascii=False),
        "location_site": None,  # 可從 entity.spatial_path 拆，如果需要
        "location_building": None,
        "location_level": None,
        "location_space": None,
    })

    # 寫 props（N rows）
    for name, obj in merged_props.items():
        out_rows_props.append({
            "asset_id": asset_id,
            "name": name,
            "value_raw": obj.get("value_raw"),
            "unit_raw": obj.get("unit_raw"),
            "value_norm": obj.get("value_norm"),
            "unit_norm": obj.get("unit_norm"),
            "confidence": obj.get("confidence"),
            "source": obj.get("source"),
            "te_reason": obj.get("te_reason"),
        })

    # 寫 relations（neighbors）
    for nb in pack.get("neighbors") or []:
        out_rows_rel.append({
            "asset_id": asset_id,
            "relation": nb.get("rel"),
            "direction": nb.get("direction"),
            "neighbor_class": nb.get("class"),
            "neighbor_name": nb.get("name"),
            "neighbor_uid": nb.get("uid"),
        })

    # 驗證：flags
    # - AI 低置信度
    if class_conf < conf_threshold:
        out_rows_flags.append({"asset_id": asset_id, "flag": "LOW_AI_CONF", "reason": f"class_conf={class_conf}"})

    # - MISSING_REQUIRED_PROPERTY / OUT_OF_RANGE
    required = (rule_required or {}).get(canonical) or []
    missing = validate_required(
        {k: merged_props.get(k, {}).get("value_norm") for k in merged_props}, required
    )
    for k in missing:
        out_rows_flags.append({"asset_id": asset_id, "flag": "MISSING_REQUIRED_PROPERTY", "reason": k})

    for k, obj in merged_props.items():
        msg = validate_ranges(k, obj.get("value_norm"), rule_ranges or {})
        if msg:
            out_rows_flags.append({"asset_id": asset_id, "flag": "OUT_OF_RANGE", "reason": f"{k}: {msg}"})

    # - INCONSISTENT_NEIGHBOR（很簡單的期望檢查）
    msg = validate_neighbors(canonical, pack.get("neighbors") or [], neighbor_rules or {})
    if msg:
        out_rows_flags.append({"asset_id": asset_id, "flag": "INCONSISTENT_NEIGHBOR", "reason": msg})


# =========================
# CLI
# =========================
def main():
    ap = argparse.ArgumentParser(description="IFC → Canonical CSV pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    runp = sub.add_parser("run", help="run pipeline")
    runp.add_argument("--in", dest="infile", required=True, help="input JSONL (uir_enriched.jsonl)")
    runp.add_argument("--outdir", required=True, help="output dir")
    runp.add_argument("--config", required=False, default="config.yaml", help="config.yaml")
    runp.add_argument("--limit", type=int, default=0, help="limit number of lines (0=all)")
    runp.add_argument("--tolerant", action="store_true", help="continue on errors")

    args = ap.parse_args()

    if args.cmd == "run":
        infile = Path(args.infile)
        outdir = Path(args.outdir)
        cfg = load_yaml(Path(args.config))
        ensure_outdir(outdir)
        ensure_outdir(Path("logs"))
        ensure_outdir(Path("logs/errors"))

        # config
        raw_model = cfg.get("model", "mock")
        # 允許 YAML 寫成 "model: mock" 或 "model: {model: mock, ...}"
        if isinstance(raw_model, str):
            model_cfg = {"model": raw_model, "max_tokens": 800, "temperature": 0.0}
        elif isinstance(raw_model, dict):
            model_cfg = {"model": raw_model.get("model", "mock"),
                        "max_tokens": raw_model.get("max_tokens", 800),
                        "temperature": raw_model.get("temperature", 0.0)}
        else:
            model_cfg = {"model": "mock", "max_tokens": 800, "temperature": 0.0}

        conf_threshold = float(cfg.get("confidence_threshold", 0.75))
        top_n = int(cfg.get("retrieval_top_n", 5))

        # rules
        class_maps = load_yaml(Path("rules/class_maps.yaml"))
        allowed_classes = class_maps.get("allowed_classes") or list(set((class_maps.get("ifc_to_canonical") or {}).values()))
        required_rules = load_yaml(Path("rules/required_props.yaml"))
        ranges_rules = load_yaml(Path("rules/ranges.yaml"))
        neighbor_rules = load_yaml(Path("rules/neighbor_rules.yaml"))

        # templates
        class_tmpl = read_text_if_exists(Path("prompt_templates/class_mapping.txt"))
        prop_tmpl = read_text_if_exists(Path("prompt_templates/property_extraction.txt"))

        # outputs
        assets_rows: List[Dict[str, Any]] = []
        props_rows: List[Dict[str, Any]] = []
        rel_rows: List[Dict[str, Any]] = []
        flag_rows: List[Dict[str, Any]] = []

        total = 0
        errors = 0

        log.info("Reading %s ...", infile)
        with infile.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                total += 1
                if args.limit and total > args.limit:
                    break
                try:
                    pack = json.loads(line)
                    process_one_pack(
                        pack, class_tmpl, prop_tmpl, allowed_classes, top_n, model_cfg,
                        te_cfg={}, rule_required=required_rules, rule_ranges=ranges_rules,
                        neighbor_rules=neighbor_rules, conf_threshold=conf_threshold,
                        out_rows_assets=assets_rows, out_rows_props=props_rows,
                        out_rows_rel=rel_rows, out_rows_flags=flag_rows
                    )
                except Exception as e:
                    errors += 1
                    log.exception("Error on index=%s: %s", i, e)
                    # dump head for debug
                    try:
                        head = line[:500]
                    except Exception:
                        head = ""
                    err_path = Path("logs/errors/error_%s.json" % i)
                    err_payload = {
                        "index": i,
                        "error": str(e),
                        "raw_head": head
                    }
                    err_path.write_text(json.dumps(err_payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    if not args.tolerant:
                        break

        # write CSVs
        def write_csv(path: Path, rows: List[Dict[str, Any]], headers: List[str]):
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                for r in rows:
                    w.writerow({k: r.get(k) for k in headers})

        write_csv(outdir / "assets.csv", assets_rows, [
            "asset_id","source","local_id","ifc_class","name",
            "canonical_class","class_confidence","class_codes",
            "location_site","location_building","location_level","location_space"
        ])
        write_csv(outdir / "asset_props.csv", props_rows, [
            "asset_id","name","value_raw","unit_raw","value_norm","unit_norm","confidence","source","te_reason"
        ])
        write_csv(outdir / "asset_relations.csv", rel_rows, [
            "asset_id","relation","direction","neighbor_class","neighbor_name","neighbor_uid"
        ])
        write_csv(outdir / "asset_flags.csv", flag_rows, [
            "asset_id","flag","reason"
        ])

        # stage report
        stage_report = {
            "total_input_lines": total,
            "assets_written": len(assets_rows),
            "props_written": len(props_rows),
            "relations_written": len(rel_rows),
            "flags_written": len(flag_rows),
            "errors": errors
        }
        (outdir / "stage_report.json").write_text(json.dumps(stage_report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(stage_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
