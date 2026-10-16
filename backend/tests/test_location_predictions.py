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
    Dadar has lower elevation (10.0m) and historical basin recurrence vs Bandra (15.0m).
    Verify that Dadar produces higher risk probability than Bandra under identical rainfall.
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
            "drainage_capacity_ratio": 0.65,
            "historical_incident_count": 3
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
            "drainage_capacity_ratio": 0.40,
            "historical_incident_count": 8
        }
    }
    resp_dadar = client.post("/api/predictions", json=req_dadar)
    assert resp_dadar.status_code == 200
    data_dadar = resp_dadar.json()

    # Bandra and Dadar must have distinct probabilities reflecting their physical terrain and drainage
    assert data_bandra["location_name"] == "Mumbai · Bandra"
    assert data_dadar["location_name"] == "Mumbai · Dadar"
    assert data_dadar["risk_probability"] > data_bandra["risk_probability"]
    assert data_dadar["details"]["elevation_m"] == 10.0
    assert data_bandra["details"]["elevation_m"] == 15.0

def test_timeline_location_consistency_and_horizon_match(client):
    """
    Test that the 6h forecast timeline for a location is location-specific,
    and that the 3h timeline entry probability matches the horizon=3 prediction.
    """
    resp_bandra_tl = client.get("/api/predictions/Mumbai/forecast?location_name=Mumbai%20%C2%B7%20Bandra&base_rainfall_mm=10.0")
    assert resp_bandra_tl.status_code == 200
    tl_bandra = resp_bandra_tl.json()

    resp_dadar_tl = client.get("/api/predictions/Mumbai/forecast?location_name=Mumbai%20%C2%B7%20Dadar&base_rainfall_mm=10.0")
    assert resp_dadar_tl.status_code == 200
    tl_dadar = resp_dadar_tl.json()

    # Dadar timeline probabilities should exceed Bandra's at each hour due to 10m vs 15m elevation
    assert len(tl_bandra["timeline"]) == 6
    assert len(tl_dadar["timeline"]) == 6
    for h in range(6):
        assert tl_dadar["timeline"][h]["risk_probability"] > tl_bandra["timeline"][h]["risk_probability"]

    # Verify that Dadar at +3h matches POST /api/predictions for Dadar at +3h
    h3_prob = tl_dadar["timeline"][2]["risk_probability"]
    req = {
        "city": "Mumbai",
        "location_name": "Dadar",
        "forecast_horizon_hours": 3,
        "features": {
            "rainfall_mm": tl_dadar["timeline"][2]["rainfall_forecast_mm"],
            "elevation_m": 10.0,
            "drainage_capacity_ratio": 0.40,
            "historical_incident_count": 8
        }
    }
    pred_resp = client.post("/api/predictions", json=req)
    assert pred_resp.status_code == 200
    assert pred_resp.json()["risk_probability"] == h3_prob
