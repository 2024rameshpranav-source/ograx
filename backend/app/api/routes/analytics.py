from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.analytics import (
    AnalyticsOverview,
    IncidentsAnalytics,
    LocationsAnalytics,
)
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/analytics", tags=["Operational Analytics"])

@router.get("/overview", response_model=AnalyticsOverview)
def get_analytics_overview(
    city: str = Query("Mumbai", description="Target city: Mumbai or Pune"),
    db: Session = Depends(get_db)
) -> AnalyticsOverview:
    """
    Returns high-level operational overview metrics for the city:
    - Stored report counts by status and severity
    - Total model predictions generated
    - Latest prediction summary
    - Input data freshness
    """
    return analytics_service.get_overview(city, db)

@router.get("/incidents", response_model=IncidentsAnalytics)
def get_incidents_analytics(
    city: str = Query("Mumbai", description="Target city: Mumbai or Pune"),
    db: Session = Depends(get_db)
) -> IncidentsAnalytics:
    """
    Returns incident distribution breakdowns by severity and road access impact.
    """
    return analytics_service.get_incidents_analytics(city, db)

@router.get("/locations", response_model=LocationsAnalytics)
def get_locations_analytics(
    city: str = Query("Mumbai", description="Target city: Mumbai or Pune"),
    db: Session = Depends(get_db)
) -> LocationsAnalytics:
    """
    Returns monitored geographic locations with their latest risk scores and incident counts.
    """
    return analytics_service.get_locations_analytics(city, db)
