"""
City-Specific Prediction & Early-Warning Router for AquaSignal AI.
Directs incoming requests to the appropriate city engine:
- Mumbai: MumbaiWaterloggingService (Rule-driven rainfall screening prototype) or trained ML model when loaded
- Pune: PunePredictionService (Trained Machine Learning model)
Maintains strict isolation between the two pipelines.
"""
from typing import Dict, Any, List, Optional
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.schemas.prediction import (
    PredictionRequest,
    PredictionResponse,
    ForecastTimelineResponse,
    ForecastTimelineItem,
)
from app.db.models import PredictionDB
from app.services.model_service import model_service
from app.services.prediction_service import prediction_service
from app.services.mumbai_engine.service import mumbai_waterlogging_service
from app.services.pune_engine.service import pune_prediction_service
from app.utils.logging_config import logger

SUPPORTED_CITIES = ["Mumbai", "Pune"]

class CityPredictionRouter:
    @staticmethod
    def normalize_city(city: str) -> str:
        if not city:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="City identifier is required. Supported cities: 'Mumbai', 'Pune'."
            )
        clean = city.strip().title()
        if clean not in SUPPORTED_CITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Unsupported city '{city}'. AquaSignal currently routes to: {', '.join(SUPPORTED_CITIES)}."
            )
        return clean

    @staticmethod
    def match_mumbai_location(
        screening_locations: List[Dict[str, Any]],
        location_id: Optional[str] = None,
        location_name: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Locates the specific Mumbai monitoring corridor or area based on:
        1. Unique location_id (e.g. mum_bandra, BND-01)
        2. Clean locality name (e.g. 'Mumbai · Bandra' -> 'Bandra')
        3. Closest spatial coordinates (latitude, longitude)
        """
        if not screening_locations:
            raise ValueError("No screening locations available in engine.")

        # 1. Match by location_id
        if location_id:
            lid_clean = location_id.strip().lower()
            for loc in screening_locations:
                if loc["location_id"].lower() == lid_clean:
                    return loc
            # Prefix match e.g. BND -> Bandra, DAD -> Dadar, AND -> Andheri, KRL -> Kurla
            prefix_map = {
                "bnd": "bandra", "dad": "dadar", "and": "andheri",
                "krl": "kurla", "chm": "chembur", "col": "colaba",
                "pow": "powai", "sio": "sion"
            }
            for pref, lname in prefix_map.items():
                if lid_clean.startswith(pref):
                    for loc in screening_locations:
                        if loc["location_name"].lower() == lname:
                            return loc

        # 2. Match by location_name
        if location_name:
            clean = location_name.strip().lower()
            if "·" in clean:
                clean = clean.split("·")[-1].strip()
            # Strip extra corridor details like " - Hindmata Flyover"
            core_part = clean.split("-")[0].strip()

            for loc in screening_locations:
                if loc["location_name"].lower() == clean or loc["location_name"].lower() == core_part:
                    return loc
            for loc in screening_locations:
                if loc["location_name"].lower() in clean or clean in loc["location_name"].lower():
                    return loc

        # 3. Match by coordinates (Euclidean proximity)
        if latitude is not None and longitude is not None:
            best_loc = min(
                screening_locations,
                key=lambda loc: (loc["latitude"] - latitude)**2 + (loc["longitude"] - longitude)**2
            )
            return best_loc

        # Fallback to first available
        return screening_locations[0]

    @staticmethod
    def get_mumbai_locations() -> List[Dict[str, Any]]:
        """Delegates strictly to Mumbai warning engine."""
        return mumbai_waterlogging_service.get_supported_locations()

    @staticmethod
    def get_mumbai_screening(horizon: int = 3, force_refresh: bool = False) -> Dict[str, Any]:
        """Delegates strictly to Mumbai rule-based screening engine."""
        return mumbai_waterlogging_service.get_screening_results(horizon=horizon, force_refresh=force_refresh)

    @staticmethod
    def run_prediction(req: PredictionRequest, db: Session) -> Any:
        """
        Routes prediction request based on target city.
        Pune routes strictly to its independent ML service.
        Mumbai routes exclusively to the final rule-based warning engine.
        """
        city = CityPredictionRouter.normalize_city(req.city)

        if city == "Pune":
            return pune_prediction_service.predict(req, db)

        # Mumbai: strictly evaluate via final Mumbai warning engine
        horizon = req.forecast_horizon_hours if req.forecast_horizon_hours in [1, 3, 6] else (
            1 if req.forecast_horizon_hours <= 1 else (3 if req.forecast_horizon_hours <= 4 else 6)
        )
        screening = mumbai_waterlogging_service.get_screening_results(horizon=horizon)

        # Match location specifically
        loc_match = CityPredictionRouter.match_mumbai_location(
            screening["locations"],
            location_id=req.location_id,
            location_name=req.location_name,
            latitude=req.latitude,
            longitude=req.longitude,
        )

        warning_status = loc_match["warning_status"]
        timestamp = screening["generated_at"]

        # Persist prediction record in DB for audit trail
        try:
            pred_record = PredictionDB(
                city="Mumbai",
                location_id=req.location_id or loc_match["location_id"],
                location_name=req.location_name or loc_match["location_name"],
                forecast_horizon_hours=horizon,
                risk_score=0.0,
                risk_category=warning_status,
                model_version="mumbai_warning_engine_v1.0",
                features_snapshot=req.features.model_dump_json(),
                created_at=timestamp,
            )
            db.add(pred_record)
            db.commit()
            db.refresh(pred_record)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist Mumbai screening audit record: {e}")

        logger.info(
            f"[AquaSignal:MumbaiWarningEngine] Location: {loc_match['location_name']}, +{horizon}h -> Status: {warning_status}"
        )

        return PredictionResponse(
            city="Mumbai",
            location_id=req.location_id or loc_match["location_id"],
            location_name=req.location_name or loc_match["location_name"],
            forecast_horizon_hours=horizon,
            risk_probability=None,  # Rule: never invent or calculate a probability
            risk_category=warning_status,
            model_id="mumbai_rainfall_warning_engine_v1.0",
            prediction_timestamp=timestamp,
            input_freshness=screening["data_freshness"],
            uncertainty_range="UNVALIDATED_PROTOTYPE",
            is_demonstration_fallback=False,
            details={
                "is_rule_based_warning_engine": True,
                "model_type": "Rule-Based Rainfall Threshold Screening Engine",
                "validation_status": "NOT_VALIDATED",
                "disclaimer": (
                    "Experimental rule-based rainfall screening output. "
                    "This is NOT a trained machine-learning model and does NOT provide a validated waterlogging probability."
                ),
                "warning_status": warning_status,
                "warning_1h": loc_match.get("warning_1h"),
                "warning_3h": loc_match.get("warning_3h"),
                "warning_6h": loc_match.get("warning_6h"),
                "overall_screening_status": loc_match.get("overall_screening_status"),
                "rain_last_1h_mm": loc_match.get("rain_last_1h_mm"),
                "rain_last_3h_mm": loc_match.get("rain_last_3h_mm"),
                "rain_last_6h_mm": loc_match.get("rain_last_6h_mm"),
                "rain_last_24h_mm": loc_match.get("rain_last_24h_mm"),
                "rain_next_1h_mm": loc_match.get("rain_next_1h_mm"),
                "rain_next_3h_mm": loc_match.get("rain_next_3h_mm"),
                "rain_next_6h_mm": loc_match.get("rain_next_6h_mm"),
                "recent_rainfall_mm": loc_match.get("recent_rainfall_mm"),
                "forecast_rainfall_mm": loc_match.get("forecast_rainfall_mm"),
                "elevation_m": loc_match.get("elevation_m"),
                "explanation": loc_match.get("explanation"),
                "hotspot_evidence": loc_match.get("hotspot_evidence"),
            }
        )

    @staticmethod
    def get_latest_prediction(city: str, db: Session) -> Optional[PredictionResponse]:
        clean_city = CityPredictionRouter.normalize_city(city)
        if clean_city == "Pune":
            return pune_prediction_service.get_latest(db)

        # Mumbai: generate live snapshot from the warning engine
        screening = mumbai_waterlogging_service.get_screening_results(horizon=3)
        first_loc = screening["locations"][0]
        return PredictionResponse(
            city="Mumbai",
            location_id=first_loc["location_id"],
            location_name=first_loc["location_name"],
            forecast_horizon_hours=3,
            risk_probability=None,
            risk_category=first_loc["warning_status"],
            model_id="mumbai_rainfall_warning_engine_v1.0",
            prediction_timestamp=screening["generated_at"],
            input_freshness=screening["data_freshness"],
            uncertainty_range="UNVALIDATED_PROTOTYPE",
            is_demonstration_fallback=False,
            details={"screening_snapshot": screening}
        )

    @staticmethod
    def get_forecast_timeline(
        city: str,
        location_name: str,
        base_rainfall_mm: float,
        db: Session,
        location_id: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> ForecastTimelineResponse:
        clean_city = CityPredictionRouter.normalize_city(city)
        if clean_city == "Pune":
            return pune_prediction_service.get_forecast_timeline(location_name, base_rainfall_mm, db)

        # Mumbai: generate timeline strictly mapped to screening engine horizons (+1h, +3h, +6h)
        sc = mumbai_waterlogging_service.get_screening_results(horizon=3)
        loc_item = CityPredictionRouter.match_mumbai_location(
            sc["locations"],
            location_id=location_id,
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
        )

        now = datetime.now(timezone.utc)
        items = []
        for h in range(1, 7):
            mapped_h = 1 if h <= 1 else (3 if h <= 4 else 6)
            h_status = loc_item.get(f"warning_{mapped_h}h", loc_item["warning_status"])
            forecast_rain = loc_item.get(f"rain_next_{mapped_h}h_mm")

            items.append(
                ForecastTimelineItem(
                    horizon_hours=h,
                    timestamp=(now + timedelta(hours=h)).isoformat(),
                    risk_probability=None,
                    risk_category=h_status,
                    rainfall_forecast_mm=forecast_rain,
                    confidence_level="Experimental Screening (Unvalidated)",
                )
            )

        return ForecastTimelineResponse(
            city="Mumbai",
            location_name=loc_item["location_name"],
            timeline=items,
            generated_at=now.isoformat(),
            model_id="mumbai_rainfall_warning_engine_v1.0",
            source="mumbai_warning_engine",
        )

city_prediction_router = CityPredictionRouter()
