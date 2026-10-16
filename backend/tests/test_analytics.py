def test_analytics_overview_empty(client):
    response = client.get("/api/analytics/overview?city=Mumbai")
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Mumbai"
    assert data["total_reports"] == 0
    assert data["total_predictions"] == 0
    assert data["latest_prediction"] is None
    assert "models_status" in data

def test_analytics_overview_populated(client, mock_mumbai_model):
    # Add a report
    client.post("/api/reports", json={
        "city": "Mumbai",
        "area": "Mithi River Area",
        "latitude": 19.07,
        "longitude": 72.87,
        "landmark": "Dharavi Junction",
        "severity": "Moderate",
        "description": "Standing water across 2 traffic lanes.",
    })

    # Add a prediction
    client.post("/api/predictions", json={
        "city": "Mumbai",
        "location_id": "LOC-01",
        "location_name": "Dharavi Junction",
        "forecast_horizon_hours": 2,
        "features": {"rainfall_mm": 35.0}
    })

    response = client.get("/api/analytics/overview?city=Mumbai")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reports"] == 1
    assert data["reports_by_severity"]["Moderate"] == 1
    assert data["total_predictions"] == 1
    assert data["latest_prediction"] is not None
    assert data["latest_prediction"]["location_name"] == "Dharavi Junction"

def test_analytics_incidents(client):
    client.post("/api/reports", json={
        "city": "Pune",
        "area": "Central Pune",
        "latitude": 18.52,
        "longitude": 73.85,
        "landmark": "Alka Talkies Chowk",
        "severity": "Severe",
        "description": "Severe flooding blocking road passage completely.",
        "access": "Not passable",
    })

    response = client.get("/api/analytics/incidents?city=Pune")
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Pune"
    assert data["total_incidents"] == 1
    assert data["by_severity"]["Severe"] == 1
    assert data["by_access"]["Not passable"] == 1

def test_analytics_locations(client, mock_mumbai_model):
    client.post("/api/predictions", json={
        "city": "Mumbai",
        "location_id": "LOC-HND",
        "location_name": "Hindmata Flyover",
        "forecast_horizon_hours": 3,
        "features": {"rainfall_mm": 60.0}
    })

    response = client.get("/api/analytics/locations?city=Mumbai")
    assert response.status_code == 200
    data = response.json()
    assert data["city"] == "Mumbai"
    assert data["total_monitored_locations"] >= 1
    loc = next((l for l in data["locations"] if l["location_name"] == "Hindmata Flyover"), None)
    assert loc is not None
    assert loc["location_id"] == "LOC-HND"
