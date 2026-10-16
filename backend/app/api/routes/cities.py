"""
City-Specific API Routes for AquaSignal AI.
Provides dedicated endpoints for Mumbai rule-based screening and city capabilities.
"""
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException, status

from app.services.city_prediction_router import city_prediction_router
from app.services.mumbai_engine.service import mumbai_waterlogging_service

router = APIRouter(prefix="/cities", tags=["City Models & Screening"])

@router.get("/mumbai/locations", response_model=List[Dict[str, Any]])
def get_mumbai_locations() -> List[Dict[str, Any]]:
    """
    Returns the 8 supported Mumbai monitoring locations,
    their geographic coordinates, elevations, and hotspot evidence status.
    """
    return city_prediction_router.get_mumbai_locations()

@router.get("/mumbai/waterlogging", response_model=Dict[str, Any])
def get_mumbai_waterlogging_screening(
    hours: int = Query(3, description="Forecast horizon in hours (supported: 1, 3, or 6)"),
    refresh: bool = Query(False, description="Force refresh from Open-Meteo live API")
) -> Dict[str, Any]:
    """
    Returns rule-based rainfall screening results for all 8 Mumbai locations.
    Evaluates recent and forecast rainfall against experimental thresholds.
    Discloses that this is an unvalidated prototype, not a machine learning model.
    """
    if hours not in [1, 3, 6]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid horizon '{hours}'. Mumbai screening engine supports 1, 3, or 6 hours."
        )

    return city_prediction_router.get_mumbai_screening(horizon=hours, force_refresh=refresh)

@router.get("/{city}/waterlogging", response_model=Dict[str, Any])
def get_city_waterlogging(
    city: str,
    hours: int = Query(3, description="Forecast horizon in hours")
) -> Dict[str, Any]:
    """
    Routes city waterlogging requests:
    - Mumbai routes to rule-based screening engine.
    - Pune returns instructions to use ML prediction endpoints.
    """
    clean_city = city_prediction_router.normalize_city(city)
    if clean_city == "Mumbai":
        return city_prediction_router.get_mumbai_screening(horizon=hours)
    else:
        return {
            "success": True,
            "city": "pune",
            "prediction_type": "machine_learning_model",
            "notice": "Pune is powered by an independent machine learning model. Use POST /api/predictions for ML inference."
        }
