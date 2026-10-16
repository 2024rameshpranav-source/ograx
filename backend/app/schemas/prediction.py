from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator

class PredictionInputFeatures(BaseModel):
    rainfall_mm: float = Field(..., ge=0.0, description="Rainfall accumulation in mm")
    rainfall_intensity: Optional[float] = Field(None, ge=0.0, description="Rainfall intensity in mm/hour")
    drainage_capacity_ratio: Optional[float] = Field(None, ge=0.0, le=1.0, description="Ratio of drainage capacity available (0.0 to 1.0)")
    elevation_m: Optional[float] = Field(None, description="Ground elevation in meters above mean sea level")
    tide_level_m: Optional[float] = Field(None, description="Tidal water level in meters (especially coastal Mumbai)")
    soil_saturation_index: Optional[float] = Field(None, ge=0.0, le=1.0, description="Antecedent soil moisture saturation index")
    road_gradient_pct: Optional[float] = Field(None, description="Road gradient percentage")
    historical_incident_count: Optional[int] = Field(None, ge=0, description="Historical waterlogging incident frequency")
    extra_features: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary additional feature columns required by specific models")

class PredictionRequest(BaseModel):
    city: str = Field(..., description="Target city: 'Mumbai' or 'Pune'")
    location_id: Optional[str] = Field(None, max_length=64, description="Optional unique identifier for road/hotspot segment")
    location_name: Optional[str] = Field(None, max_length=256, description="Human readable name of the location")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    forecast_horizon_hours: int = Field(1, ge=1, le=6, description="Forecast horizon in hours (1 to 6)")
    features: PredictionInputFeatures

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        clean = v.strip().title()
        if clean not in ["Mumbai", "Pune"]:
            raise ValueError("Unsupported city. Only 'Mumbai' and 'Pune' are currently supported.")
        return clean

class PredictionResponse(BaseModel):
    city: str
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    forecast_horizon_hours: int
    risk_probability: float = Field(..., ge=0.0, le=100.0, description="Predicted waterlogging probability percentage (0-100%)")
    risk_category: str = Field(..., description="Categorized risk: 'Low', 'Moderate', 'High', or 'Critical'")
    model_id: str
    prediction_timestamp: str
    input_freshness: str = "fresh"
    uncertainty_range: Optional[str] = None
    is_demonstration_fallback: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)

class ForecastTimelineItem(BaseModel):
    horizon_hours: int
    timestamp: str
    risk_probability: float
    risk_category: str
    rainfall_forecast_mm: Optional[float] = None
    confidence_level: str = "High"

class ForecastTimelineResponse(BaseModel):
    city: str
    location_name: str
    timeline: List[ForecastTimelineItem]
    generated_at: str
    model_id: str
    source: str  # "model_prediction" | "model_unavailable"
