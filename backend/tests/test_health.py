def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "AquaSignal" in data["service"]
    assert "Mumbai" in data["supported_cities"]
    assert "Pune" in data["supported_cities"]

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "models" in data
    assert "mumbai" in data["models"]
    assert "pune" in data["models"]
    assert "configured_path" in data["models"]["mumbai"]
    assert "status" in data["models"]["mumbai"]

def test_cities_endpoint(client):
    response = client.get("/api/cities")
    assert response.status_code == 200
    data = response.json()
    assert "Mumbai" in data["supported_cities"]
    assert "Pune" in data["supported_cities"]

def test_cors_headers(client):
    # Test that CORS allows request from localhost:5173
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
