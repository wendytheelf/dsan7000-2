# -*- coding: utf-8 -*-
"""
llm_runner.py — resilient LLM wrapper with mock-classifier
- Safe template rendering (avoids KeyError from literal { } in templates)
- Mock model ("model: mock") that maps IFC -> Tier-1 canonical using rules + keywords
- Non-mock: keep run_llm() placeholder; pipeline will still fall back gracefully
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List
import requests

# ---------------------------------------------------------------------
# Low-noise logging
# ---------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Retrieved docs formatting (for prompts)
# ---------------------------------------------------------------------
def _format_retrieved_block(retrieved_docs: List[Dict[str, Any]], top_n: int) -> str:
    if not retrieved_docs:
        return ""
    docs = sorted(retrieved_docs, key=lambda d: -(d.get("rerank") or 0.0))[:top_n]
    lines = []
    for i, d in enumerate(docs, 1):
        title = (d.get("title") or "").strip()
        snippet = (d.get("snippet") or "").strip()
        lines.append(
            f"[{i}] {title}\n{snippet}\n"
            f"(source={d.get('source','')}, score={d.get('score')}, rerank={d.get('rerank')})"
        )
    return "\n---\n".join(lines)


# ---------------------------------------------------------------------
# Safe template rendering
#   1) prefer [[var]] tokens (literal braces are harmless)
#   2) try str.format(**mapping); if fails (KeyError due to literals), fallback
#   3) fallback: build brace-safe JSON prompt programmatically
# ---------------------------------------------------------------------
def _render_template_safe_or_none(tmpl: str, mapping: Dict[str, str]) -> str | None:
    # 1) [[var]] style
    out = tmpl
    for k, v in mapping.items():
        token = f"[[{k}]]"
        if token in out:
            out = out.replace(token, v)
    if out != tmpl:
        return out

    # 2) try {var} style directly
    try:
        return tmpl.format(**mapping)
    except Exception as e:
        logger.debug("Template format failed (%s). Will fallback to JSON-style prompt.", e)
        return None


# ---------------------------------------------------------------------
# LLM runner
#   - mock: handled in class_mapping/property_extraction
#   - non-mock: raise (you can implement HTTP to your Llama endpoint here)
# ---------------------------------------------------------------------
# def run_llm(prompt: str, model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
#     # If you wire up a real endpoint, implement it here.
#     raise NotImplementedError("Connect Llama here.")

def run_llm(prompt: str, model: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """
    Generic LLM caller.
    - If model == 'mock': 不會進到這裡（上層已處理）
    - 其他情況：視為 Ollama 模型名稱，呼叫本機 Ollama API (/api/generate)

    注意：
    - 這個函式只回傳「模型生成的純文字」，上層會再用 json.loads() 解析。
    - prompt 已經在 class_mapping / property_extraction 中加好：
      '請回傳有效 JSON' 的指示。
    """
    model_name = _normalize_model_name(model)

    if not model_name:
        raise ValueError("run_llm called with empty model name")

    # Ollama /api/generate 文件的基本格式：
    # POST http://127.0.0.1:11434/api/generate
    # payload: { "model": "...", "prompt": "...", "stream": false, "options": { ... } }
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            # Ollama 參數名稱是 num_predict，不是 max_tokens：
            # 這裡直接使用同樣概念
            "num_predict": int(max_tokens),
            "temperature": float(temperature),
        },
    }

    try:
        resp = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json=payload,
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()
        # Ollama /api/generate 回傳格式：{ "model": "...", "created_at": "...", "response": "..." , ... }
        text = data.get("response", "")
        if not isinstance(text, str):
            raise ValueError(f"Ollama response missing 'response' text: {data}")
        return text
    except Exception as e:
        logger.error("run_llm failed for model=%s: %s", model_name, e)
        # 讓上層 class_mapping / property_extraction 的 try/except 去 fallback
        raise


# ---------------------------------------------------------------------
# Helpers for mock classifier
# ---------------------------------------------------------------------
def _norm(s: Any) -> str:
    return (s or "").strip().lower()

def _normalize_model_name(model: str | None) -> str:
    """
    Normalize model name for Ollama.
    - Strips spaces
    - If it starts with 'ollama:', remove這個 prefix
      e.g. 'ollama:qwen2.5:7b-instruct' → 'qwen2.5:7b-instruct'
    """
    if not model:
        return ""
    m = model.strip()
    if m.startswith("ollama:"):
        return m.split(":", 1)[1]
    return m


def _hit(name: str, keywords: List[str] | None) -> bool:
    if not keywords:
        return False
    n = _norm(name)
    return any(_norm(kw) in n for kw in keywords)


def _load_class_maps() -> Dict[str, Any]:
    try:
        import yaml  # local dependency
        from pathlib import Path
        p = Path("rules/class_maps.yaml")
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.debug("Failed loading class_maps.yaml: %s", e)
    return {}


def _mock_map_to_tier1(ent: Dict[str, Any], class_maps: Dict[str, Any]) -> str | None:
    """Heuristic mapping using IFC class + attributes + name keywords."""
    ifc = ent.get("ifc_class") or ""
    name = ent.get("name") or ""
    attrs = ent.get("attributes") or {}
    ptype = _norm(attrs.get("PredefinedType") or attrs.get("Predefinedtype") or "")

    base_map: Dict[str, str] = (class_maps.get("ifc_to_canonical") or {})
    kw: Dict[str, List[str]] = class_maps.get("keyword_overrides") or {}
    canonical = base_map.get(ifc)

    # ----- Walls: external vs internal by name -----
    if ifc == "IfcWall":
        if _hit(name, kw.get("External walls (façade)")):
            canonical = "External walls (façade)"
        elif _hit(name, kw.get("Internal walls")):
            canonical = "Internal walls"

    # ----- Slab/Floor/Roof/Foundation via PredefinedType+name -----
    if ifc == "IfcSlab":
        if ptype == "baseslab" or _hit(name, kw.get("Foundation_Slab")):
            canonical = "Foundation_Slab"
        elif ptype == "floor" or _hit(name, kw.get("Floors")):
            canonical = "Floors"
        elif ptype == "roof" or _hit(name, kw.get("Roof")):
            canonical = "Roof"
        else:
            canonical = canonical or "Slabs"

    if ifc == "IfcCovering":
        if ptype == "ceiling":
            canonical = "Ceilings"
        elif ptype == "flooring":
            canonical = "Floors"

    # ----- Column/Beam material split by name keywords (very heuristic) -----
    if ifc == "IfcColumn":
        if _hit(name, kw.get("Column (Steel)")):
            canonical = "Column (Steel)"
        else:
            canonical = "Columns (Concrete)"
    if ifc == "IfcBeam":
        if _hit(name, kw.get("Beam (Steel)")):
            canonical = "Beam (Steel)"
        else:
            canonical = "Beam (Concrete)"

    # ----- Duct / Pipe / Cable / Conduit family -----
    if ifc == "IfcDuctSegment":
        canonical = "Flexible duct"  # default
    if ifc == "IfcFireSuppressionTerminal":
        for lab in ["Sprinkler", "Extinguishers", "Hose reel", "Hydrant"]:
            if _hit(name, kw.get(lab)):
                canonical = lab
                break
    if ifc == "IfcFlowTerminal":
        for lab in ["Sink", "Hose reel", "Hydrant"]:
            if _hit(name, kw.get(lab)):
                canonical = lab
                break
    if ifc == "IfcLamp":
        if _hit(name, kw.get("Emergency lighting")):
            canonical = "Emergency lighting"
    if ifc == "IfcAlarm":
        if _hit(name, kw.get("Fire Alarm Control panel")):
            canonical = "Fire Alarm Control panel"
        elif _hit(name, kw.get("Audible/visual discharge alarm")):
            canonical = "Audible/visual discharge alarm"
    if ifc == "IfcSensor":
        canonical = "Detector"
    if ifc == "IfcLightFixture":
        canonical = "Lighting Fixture"
    if ifc == "IfcSwitchingDevice":
        canonical = "Switch (various types)"
    if ifc == "IfcOutlet":
        canonical = "Sockets"
    if ifc == "IfcCableSegment":
        canonical = "Conduit"
    if ifc == "IfcCableFitting":
        canonical = "Conduit fittings"

    # Fallback: IfcXxx → Xxx, only if inside allowed_classes
    if not canonical:
        m = re.match(r"Ifc([A-Za-z0-9_]+)", ifc or "")
        guess = m.group(1) if m else None
        allowed = set(class_maps.get("allowed_classes") or [])
        if guess in allowed:
            canonical = guess

    return canonical


# ---------------------------------------------------------------------
# class_mapping: builds prompt safely, supports mock, otherwise call LLM
# ---------------------------------------------------------------------
def class_mapping(
    pack: Dict[str, Any],
    tmpl: str,
    allowed_classes: List[str],
    top_n: int,
    model_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    ent = pack["entity"]
    retrieved_block = _format_retrieved_block(pack.get("retrieved_docs", []), top_n)
    neighbor_summary = {
        "neighbors": [
            {"class": (n.get("class") if isinstance(n, dict) else None),
             "rel": (n.get("rel") if isinstance(n, dict) else None)}
            for n in (pack.get("neighbors") or [])
        ]
    }

    # -------- MOCK path (no LLM needed) --------
    if _norm(model_cfg.get("model")) == "mock":
        class_maps = _load_class_maps()
        canonical = _mock_map_to_tier1(ent, class_maps)
        conf = 0.9 if canonical else 0.5
        return {
            "canonical_class": canonical,
            "confidence": conf,
            "class_codes": {"IFC": ent.get("ifc_class"), "Uniclass": None},
        }

    # -------- Real-LLM path --------
    mapping = {
        "ifc_class": str(ent.get("ifc_class")),
        "name": str(ent.get("name")),
        "attributes": json.dumps(ent.get("attributes", {}), ensure_ascii=False),
        "properties": json.dumps(ent.get("properties", {}), ensure_ascii=False),
        "spatial_path": json.dumps(ent.get("spatial_path", []), ensure_ascii=False),
        "neighbor_summary": json.dumps(neighbor_summary, ensure_ascii=False),
        "top_n": str(top_n),
        "retrieved_block": retrieved_block,
        "allowed_classes": ", ".join(allowed_classes) if allowed_classes else "<no-constraint>",
    }

    prompt = _render_template_safe_or_none(tmpl, mapping)
    if prompt is None:
        # brace-safe fallback prompt
        prompt = (
            "System: You are a BIM classification assistant.\n"
            "Input JSON:\n" +
            json.dumps({
                "ifc_class": ent.get("ifc_class"),
                "name": ent.get("name"),
                "attributes": ent.get("attributes", {}),
                "properties": ent.get("properties", {}),
                "spatial_path": ent.get("spatial_path", []),
                "neighbors": neighbor_summary["neighbors"],
                "retrieved_topN": retrieved_block
            }, ensure_ascii=False, indent=2) +
            "\nTask:\n"
            f"1) Map to one canonical_class from this closed list: {mapping['allowed_classes']}.\n"
            "2) Provide confidence in [0,1].\n"
            '3) Provide optional class_codes with keys "IFC" and "Uniclass" if confidently known.\n'
            'Output JSON: {"canonical_class":"...", "confidence":0.0, "class_codes":{"IFC":"...","Uniclass":"..."}}\n'
        )

    try:
        raw = run_llm(prompt, **model_cfg)
        data = json.loads(raw)
        return {
            "canonical_class": data.get("canonical_class"),
            "confidence": float(data.get("confidence", 0.0)),
            "class_codes": data.get("class_codes", {}) or {},
        }
    except Exception as e:
        logger.debug("class_mapping LLM failed; fallback to None (%s)", e)
        return {"canonical_class": None, "confidence": 0.0, "class_codes": {}}


# ---------------------------------------------------------------------
# property_extraction: mock returns empty; real LLM path uses prompt
# ---------------------------------------------------------------------
def property_extraction(
    pack: Dict[str, Any],
    tmpl: str,
    canonical_class: str,
    known_props_flat: Dict[str, Any],
    top_n: int,
    model_cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    # Mock: no extra properties
    if _norm(model_cfg.get("model")) == "mock":
        return []

    ent = pack["entity"]
    retrieved_block = _format_retrieved_block(pack.get("retrieved_docs", []), top_n)
    mapping = {
        "canonical_class": str(canonical_class),
        "known_props": json.dumps(known_props_flat, ensure_ascii=False),
        "attributes": json.dumps(ent.get("attributes", {}), ensure_ascii=False),
        "top_n": str(top_n),
        "retrieved_block": retrieved_block,
    }

    prompt = _render_template_safe_or_none(tmpl, mapping)
    if prompt is None:
        prompt = (
            "System: You extract missing engineering properties.\n"
            "Input JSON:\n" +
            json.dumps({
                "canonical_class": canonical_class,
                "known_props": known_props_flat,
                "attributes": ent.get("attributes", {}),
                "retrieved_topN": retrieved_block
            }, ensure_ascii=False, indent=2) +
            "\nTask:\n"
            'Return JSON array: [{"k":"<name>","v":<value or string>,"u":"<unit or null>","confidence":0.0}, ...]\n'
            "Prefer SI units: kW, L/s, m, m², °C.\n"
        )

    try:
        raw = run_llm(prompt, **model_cfg)
        arr = json.loads(raw)
        if isinstance(arr, list):
            return arr
    except Exception as e:
        logger.debug("property_extraction LLM failed; fallback to empty (%s)", e)
    return []
