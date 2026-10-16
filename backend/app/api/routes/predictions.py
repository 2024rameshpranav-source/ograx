from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
    ForecastTimelineResponse,
)
from app.services.city_prediction_router import city_prediction_router
from app.services.prediction_service import prediction_service

router = APIRouter(prefix="/predictions", tags=["Predictions & Forecasting"])

@router.post("", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
def create_prediction(
    request: PredictionRequest,
    db: Session = Depends(get_db)
) -> PredictionResponse:
    """
    Generate an early-warning waterlogging risk prediction for Mumbai or Pune.
    - Routes Pune to its independent machine learning model.
    - Routes Mumbai to its rule-based screening engine with transparency disclosures.
    - Validates request schema and numerical feature ranges.
    - Persists the prediction audit record.
    """
    return city_prediction_router.run_prediction(request, db)

@router.get("/{city}/latest", response_model=PredictionResponse)
def get_latest_prediction(
    city: str,
    db: Session = Depends(get_db)
) -> PredictionResponse:
    """
    Retrieves the most recent prediction or screening snapshot for the specified city.
    """
    latest = city_prediction_router.get_latest_prediction(city, db)
    if not latest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No previous prediction records found for city '{city}'."
        )
    return latest

@router.get("/{city}", response_model=List[PredictionResponse])
def list_city_predictions(
    city: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
) -> List[PredictionResponse]:
    """Retrieves historical stored predictions for a given city."""
    clean_city = city_prediction_router.normalize_city(city)
    return prediction_service.list_predictions(clean_city, db, limit=limit)

@router.get("/{city}/forecast", response_model=ForecastTimelineResponse)
def get_forecast_timeline(
    city: str,
    location_name: str = Query("Primary Arterial Corridor", description="Target road or area"),
    location_id: Optional[str] = Query(None, description="Unique segment or location ID"),
    latitude: Optional[float] = Query(None, description="Location latitude"),
    longitude: Optional[float] = Query(None, description="Location longitude"),
    base_rainfall_mm: float = Query(35.0, ge=0.0, description="Observed rainfall rate"),
    db: Session = Depends(get_db)
) -> ForecastTimelineResponse:
    """
    Generates a forecast timeline for the specified city and location.
    - Pune uses trained ML model per horizon.
    - Mumbai uses rule-based screening engine (+1h, +3h, +6h).
    """
    return city_prediction_router.get_forecast_timeline(
        city=city,
        location_name=location_name,
        base_rainfall_mm=base_rainfall_mm,
        db=db,
        location_id=location_id,
        latitude=latitude,
        longitude=longitude,
    )

