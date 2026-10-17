from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Text, DateTime, Boolean
from app.db.session import Base

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class ReportDB(Base):
    __tablename__ = "reports"

    id = Column(String(64), primary_key=True, index=True)
    city = Column(String(32), index=True, nullable=False)
    area = Column(String(128), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    landmark = Column(String(256), nullable=False)
    severity = Column(String(32), nullable=False)
    description = Column(Text, nullable=False)
    access = Column(String(64), nullable=False)
    evidence_reference = Column(String(256), nullable=True)
    coordinate_source = Column(String(32), nullable=False, default="area_centre")
    accuracy_m = Column(Float, nullable=True)
    photo_url = Column(String(512), nullable=True)
    status = Column(String(64), nullable=False, default="UNVERIFIED REPORT")
    created_at = Column(String(64), nullable=False, default=utc_now_iso)
    updated_at = Column(String(64), nullable=False, default=utc_now_iso)

class PredictionDB(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(32), index=True, nullable=False)
    location_id = Column(String(64), index=True, nullable=True)
    location_name = Column(String(256), nullable=True)
    forecast_horizon_hours = Column(Integer, nullable=False, default=1)
    risk_score = Column(Float, nullable=False)  # Stored as percentage 0.0 - 100.0
    risk_category = Column(String(32), nullable=False)
    model_version = Column(String(64), nullable=False)
    features_snapshot = Column(Text, nullable=True)  # JSON serialized features
    created_at = Column(String(64), nullable=False, default=utc_now_iso)


class IncidentDB(Base):
    __tablename__ = "incidents"

    id = Column(String(64), primary_key=True, index=True)
    city = Column(String(32), index=True, nullable=False, default="Mumbai")
    location_name = Column(String(256), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    captured_at = Column(String(64), nullable=False, default=utc_now_iso)
    submitted_at = Column(String(64), nullable=False, default=utc_now_iso)
    image_reference = Column(String(512), nullable=True)
    predicted_class = Column(String(64), nullable=False)  # "Flooded Scene" / "Non Flooded"
    model_score = Column(Float, nullable=False, default=0.0)  # 0.0 - 1.0
    model_name = Column(String(128), nullable=False, default="prithivMLmods/Flood-Image-Detection")
    verification_status = Column(String(64), nullable=False, default="PENDING")
    source_type = Column(String(64), nullable=False, default="live_citizen")  # live_citizen, camera_upload, demo, field_responder
    is_demo = Column(Boolean, nullable=False, default=False)
    duplicate_of = Column(String(64), nullable=True)
    baseline_risk_score = Column(Float, nullable=False, default=0.0)
    report_risk_adjustment = Column(Float, nullable=False, default=0.0)
    final_risk_score = Column(Float, nullable=False, default=0.0)
    ground_truth_label = Column(String(64), nullable=True)  # Flooded Scene, Non Flooded, Inconclusive
    reviewed_by = Column(String(128), nullable=True)
    reviewed_at = Column(String(64), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    created_at = Column(String(64), nullable=False, default=utc_now_iso)
    updated_at = Column(String(64), nullable=False, default=utc_now_iso)
