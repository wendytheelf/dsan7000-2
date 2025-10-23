from typing import Dict, Any, List, Tuple


def required_props_for_class(cls: str, rp_table: Dict[str, List[str]]) -> List[str]:
    return rp_table.get(cls, [])


def check_required_props(canonical_class: str, props_flat: Dict[str, Any], rp_table: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    flags = []
    must = required_props_for_class(canonical_class, rp_table)
    for k in must:
        if k not in props_flat or props_flat.get(k) in [None, "", []]:
            flags.append(("MISSING_REQUIRED_PROPERTY", f"{k}"))
    return flags


def check_ranges(props_rows: List[Dict[str, Any]], range_table: Dict[str, Dict[str, float]]) -> List[Tuple[str, str]]:
    flags = []
    for p in props_rows:
        name = p["name"]
        if name in range_table:
            lo = range_table[name].get("min")
            hi = range_table[name].get("max")
            v = p.get("value_norm")
            if isinstance(v, (int, float)):
                if (lo is not None and v < lo) or (hi is not None and v > hi):
                    flags.append(("OUT_OF_RANGE", f"{name}={v} not in [{lo},{hi}]"))
    return flags


def check_confidence(props_rows: List[Dict[str, Any]], cls_conf: float, thr_low: float) -> List[Tuple[str, str]]:
    flags = []
    if cls_conf < thr_low:
        flags.append(("LOW_AI_CONF", f"class_conf={cls_conf}"))
    for p in props_rows:
        c = p.get("confidence")
        if c is not None and c < thr_low:
            flags.append(("LOW_AI_CONF", f"prop:{p['name']} conf={c}"))
    return flags


def check_inconsistent_neighbors(canonical_class: str, neighbors: List[Dict[str, Any]], simple_rules: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    """
    simple_rules: { "Pump": ["Pipe","Valve","Motor"], ... }
    若觀察到的鄰居類別集合與期望集合幾乎無交集 → 觸發
    """
    flags = []
    try:
        expected = set(simple_rules.get(canonical_class, []))
        observed = set([n.get("class") for n in (neighbors or []) if isinstance(n, dict) and n.get("class")])
        if expected and observed and expected.isdisjoint(observed):
            flags.append(("INCONSISTENT_NEIGHBOR", f"expected~{list(expected)} vs observed~{list(observed)}"))
    except Exception:
        pass
    return flags
