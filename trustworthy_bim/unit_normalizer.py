def _to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def normalize(name: str, value, unit: str | None):
    """
    Return: (value_norm, unit_norm, notes)
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

    # --- Length → m (height included)
    if n in ["length", "diameter", "width", "height", "depth", "thickness"]:
        if unit is None:
            return v, "m", "assume_m"
        
        u = unit.lower()
        if u in ["m", "meter", "metre"]:
            return v, "m", "ok"
        if u == "mm":
            return (v / 1000.0 if v is not None else None), "m", "mm_to_m"
        if u in ["cm"]:
            return (v / 100.0 if v is not None else None), "m", "cm_to_m"
        if u in ["ft", "feet"]:
            return (v * 0.3048 if v is not None else None), "m", "ft_to_m"
        if u in ["inch", "in"]:
            return (v * 0.0254 if v is not None else None), "m", "in_to_m"

    # --- NEW: Weight → kg ---------------------------------------------
    if n in ["weight", "mass", "total_weight"]:
        if unit is None:
            return v, "kg", "assume_kg"
        
        u = unit.lower()
        if u in ["kg", "kilogram"]:
            return v, "kg", "ok"
        if u in ["g", "gram"]:
            return (v / 1000.0 if v is not None else None), "kg", "g_to_kg"
        if u in ["ton", "t"]:
            return (v * 1000.0 if v is not None else None), "kg", "ton_to_kg"
        if u in ["lb", "lbs", "pound"]:
            return (v * 0.453592 if v is not None else None), "kg", "lb_to_kg"

    # Area → m²
    if n in ["area", "netarea", "grossarea", "netarea", "grossarea", "grosssidearea", "netsidearea", "grosssurfacearea", "netsurfacearea", "grossceilingarea", "grossfootprintarea", "grosssurfacearea", "outersurfacearea", "totalarea", "projectedarea", "crosssectionarea"]:
        if unit is None or (unit and unit.lower() in ["m2", "m²"]):
            return v, "m²", "ok" if unit else "assume_m2"

    # Volume → m³
    if n in ["volume", "netvolume", "grossvolume"]:
        if unit is None or (unit and unit.lower() in ["m3", "m³"]):
            return v, "m³", "ok" if unit else "assume_m3"
    
    # Additional length/distance properties → m
    if n in ["perimeter", "invertelevation", "span", "offset", "baseoffset", "topoffset", "heightoffsetfromlevel", "levelopset", "sillheight", "headheight", "defaultheadheight", "roughheight", "roughwidth", "unconnectedheight", "heighttotoplastrail", "nosinglength", "riserheight", "treadlength", "treadlengthatinnerside", "treadlengthatoffset", "walkinglineoffset", "doorpanelheight", "doorpanelwidth", "doorpaneloffset", "windowboardextension", "windowboardprojection", "cilldepth", "cillextension", "cillprojection", "cavitycloserdepth", "cavitycloseroffsetfromext", "cavitycloserwidth", "framedepth", "framethickness", "stopthickness", "stopdepth", "fascia depth", "bas extension distance", "top extension distance", "extrusionstart", "extrusionend", "undercut", "undercut"]:
        if unit is None:
            return v, "m", "assume_m"
        
        u = unit.lower()
        if u in ["m", "meter", "metre"]:
            return v, "m", "ok"
        if u == "mm":
            return (v / 1000.0 if v is not None else None), "m", "mm_to_m"
        if u in ["cm"]:
            return (v / 100.0 if v is not None else None), "m", "cm_to_m"
        if u in ["ft", "feet"]:
            return (v * 0.3048 if v is not None else None), "m", "ft_to_m"
        if u in ["inch", "in"]:
            return (v * 0.0254 if v is not None else None), "m", "in_to_m"
    
    # Angle properties → degrees
    if n in ["pitchangle", "slope", "roll", "angle"]:
        if unit is None:
            return v, "deg", "assume_deg"
        
        u = unit.lower()
        if u in ["deg", "degree", "degrees", "°"]:
            return v, "deg", "ok"
        if u in ["rad", "radian", "radians"]:
            return (v * 57.295779513 if v is not None else None), "deg", "rad_to_deg"
    
    # Thermal properties → standardized units
    # ThermalTransmittance (U-value) → W/(m²·K)
    if n in ["thermaltransmittance", "heat transfer coefficient (u)", "u-value", "u_value"]:
        if unit is None:
            return v, "W/(m²·K)", "assume_W_per_m2K"
        
        u = unit.lower()
        if u in ["w/(m²·k)", "w/(m2·k)", "w/(m²k)", "w/(m2k)", "w/m²k", "w/m2k"]:
            return v, "W/(m²·K)", "ok"
        if u in ["btu/(h·ft²·°f)", "btu/(h·ft2·°f)"]:
            return (v * 5.678263337 if v is not None else None), "W/(m²·K)", "btu_to_W_per_m2K"
    
    # Thermal Resistance (R-value) → m²·K/W
    if n in ["thermal resistance (r)", "thermal resistance", "r-value", "r_value"]:
        if unit is None:
            return v, "m²·K/W", "assume_m2K_per_W"
        
        u = unit.lower()
        if u in ["m²·k/w", "m2·k/w", "m²k/w", "m2k/w", "m²·k/w"]:
            return v, "m²·K/W", "ok"
        if u in ["ft²·h·°f/btu", "ft2·h·°f/btu", "ft²·°f·h/btu"]:
            return (v * 0.1761101838 if v is not None else None), "m²·K/W", "ft2Fh_to_m2K_per_W"

    # Temperature → °C
    if n in ["temperature", "temp", "setpoint"]:
        if unit is None or unit in ["°C", "C", "c"]:
            return v, "°C", "ok" if unit else "assume_C"
        if unit in ["°F", "F", "f"]:
            return ((v - 32) * 5 / 9 if v is not None else None), "°C", "F_to_C"

    # Default
    return v, unit, "noop"
