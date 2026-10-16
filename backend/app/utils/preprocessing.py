import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from app.config import settings
from app.schemas.prediction import PredictionInputFeatures
from app.utils.logging_config import logger

# Canonical baseline features anticipated for waterlogging models
DEFAULT_FEATURE_ORDER = [
    "rainfall_mm",
    "rainfall_intensity",
    "drainage_capacity_ratio",
    "elevation_m",
    "tide_level_m",
    "soil_saturation_index",
    "road_gradient_pct",
    "historical_incident_count",
]

# Reasonable default values for optional features when missing from input
DEFAULT_IMPUTATION_VALUES = {
    "rainfall_mm": 0.0,
    "rainfall_intensity": 0.0,
    "drainage_capacity_ratio": 0.5,  # 50% average baseline capacity
    "elevation_m": 5.0,             # 5m AMSL typical urban baseline
    "tide_level_m": 2.0,            # 2.0m moderate high tide baseline
    "soil_saturation_index": 0.5,   # Moderate moisture saturation
    "road_gradient_pct": 1.0,       # 1% standard drainage slope
    "historical_incident_count": 0,
}

def prepare_feature_dict(features: PredictionInputFeatures) -> Dict[str, Any]:
    """Flattens PredictionInputFeatures and extra_features into a single clean dictionary."""
    data = features.model_dump()
    extra = data.pop("extra_features", {}) or {}
    data.update(extra)
    return data

def build_model_input_dataframe(
    feature_dict: Dict[str, Any],
    expected_features: Optional[List[str]] = None
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Transforms input dictionary into a pandas DataFrame aligned with the model's expected columns.
    If expected_features is provided by the loaded model (e.g. model.feature_names_in_),
    the DataFrame columns will strictly match that order, filling missing ones with default imputations.
    """
    columns = expected_features if expected_features else DEFAULT_FEATURE_ORDER

    row = {}
    missing_imputed = []

    for col in columns:
        if col in feature_dict and feature_dict[col] is not None:
            try:
                row[col] = float(feature_dict[col])
            except (ValueError, TypeError):
                row[col] = DEFAULT_IMPUTATION_VALUES.get(col, 0.0)
                missing_imputed.append(col)
        else:
            row[col] = DEFAULT_IMPUTATION_VALUES.get(col, 0.0)
            missing_imputed.append(col)

    if missing_imputed:
        logger.debug(f"Imputed default values for features: {missing_imputed}")

    df = pd.DataFrame([row], columns=columns)
    return df, missing_imputed

def categorize_risk_score(score: float) -> str:
    """
    Categorizes risk probability/score (0-100 or 0-1) into standardized categories:
    Low, Moderate, High, Critical
    """
    # Normalize to 0-100 range if given as 0-1
    pct = score * 100.0 if score <= 1.0 else score
    pct = max(0.0, min(100.0, pct))

    t = settings.RISK_THRESHOLDS
    if pct >= t["critical_lower"]:
        return "Critical"
    elif pct >= t["moderate_upper"]:
        return "High"
    elif pct >= t["low_upper"]:
        return "Moderate"
    else:
        return "Low"
