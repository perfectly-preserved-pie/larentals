from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import requests

def query_cpuc(
    *,
    x: float,
    y: float,
    consumer: bool = True,
    timeout_s: float = 15.0,
) -> Dict[str, Any]:
    """
    Query the CPUC Provider Identify ArcGIS layer for ISP options at a point.

    This performs a point-in-polygon lookup against provider coverage areas.

    Args:
        x: Longitude (WGS84).
        y: Latitude (WGS84).
        consumer: If True, filter for Consumer services; if False, Business. Default is True.
        timeout_s: HTTP timeout in seconds.

    Returns:
        Raw JSON response from the ArcGIS REST endpoint.

    Raises:
        requests.HTTPError: If the request fails.
    """
    base_url = (
        "https://cpuc2016.westus.cloudapp.azure.com/arcgis/rest/services/"
        "CPUC/CPUC_EOY_2023_Provider_Identify/MapServer/0/query"
    )

    where_clause = "Busconsm = 'Consumer'" if consumer else "Busconsm = 'Business'"

    geometry = {
        "x": x,
        "y": y,
        "spatialReference": {"wkid": 4326},
    }

    params = {
        "returnGeometry": "false",
        "where": where_clause,
        "outSR": 4326,
        "outFields": "*",
        "inSR": 4326,
        "geometry": json.dumps(geometry),
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "f": "json",
    }

    headers = {
        "Accept": "*/*",
        "User-Agent": "cpuc-broadband-lookup/1.0",
        "Referer": "https://www.broadbandmap.ca.gov/",
        "Origin": "https://www.broadbandmap.ca.gov",
    }

    response = requests.get(
        base_url,
        params=params,
        headers=headers,
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()

# Now we parse the JSON response
@dataclass(frozen=True)
class ISPOption:
    """A normalized ISP option from the CPUC Provider Identify ArcGIS layer."""
    dba: str
    tech_code: int
    tech_label: str
    service_type: Optional[str]
    busconsm: Optional[str]
    max_down_mbps: Optional[float]
    max_up_mbps: Optional[float]
    min_down_mbps: Optional[float]
    min_up_mbps: Optional[float]
    contact_url: Optional[str]


def tech_code_to_label(tech_code: int) -> str:
    """
    Convert FCC/BDC technology codes (as used by CPUC) to readable labels.

    Notes:
        CPUC's layer uses the same TechCode scheme commonly used in FCC BDC reporting.
        Not all codes may appear; unknowns are returned as "Unknown (<code>)".
    """
    mapping: Dict[int, str] = {
        10: "Copper wire (xDSL/ethernet over copper/T1, etc.)",
        20: "Cable modem / other copper coax",
        30: "Other copper wireline",
        40: "Cable / HFC",
        50: "Fiber to the Premises (FTTP)",
        60: "Geostationary satellite (GSO)",
        61: "Non-geostationary satellite (NGSO)",
        70: "Unlicensed fixed wireless",
        71: "Licensed fixed wireless",
        72: "Licensed-by-rule fixed wireless",
    }
    return mapping.get(int(tech_code), f"Unknown ({tech_code})")


def _to_float_or_none(value: Any) -> Optional[float]:
    """Convert a JSON value to float, returning None if missing/unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
    
def dedupe_best_options(options: Iterable[ISPOption]) -> List[ISPOption]:
    """
    Dedupe options by (DBA, TechCode, Busconsm), keeping the best speeds.

    "Best" is defined as:
        higher max_down_mbps, then higher max_up_mbps.

    Args:
        options: Iterable of ISPOption.

    Returns:
        Deduped and sorted list of ISPOption.
    """
    best: Dict[Tuple[str, int, str], ISPOption] = {}

    def norm_busconsm(v: Optional[str]) -> str:
        return (v or "X").strip().upper()

    for opt in options:
        key = (opt.dba.lower(), opt.tech_code, norm_busconsm(opt.busconsm))
        current = best.get(key)
        if current is None:
            best[key] = opt
            continue

        cand_down = opt.max_down_mbps or 0.0
        cand_up = opt.max_up_mbps or 0.0
        curr_down = current.max_down_mbps or 0.0
        curr_up = current.max_up_mbps or 0.0

        if (cand_down, cand_up) > (curr_down, curr_up):
            best[key] = opt

    def tech_priority(label: str) -> int:
        t = label.lower()
        if "fiber" in t:
            return 1
        if "cable" in t or "hfc" in t:
            return 2
        if "fixed wireless" in t:
            return 3
        if "copper" in t or "dsl" in t:
            return 4
        if "satellite" in t:
            return 5
        return 9

    return sorted(
        best.values(),
        key=lambda o: (tech_priority(o.tech_label), -(o.max_down_mbps or 0.0), -(o.max_up_mbps or 0.0), o.dba.lower()),
    )

def parse_cpuc_response(payload: Dict[str, Any]) -> List[ISPOption]:
    """
    Parse the CPUC ArcGIS response JSON into a normalized list of ISPOption.

    Args:
        payload: The JSON response from the ArcGIS endpoint.

    Returns:
        A list of ISPOption records (may be empty).
    """
    features = payload.get("features", [])
    if not isinstance(features, list):
        return []

    options: List[ISPOption] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        attrs = feat.get("attributes", {})
        if not isinstance(attrs, dict):
            continue

        dba = str(attrs.get("DBA", "Unknown")).strip() or "Unknown"
        tech_code = int(attrs.get("TechCode", -1))

        options.append(
            ISPOption(
                dba=dba,
                tech_code=tech_code,
                tech_label=tech_code_to_label(tech_code),
                service_type=(str(attrs["Service_Type"]).strip() if attrs.get("Service_Type") is not None else None),
                busconsm=(str(attrs["Busconsm"]).strip() if attrs.get("Busconsm") is not None else None),
                max_down_mbps=_to_float_or_none(attrs.get("MaxAdDn")),
                max_up_mbps=_to_float_or_none(attrs.get("MaxAdUp")),
                min_down_mbps=_to_float_or_none(attrs.get("MINDOWN")),
                min_up_mbps=_to_float_or_none(attrs.get("MINUP")),
                contact_url=(str(attrs["Contact"]).strip() if attrs.get("Contact") is not None else None),
            )
        )

    options = dedupe_best_options(options)
    return options

# Example usage:
# response_json = ...  # JSON response from CPUC ArcGIS endpoint
# options = parse_cpuc_response(response_json)
# deduped_options = dedupe_best_options(options)