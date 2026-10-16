"""
Pune Waterlogging Prediction Service.
Encapsulates inference and forecast timelines for Pune's trained machine learning model.
Completely isolated from Mumbai's rule-based screening engine.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
    ForecastTimelineResponse,
)
from app.services.prediction_service import prediction_service
from app.utils.logging_config import logger

class PunePredictionService:
    def __init__(self):
        self.city_name = "Pune"

    def predict(self, req: PredictionRequest, db: Session) -> PredictionResponse:
        """Invokes Pune's machine learning model through prediction_service."""
        if req.city.strip().title() != "Pune":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PunePredictionService can only process requests for Pune, received '{req.city}'."
            )
        return prediction_service.run_prediction(req, db)

    def get_latest(self, db: Session) -> Optional[PredictionResponse]:
        """Retrieves latest stored ML prediction for Pune."""
        return prediction_service.get_latest_prediction("Pune", db)

    def get_forecast_timeline(
        self,
        location_name: str,
        base_rainfall_mm: float,
        db: Session
    ) -> ForecastTimelineResponse:
        """Generates timeline based on Pune ML model."""
        return prediction_service.generate_forecast_timeline("Pune", location_name, base_rainfall_mm, db)

    def list_predictions(self, db: Session, limit: int = 20) -> List[PredictionResponse]:
        """Lists historical predictions for Pune."""
        return prediction_service.list_predictions("Pune", db, limit=limit)

pune_prediction_service = PunePredictionService()
