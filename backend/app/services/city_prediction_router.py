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
from app.services.mumbai_engine.screening import (
    compute_location_heuristic_risk,
)
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
        """Delegates strictly to Mumbai engine."""
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
        Mumbai routes to trained ML model if loaded, or to heuristic screening engine.
        """
        city = CityPredictionRouter.normalize_city(req.city)

        if city == "Pune":
            return pune_prediction_service.predict(req, db)

        # Mumbai
        mumbai_model = model_service.get_model("Mumbai")
        if mumbai_model.is_loaded:
            return prediction_service.run_prediction(req, db)

        # Mumbai location-specific screening and heuristic prediction
        horizon = req.forecast_horizon_hours if req.forecast_horizon_hours in [1, 2, 3, 4, 5, 6] else 3
        screen_h = 1 if horizon <= 1 else (3 if horizon <= 3 else 6)
        screening = mumbai_waterlogging_service.get_screening_results(horizon=screen_h)

        # Match location specifically
        loc_match = CityPredictionRouter.match_mumbai_location(
            screening["locations"],
            location_id=req.location_id,
            location_name=req.location_name,
            latitude=req.latitude,
            longitude=req.longitude,
        )

        elevation_m = (
            req.features.elevation_m
            if req.features.elevation_m is not None
            else loc_match["elevation_m"]
        )
        rainfall_mm = (
            req.features.rainfall_mm
            if req.features.rainfall_mm is not None
            else (loc_match["forecast_rainfall_mm"] or 0.0)
        )
        drainage_ratio = (
            req.features.drainage_capacity_ratio
            if req.features.drainage_capacity_ratio is not None
            else (0.40 if elevation_m <= 10.0 else 0.60)
        )
        hist_count = (
            req.features.historical_incident_count
            if req.features.historical_incident_count is not None
            else (8 if "dadar" in loc_match["location_name"].lower() else (9 if "kurla" in loc_match["location_name"].lower() else 3))
        )

        # Compute location-specific risk score and factor breakdown
        risk_prob, risk_cat, factors = compute_location_heuristic_risk(
            elevation_m=elevation_m,
            rainfall_mm=rainfall_mm,
            drainage_capacity_ratio=drainage_ratio,
            historical_incident_count=hist_count,
            horizon_hours=horizon,
        )

        logger.info(
            f"[AquaSignal:PredictionRouter] Location: {loc_match['location_name']} "
            f"(id: {req.location_id or loc_match['location_id']}), +{horizon}h, Elev: {elevation_m}m, "
            f"Rain: {rainfall_mm}mm -> Prob: {risk_prob}%, Cat: {risk_cat}"
        )

        timestamp = screening["generated_at"]

        # Persist prediction record in DB for audit trail
        try:
            pred_record = PredictionDB(
                city="Mumbai",
                location_id=req.location_id or loc_match["location_id"],
                location_name=req.location_name or loc_match["location_name"],
                forecast_horizon_hours=horizon,
                risk_score=risk_prob,
                risk_category=risk_cat,
                model_version="heuristic_demonstration_v1.2",
                features_snapshot=req.features.model_dump_json(),
                created_at=timestamp,
            )
            db.add(pred_record)
            db.commit()
            db.refresh(pred_record)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist Mumbai screening audit record: {e}")

        return PredictionResponse(
            city="Mumbai",
            location_id=req.location_id or loc_match["location_id"],
            location_name=req.location_name or loc_match["location_name"],
            forecast_horizon_hours=horizon,
            risk_probability=risk_prob,
            risk_category=risk_cat,
            model_id="mumbai_heuristic_screening_v1.2",
            prediction_timestamp=timestamp,
            input_freshness=screening["data_freshness"],
            uncertainty_range=f"±{8 + horizon * 2}%",
            is_demonstration_fallback=False,
            details={
                "is_heuristic_demonstration": True,
                "model_type": "Physical Heuristic (Elevation + Drainage + Live Rain)",
                "disclaimer": (
                    "Heuristic demonstration early-warning output based on local terrain elevation, "
                    "drainage capacity, and weather. Not a certified operational flood model."
                ),
                "warning_status": loc_match["warning_status"],
                "elevation_m": elevation_m,
                "drainage_capacity_ratio": drainage_ratio,
                "recent_rainfall_mm": loc_match["recent_rainfall_mm"],
                "forecast_rainfall_mm": loc_match["forecast_rainfall_mm"],
                "explanation": loc_match["explanation"],
                "factors": factors,
                "hotspot_evidence": loc_match["hotspot_evidence"],
                "validation_status": "NOT_VALIDATED",
            }
        )

    @staticmethod
    def get_latest_prediction(city: str, db: Session) -> Optional[PredictionResponse]:
        clean_city = CityPredictionRouter.normalize_city(city)
        if clean_city == "Pune":
            return pune_prediction_service.get_latest(db)

        # For Mumbai, check if there is an existing stored prediction in DB
        latest = prediction_service.get_latest_prediction("Mumbai", db)
        if latest:
            return latest

        # Otherwise generate a live snapshot from screening engine
        screening = mumbai_waterlogging_service.get_screening_results(horizon=3)
        first_loc = screening["locations"][0]
        return PredictionResponse(
            city="Mumbai",
            location_id=first_loc["location_id"],
            location_name=first_loc["location_name"],
            forecast_horizon_hours=3,
            risk_probability=0.0,
            risk_category=first_loc["warning_status"].replace("_", " ").title(),
            model_id="mumbai_rule_based_screening_v1.0",
            prediction_timestamp=screening["generated_at"],
            input_freshness="live_screening",
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

        # Mumbai
        mumbai_model = model_service.get_model("Mumbai")
        if mumbai_model.is_loaded:
            return prediction_service.generate_forecast_timeline("Mumbai", location_name, base_rainfall_mm, db)

        # Retrieve screening results to obtain baseline observations
        sc = mumbai_waterlogging_service.get_screening_results(horizon=3)
        loc_item = CityPredictionRouter.match_mumbai_location(
            sc["locations"],
            location_id=location_id,
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
        )

        elevation_m = loc_item["elevation_m"]
        drainage_ratio = 0.40 if elevation_m <= 10.0 else 0.60
        hist_count = (
            8 if "dadar" in loc_item["location_name"].lower()
            else (9 if "kurla" in loc_item["location_name"].lower() else 3)
        )

        now = datetime.now(timezone.utc)
        items = []
        for h in range(1, 7):
            hourly_rain = base_rainfall_mm * (1.0 + (h - 1) * 0.15)
            h_prob, h_cat, _ = compute_location_heuristic_risk(
                elevation_m=elevation_m,
                rainfall_mm=hourly_rain,
                drainage_capacity_ratio=drainage_ratio,
                historical_incident_count=hist_count,
                horizon_hours=h,
            )
            items.append(
                ForecastTimelineItem(
                    horizon_hours=h,
                    timestamp=(now + timedelta(hours=h)).isoformat(),
                    risk_probability=h_prob,
                    risk_category=h_cat,
                    rainfall_forecast_mm=round(hourly_rain, 1),
                    confidence_level=f"±{8 + h * 2}%"
                )
            )

        logger.info(
            f"[AquaSignal:TimelineRouter] Generated 6h timeline for {loc_item['location_name']} "
            f"(Elev: {elevation_m}m, base rain: {base_rainfall_mm}mm). "
            f"+1h: {items[0].risk_probability}%, +3h: {items[2].risk_probability}%, +6h: {items[5].risk_probability}%"
        )

        return ForecastTimelineResponse(
            city="Mumbai",
            location_name=location_name,
            timeline=items,
            generated_at=now.isoformat(),
            model_id="mumbai_heuristic_screening_v1.2",
            source="mumbai_heuristic_timeline",
        )

city_prediction_router = CityPredictionRouter()
