from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import json
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for the backend
BACKEND_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "AquaSignal AI Waterlogging Early-Warning Platform"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # CORS origins
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:8443",
        "http://127.0.0.1:8443",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://localhost:8001",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    # Model file paths (configurable via environment variables)
    PUNE_MODEL_PATH: str = str(BACKEND_DIR / "app" / "models" / "pune_model.joblib")

    DATABASE_URL: str = f"sqlite:///{BACKEND_DIR / 'app' / 'data' / 'aquasignal.db'}"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if v.startswith("sqlite:///./backend/"):
            clean_rel = v.replace("sqlite:///./backend/", "")
            return f"sqlite:///{BACKEND_DIR / clean_rel}"
        elif v.startswith("sqlite:///./"):
            clean_rel = v.replace("sqlite:///./", "")
            return f"sqlite:///{BACKEND_DIR / clean_rel}"
        return v

    MONGODB_URI: Optional[str] = None
    MONGODB_DB_NAME: str = "aquasignal"
    MONGODB_TIMEOUT_MS: int = 5000

    # Logging
    LOG_LEVEL: str = "INFO"

    # Photo upload configuration
    UPLOAD_DIR: str = str(BACKEND_DIR / "app" / "data" / "uploads")
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    ALLOWED_IMAGE_TYPES: List[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    ]

    # Risk thresholds for categorizing probability / severity (0.0 to 1.0 or 0 to 100)
    RISK_THRESHOLDS: Dict[str, float] = {
        "low_upper": 35.0,        # < 35% is Low
        "moderate_upper": 60.0,   # 35% - 59% is Moderate
        "high_upper": 80.0,       # 60% - 79% is High
        "critical_lower": 80.0    # >= 80% is Critical / Severe
    }

    # Geographic bounding boxes for validation
    GEO_BOUNDS: Dict[str, Dict[str, float]] = {
        "mumbai": {
            "min_lat": 18.80,
            "max_lat": 19.35,
            "min_lng": 72.70,
            "max_lng": 73.15,
        },
        "pune": {
            "min_lat": 18.35,
            "max_lat": 18.75,
            "min_lng": 73.65,
            "max_lng": 74.15,
        }
    }

    model_config = SettingsConfigDict(
        env_file=(str(BACKEND_DIR / ".env"), str(BACKEND_DIR.parent / ".env")),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
