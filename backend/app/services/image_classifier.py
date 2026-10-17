import io
import os
import logging
from typing import Dict, Any, Union, Optional
from pathlib import Path

logger = logging.getLogger("aquasignal.image_classifier")

class FloodImageClassifierService:
    """
    Singleton service for the Hugging Face Flood Image Classification Model:
    prithivMLmods/Flood-Image-Detection (SiglipForImageClassification)
    """

    MODEL_ID = "prithivMLmods/Flood-Image-Detection"
    LABELS = {0: "Flooded Scene", 1: "Non Flooded"}

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(FloodImageClassifierService, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.model = None
        self.processor = None
        self.is_loaded = False
        self.load_error = None
        self.device = "cpu"
        self._initialized = True

    def initialize(self) -> bool:
        """
        Lazily loads the pretrained Hugging Face model and processor.
        """
        if self.is_loaded:
            return True

        try:
            import torch
            from PIL import Image
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            # Select compute device (MPS for Apple Silicon, CUDA, or CPU fallback)
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"

            logger.info(f"Loading Hugging Face model '{self.MODEL_ID}' on device: {self.device}...")
            self.processor = AutoImageProcessor.from_pretrained(self.MODEL_ID)
            self.model = AutoModelForImageClassification.from_pretrained(self.MODEL_ID)
            self.model.to(self.device)
            self.model.eval()

            self.is_loaded = True
            self.load_error = None
            logger.info(f"Successfully loaded '{self.MODEL_ID}'. Labels: {self.model.config.id2label}")
            return True

        except Exception as e:
            self.load_error = str(e)
            logger.error(f"Failed to load image classifier model '{self.MODEL_ID}': {str(e)}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Returns model loading and metadata status."""
        return {
            "model_id": self.MODEL_ID,
            "is_loaded": self.is_loaded,
            "device": str(self.device),
            "supported_classes": self.LABELS,
            "load_error": self.load_error,
        }

    def classify(self, image_data: Union[bytes, str, Path]) -> Dict[str, Any]:
        """
        Executes real inference on an input image (file path or raw bytes).
        Returns predicted class, probability score, and class probabilities.
        """
        if not self.is_loaded:
            loaded = self.initialize()
            if not loaded:
                raise RuntimeError(f"Flood image classification model is not available: {self.load_error}")

        import torch
        from PIL import Image

        try:
            if isinstance(image_data, Image.Image):
                image = image_data.convert("RGB")
            elif isinstance(image_data, (str, Path)):
                if not os.path.exists(image_data):
                    raise FileNotFoundError(f"Image file not found: {image_data}")
                image = Image.open(image_data).convert("RGB")
            elif isinstance(image_data, bytes):
                image = Image.open(io.BytesIO(image_data)).convert("RGB")
            else:
                raise ValueError("image_data must be bytes, PIL.Image.Image, str path, or Path object")

            # Validate minimum dimensions
            if image.width < 16 or image.height < 16:
                raise ValueError(f"Image dimensions too small ({image.width}x{image.height}) for meaningful visual classification.")

            # Preprocess image using model's processor
            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1).squeeze().tolist()

            # Ensure probs is list if single float returned
            if isinstance(probs, float):
                probs = [probs, 1.0 - probs]

            # Label mapping from model config or fallback
            id2label = getattr(self.model.config, "id2label", None) or self.LABELS
            # Convert string keys to int if needed
            normalized_id2label = {int(k): v for k, v in id2label.items()}

            class_probs = {}
            for idx, prob in enumerate(probs):
                label_name = normalized_id2label.get(idx, f"Class_{idx}")
                class_probs[label_name] = round(float(prob), 4)

            # Determine top predicted class
            top_idx = int(torch.argmax(logits, dim=-1).item())
            predicted_label = normalized_id2label.get(top_idx, self.LABELS.get(top_idx, "Unknown"))
            top_score = class_probs.get(predicted_label, round(float(probs[top_idx]), 4))

            # Flooded scene determination
            clean_label = predicted_label.lower()
            is_flooded = ("flood" in clean_label) and ("non" not in clean_label) and ("not" not in clean_label)
            confidence = "HIGH" if top_score >= 0.80 else ("MODERATE" if top_score >= 0.60 else "LOW")

            return {
                "success": True,
                "model_name": self.MODEL_ID,
                "predicted_class": predicted_label,
                "model_score": top_score,
                "class_probabilities": class_probs,
                "is_flooded": is_flooded,
                "confidence_level": confidence,
            }

        except Exception as e:
            logger.error(f"Inference error during image classification: {str(e)}")
            raise

flood_classifier_service = FloodImageClassifierService()
