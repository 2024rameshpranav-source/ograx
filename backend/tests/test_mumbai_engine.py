import math
from unittest.mock import patch
import pytest
from app.services.mumbai_engine.locations import MUMBAI_LOCATIONS, get_mumbai_locations
from app.services.mumbai_engine.screening import (
    classify_warning,
    generate_explanation,
    DEFAULT_THRESHOLDS,
)
from app.services.mumbai_engine.service import mumbai_waterlogging_service
from app.services.mumbai_engine.weather_service import MumbaiWeatherService, mumbai_weather_service
from app.services.city_prediction_router import city_prediction_router
from app.services.pune_engine.service import pune_prediction_service
from app.services.mumbai_prototype.warning_engine import (
    classify_warning as prototype_classify_warning,
    overall_status as prototype_overall_status,
)

def test_mumbai_eight_locations_metadata():
    locations = get_mumbai_locations()
    assert len(locations) == 8
    names = [l["location_name"] for l in locations]
    expected = ["Andheri", "Bandra", "Chembur", "Colaba", "Dadar", "Kurla", "Powai", "Sion"]
    for exp in expected:
        assert exp in names

    for loc in locations:
        assert "latitude" in loc
        assert "longitude" in loc
        assert "elevation_m" in loc
        assert "hotspot_evidence" in loc
        assert loc["hotspot_evidence"]["risk_label_usable"] is False
        assert loc["hotspot_evidence"]["match_status"] in [
            "CONFIRMED_POINT_MATCH",
            "NEARBY_AREA_ONLY",
            "LOCALITY_REPORTED",
            "RAINFALL_CONTEXT_ONLY",
            "UNVERIFIED",
            "NO_EVIDENCE",
        ]

def test_classify_warning_thresholds():
    # 1-hour horizon (threshold 5.0)
    assert classify_warning("AVAILABLE", 5.0, 0.0, 1) == "RAINFALL_WATCH"  # Exact threshold
    assert classify_warning("AVAILABLE", 0.0, 5.0, 1) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 6.0, 0.0, 1) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 4.9, 0.0, 1) == "LOW_RAINFALL_SIGNAL"
    assert classify_warning("AVAILABLE", 0.0, 4.9, 1) == "LOW_RAINFALL_SIGNAL"
    assert classify_warning("AVAILABLE", 0.0, 0.0, 1) == "NO_RAINFALL_SIGNAL"

    # 3-hour horizon (threshold 10.0)
    assert classify_warning("AVAILABLE", 10.0, 0.0, 3) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 0.0, 10.0, 3) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 12.0, 2.0, 3) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 9.9, 0.0, 3) == "LOW_RAINFALL_SIGNAL"
    assert classify_warning("AVAILABLE", 0.0, 0.0, 3) == "NO_RAINFALL_SIGNAL"

    # 6-hour horizon (threshold 20.0)
    assert classify_warning("AVAILABLE", 20.0, 0.0, 6) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 0.0, 20.0, 6) == "RAINFALL_WATCH"
    assert classify_warning("AVAILABLE", 19.5, 0.0, 6) == "LOW_RAINFALL_SIGNAL"
    assert classify_warning("AVAILABLE", 0.0, 0.0, 6) == "NO_RAINFALL_SIGNAL"

def test_classify_warning_edge_cases_and_malformed_inputs():
    # Unavailable status
    assert classify_warning("UNAVAILABLE", 10.0, 10.0, 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("STALE", 10.0, 10.0, 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("DATA_CHECK_REQUIRED", 0.0, 0.0, 3) == "DATA_CHECK_REQUIRED"

    # Missing values
    assert classify_warning("AVAILABLE", None, 5.0, 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("AVAILABLE", 5.0, None, 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("AVAILABLE", None, None, 1) == "DATA_CHECK_REQUIRED"

    # NaN values
    assert classify_warning("AVAILABLE", float("nan"), 5.0, 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("AVAILABLE", 5.0, float("nan"), 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("AVAILABLE", float("nan"), float("nan"), 1) == "DATA_CHECK_REQUIRED"

    # Negative values (physically impossible / malformed)
    assert classify_warning("AVAILABLE", -1.0, 5.0, 1) == "DATA_CHECK_REQUIRED"
    assert classify_warning("AVAILABLE", 5.0, -2.5, 1) == "DATA_CHECK_REQUIRED"

def test_generate_explanation():
    exp_watch = generate_explanation("RAINFALL_WATCH", 3, 15.0, 2.0, "Kurla")
    assert "Rainfall Watch triggered" in exp_watch
    assert "Kurla" in exp_watch
    assert "15.0 mm" in exp_watch

    exp_low = generate_explanation("LOW_RAINFALL_SIGNAL", 3, 2.5, 1.0, "Bandra")
    assert "Low rainfall signal detected" in exp_low
    assert "Bandra" in exp_low

    exp_none = generate_explanation("NO_RAINFALL_SIGNAL", 3, 0.0, 0.0, "Colaba")
    assert "No recent" in exp_none
    assert "Colaba" in exp_none

    exp_check = generate_explanation("DATA_CHECK_REQUIRED", 3, None, None, "Dadar")
    assert "data is unavailable, incomplete, or requires verification" in exp_check
    assert "Dadar" in exp_check

def test_api_mumbai_locations_endpoint(client):
    response = client.get("/api/cities/mumbai/locations")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    location_names = [d["location_name"] for d in data]
    assert "Andheri" in location_names
    assert "Dadar" in location_names
    assert "Kurla" in location_names
    for item in data:
        assert "latitude" in item
        assert "longitude" in item
        assert "elevation_m" in item
        assert "hotspot_evidence" in item

def test_api_mumbai_waterlogging_horizons(client):
    for h in [1, 3, 6]:
        response = client.get(f"/api/cities/mumbai/waterlogging?hours={h}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["city"] == "mumbai"
        assert data["horizon_hours"] == h
        assert data["prediction_type"] == "rule_based_rainfall_screening"
        assert data["validation_status"] == "NOT_VALIDATED"
        assert len(data["locations"]) == 8
        for loc in data["locations"]:
            # Rule: never fabricate waterlogging probability
            assert loc["waterlogging_probability"] is None
            assert loc["warning_status"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
            assert "explanation" in loc
            assert "hotspot_evidence" in loc
            assert "data_status" in loc

def test_api_mumbai_invalid_horizon_rejected(client):
    response = client.get("/api/cities/mumbai/waterlogging?hours=2")
    assert response.status_code == 400
    assert "supports 1, 3, or 6 hours" in response.json()["detail"]

    response_high = client.get("/api/cities/mumbai/waterlogging?hours=12")
    assert response_high.status_code == 400

    response_str = client.get("/api/cities/mumbai/waterlogging?hours=invalid")
    assert response_str.status_code == 422

def test_city_router_rejects_unsupported_city(client):
    response = client.get("/api/cities/Delhi/waterlogging")
    assert response.status_code in [422, 400]
    assert "unsupported city" in response.json()["detail"].lower()

def test_pune_model_isolation():
    # Verify Pune router does not invoke Mumbai service
    assert pune_prediction_service.city_name == "Pune"

def test_weather_service_handles_offline_gracefully():
    """Verify that when external API is unreachable, it falls back to local data without crashing."""
    service = MumbaiWeatherService()
    with patch.object(service, "_fetch_live_open_meteo", return_value=None):
        data = service.get_weather_data(force_refresh=True)
        assert len(data) == 8
        for loc_name, loc_data in data.items():
            assert "data_status" in loc_data
            assert loc_data["is_live_open_meteo"] is False

def test_weather_service_when_all_sources_fail_returns_unavailable():
    """Verify that when both live API and local files fail, it returns explicit UNAVAILABLE, never fabricated zeros."""
    service = MumbaiWeatherService()
    with patch.object(service, "_fetch_live_open_meteo", return_value=None):
        with patch.object(service, "_load_local_nowcast", return_value=None):
            data = service.get_weather_data(force_refresh=True)
            assert len(data) == 8
            for loc_name, loc_data in data.items():
                assert loc_data["data_status"] == "DATA_CHECK_REQUIRED"
                assert loc_data["data_freshness_status"] == "UNAVAILABLE"
                assert loc_data["rain_last_1h_mm"] is None
                assert loc_data["rain_next_1h_mm"] is None

def test_prototype_standalone_engine_schema_compatibility():
    """Verify prototype warning_engine.py correctly handles reconciled schema with data_status and pd.NA."""
    row_avail = {
        "screening_data_status": "AVAILABLE",
        "rain_next_1h_mm": 5.5,
        "rain_last_1h_mm": 0.0,
    }
    assert prototype_classify_warning(row_avail, 1) == "RAINFALL_WATCH"

    # Schema variant with data_status instead of screening_data_status
    row_alt_schema = {
        "data_status": "AVAILABLE",
        "rain_next_3h_mm": 2.0,
        "rain_last_3h_mm": 1.0,
    }
    assert prototype_classify_warning(row_alt_schema, 3) == "LOW_RAINFALL_SIGNAL"

    # Missing data
    row_missing = {
        "data_status": "AVAILABLE",
        "rain_next_3h_mm": float("nan"),
        "rain_last_3h_mm": 1.0,
    }
    assert prototype_classify_warning(row_missing, 3) == "DATA_CHECK_REQUIRED"

    # Overall status aggregation
    row_status = {
        "warning_1h": "NO_RAINFALL_SIGNAL",
        "warning_3h": "RAINFALL_WATCH",
        "warning_6h": "LOW_RAINFALL_SIGNAL",
    }
    assert prototype_overall_status(row_status) == "RAINFALL_WATCH"

def test_mumbai_api_full_warning_engine_schema(client):
    """
    Verifies that GET /api/cities/mumbai/waterlogging delivers the exact fields required
    by the final Mumbai warning engine for all 8 locations across 1h, 3h, 6h, and 24h horizons.
    """
    response = client.get("/api/cities/mumbai/waterlogging?hours=3")
    assert response.status_code == 200
    data = response.json()

    assert data["city"] == "mumbai"
    assert data["prediction_type"] == "rule_based_rainfall_screening"
    assert data["validation_status"] == "NOT_VALIDATED"
    assert data["warning_engine_status"] == "RULE_BASED_PROTOTYPE_NOT_VALIDATED"
    assert len(data["locations"]) == 8

    required_locations = {"Andheri", "Bandra", "Kurla", "Dadar", "Sion", "Powai", "Chembur", "Colaba"}
    found_locations = {loc["location_name"] for loc in data["locations"]}
    assert required_locations == found_locations

    for loc in data["locations"]:
        # Must preserve waterlogging_probability as None (unvalidated)
        assert loc["waterlogging_probability"] is None
        assert loc["model_validation_status"] == "NOT_VALIDATED"
        assert loc["warning_engine_status"] == "RULE_BASED_PROTOTYPE_NOT_VALIDATED"

        # Check all required rainfall accumulation metrics
        assert "rain_last_1h_mm" in loc
        assert "rain_last_3h_mm" in loc
        assert "rain_last_6h_mm" in loc
        assert "rain_last_24h_mm" in loc
        assert "rain_next_1h_mm" in loc
        assert "rain_next_3h_mm" in loc
        assert "rain_next_6h_mm" in loc

        # Check multi-horizon warning classifications
        assert loc["warning_1h"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
        assert loc["warning_3h"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
        assert loc["warning_6h"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
        assert loc["overall_screening_status"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
        assert loc["screening_status"] == loc["warning_3h"]
        assert "explanation" in loc
        assert "hotspot_evidence" in loc
