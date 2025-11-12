from typing import Dict, Any, List, Tuple, Optional
import math

def _is_number(x: Any) -> bool:
    """Return True if x is an int/float and not NaN."""
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))

def required_props_for_class(cls: str, rp_table: Dict[str, List[str]]) -> List[str]:
    """Get the list of required property names for a given canonical class."""
    return rp_table.get(cls, []) or []

def check_required_props(
    canonical_class: str,
    props_flat: Dict[str, Any],
    rp_table: Dict[str, List[str]]
) -> List[Tuple[str, str]]:
    """
    Flag missing required properties.

    Returns a list of (flag, reason) tuples, where flag is "MISSING_REQUIRED_PROPERTY"
    and reason is the missing key name.
    """
    flags: List[Tuple[str, str]] = []
    must = required_props_for_class(canonical_class, rp_table)
    for k in must:
        if k not in props_flat or props_flat.get(k) in (None, "", []):
            flags.append(("MISSING_REQUIRED_PROPERTY", f"{k}"))
    return flags

def check_ranges(
    props_rows: List[Dict[str, Any]],
    range_table: Dict[str, Dict[str, float]]
) -> List[Tuple[str, str]]:
    """
    Flag normalized property values that fall outside configured ranges.

    range_table example: {"height": {"min": 0.0, "max": 100.0}}
    """
    flags: List[Tuple[str, str]] = []
    for p in props_rows:
        name = p.get("name")
        if not name or name not in range_table:
            continue
        lo: Optional[float] = range_table[name].get("min")
        hi: Optional[float] = range_table[name].get("max")
        v = p.get("value_norm")
        if _is_number(v):
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                flags.append(("OUT_OF_RANGE", f"{name}={v} not in [{lo},{hi}]"))
    return flags

def check_confidence(
    props_rows: List[Dict[str, Any]],
    cls_conf: float,
    thr_low: float
) -> List[Tuple[str, str]]:
    """
    Flag low-confidence class prediction and low-confidence properties.

    - If class confidence < thr_low → "LOW_AI_CONF"
    - For each property with confidence < thr_low → "LOW_AI_CONF"
    """
    flags: List[Tuple[str, str]] = []
    if _is_number(cls_conf) and cls_conf < thr_low:
        flags.append(("LOW_AI_CONF", f"class_conf={cls_conf}"))
    for p in props_rows:
        c = p.get("confidence")
        name = p.get("name", "<unknown>")
        if _is_number(c) and c < thr_low:
            flags.append(("LOW_AI_CONF", f"prop:{name} conf={c}"))
    return flags

def check_inconsistent_neighbors(
    canonical_class: str,
    neighbors: List[Dict[str, Any]],
    simple_rules: Dict[str, List[str]]
) -> List[Tuple[str, str]]:
    """
    Flag inconsistent neighbor classes based on simple expected-class rules.

    simple_rules example:
        { "Pump": ["Pipe", "Valve", "Motor"], ... }

    If the observed neighbor class set is disjoint from the expected set,
    an "INCONSISTENT_NEIGHBOR" flag is emitted.
    """
    flags: List[Tuple[str, str]] = []
    try:
        expected = set(simple_rules.get(canonical_class, []) or [])
        observed = {
            n.get("class")
            for n in (neighbors or [])
            if isinstance(n, dict) and n.get("class")
        }
        if expected and observed and expected.isdisjoint(observed):
            flags.append((
                "INCONSISTENT_NEIGHBOR",
                f"expected~{sorted(expected)} vs observed~{sorted(observed)}"
            ))
    except Exception:
        # Be conservative: swallow errors and return no flags from this check
        pass
    return flags
