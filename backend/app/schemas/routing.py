from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator

class LatLngPoint(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    name: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_lat_lng(cls, data: Any):
        if isinstance(data, dict):
            # Create a shallow copy if mutating to avoid side effects
            d = dict(data)
            if "lat" in d and "latitude" not in d:
                d["latitude"] = d["lat"]
            if "lng" in d and "longitude" not in d:
                d["longitude"] = d["lng"]
            if "label" in d and "name" not in d:
                d["name"] = d["label"]
            return d
        return data

class RouteRequest(BaseModel):
    city: str = Field("Mumbai", description="Mumbai or Pune")
    origin: LatLngPoint
    destination: LatLngPoint
    prefer_alternatives: bool = Field(True, description="Whether to request alternative routes")
    tolerance_meters: float = Field(250.0, ge=50.0, le=2000.0, description="Spatial tolerance radius around route for hazard intersection")
    horizon_hours: int = Field(3, ge=1, le=6, description="Forecast horizon for rainfall screening")

class HazardIntersection(BaseModel):
    hazard_type: str = Field(..., description="VERIFIED_WATERLOGGING, PENDING_AI_DETECTION, CITIZEN_REPORT, or RAINFALL_WATCH")
    location_name: str
    latitude: float
    longitude: float
    distance_to_route_meters: float
    severity_or_status: str
    reported_at: Optional[str] = None
    age_hours: Optional[float] = None
    description: str
    risk_points_contributed: float

class RouteOption(BaseModel):
    route_id: str
    summary_name: str
    distance_km: float
    duration_minutes: float
    coordinates: List[List[float]] = Field(..., description="List of [lat, lng] coordinates for the polyline")
    
    # Risk Metrics
    risk_score: float = Field(..., description="Computed hazard exposure score (0 - 100)")
    risk_category: str = Field(..., description="LOWER_KNOWN_RISK, ELEVATED_RISK, HIGH_HAZARD, or DATA_UNAVAILABLE")
    is_recommended: bool = False
    recommendation_reason: str
    
    # Hazard breakdown
    hazard_count: int = 0
    verified_waterlogging_count: int = 0
    pending_ai_reports_count: int = 0
    rainfall_watch_count: int = 0
    hazards: List[HazardIntersection] = []
    
    # Metadata
    data_freshness: str
    data_source: str

class RouteComparisonResponse(BaseModel):
    success: bool = True
    city: str
    origin_name: str
    destination_name: str
    total_routes_found: int
    routes: List[RouteOption]
    recommended_route_id: Optional[str] = None
    screening_status_summary: Optional[str] = None
    calculation_methodology: str
    safety_disclaimer: str
    timestamp: str

class RoutePreset(BaseModel):
    id: str
    city: str
    name: str
    origin: LatLngPoint
    destination: LatLngPoint
    corridor_description: str
