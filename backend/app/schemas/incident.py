from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class IncidentAnalyzeResponse(BaseModel):
    success: bool = True
    model_name: str = "prithivMLmods/Flood-Image-Detection"
    predicted_class: str = Field(..., description="'Flooded Scene' or 'Non Flooded'")
    model_score: float = Field(..., description="Classification probability score between 0.0 and 1.0")
    class_probabilities: Dict[str, float] = Field(..., description="Probabilities for each class")
    is_flooded: bool = Field(..., description="True if predicted class is Flooded Scene")
    confidence_level: str = Field(..., description="HIGH, MODERATE, or LOW")
    image_reference: Optional[str] = None
    warning_note: Optional[str] = None

class IncidentCreateRequest(BaseModel):
    city: str = Field("Mumbai", description="City name, e.g. Mumbai or Pune")
    location_name: str = Field(..., description="Corridor, ward, or street landmark name")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    captured_at: Optional[str] = None
    image_reference: Optional[str] = None
    predicted_class: str = Field(..., description="'Flooded Scene' or 'Non Flooded'")
    model_score: float = Field(..., ge=0.0, le=1.0)
    source_type: str = Field("live_citizen", description="live_citizen, camera_upload, demo, field_responder")
    is_demo: bool = Field(False, description="True for synthetic demo records")
    baseline_risk_score: Optional[float] = None
    notes: Optional[str] = None

class IncidentReviewRequest(BaseModel):
    verification_status: Optional[str] = Field(None, description="VERIFIED_GENUINE, VERIFIED_NON_WATERLOGGING, INCONCLUSIVE, REJECTED, DUPLICATE")
    ground_truth_label: Optional[str] = Field(None, description="Flooded Scene, Non Flooded, Inconclusive, GENUINE_WATERLOGGING, NON_WATERLOGGING")
    reviewed_by: str = Field(..., description="Reviewer name, badge, or identifier")
    reviewer_notes: Optional[str] = None

class IncidentResponse(BaseModel):
    id: str
    incident_id: Optional[str] = None
    city: str
    location_name: str
    latitude: float
    longitude: float
    captured_at: str
    submitted_at: str
    image_reference: Optional[str]
    predicted_class: str
    model_score: float
    model_name: str
    verification_status: str
    source_type: str
    is_demo: bool
    duplicate_of: Optional[str]
    baseline_risk_score: float
    report_risk_adjustment: float
    final_risk_score: float
    ground_truth_label: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    reviewer_notes: Optional[str]
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)

    def model_post_init(self, __context: Any) -> None:
        if self.incident_id is None:
            self.incident_id = self.id

class DynamicRiskResponse(BaseModel):
    city: str
    location_name: str
    latitude: float
    longitude: float
    baseline_risk_score: float
    report_risk_adjustment: float
    final_risk_score: float
    baseline_risk: Optional[float] = None
    report_adjustment: Optional[float] = None
    final_risk: Optional[float] = None
    adjustment_breakdown: Optional[str] = None
    active_incidents_count: int
    verified_genuine_count: int
    pending_ai_positive_count: int
    calculation_basis: str
    radius_km: float

    def model_post_init(self, __context: Any) -> None:
        if self.final_risk is None:
            self.final_risk = self.final_risk_score
        if self.baseline_risk is None:
            self.baseline_risk = self.baseline_risk_score
        if self.report_adjustment is None:
            self.report_adjustment = self.report_risk_adjustment
        if self.adjustment_breakdown is None:
            self.adjustment_breakdown = self.calculation_basis

class ConfusionMatrix(BaseModel):
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

class ModelEvaluationResponse(BaseModel):
    model_name: str = "prithivMLmods/Flood-Image-Detection"
    model_architecture: str = "SiglipForImageClassification"
    evaluation_status: str
    evaluation_source: Optional[str] = "all"
    dataset_type: str  # real_ground_truth or demo_benchmark
    dataset_version: str
    total_samples: int
    total_evaluated_samples: Optional[int] = None
    labeled_samples: int
    confusion_matrix: ConfusionMatrix
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    metrics: Optional[Dict[str, Any]] = None
    disclaimer: str

    def model_post_init(self, __context: Any) -> None:
        if self.total_evaluated_samples is None:
            self.total_evaluated_samples = self.labeled_samples
        if self.metrics is None:
            self.metrics = {
                "accuracy": self.accuracy if self.accuracy is not None else 0.0,
                "precision": self.precision if self.precision is not None else 0.0,
                "recall": self.recall if self.recall is not None else 0.0,
                "f1_score": self.f1_score if self.f1_score is not None else 0.0,
            }

class DemoSummaryResponse(BaseModel):
    total_incidents: int
    real_incidents_count: int
    demo_incidents_count: int
    verified_genuine_count: int
    verified_non_waterlogging_count: int
    pending_verification_count: int
    rejected_or_duplicate_count: int
    last_seeded_at: Optional[str] = None
    is_demo_mode_active: bool = True
