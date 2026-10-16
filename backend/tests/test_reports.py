def test_create_and_get_report(client):
    report_payload = {
        "city": "Mumbai",
        "area": "Mumbai · Mithi River Demonstration Area",
        "latitude": 19.0759,
        "longitude": 72.8776,
        "landmark": "Milan Subway West Approach",
        "severity": "High",
        "description": "Water logging rapidly exceeding 1 foot depth, vehicles turning back.",
        "access": "Not passable",
    }
    response = client.post("/api/reports", json=report_payload)
    assert response.status_code == 201
    created = response.json()
    assert created["landmark"] == "Milan Subway West Approach"
    assert created["city"] == "Mumbai"
    assert created["status"] == "UNVERIFIED REPORT"
    assert created["id"].startswith("AQ-MUM-")
    report_id = created["id"]

    # Retrieve individual report
    get_resp = client.get(f"/api/reports/{report_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == report_id

def test_report_validation_errors(client):
    # Description too short
    payload = {
        "city": "Mumbai",
        "area": "Central Area",
        "latitude": 19.0,
        "longitude": 72.8,
        "landmark": "Test road",
        "description": "Short",  # < 10 chars
    }
    resp = client.post("/api/reports", json=payload)
    assert resp.status_code == 422

    # Unsupported city
    payload2 = {
        "city": "Kolkata",
        "area": "Central Area",
        "latitude": 22.5,
        "longitude": 88.3,
        "landmark": "Test road",
        "description": "Adequate length description for test.",
    }
    resp2 = client.post("/api/reports", json=payload2)
    assert resp2.status_code == 422

def test_list_reports_with_filters(client):
    # Create two reports in different cities
    client.post("/api/reports", json={
        "city": "Mumbai",
        "area": "Mithi River",
        "latitude": 19.07,
        "longitude": 72.87,
        "landmark": "Kurla Depot",
        "severity": "Moderate",
        "description": "Water overflowing storm drain along bus terminal.",
    })
    client.post("/api/reports", json={
        "city": "Pune",
        "area": "Mula-Mutha",
        "latitude": 18.53,
        "longitude": 73.87,
        "landmark": "Sangam Bridge",
        "severity": "Severe",
        "description": "Submerged footpaths near old river confluence.",
    })

    # List all
    all_resp = client.get("/api/reports")
    assert all_resp.status_code == 200
    assert all_resp.json()["total"] >= 2

    # Filter by city
    pune_resp = client.get("/api/reports?city=Pune")
    assert pune_resp.status_code == 200
    reports = pune_resp.json()["reports"]
    assert all(r["city"] == "Pune" for r in reports)

    # Search keyword
    search_resp = client.get("/api/reports?q=Sangam")
    assert search_resp.status_code == 200
    assert search_resp.json()["total"] >= 1

def test_update_report_status(client):
    created = client.post("/api/reports", json={
        "city": "Mumbai",
        "area": "Western Suburbs",
        "latitude": 19.11,
        "longitude": 72.84,
        "landmark": "Andheri Subway",
        "severity": "High",
        "description": "Water ponding under rail underpass reach.",
    }).json()

    report_id = created["id"]
    update_resp = client.patch(f"/api/reports/{report_id}/status", json={"status": "ADMIN-VERIFIED"})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "ADMIN-VERIFIED"

    # Invalid status
    invalid_resp = client.patch(f"/api/reports/{report_id}/status", json={"status": "INVALID_STATE"})
    assert invalid_resp.status_code == 422
