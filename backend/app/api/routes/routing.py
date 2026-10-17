from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.routing import (
    RouteRequest,
    RouteComparisonResponse,
    RoutePreset,
)
from app.services.routing_service import routing_service

router = APIRouter(prefix="/routes", tags=["Waterlogging-Aware Routing"])


@router.post(
    "/recommendations",
    response_model=RouteComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute waterlogging-aware route alternatives and risk rankings"
)
def get_route_recommendations(
    request: RouteRequest,
    db: Session = Depends(get_db)
):
    """
    Computes candidate driving routes between origin and destination,
    spatially correlates route geometry against live waterlogging reports,
    AI image classifications, and rainfall-screening hotspots,
    and returns travel times, distances, hazard breakdowns, and recommendations.
    """
    try:
        return routing_service.compute_route_recommendations(request, db=db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Route calculation failed: {str(e)}"
        )


@router.get(
    "/presets",
    response_model=List[RoutePreset],
    summary="Get common commuter corridor presets for Mumbai and Pune"
)
def get_route_presets(city: Optional[str] = Query(None, description="Filter presets by city (Mumbai or Pune)")):
    """
    Returns curated commuter origin/destination pairs across Mumbai and Pune.
    """
    return routing_service.get_presets(city)
