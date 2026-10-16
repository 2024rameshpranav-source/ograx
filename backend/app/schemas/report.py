from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


VALID_SEVERITIES = ["Low", "Moderate", "High", "Severe", "Critical"]
VALID_STATUSES = ["UNVERIFIED REPORT", "CORROBORATED", "ADMIN-VERIFIED"]
VALID_ACCESS = ["Passable with caution", "Not passable", "Unknown"]

class ReportCreate(BaseModel):
    id: Optional[str] = Field(None, max_length=64, description="Optional custom ID (e.g. AQ-MUM-123456)")
    city: str = Field(..., description="Target city: 'Mumbai' or 'Pune'")
    area: str = Field(..., min_length=2, max_length=128)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    landmark: str = Field(..., min_length=2, max_length=256, description="Road segment or landmark")
    severity: str = Field("Moderate", description="Observed severity: Low, Moderate, High, Severe")
    description: str = Field(..., min_length=10, max_length=1000, description="Description of waterlogging conditions")
    access: str = Field("Passable with caution", description="Road access status")
    evidenceReference: Optional[str] = Field(None, max_length=256, description="Optional evidence or photo reference")
    coordinateSource: Optional[str] = Field("area_centre", max_length=32, description="Source of coordinates: 'gps', 'manual', or 'area_centre'")
    accuracyM: Optional[float] = Field(None, ge=0.0, description="Estimated accuracy radius in metres")
    photoUrl: Optional[str] = Field(None, max_length=512, description="URL or static path to uploaded photo evidence")

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        clean = v.strip().title()
        if clean not in ["Mumbai", "Pune"]:
            raise ValueError("City must be 'Mumbai' or 'Pune'")
        return clean

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        clean = v.strip().title()
        if clean not in VALID_SEVERITIES:
            raise ValueError(f"Severity must be one of: {', '.join(VALID_SEVERITIES)}")
        return clean

    @field_validator("access")
    @classmethod
    def validate_access(cls, v: str) -> str:
        if v not in VALID_ACCESS:
            return "Passable with caution"
        return v

class ReportStatusUpdate(BaseModel):
    status: str = Field(..., description="Target status: UNVERIFIED REPORT, CORROBORATED, or ADMIN-VERIFIED")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(VALID_STATUSES)}")
        return clean

class ReportResponse(BaseModel):
    id: str
    city: str
    area: str
    latitude: float
    longitude: float
    landmark: str
    severity: str
    description: str
    access: str
    evidenceReference: Optional[str] = None
    coordinateSource: Optional[str] = "area_centre"
    accuracyM: Optional[float] = None
    photoUrl: Optional[str] = None
    status: str
    createdAt: str
    updatedAt: str

    model_config = ConfigDict(from_attributes=True)

class ReportListResponse(BaseModel):
    total: int
    reports: List[ReportResponse]
    skip: int
    limit: int
