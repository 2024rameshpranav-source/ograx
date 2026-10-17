import pytest
from app.services.city_prediction_router import city_prediction_router
from app.services.mumbai_engine.locations import get_mumbai_locations
from app.schemas.prediction import PredictionRequest, PredictionInputFeatures

def test_match_mumbai_location_by_id():
    locations = get_mumbai_locations()
    bandra = city_prediction_router.match_mumbai_location(locations, location_id="BND-01")
    assert bandra["location_name"] == "Bandra"

    dadar = city_prediction_router.match_mumbai_location(locations, location_id="DAD-02")
    assert dadar["location_name"] == "Dadar"

    kurla = city_prediction_router.match_mumbai_location(locations, location_id="KRL-05")
    assert kurla["location_name"] == "Kurla"

def test_match_mumbai_location_by_area_name_and_substring():
    locations = get_mumbai_locations()
    # "Mumbai · Bandra"
    bnd = city_prediction_router.match_mumbai_location(locations, location_name="Mumbai · Bandra")
    assert bnd["location_name"] == "Bandra"

    # "Mumbai · Dadar"
    dad = city_prediction_router.match_mumbai_location(locations, location_name="Mumbai · Dadar")
    assert dad["location_name"] == "Dadar"

    # "Dadar - Hindmata Flyover"
    hindmata = city_prediction_router.match_mumbai_location(locations, location_name="Dadar - Hindmata Flyover")
    assert hindmata["location_name"] == "Dadar"

def test_match_mumbai_location_by_coordinates():
    locations = get_mumbai_locations()
    # Near Dadar coordinates (19.0178, 72.8478)
    near_dadar = city_prediction_router.match_mumbai_location(locations, latitude=19.0185, longitude=72.8430)
    assert near_dadar["location_name"] == "Dadar"

    # Near Bandra coordinates (19.0607, 72.8362)
    near_bandra = city_prediction_router.match_mumbai_location(locations, latitude=19.0610, longitude=72.8370)
    assert near_bandra["location_name"] == "Bandra"

def test_bandra_and_dadar_distinct_predictions_when_inputs_differ(client):
    """
    Verify that Bandra and Dadar produce distinct location metadata, elevations,
    and valid screening engine warning statuses without fabricated probabilities.
    """
    req_bandra = {
        "city": "Mumbai",
        "location_id": "BND-01",
        "location_name": "Mumbai · Bandra",
        "latitude": 19.0607,
        "longitude": 72.8362,
        "forecast_horizon_hours": 3,
        "features": {
            "rainfall_mm": 15.0,
            "elevation_m": 15.0,
        }
    }
    resp_bandra = client.post("/api/predictions", json=req_bandra)
    assert resp_bandra.status_code == 200
    data_bandra = resp_bandra.json()

    req_dadar = {
        "city": "Mumbai",
        "location_id": "DAD-01",
        "location_name": "Mumbai · Dadar",
        "latitude": 19.0178,
        "longitude": 72.8478,
        "forecast_horizon_hours": 3,
        "features": {
            "rainfall_mm": 15.0,
            "elevation_m": 10.0,
        }
    }
    resp_dadar = client.post("/api/predictions", json=req_dadar)
    assert resp_dadar.status_code == 200
    data_dadar = resp_dadar.json()

    # Bandra and Dadar must have distinct locations, coordinates, and elevations
    assert data_bandra["location_name"] == "Bandra" or "Bandra" in data_bandra["location_name"]
    assert data_dadar["location_name"] == "Dadar" or "Dadar" in data_dadar["location_name"]
    assert data_dadar["details"]["elevation_m"] == 10.0
    assert data_bandra["details"]["elevation_m"] == 15.0
    # Probabilities must be None (unvalidated warning engine)
    assert data_bandra["risk_probability"] is None
    assert data_dadar["risk_probability"] is None
    assert data_bandra["risk_category"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]
    assert data_dadar["risk_category"] in ["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"]

def test_timeline_location_consistency_and_horizon_match(client):
    """
    Test that the 6h forecast timeline for a location is location-specific,
    and returns valid warning engine statuses without fabricated probabilities.
    """
    resp_bandra_tl = client.get("/api/predictions/Mumbai/forecast?location_name=Mumbai%20%C2%B7%20Bandra&base_rainfall_mm=10.0")
    assert resp_bandra_tl.status_code == 200
    tl_bandra = resp_bandra_tl.json()

    resp_dadar_tl = client.get("/api/predictions/Mumbai/forecast?location_name=Mumbai%20%C2%B7%20Dadar&base_rainfall_mm=10.0")
    assert resp_dadar_tl.status_code == 200
    tl_dadar = resp_dadar_tl.json()

    assert len(tl_bandra["timeline"]) == 6
    assert len(tl_dadar["timeline"]) == 6
    assert tl_bandra["location_name"] == "Bandra"
    assert tl_dadar["location_name"] == "Dadar"

    for h in range(6):
        assert tl_dadar["timeline"][h]["risk_probability"] is None
        assert tl_bandra["timeline"][h]["risk_probability"] is None
        assert tl_dadar["timeline"][h]["risk_category"] in [
            "NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"
        ]

    # Verify that Dadar at +3h matches POST /api/predictions for Dadar at +3h
    req = {
        "city": "Mumbai",
        "location_name": "Dadar",
        "forecast_horizon_hours": 3,
        "features": {
            "rainfall_mm": 10.0,
        }
    }
    pred_resp = client.post("/api/predictions", json=req)
    assert pred_resp.status_code == 200
    assert pred_resp.json()["risk_probability"] is None
    assert pred_resp.json()["risk_category"] == tl_dadar["timeline"][2]["risk_category"]
