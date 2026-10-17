from fastapi import APIRouter
from typing import Dict, Any, List
from app.config import settings
from app.services.model_service import model_service, SUPPORTED_CITIES
from app.db.mongodb import mongo_manager

router = APIRouter(tags=["Health & Configuration"])

@router.get("/health", response_model=Dict[str, Any])
def get_health() -> Dict[str, Any]:
    """
    Health and infrastructure inspection endpoint.
    Returns:
    - Application status
    - Backend API version
    - Database mode (MongoDB Atlas or SQLite fallback) with real-time ping check
    - Availability and configuration state for Mumbai and Pune models
    """
    models_status = model_service.get_status_summary()
    all_ready = all(m["loaded"] for m in models_status.values())
    mongo_status = mongo_manager.ping()
    active_mode = "mongodb" if mongo_status.get("connected") else "sqlite"

    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": {
            "active_mode": active_mode,
            "sqlite_fallback_ready": True,
            "mongodb": mongo_status,
        },
        "models_all_ready": all_ready,
        "models": models_status,
        "supported_cities": SUPPORTED_CITIES,
    }

@router.get("/health/mongodb", response_model=Dict[str, Any])
def ping_mongodb() -> Dict[str, Any]:
    """
    Explicit MongoDB Atlas ping endpoint that executes admin.command('ping').
    """
    return mongo_manager.ping()

@router.get("/cities", response_model=Dict[str, Any])
def get_cities() -> Dict[str, Any]:
    """Returns supported cities and their respective model availability."""
    return {
        "supported_cities": SUPPORTED_CITIES,
        "models": model_service.get_status_summary(),
    }
