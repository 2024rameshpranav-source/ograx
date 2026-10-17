import os
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas.incident import (
    IncidentAnalyzeResponse,
    IncidentCreateRequest,
    IncidentResponse,
    IncidentReviewRequest,
    DynamicRiskResponse,
    ModelEvaluationResponse,
    DemoSummaryResponse
)
from app.services.image_classifier import flood_classifier_service
from app.services.incident_service import incident_service

router = APIRouter(prefix="/incidents", tags=["Incidents & Vision Intelligence"])

ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

@router.post("/analyze", response_model=IncidentAnalyzeResponse)
async def analyze_image_with_model(
    file: UploadFile = File(..., description="Captured image file for flood classification")
):
    """
    Runs actual inference using the pretrained Hugging Face model
    'prithivMLmods/Flood-Image-Detection' (SiglipForImageClassification).
    Returns predicted class ('Flooded Scene' vs 'Non Flooded') and confidence score.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type '{file.content_type}'. Supported: JPEG, PNG, WEBP."
        )

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size exceeds 10 MB limit."
        )

    # Save to disk securely
    ext = ".jpg" if "jpeg" in file.content_type else (".png" if "png" in file.content_type else ".webp")
    filename = f"incident_photo_{uuid.uuid4().hex[:12]}{ext}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(contents)

    image_ref = f"/uploads/{filename}"

    try:
        # Run real model inference
        result = flood_classifier_service.classify(contents)
        result["image_reference"] = image_ref
        return result
    except Exception as e:
        # Return structured analysis error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model inference failed: {str(e)}"
        )

@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident_report(request: IncidentCreateRequest):
    """
    Creates a persistent incident record in the database,
    evaluates baseline risk, applies duplicate suppression,
    and recalculates dynamic area risk.
    """
    try:
        incident = incident_service.create_incident(request)
        return incident
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create incident: {str(e)}"
        )

@router.get("/history", response_model=Dict[str, Any])
def list_incident_history(
    city: Optional[str] = Query(None, description="Filter by city (e.g. Mumbai or Pune)"),
    status: Optional[str] = Query(None, description="Filter by verification status"),
    is_demo: Optional[bool] = Query(None, description="Filter by demo vs real data"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Lists historical incidents with support for filtering by city,
    status, and real vs. demo dataset segregation.
    """
    incidents, total = incident_service.get_incidents(
        city=city,
        verification_status=status,
        is_demo=is_demo,
        skip=skip,
        limit=limit
    )
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "incidents": [IncidentResponse.model_validate(i) for i in incidents]
    }

@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str):
    """
    Retrieves full details of a single incident.
    """
    inc = incident_service.get_incident_by_id(incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found")
    return IncidentResponse.model_validate(inc)

@router.patch("/{incident_id}/review", response_model=IncidentResponse)
def review_incident(incident_id: str, review: IncidentReviewRequest):
    """
    Human review workflow: marks report as genuine waterlogging, non-waterlogging,
    inconclusive, or duplicate, and recomputes the dynamic area risk adjustment.
    """
    try:
        updated = incident_service.review_incident(incident_id, review)
        return IncidentResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/risk/area", response_model=DynamicRiskResponse)
def get_area_dynamic_risk(
    city: str = Query("Mumbai"),
    location_name: str = Query("Andheri Subway"),
    latitude: float = Query(19.1197),
    longitude: float = Query(72.8468),
    radius_km: float = Query(1.5, ge=0.1, le=10.0),
    baseline_risk: Optional[float] = Query(None, description="Optional override baseline risk score (0-100)")
):
    """
    Calculates dynamic area risk using the formula:
    Final Area Risk = Clamp(Baseline Risk + Report Adjustment, 0, 100).
    Separately reports baseline score, report adjustment, and final risk.
    """
    res = incident_service.calculate_area_risk(
        city=city,
        location_name=location_name,
        lat=latitude,
        lng=longitude,
        radius_km=radius_km,
        baseline_risk=baseline_risk
    )
    return res

@router.get("/models/evaluation", response_model=ModelEvaluationResponse)
def get_model_evaluation(
    include_demo: bool = Query(True, description="Include labeled demo benchmark incidents")
):
    """
    Computes real confusion matrix, precision, recall, F1, and accuracy
    against labeled ground-truth examples.
    """
    return incident_service.calculate_model_evaluation(include_demo=include_demo)

@router.get("/models/export-dataset")
def export_retraining_dataset():
    """
    Exports eligible, verified ground-truth records partitioned into
    train (70%), validation (15%), and test (15%) splits without data leakage.
    """
    return incident_service.export_dataset()

@router.get("/demo/summary", response_model=DemoSummaryResponse)
def get_demo_summary():
    """
    Summarizes total demo and real incidents, positive vs negative classifications,
    and verification statuses.
    """
    return incident_service.get_demo_summary()

@router.post("/demo/seed")
def seed_demo_incidents():
    """
    Seeds realistic demonstration incident records across Mumbai and Pune.
    """
    count = incident_service.seed_demo_data()
    return {"success": True, "message": f"Seeded {count} demonstration incidents.", "demo_count": count}

@router.post("/demo/reset")
def reset_demo_incidents():
    """
    Deletes all synthetic demo records without touching real user submissions.
    """
    deleted = incident_service.reset_demo_data()
    return {"success": True, "message": f"Reset {deleted} demonstration incidents.", "deleted_count": deleted}
