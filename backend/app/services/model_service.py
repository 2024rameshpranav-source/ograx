import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from fastapi import HTTPException, status
from app.config import settings
from app.utils.logging_config import logger

class LoadedModel:
    def __init__(self, city: str, file_path: str):
        self.city: str = city
        self.file_path: str = file_path
        self.model: Any = None
        self.is_loaded: bool = False
        self.load_error: Optional[str] = None
        self.expected_features: Optional[List[str]] = None
        self.has_predict_proba: bool = False
        self.model_type: str = "unknown"
        self.version: str = "v1.0"

    def load(self) -> bool:
        """Attempts to safely load the model file using joblib or pickle."""
        path = Path(self.file_path)
        if not path.is_absolute():
            # Resolve relative to repo root or backend root
            candidate = Path.cwd() / path
            if candidate.exists():
                path = candidate

        if not path.exists():
            self.is_loaded = False
            self.load_error = f"Model file not found at: {self.file_path}"
            logger.warning(f"[{self.city}] Model file does not exist at {path}. Model-based predictions will return HTTP 503 until supplied.")
            return False

        try:
            # Check file size to avoid loading corrupted/empty files
            if path.stat().st_size == 0:
                self.is_loaded = False
                self.load_error = f"Model file at {self.file_path} is empty (0 bytes)."
                logger.error(f"[{self.city}] {self.load_error}")
                return False

            import joblib
            self.model = joblib.load(path)
            self.is_loaded = True
            self.load_error = None

            # Inspect model attributes
            if hasattr(self.model, "feature_names_in_"):
                self.expected_features = list(self.model.feature_names_in_)
            elif hasattr(self.model, "features_"):
                self.expected_features = list(self.model.features_)

            if hasattr(self.model, "predict_proba"):
                self.has_predict_proba = True
                self.model_type = "classifier"
            elif hasattr(self.model, "predict"):
                self.model_type = "regressor_or_classifier"

            logger.info(f"[{self.city}] Successfully loaded model from {path} (type: {self.model_type}, features: {self.expected_features})")
            return True

        except Exception as e:
            self.is_loaded = False
            self.model = None
            self.load_error = f"Failed to load model file: {str(e)}"
            logger.error(f"[{self.city}] Error loading model from {path}: {str(e)}")
            return False

    def predict(self, input_df: Any) -> Tuple[float, Dict[str, Any]]:
        """
        Executes model prediction on input DataFrame.
        Returns:
            probability_pct: float (0.0 to 100.0)
            meta: Dict[str, Any] detailing output
        """
        if not self.is_loaded or self.model is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{self.city} model is unavailable: {self.load_error or 'Model not loaded'}. Please place the trained model artifact at '{self.file_path}'."
            )

        try:
            if self.has_predict_proba:
                proba = self.model.predict_proba(input_df)
                # Usually binary classification where index 1 is probability of waterlogging
                if len(proba.shape) == 2 and proba.shape[1] >= 2:
                    raw_prob = float(proba[0][1])
                else:
                    raw_prob = float(proba[0][0])
                prob_pct = max(0.0, min(100.0, raw_prob * 100.0))
                return prob_pct, {"output_type": "probability", "raw_value": raw_prob}

            elif hasattr(self.model, "predict"):
                raw_pred = self.model.predict(input_df)
                raw_val = float(raw_pred[0])
                # Normalize raw prediction: if between 0 and 1 treat as probability, else cap at 100
                if 0.0 <= raw_val <= 1.0:
                    prob_pct = raw_val * 100.0
                else:
                    prob_pct = max(0.0, min(100.0, raw_val))
                return prob_pct, {"output_type": "continuous_score", "raw_value": raw_val}

            else:
                raise ValueError("Loaded model object does not implement predict or predict_proba methods.")

        except Exception as e:
            logger.error(f"[{self.city}] Model inference execution error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Inference execution failed for {self.city} model: {str(e)}"
            )

SUPPORTED_CITIES = ["Mumbai", "Pune"]

class ModelService:
    _instance = None

    def __init__(self):
        # Pune operates via trained ML model. Mumbai operates via dedicated rule-based warning engine.
        self.models: Dict[str, LoadedModel] = {
            "Pune": LoadedModel("Pune", settings.PUNE_MODEL_PATH),
        }

    @classmethod
    def get_instance(cls) -> "ModelService":
        if cls._instance is None:
            cls._instance = ModelService()
        return cls._instance

    def initialize_models(self):
        """Loads all configured machine learning models once at application startup."""
        logger.info("Initializing ML model registry for AquaSignal...")
        for city, model_wrapper in self.models.items():
            model_wrapper.load()

    def normalize_city(self, city: str) -> str:
        clean = city.strip().title()
        if clean not in SUPPORTED_CITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported city '{city}'. AquaSignal currently supports: {', '.join(SUPPORTED_CITIES)}"
            )
        return clean

    def get_model(self, city: str) -> LoadedModel:
        normalized = self.normalize_city(city)
        if normalized not in self.models:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"City '{normalized}' is powered by the rule-based warning engine, not a joblib ML model."
            )
        return self.models[normalized]

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides status breakdown for health check endpoint."""
        summary = {}
        # Mumbai rule-based screening engine status
        summary["mumbai"] = {
            "city": "Mumbai",
            "loaded": True,
            "configured_path": "backend/app/services/mumbai_engine",
            "engine_type": "rule_based_rainfall_warning_engine",
            "model_type": "rainfall_screening_engine",
            "validation_status": "NOT_VALIDATED",
            "status": "ready (rule-based warning engine)",
        }
        # Pune machine learning model status
        for city, model_wrapper in self.models.items():
            summary[city.lower()] = {
                "city": city,
                "loaded": model_wrapper.is_loaded,
                "configured_path": model_wrapper.file_path,
                "model_type": model_wrapper.model_type,
                "expected_features": model_wrapper.expected_features,
                "status": "ready" if model_wrapper.is_loaded else (model_wrapper.load_error or "Not loaded")
            }
        return summary

model_service = ModelService.get_instance()
