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
    24: {"forecast": 30.0, "recent": 30.0},
}

VALID_STATUSES = [
    "NO_RAINFALL_SIGNAL",
    "LOW_RAINFALL_SIGNAL",
    "RAINFALL_WATCH",
    "DATA_CHECK_REQUIRED",
]

def overall_status(warnings: List[str]) -> str:
    """
    Computes overall screening status across multiple horizons (1h, 3h, 6h).
    Strictly follows warning_engine.py priority:
    DATA_CHECK_REQUIRED > RAINFALL_WATCH > LOW_RAINFALL_SIGNAL > NO_RAINFALL_SIGNAL
    """
    if "DATA_CHECK_REQUIRED" in warnings:
        return "DATA_CHECK_REQUIRED"
    if "RAINFALL_WATCH" in warnings:
        return "RAINFALL_WATCH"
    if "LOW_RAINFALL_SIGNAL" in warnings:
        return "LOW_RAINFALL_SIGNAL"
    return "NO_RAINFALL_SIGNAL"

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


