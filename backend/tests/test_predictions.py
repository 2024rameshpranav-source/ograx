import pytest
from app.services.model_service import model_service
from tests.conftest import MockFailingModelDouble

def test_prediction_unsupported_city(client):
    payload = {
        "city": "Delhi",
        "location_name": "Connaught Place",
        "forecast_horizon_hours": 1,
        "features": {
            "rainfall_mm": 25.0
        }
    }
    response = client.post("/api/predictions", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "Unsupported city" in str(data)

def test_prediction_missing_required_feature(client):
    payload = {
        "city": "Mumbai",
        "location_name": "Dadar",
        "features": {
            # Missing rainfall_mm
            "rainfall_intensity": 10.0
        }
    }
    response = client.post("/api/predictions", json=payload)
    assert response.status_code == 422
    assert "rainfall_mm" in str(response.json())

def test_prediction_negative_rainfall(client):
    payload = {
        "city": "Mumbai",
        "location_name": "Dadar",
        "features": {
            "rainfall_mm": -15.0
        }
    }
    response = client.post("/api/predictions", json=payload)
    assert response.status_code == 422

def test_prediction_when_model_is_missing(client):
    # Ensure Pune model is not loaded
    model_service.models["Pune"].is_loaded = False
    model_service.models["Pune"].load_error = "Model file not found"

    payload = {
        "city": "Pune",
        "location_name": "Deccan Gymkhana",
        "forecast_horizon_hours": 2,
        "features": {
            "rainfall_mm": 35.0,
            "rainfall_intensity": 12.0
        }
    }
    response = client.post("/api/predictions", json=payload)
    assert response.status_code == 503
    data = response.json()
    assert "unavailable" in data["detail"].lower()
    assert "pune" in data["detail"].lower()

def test_prediction_successful_pune_ml_model(client, mock_pune_model):
    payload = {
        "city": "pune",  # Test case normalization
        "location_id": "LOC-PUN-01",
        "location_name": "Shivajinagar Junction",
        "latitude": 18.5300,
        "longitude": 73.8500,
        "forecast_horizon_hours": 3,
        "features": {
            "rainfall_mm": 54.0,
            "rainfall_intensity": 18.0,
            "elevation_m": 555.0,
            "drainage_capacity_ratio": 0.5,
        }
    }
    response = client.post("/api/predictions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Pune"
    assert data["location_id"] == "LOC-PUN-01"
    assert data["risk_probability"] == 85.0
    assert data["risk_category"] == "Critical"
    assert data["forecast_horizon_hours"] == 3
    assert "pune_model" in data["model_id"]
    assert "prediction_timestamp" in data

    # Test latest prediction retrieval
    latest_resp = client.get("/api/predictions/Pune/latest")
    assert latest_resp.status_code == 200
    latest_data = latest_resp.json()
    assert latest_data["location_id"] == "LOC-PUN-01"
    assert latest_data["risk_probability"] == 85.0

def test_prediction_successful_mumbai_warning_engine(client):
    payload = {
        "city": "mumbai",  # Test case normalization
        "location_id": "mum_bandra",
        "location_name": "Bandra",
        "latitude": 19.0607,
        "longitude": 72.8362,
        "forecast_horizon_hours": 3,
        "features": {
            "rainfall_mm": 15.0,
        }
    }
    response = client.post("/api/predictions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Mumbai"
    assert data["location_name"] == "Bandra"
    assert data["risk_probability"] is None  # Unvalidated warning engine
    assert data["risk_category"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
    assert data["model_id"] == "mumbai_rainfall_warning_engine_v1.0"
    assert data["details"]["is_rule_based_warning_engine"] is True
    assert data["details"]["validation_status"] == "NOT_VALIDATED"

def test_prediction_handles_inference_error_gracefully(client):
    # Inject a failing model into Pune
    orig = model_service.models["Pune"].model
    orig_loaded = model_service.models["Pune"].is_loaded
    model_service.models["Pune"].model = MockFailingModelDouble()
    model_service.models["Pune"].is_loaded = True
    model_service.models["Pune"].has_predict_proba = True

    try:
        payload = {
            "city": "Pune",
            "features": {"rainfall_mm": 40.0}
        }
        response = client.post("/api/predictions", json=payload)
        assert response.status_code == 500
        assert "Inference execution failed" in response.json()["detail"]
    finally:
        model_service.models["Pune"].model = orig
        model_service.models["Pune"].is_loaded = orig_loaded

def test_get_latest_prediction_not_found(client):
    response = client.get("/api/predictions/Pune/latest")
    assert response.status_code == 404

def test_forecast_timeline_endpoint(client, mock_pune_model):
    response = client.get("/api/predictions/Pune/forecast?location_name=Deccan&base_rainfall_mm=30.0")
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Pune"
    assert data["location_name"] == "Deccan"
    assert len(data["timeline"]) == 6
    assert data["timeline"][0]["horizon_hours"] == 1
    assert data["timeline"][5]["horizon_hours"] == 6
    assert data["source"] == "model_prediction"

def test_mumbai_forecast_timeline_endpoint(client):
    response = client.get("/api/predictions/Mumbai/forecast?location_name=Bandra&base_rainfall_mm=30.0")
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Mumbai"
    assert data["location_name"] == "Bandra"
    assert len(data["timeline"]) == 6
    assert data["source"] == "mumbai_warning_engine"
    for item in data["timeline"]:
        assert item["risk_probability"] is None
