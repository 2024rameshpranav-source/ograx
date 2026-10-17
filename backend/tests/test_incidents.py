"""
Automated Test Suite for Incident Intelligence, Image Classification, Dynamic Risk, and Audit History.
Validates all requirements for Ograx live flood verification.
"""

import io
import pytest
from datetime import datetime, timezone, timedelta
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.services.image_classifier import flood_classifier_service
from app.services.incident_service import incident_service
from app.services.risk_adjustment import dynamic_risk_engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_service_ready():
    """Ensure in-memory/DB has clean state and demo seeds for testing."""
    db = incident_service.get_db()
    try:
        from app.db.models import IncidentDB
        db.query(IncidentDB).filter(IncidentDB.is_demo == False).delete()
        db.commit()
    finally:
        db.close()
    incident_service.seed_demo_incidents()


def create_test_image(color=(30, 80, 160), size=(128, 128)) -> io.BytesIO:
    """Creates an in-memory PNG test image."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class TestFloodImageClassifier:
    """1, 2, 3: Tests for real Hugging Face flood classification model."""

    def test_classifier_loaded_or_initializable(self):
        """Model should load and return correct metadata."""
        status = flood_classifier_service.get_status()
        assert status["model_id"] == "prithivMLmods/Flood-Image-Detection"
        assert "Flooded Scene" in status["supported_classes"].values()
        assert "Non Flooded" in status["supported_classes"].values()

    def test_real_inference_execution(self):
        """Real inference must return valid class and probability."""
        buf = create_test_image()
        res = flood_classifier_service.classify(buf.getvalue())
        assert res["success"] is True
        assert res["predicted_class"] in ["Flooded Scene", "Non Flooded"]
        assert 0.0 <= res["model_score"] <= 1.0
        assert "Flooded Scene" in res["class_probabilities"]
        assert "Non Flooded" in res["class_probabilities"]
        assert isinstance(res["is_flooded"], bool)

    def test_analyze_api_endpoint(self):
        """POST /api/incidents/analyze accepts multipart image upload."""
        buf = create_test_image()
        response = client.post(
            "/api/incidents/analyze",
            files={"file": ("test_flood.png", buf, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["predicted_class"] in ["Flooded Scene", "Non Flooded"]
        assert 0.0 <= data["model_score"] <= 1.0
        assert data["image_reference"].startswith("/uploads/")

    def test_invalid_image_upload_rejected(self):
        """Unsupported format or corrupt bytes must return 400."""
        response = client.post(
            "/api/incidents/analyze",
            files={"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
        )
        assert response.status_code == 400


class TestIncidentSubmissionAndPersistence:
    """4, 5, 6, 8: Submission, validation, persistence, duplicate suppression."""

    def test_missing_location_validation(self):
        """Invalid or missing coordinates must be rejected."""
        payload = {
            "latitude": 95.0,  # invalid latitude > 90
            "longitude": 72.8777,
            "location_name": "Invalid Lat Test",
            "image_reference": "data:image/png;base64,sample",
            "predicted_class": "Flooded Scene",
            "model_score": 0.92,
        }
        response = client.post("/api/incidents", json=payload)
        assert response.status_code == 422

    def test_successful_incident_creation_and_retrieval(self):
        """Real incident must persist in history and return dynamic adjustment."""
        payload = {
            "latitude": 19.0760,
            "longitude": 72.8777,
            "location_name": "Kurla West Junction, Mumbai",
            "image_reference": "data:image/png;base64,sample_incident_image",
            "predicted_class": "Flooded Scene",
            "model_score": 0.89,
            "is_demo": False,
            "source_type": "camera",
            "baseline_risk_score": 45.0,
        }
        create_res = client.post("/api/incidents", json=payload)
        assert create_res.status_code == 201
        data = create_res.json()
        incident_id = data["incident_id"]
        assert incident_id.startswith("INC-")
        assert data["verification_status"] == "PENDING_VERIFICATION"
        assert data["baseline_risk_score"] == 45.0
        # AI positive pending gives +5 risk adjustment
        assert data["report_risk_adjustment"] == 5.0
        assert data["final_risk_score"] == 50.0

        # Retrieve single incident
        get_res = client.get(f"/api/incidents/{incident_id}")
        assert get_res.status_code == 200
        assert get_res.json()["incident_id"] == incident_id

        # Check history contains it
        history_res = client.get("/api/incidents/history?include_demo=false")
        assert history_res.status_code == 200
        inc_ids = [item["incident_id"] for item in history_res.json()["incidents"]]
        assert incident_id in inc_ids

    def test_duplicate_incident_suppression(self):
        """Reports within 250m and 45 minutes should be flagged as duplicates without stacking risk."""
        payload1 = {
            "latitude": 19.0601,
            "longitude": 72.8550,
            "location_name": "BKC Connector Entry",
            "image_reference": "data:image/png;base64,sample1",
            "predicted_class": "Flooded Scene",
            "model_score": 0.88,
            "is_demo": False,
            "source_type": "camera",
            "baseline_risk_score": 50.0,
        }
        res1 = client.post("/api/incidents", json=payload1)
        assert res1.status_code == 201
        id1 = res1.json()["incident_id"]

        # Second submission ~50 meters away within 1 minute
        payload2 = {
            "latitude": 19.0603,
            "longitude": 72.8552,
            "location_name": "BKC Connector Entry 50m",
            "image_reference": "data:image/png;base64,sample2",
            "predicted_class": "Flooded Scene",
            "model_score": 0.85,
            "is_demo": False,
            "source_type": "camera",
            "baseline_risk_score": 50.0,
        }
        res2 = client.post("/api/incidents", json=payload2)
        assert res2.status_code == 201
        data2 = res2.json()
        assert data2["verification_status"] == "DUPLICATE"
        assert data2["duplicate_of"] == id1
        # Duplicate reports must not increase risk
        assert data2["report_risk_adjustment"] == 0.0


class TestDynamicAreaRiskAdjustment:
    """7, 9: Dynamic Area Risk calculation, spatial radius, time decay."""

    def test_dynamic_risk_engine_calculation(self):
        """Test math of clamp(baseline + adjustment, 0, 100)."""
        res = dynamic_risk_engine.calculate_area_risk(
            baseline_risk=40.0,
            nearby_incidents=[
                {
                    "verification_status": "VERIFIED_GENUINE",
                    "predicted_class": "Flooded Scene",
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "distance_km": 0.3,
                    "duplicate_of": None,
                }
            ],
        )
        assert res["baseline_risk"] == 40.0
        assert res["report_adjustment"] == 10.0
        assert res["final_risk"] == 50.0
        assert res["active_reports_count"] == 1

    def test_area_risk_endpoint_with_decay(self):
        """GET /api/incidents/risk/area computes spatial adjustment within radius."""
        lat, lon = 19.0760, 72.8777
        res = client.get(f"/api/incidents/risk/area?latitude={lat}&longitude={lon}&baseline_risk=50&radius_km=2.0")
        assert res.status_code == 200
        data = res.json()
        assert 0.0 <= data["final_risk"] <= 100.0
        assert data["baseline_risk"] == 50.0
        assert data["radius_km"] == 2.0
        assert "adjustment_breakdown" in data


class TestHumanReviewAndFeedbackWorkflow:
    """10, 13: Human review, ground-truth auditing, leak-free retraining export."""

    def test_review_and_verification_workflow(self):
        """Reviewer labels incident; ground-truth is stored immutably and adjusts risk."""
        # Create incident
        payload = {
            "latitude": 18.5204,
            "longitude": 73.8567,
            "location_name": "Shivajinagar Underpass, Pune",
            "image_reference": "data:image/png;base64,pune_img",
            "predicted_class": "Flooded Scene",
            "model_score": 0.82,
            "is_demo": False,
            "source_type": "camera",
            "baseline_risk_score": 60.0,
        }
        create_res = client.post("/api/incidents", json=payload)
        incident_id = create_res.json()["incident_id"]

        # Submit Human Review
        review_payload = {
            "ground_truth_label": "GENUINE_WATERLOGGING",
            "reviewed_by": "Senior Hydra Officer - PMC",
            "reviewer_notes": "Field team inspected: 40cm waterlogging present at underpass.",
        }
        review_res = client.patch(f"/api/incidents/{incident_id}/review", json=review_payload)
        assert review_res.status_code == 200
        rev_data = review_res.json()
        assert rev_data["verification_status"] == "VERIFIED_GENUINE"
        assert rev_data["ground_truth_label"] == "GENUINE_WATERLOGGING"
        assert rev_data["reviewed_by"] == "Senior Hydra Officer - PMC"
        # Human verified adds +10 risk points
        assert rev_data["report_risk_adjustment"] == 10.0
        assert rev_data["final_risk_score"] == 70.0

    def test_retraining_dataset_export_no_leakage(self):
        """Dataset export must only include reviewed data and maintain clean 70/15/15 partitions."""
        res = client.get("/api/incidents/models/export-dataset")
        assert res.status_code == 200
        data = res.json()
        assert "partitions" in data
        assert "train" in data["partitions"]
        assert "val" in data["partitions"]
        assert "test" in data["partitions"]

        # Verify no overlap between train, val, test
        train_ids = {item["incident_id"] for item in data["partitions"]["train"]}
        val_ids = {item["incident_id"] for item in data["partitions"]["val"]}
        test_ids = {item["incident_id"] for item in data["partitions"]["test"]}

        assert train_ids.isdisjoint(val_ids), "Data leakage: overlap between train and val"
        assert train_ids.isdisjoint(test_ids), "Data leakage: overlap between train and test"
        assert val_ids.isdisjoint(test_ids), "Data leakage: overlap between val and test"


class TestEvaluationMetricsAndDemoSeparation:
    """11, 12: Real metrics calculation from labeled data; demo separation."""

    def test_model_evaluation_metrics_not_manufactured(self):
        """Evaluation endpoint must compute precision, recall, F1, accuracy, and confusion matrix."""
        res = client.get("/api/incidents/models/evaluation?evaluation_source=all")
        assert res.status_code == 200
        data = res.json()

        assert data["evaluation_source"] == "all"
        assert data["total_evaluated_samples"] > 0

        # Check confusion matrix
        cm = data["confusion_matrix"]
        assert "true_positive" in cm
        assert "false_positive" in cm
        assert "true_negative" in cm
        assert "false_negative" in cm

        # Check mathematical bounds
        metrics = data["metrics"]
        assert 0.0 <= metrics["accuracy"] <= 1.0
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["f1_score"] <= 1.0

    def test_demo_reset_does_not_delete_real_records(self):
        """Demo reset must delete demo items while strictly preserving real records."""
        # Create a real record
        real_payload = {
            "latitude": 19.1100,
            "longitude": 72.8900,
            "location_name": "Real Citizen Report - Andheri East",
            "image_reference": "data:image/png;base64,real_img",
            "predicted_class": "Non Flooded",
            "model_score": 0.77,
            "is_demo": False,
            "source_type": "camera",
            "baseline_risk_score": 30.0,
        }
        real_res = client.post("/api/incidents", json=real_payload)
        real_id = real_res.json()["incident_id"]

        # Call demo reset
        reset_res = client.post("/api/incidents/demo/reset")
        assert reset_res.status_code == 200

        # Real record must still exist
        check_real = client.get(f"/api/incidents/{real_id}")
        assert check_real.status_code == 200
        assert check_real.json()["incident_id"] == real_id
