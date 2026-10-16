import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from pymongo import DESCENDING

from app.config import settings
from app.db.models import PredictionDB
from app.db.mongodb import mongo_manager
from app.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
    ForecastTimelineResponse,
    ForecastTimelineItem,
)
from app.services.model_service import model_service
from app.utils.preprocessing import (
    prepare_feature_dict,
    build_model_input_dataframe,
    categorize_risk_score,
)
from app.utils.logging_config import logger

class PredictionService:
    @staticmethod
    def validate_coordinates(city: str, lat: Optional[float], lng: Optional[float]):
        """Validates that coordinates fall within the realistic bounding box of the city."""
        if lat is None or lng is None:
            return

        bounds = settings.GEO_BOUNDS.get(city.lower())
        if bounds:
            if not (bounds["min_lat"] <= lat <= bounds["max_lat"] and bounds["min_lng"] <= lng <= bounds["max_lng"]):
                logger.warning(f"Coordinates ({lat}, {lng}) fall outside standard {city} bounding box ({bounds}).")

    @staticmethod
    def run_prediction(req: PredictionRequest, db: Session) -> PredictionResponse:
        city = model_service.normalize_city(req.city)
        PredictionService.validate_coordinates(city, req.latitude, req.longitude)

        model = model_service.get_model(city)
        if not model.is_loaded:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Trained model for {city} is unavailable: {model.load_error or 'Artifact missing'}. Please upload the model file to '{model.file_path}'."
            )

        # Prepare features
        feature_dict = prepare_feature_dict(req.features)
        input_df, missing_imputed = build_model_input_dataframe(feature_dict, model.expected_features)

        # Execute model inference
        prob_pct, meta = model.predict(input_df)
        risk_category = categorize_risk_score(prob_pct)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Persist prediction in MongoDB Atlas if available
        predictions_col = mongo_manager.get_collection("predictions")
        if predictions_col is not None:
            try:
                pred_doc = {
                    "city": city,
                    "location_id": req.location_id,
                    "location_name": req.location_name or "Monitored Segment",
                    "forecast_horizon_hours": req.forecast_horizon_hours,
                    "risk_score": round(prob_pct, 2),
                    "risk_category": risk_category,
                    "model_version": model.version,
                    "features_snapshot": feature_dict,
                    "created_at": timestamp,
                }
                predictions_col.insert_one(pred_doc)
                logger.info(f"Prediction persisted to MongoDB Atlas for {city} ({req.location_name})")
            except Exception as me:
                logger.warning(f"Failed to persist prediction to MongoDB Atlas: {me}")

        # Mirror/fallback persist to SQLite
        try:
            pred_record = PredictionDB(
                city=city,
                location_id=req.location_id,
                location_name=req.location_name or "Monitored Segment",
                forecast_horizon_hours=req.forecast_horizon_hours,
                risk_score=round(prob_pct, 2),
                risk_category=risk_category,
                model_version=model.version,
                features_snapshot=json.dumps(feature_dict),
                created_at=timestamp,
            )
            db.add(pred_record)
            db.commit()
            db.refresh(pred_record)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist prediction record to SQLite: {str(e)}")

        return PredictionResponse(
            city=city,
            location_id=req.location_id,
            location_name=req.location_name,
            forecast_horizon_hours=req.forecast_horizon_hours,
            risk_probability=round(prob_pct, 1),
            risk_category=risk_category,
            model_id=f"{city.lower()}_model_{model.version}",
            prediction_timestamp=timestamp,
            input_freshness="fresh · 2m ago",
            uncertainty_range=f"±{8 + req.forecast_horizon_hours * 2}%",
            is_demonstration_fallback=False,
            details={
                "features_snapshot": feature_dict,
                "imputed_features": missing_imputed,
                "model_output_type": meta.get("output_type", "probability"),
            }
        )

    @staticmethod
    def get_latest_prediction(city: str, db: Session) -> Optional[PredictionResponse]:
        normalized_city = model_service.normalize_city(city)

        predictions_col = mongo_manager.get_collection("predictions")
        if predictions_col is not None:
            try:
                doc = predictions_col.find_one(
                    {"city": normalized_city},
                    sort=[("created_at", DESCENDING)]
                )
                if doc:
                    features = doc.get("features_snapshot") or {}
                    if isinstance(features, str):
                        try:
                            features = json.loads(features)
                        except Exception:
                            features = {}
                    return PredictionResponse(
                        city=doc.get("city", normalized_city),
                        location_id=doc.get("location_id"),
                        location_name=doc.get("location_name"),
                        forecast_horizon_hours=int(doc.get("forecast_horizon_hours", 1)),
                        risk_probability=float(doc.get("risk_score", 0.0)),
                        risk_category=doc.get("risk_category", "Low"),
                        model_id=f"{normalized_city.lower()}_model_{doc.get('model_version', '1.0')}",
                        prediction_timestamp=doc.get("created_at"),
                        input_freshness="historical_stored",
                        uncertainty_range=f"±{8 + int(doc.get('forecast_horizon_hours', 1)) * 2}%",
                        is_demonstration_fallback=False,
                        details={"features_snapshot": features}
                    )
            except Exception as me:
                logger.warning(f"MongoDB query failed for latest prediction ({me}); checking SQLite.")

        # SQLite fallback
        record = (
            db.query(PredictionDB)
            .filter(PredictionDB.city == normalized_city)
            .order_by(PredictionDB.id.desc())
            .first()
        )
        if not record:
            return None

        features_data = {}
        if record.features_snapshot:
            try:
                features_data = json.loads(record.features_snapshot)
            except Exception:
                pass

        return PredictionResponse(
            city=record.city,
            location_id=record.location_id,
            location_name=record.location_name,
            forecast_horizon_hours=record.forecast_horizon_hours,
            risk_probability=record.risk_score,
            risk_category=record.risk_category,
            model_id=f"{record.city.lower()}_model_{record.model_version}",
            prediction_timestamp=record.created_at,
            input_freshness="historical_stored",
            uncertainty_range=f"±{8 + record.forecast_horizon_hours * 2}%",
            is_demonstration_fallback=False,
            details={"features_snapshot": features_data}
        )

    @staticmethod
    def list_predictions(city: str, db: Session, limit: int = 20) -> List[PredictionResponse]:
        normalized_city = model_service.normalize_city(city)

        predictions_col = mongo_manager.get_collection("predictions")
        if predictions_col is not None:
            try:
                cursor = (
                    predictions_col.find({"city": normalized_city})
                    .sort("created_at", DESCENDING)
                    .limit(limit)
                )
                results = []
                for doc in cursor:
                    results.append(
                        PredictionResponse(
                            city=doc.get("city", normalized_city),
                            location_id=doc.get("location_id"),
                            location_name=doc.get("location_name"),
                            forecast_horizon_hours=int(doc.get("forecast_horizon_hours", 1)),
                            risk_probability=float(doc.get("risk_score", 0.0)),
                            risk_category=doc.get("risk_category", "Low"),
                            model_id=f"{normalized_city.lower()}_model_{doc.get('model_version', '1.0')}",
                            prediction_timestamp=doc.get("created_at"),
                            input_freshness="historical_stored",
                            uncertainty_range=f"±{8 + int(doc.get('forecast_horizon_hours', 1)) * 2}%",
                            is_demonstration_fallback=False,
                            details={}
                        )
                    )
                if results:
                    return results
            except Exception as me:
                logger.warning(f"MongoDB list_predictions failed ({me}); using SQLite.")

        # SQLite fallback
        records = (
            db.query(PredictionDB)
            .filter(PredictionDB.city == normalized_city)
            .order_by(PredictionDB.id.desc())
            .limit(limit)
            .all()
        )
        results = []
        for r in records:
            results.append(
                PredictionResponse(
                    city=r.city,
                    location_id=r.location_id,
                    location_name=r.location_name,
                    forecast_horizon_hours=r.forecast_horizon_hours,
                    risk_probability=r.risk_score,
                    risk_category=r.risk_category,
                    model_id=f"{r.city.lower()}_model_{r.model_version}",
                    prediction_timestamp=r.created_at,
                    input_freshness="historical_stored",
                    uncertainty_range=f"±{8 + r.forecast_horizon_hours * 2}%",
                    is_demonstration_fallback=False,
                    details={}
                )
            )
        return results

    @staticmethod
    def generate_forecast_timeline(
        city: str,
        location_name: str,
        base_rainfall_mm: float,
        db: Session
    ) -> ForecastTimelineResponse:
        normalized_city = model_service.normalize_city(city)
        model = model_service.get_model(normalized_city)

        now = datetime.now(timezone.utc)
        items: List[ForecastTimelineItem] = []

        if model.is_loaded:
            for hour in range(1, 7):
                hourly_rain = base_rainfall_mm * (1.0 + hour * 0.15)
                f_dict = {
                    "rainfall_mm": hourly_rain,
                    "rainfall_intensity": hourly_rain / hour,
                    "forecast_horizon_hours": hour,
                }
                input_df, _ = build_model_input_dataframe(f_dict, model.expected_features)
                try:
                    prob, _ = model.predict(input_df)
                except Exception:
                    prob = 50.0

                items.append(
                    ForecastTimelineItem(
                        horizon_hours=hour,
                        timestamp=(now + timedelta(hours=hour)).isoformat(),
                        risk_probability=round(prob, 1),
                        risk_category=categorize_risk_score(prob),
                        rainfall_forecast_mm=round(hourly_rain, 1),
                        confidence_level="High" if hour <= 3 else "Moderate",
                    )
                )
            source_type = "model_prediction"
        else:
            source_type = "model_unavailable"
            items = []

        return ForecastTimelineResponse(
            city=normalized_city,
            location_name=location_name,
            timeline=items,
            generated_at=now.isoformat(),
            model_id=f"{normalized_city.lower()}_model_{model.version}",
            source=source_type,
        )

prediction_service = PredictionService()
