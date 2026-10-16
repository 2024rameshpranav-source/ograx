from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class AnalyticsOverview(BaseModel):
    city: str
    total_reports: int
    reports_by_status: Dict[str, int]
    reports_by_severity: Dict[str, int]
    total_predictions: int
    latest_prediction: Optional[Dict[str, Any]] = None
    data_freshness_minutes: int
    models_status: Dict[str, Any]

class IncidentsAnalytics(BaseModel):
    city: str
    total_incidents: int
    by_severity: Dict[str, int]
    by_access: Dict[str, int]
    recent_incidents: List[Dict[str, Any]]

class LocationRiskItem(BaseModel):
    location_id: Optional[str] = None
    location_name: str
    risk_score: float
    risk_category: str
    forecast_horizon_hours: int
    last_updated: str
    report_count: int

class LocationsAnalytics(BaseModel):
    city: str
    total_monitored_locations: int
    locations: List[LocationRiskItem]
