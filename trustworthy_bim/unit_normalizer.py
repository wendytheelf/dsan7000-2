def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def normalize(name: str, value, unit: str | None):
    """
    回傳: (value_norm, unit_norm, notes)
    """
    if value is None:
        return None, unit, "no_value"
    v = _to_float(value)

    n = (name or "").lower()

    # Power → kW
    if n in ["power", "rated_power", "kw", "power_kw"]:
        if unit is None:
            return v, "kW", "assume_kw" if v is not None else "no_value"
        u = unit.lower()
        if u in ["kw"]:
            return v, "kW", "ok"
        if u in ["w"]:
            return (v / 1000.0 if v is not None else None), "kW", "w_to_kw"
        if u in ["hp"]:
            return (v * 0.7457 if v is not None else None), "kW", "hp_to_kw"

    # Flow → L/s
    if n in ["flow", "flow_rate", "q"]:
        if unit is None:
            return v, "L/s", "assume_Lps" if v is not None else "no_value"
        u = unit.lower()
        if u in ["l/s", "lps", "l/sec"]:
            return v, "L/s", "ok"
        if u in ["m3/h", "m³/h", "m^3/h"]:
            return (v * 1000 / 3600 if v is not None else None), "L/s", "m3h_to_Lps"

    # Length → m
    if n in ["length", "diameter", "width", "height", "depth", "thickness"]:
        if unit is None or (unit and unit.lower() in ["m", "meter", "metre"]):
            return v, "m", "ok" if unit else "assume_m"
        if unit and unit.lower() == "mm":
            return (v / 1000.0 if v is not None else None), "m", "mm_to_m"

    # Area → m²
    if n in ["area", "netarea", "grossarea"]:
        if unit is None or (unit and unit.lower() in ["m2", "m²"]):
            return v, "m²", "ok" if unit else "assume_m2"

    # Volume → m³
    if n in ["volume", "netvolume", "grossvolume"]:
        if unit is None or (unit and unit.lower() in ["m3", "m³"]):
            return v, "m³", "ok" if unit else "assume_m3"

    # Temperature → °C
    if n in ["temperature", "temp", "setpoint"]:
        if unit is None or unit in ["°C", "C", "c"]:
            return v, "°C", "ok" if unit else "assume_C"
        if unit in ["°F", "F", "f"]:
            return ((v - 32) * 5 / 9 if v is not None else None), "°C", "F_to_C"

    # Default
    return v, unit, "noop"
