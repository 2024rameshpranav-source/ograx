"""
Rule-Based Rainfall Screening Logic for Mumbai Prototype.
Implements the calibrated thresholds from warning_engine.py.
Note: This is an experimental screening mechanism, NOT a validated machine learning model.
It does not compute a waterlogging probability.
"""
from typing import Dict, Any, Optional, Tuple, List

DEFAULT_THRESHOLDS: Dict[int, Dict[str, float]] = {
    1: {"forecast": 5.0, "recent": 5.0},
    3: {"forecast": 10.0, "recent": 10.0},
    6: {"forecast": 20.0, "recent": 20.0},
}

VALID_STATUSES = [
    "NO_RAINFALL_SIGNAL",
    "LOW_RAINFALL_SIGNAL",
    "RAINFALL_WATCH",
    "DATA_CHECK_REQUIRED",
]

import math

def classify_warning(
    data_status: str,
    recent_mm: Optional[float],
    forecast_mm: Optional[float],
    horizon: int,
    thresholds: Optional[Dict[int, Dict[str, float]]] = None
) -> str:
    """
    Classifies waterlogging rainfall screening status for a given horizon.
    Returns DATA_CHECK_REQUIRED if data is unavailable, missing, NaN, negative, or malformed.
    """
    if data_status != "AVAILABLE":
        return "DATA_CHECK_REQUIRED"

    if recent_mm is None or forecast_mm is None:
        return "DATA_CHECK_REQUIRED"

    try:
        r = float(recent_mm)
        f = float(forecast_mm)
        if math.isnan(r) or math.isnan(f):
            return "DATA_CHECK_REQUIRED"
        if r < 0.0 or f < 0.0:
            return "DATA_CHECK_REQUIRED"
    except (TypeError, ValueError):
        return "DATA_CHECK_REQUIRED"

    t = (thresholds or DEFAULT_THRESHOLDS).get(horizon, {"forecast": 10.0, "recent": 10.0})

    if f >= t["forecast"] or r >= t["recent"]:
        return "RAINFALL_WATCH"
    elif f > 0.0 or r > 0.0:
        return "LOW_RAINFALL_SIGNAL"
    else:
        return "NO_RAINFALL_SIGNAL"

def generate_explanation(
    status: str,
    horizon: int,
    recent_mm: Optional[float],
    forecast_mm: Optional[float],
    location_name: str,
    thresholds: Optional[Dict[int, Dict[str, float]]] = None
) -> str:
    """
    Generates a clear, transparent human-readable explanation of why a status was assigned.
    Clearly avoids claiming flood certainty.
    """
    t = (thresholds or DEFAULT_THRESHOLDS).get(horizon, {"forecast": 10.0, "recent": 10.0})
    try:
        rec_val = round(float(recent_mm), 1) if (recent_mm is not None and not math.isnan(float(recent_mm))) else 0.0
    except (TypeError, ValueError):
        rec_val = 0.0

    try:
        fc_val = round(float(forecast_mm), 1) if (forecast_mm is not None and not math.isnan(float(forecast_mm))) else 0.0
    except (TypeError, ValueError):
        fc_val = 0.0

    if status == "DATA_CHECK_REQUIRED":
        return (
            f"Screening data is unavailable, incomplete, or requires verification for {location_name} "
            f"at the +{horizon}h horizon. Rainfall totals could not be confirmed."
        )
    elif status == "RAINFALL_WATCH":
        reason = []
        if fc_val >= t["forecast"]:
            reason.append(f"forecast rainfall ({fc_val} mm) exceeds the {t['forecast']} mm threshold")
        if rec_val >= t["recent"]:
            reason.append(f"recent rainfall ({rec_val} mm) exceeds the {t['recent']} mm threshold")
        return (
            f"Rainfall Watch triggered for {location_name} (+{horizon}h): {' and '.join(reason)}. "
            f"Potential surface accumulation watch; field drainage capacity may be tested."
        )
    elif status == "LOW_RAINFALL_SIGNAL":
        return (
            f"Low rainfall signal detected for {location_name} (+{horizon}h): {rec_val} mm recent, "
            f"{fc_val} mm forecast, below the {t['forecast']} mm watch threshold."
        )
    else:  # NO_RAINFALL_SIGNAL
        return (
            f"No recent ({rec_val} mm) or forecast ({fc_val} mm) rainfall signal detected "
            f"in available weather data for {location_name} across the +{horizon}h horizon."
        )

def compute_location_heuristic_risk(
    elevation_m: float,
    rainfall_mm: float,
    drainage_capacity_ratio: float = 0.5,
    historical_incident_count: int = 0,
    horizon_hours: int = 3,
) -> Tuple[float, str, List[Dict[str, Any]]]:
    """
    Computes a deterministic physical heuristic risk score (0.0 - 100.0%) and factor breakdown
    based on location terrain elevation, rainfall accumulation, drainage capacity, and historical incidents.
    Explicitly transparent and labeled as an unvalidated heuristic demonstration.
    """
    # 1. Elevation vulnerability: Sea-level Mumbai baseline is 5m to 20m AMSL
    # Below 10m (e.g. Kurla 7m, Dadar 10m) represents low-lying natural collection basins
    if elevation_m <= 7.0:
        elev_risk = 35.0  # High natural pooling risk
        elev_factor = f"Low elevation basin ({elevation_m:.1f}m AMSL) strongly impedes natural runoff"
    elif elevation_m <= 10.0:
        elev_risk = 28.0  # Significant depression risk (e.g. Dadar Hindmata bowl)
        elev_factor = f"Depressed bowl terrain ({elevation_m:.1f}m AMSL) prone to accumulation"
    elif elevation_m <= 15.0:
        elev_risk = 18.0  # Moderate coastal elevation (e.g. Bandra junctions)
        elev_factor = f"Moderate elevation ({elevation_m:.1f}m AMSL) with localized junction dips"
    else:
        elev_risk = 8.0   # Elevated ground (e.g. Powai 43m)
        elev_factor = f"Elevated terrain ({elevation_m:.1f}m AMSL) facilitates surface runoff"

    # 2. Rainfall accumulation factor
    thresh = 5.0 if horizon_hours <= 1 else (10.0 if horizon_hours <= 3 else 20.0)
    rain_ratio = min(3.0, max(0.0, rainfall_mm) / max(1.0, thresh))
    rain_risk = min(45.0, rain_ratio * 25.0)
    rain_factor = f"Forecast/recent rainfall {rainfall_mm:.1f}mm relative to {thresh}mm watch threshold"

    # 3. Drainage capacity deficit
    clean_drain = max(0.0, min(1.0, drainage_capacity_ratio))
    drainage_deficit = max(0.0, 1.0 - clean_drain)
    drain_risk = drainage_deficit * 20.0
    drain_factor = f"Drainage capacity ratio {int(clean_drain * 100)}% ({'bottlenecked discharge' if clean_drain < 0.5 else 'adequate capacity'})"

    # 4. Historical incident recurrence
    hist_risk = min(15.0, max(0, historical_incident_count) * 2.0)
    hist_factor = f"Historical incident frequency ({historical_incident_count} recorded waterlogging events)"

    # Total score bounded to 5.0 - 95.0%
    raw_total = elev_risk + rain_risk + drain_risk + hist_risk
    # Scale slightly with horizon as uncertainty and cumulative accumulation increase
    horizon_multiplier = 1.0 + (horizon_hours - 1) * 0.05
    score = max(5.0, min(95.0, round(raw_total * horizon_multiplier, 1)))

    if score >= 80.0:
        category = "Severe"
    elif score >= 60.0:
        category = "High"
    elif score >= 35.0:
        category = "Moderate"
    else:
        category = "Low"

    safe_raw = max(1.0, raw_total)
    factors = [
        {"name": "Terrain Elevation", "impact": elev_factor, "weight": f"{int(elev_risk / safe_raw * 100)}%"},
        {"name": "Rainfall Accumulation", "impact": rain_factor, "weight": f"{int(rain_risk / safe_raw * 100)}%"},
        {"name": "Drainage Infrastructure", "impact": drain_factor, "weight": f"{int(drain_risk / safe_raw * 100)}%"},
        {"name": "Historical Incidents", "impact": hist_factor, "weight": f"{int(hist_risk / safe_raw * 100)}%"},
    ]

    return score, category, factors
