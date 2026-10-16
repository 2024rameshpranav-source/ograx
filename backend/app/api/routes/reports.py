import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, Query, status, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.config import settings
from app.db.session import get_db
from app.schemas.report import (
    ReportCreate,
    ReportResponse,
    ReportListResponse,
    ReportStatusUpdate,
)
from app.services.report_service import report_service

router = APIRouter(prefix="/reports", tags=["Citizen Incident Reports"])

@router.post("/upload-photo", status_code=status.HTTP_201_CREATED)
async def upload_report_photo(file: UploadFile = File(...)):
    """
    Uploads an optional evidence photograph for a citizen incident report.
    Validates MIME type, enforces a 5 MB maximum size limit,
    and stores with a safe, anonymized filename.
    """
    if not file.content_type or file.content_type.lower() not in settings.ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type '{file.content_type}'. Allowed types: {', '.join(settings.ALLOWED_IMAGE_TYPES)}"
        )

    original_ext = Path(file.filename or "").suffix.lower()
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif"
    }
    safe_ext = ext_map.get(file.content_type.lower(), original_ext if original_ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"] else ".jpg")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    safe_filename = f"report_photo_{uuid.uuid4().hex[:12]}{safe_ext}"
    dest_path = Path(settings.UPLOAD_DIR) / safe_filename

    total_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB chunk

    try:
        with open(dest_path, "wb") as buffer:
            while chunk := await file.read(chunk_size):
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                    buffer.close()
                    if dest_path.exists():
                        dest_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE if hasattr(status, "HTTP_413_CONTENT_TOO_LARGE") else 413,
                        detail="File exceeds maximum size limit of 5 MB."
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and store image file: {str(e)}"
        )

    return {
        "photo_url": f"/uploads/{safe_filename}",
        "filename": safe_filename,
        "size_bytes": total_bytes,
        "content_type": file.content_type
    }

@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit_report(
    report_in: ReportCreate,
    db: Session = Depends(get_db)
) -> ReportResponse:
    """
    Submits a citizen ground observation report.
    Persists data in the durable SQLite backend database.
    """
    return report_service.create_report(report_in, db)

@router.get("", response_model=ReportListResponse)
def list_reports(
    city: Optional[str] = Query(None, description="Filter by city: Mumbai or Pune"),
    status: Optional[str] = Query(None, description="Filter by status: UNVERIFIED REPORT, CORROBORATED, ADMIN-VERIFIED"),
    severity: Optional[str] = Query(None, description="Filter by severity: Low, Moderate, High, Severe"),
    q: Optional[str] = Query(None, description="Search keyword in landmark or description"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
) -> ReportListResponse:
    """
    Lists citizen reports with pagination, keyword search, and filters.
    """
    items, total = report_service.list_reports(
        db=db,
        city=city,
        status_filter=status,
        severity_filter=severity,
        query=q,
        skip=skip,
        limit=limit,
    )
    return ReportListResponse(total=total, reports=items, skip=skip, limit=limit)

@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    db: Session = Depends(get_db)
) -> ReportResponse:
    """Retrieves an individual report by its reference ID."""
    return report_service.get_report(report_id, db)

@router.patch("/{report_id}/status", response_model=ReportResponse)
def update_report_status(
    report_id: str,
    status_update: ReportStatusUpdate,
    db: Session = Depends(get_db)
) -> ReportResponse:
    """
    Updates the administrative review status of an incident report.
    Accepts: UNVERIFIED REPORT, CORROBORATED, or ADMIN-VERIFIED.
    """
    return report_service.update_status(report_id, status_update.status, db)
