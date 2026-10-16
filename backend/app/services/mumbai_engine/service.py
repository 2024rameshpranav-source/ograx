"""
Mumbai Waterlogging Early-Warning Service.
Coordinates location metadata, weather data (Open-Meteo), and the rule-based screening engine.
Strictly adheres to limitations:
- NOT a machine-learning model
- DOES NOT calculate or fabricate waterlogging probability (explicitly None)
- Highlights hotspot evidence separately from rainfall screening signals
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import HTTPException, status

from app.services.mumbai_engine.locations import MUMBAI_LOCATIONS, get_mumbai_locations
from app.services.mumbai_engine.screening import (
    classify_warning,
    generate_explanation,
    DEFAULT_THRESHOLDS,
)
from app.services.mumbai_engine.weather_service import mumbai_weather_service
from app.utils.logging_config import logger

class MumbaiWaterloggingService:
    def __init__(self):
        self.locations = MUMBAI_LOCATIONS
        self.thresholds = DEFAULT_THRESHOLDS

    def get_supported_locations(self) -> List[Dict[str, Any]]:
        """Returns metadata for the 8 Mumbai monitoring locations."""
        return get_mumbai_locations()

    def get_screening_results(self, horizon: int = 3, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Executes rainfall screening for all 8 Mumbai locations for the specified horizon (1, 3, or 6 hours).
        """
        if horizon not in [1, 3, 6]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid forecast horizon '{horizon}'. Mumbai rule-based screening engine only supports 1, 3, or 6 hours."
            )

        weather_by_loc = mumbai_weather_service.get_weather_data(force_refresh=force_refresh)
        results: List[Dict[str, Any]] = []

        overall_counts = {
            "NO_RAINFALL_SIGNAL": 0,
            "LOW_RAINFALL_SIGNAL": 0,
            "RAINFALL_WATCH": 0,
            "DATA_CHECK_REQUIRED": 0,
        }

        generated_time = datetime.now(timezone.utc).isoformat()
        primary_data_source = "Open-Meteo"
        data_freshness_overall = "FRESH"

        for loc in self.locations:
            loc_name = loc["location_name"]
            weather = weather_by_loc.get(loc_name, {})

            recent_rain = weather.get(f"rain_last_{horizon}h_mm")
            forecast_rain = weather.get(f"rain_next_{horizon}h_mm")
            data_status = weather.get("data_status", "AVAILABLE")
            data_source = weather.get("data_source", "Open-Meteo")
            primary_data_source = data_source

            if weather.get("data_freshness_status") != "FRESH_LIVE":
                data_freshness_overall = "ARCHIVE_SNAPSHOT_OR_FALLBACK"

            # Classify screening status
            warning_status = classify_warning(
                data_status=data_status,
                recent_mm=recent_rain,
                forecast_mm=forecast_rain,
                horizon=horizon,
                thresholds=self.thresholds
            )
            overall_counts[warning_status] = overall_counts.get(warning_status, 0) + 1

            # Generate explanation
            explanation = generate_explanation(
                status=warning_status,
                horizon=horizon,
                recent_mm=recent_rain,
                forecast_mm=forecast_rain,
                location_name=loc_name,
                thresholds=self.thresholds
            )

            results.append({
                "location_name": loc_name,
                "location_id": loc["location_id"],
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "elevation_m": loc["elevation_m"],
                "warning_status": warning_status,
                "recent_rainfall_mm": recent_rain,
                "forecast_rainfall_mm": forecast_rain,
                "rain_last_24h_mm": weather.get("rain_last_24h_mm"),
                "thresholds": self.thresholds[horizon],
                "explanation": explanation,
                "data_status": data_status,
                "data_source": data_source,
                "observation_time": weather.get("observation_time", generated_time),
                "waterlogging_probability": None,  # Intentionally null: unvalidated prototype
                "hotspot_evidence": loc["hotspot_evidence"],
            })

        # Determine overall city signal for horizon
        if overall_counts["DATA_CHECK_REQUIRED"] > 0:
            overall_signal = "DATA_CHECK_REQUIRED"
        elif overall_counts["RAINFALL_WATCH"] > 0:
            overall_signal = "RAINFALL_WATCH"
        elif overall_counts["LOW_RAINFALL_SIGNAL"] > 0:
            overall_signal = "LOW_RAINFALL_SIGNAL"
        else:
            overall_signal = "NO_RAINFALL_SIGNAL"

        return {
            "success": True,
            "city": "mumbai",
            "prediction_type": "rule_based_rainfall_screening",
            "validation_status": "NOT_VALIDATED",
            "warning_engine_status": "RULE_BASED_PROTOTYPE_NOT_VALIDATED",
            "horizon_hours": horizon,
            "overall_screening_status": overall_signal,
            "status_breakdown": overall_counts,
            "generated_at": generated_time,
            "data_source": primary_data_source,
            "data_freshness": data_freshness_overall,
            "locations": results,
            "disclaimer": (
                "Experimental rule-based rainfall screening prototype for 8 Mumbai locations. "
                "This is NOT a trained machine-learning model and does NOT provide a validated waterlogging probability. "
                "Do not use as an official flood-warning or emergency evacuation instruction."
            )
        }

mumbai_waterlogging_service = MumbaiWaterloggingService()
