"""
Unit and integration tests for Waterlogging-Aware Route Recommendations.
Validates:
- Route calculation (OSRM + deterministic fallback)
- Alternative routes generation and comparison
- Spatial hazard intersection matching against IncidentDB, ReportDB, and Mumbai rainfall warning engine
- Risk scoring, time-decay weighting, and safety recommendation categorization
- Validation of coordinates
- City-specific presets for Mumbai and Pune
- Preservation of Pune model isolation
"""

import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from app.db.models import IncidentDB, ReportDB
from app.services.routing_service import routing_service
from app.schemas.routing import LatLngPoint


class TestRoutingPresets:
    """Tests for GET /api/routes/presets."""

    def test_get_all_presets(self, client):
        response = client.get("/api/routes/presets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 4
        # Verify both Mumbai and Pune presets exist
        cities = {p["city"] for p in data}
        assert "Mumbai" in cities
        assert "Pune" in cities

    def test_get_mumbai_presets(self, client):
        response = client.get("/api/routes/presets?city=Mumbai")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert all(p["city"] == "Mumbai" for p in data)
        preset_names = [p["name"] for p in data]
        assert any("Andheri" in name for name in preset_names)

    def test_get_pune_presets(self, client):
        response = client.get("/api/routes/presets?city=Pune")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert all(p["city"] == "Pune" for p in data)
        preset_names = [p["name"] for p in data]
        assert any("Kothrud" in name for name in preset_names)


class TestRouteValidation:
    """Tests for input validation on POST /api/routes/recommendations."""

    def test_invalid_latitude_rejected(self, client):
        payload = {
            "origin": {"lat": 95.0, "lng": 72.85},  # Invalid lat > 90
            "destination": {"lat": 19.05, "lng": 72.85},
            "city": "Mumbai"
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 422

    def test_invalid_longitude_rejected(self, client):
        payload = {
            "origin": {"lat": 19.10, "lng": 185.0},  # Invalid lng > 180
            "destination": {"lat": 19.05, "lng": 72.85},
            "city": "Mumbai"
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 422

    def test_identical_origin_destination_handled(self, client):
        payload = {
            "origin": {"lat": 19.1136, "lng": 72.8697},
            "destination": {"lat": 19.1136, "lng": 72.8697},
            "city": "Mumbai"
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["routes"]) >= 1


class TestRouteRecommendations:
    """Tests for route calculations, hazard matching, and risk ranking."""

    def test_mumbai_andheri_to_bkc_recommendation(self, client):
        payload = {
            "origin": {"lat": 19.1136, "lng": 72.8697, "name": "Andheri East"},
            "destination": {"lat": 19.0657, "lng": 72.8687, "name": "BKC"},
            "city": "Mumbai",
            "tolerance_meters": 300.0,
            "prefer_alternatives": True
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "routes" in data
        assert len(data["routes"]) >= 1

        route = data["routes"][0]
        assert "route_id" in route
        assert "summary_name" in route
        assert "distance_km" in route
        assert route["distance_km"] > 0
        assert "duration_minutes" in route
        assert route["duration_minutes"] > 0
        assert "risk_score" in route
        assert "risk_category" in route
        assert route["risk_category"] in ["LOWER_KNOWN_RISK", "ELEVATED_RISK", "HIGH_HAZARD", "DATA_UNAVAILABLE"]
        assert "coordinates" in route
        assert len(route["coordinates"]) >= 2
        assert "safety_disclaimer" in data
        assert "floodwater" in data["safety_disclaimer"].lower() or "safety" in data["safety_disclaimer"].lower()

    def test_pune_route_recommendation(self, client):
        payload = {
            "origin": {"lat": 18.5314, "lng": 73.8446, "name": "Shivajinagar"},
            "destination": {"lat": 18.5074, "lng": 73.8077, "name": "Kothrud"},
            "city": "Pune",
            "tolerance_meters": 250.0
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["routes"]) >= 1
        assert data["city"] == "Pune"

    def test_hazard_intersection_with_incident_db(self, client, db_session):
        """Insert a verified incident directly on a known route point and check hazard detection."""
        now_str = datetime.now(timezone.utc).isoformat()
        incident = IncidentDB(
            id="test_hazard_inc_001",
            city="Mumbai",
            location_name="Milan Subway Waterlogging",
            latitude=19.0880,
            longitude=72.8450,
            captured_at=now_str,
            submitted_at=now_str,
            predicted_class="Flooded Scene",
            model_score=0.96,
            model_name="prithivMLmods/Flood-Image-Detection",
            verification_status="VERIFIED",
            source_type="field_responder",
            is_demo=False
        )
        db_session.add(incident)
        db_session.commit()

        # Route passing directly through (19.0950, 72.8450) to (19.0800, 72.8450)
        # Milan Subway at 19.0880 is on this exact line segment (distance = 0)
        payload = {
            "origin": {"lat": 19.0950, "lng": 72.8450, "name": "Santacruz West"},
            "destination": {"lat": 19.0800, "lng": 72.8450, "name": "Vile Parle South"},
            "city": "Mumbai",
            "tolerance_meters": 400.0
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert len(data["routes"]) >= 1
        
        # Check if the incident was matched on at least one route
        matched = False
        for route in data["routes"]:
            for h in route.get("hazards", []):
                if "Milan Subway" in h["location_name"]:
                    matched = True
                    assert h["risk_points_contributed"] > 0
                    assert h["distance_to_route_meters"] <= 400.0
                    break
        assert matched is True

    def test_stale_incident_has_reduced_weight(self, client, db_session):
        """Verify time-decay: an incident from 24 hours ago has zero or reduced impact compared to fresh one."""
        old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        stale_inc = IncidentDB(
            id="test_stale_inc_002",
            city="Mumbai",
            location_name="Old Stale Puddle",
            latitude=19.0880,
            longitude=72.8450,
            captured_at=old_time,
            submitted_at=old_time,
            predicted_class="Flooded Scene",
            model_score=0.90,
            model_name="prithivMLmods/Flood-Image-Detection",
            verification_status="VERIFIED",
            source_type="demo",
            is_demo=False
        )
        db_session.add(stale_inc)
        db_session.commit()

        payload = {
            "origin": {"lat": 19.0950, "lng": 72.8450},
            "destination": {"lat": 19.0800, "lng": 72.8450},
            "city": "Mumbai",
            "tolerance_meters": 400.0
        }
        response = client.post("/api/routes/recommendations", json=payload)
        assert response.status_code == 200
        data = response.json()
        
        for route in data["routes"]:
            for h in route.get("hazards", []):
                if "Old Stale Puddle" in h["location_name"]:
                    # Beyond 12 hours decay cutoff, risk_points_contributed should be 0.0
                    assert h["risk_points_contributed"] == 0.0

    def test_osrm_fallback_to_corridor_when_offline(self, client):
        """Simulate OSRM network outage; routing service must fallback gracefully to deterministic corridor."""
        with patch("urllib.request.urlopen", side_effect=Exception("Connection timed out")):
            payload = {
                "origin": {"lat": 19.1136, "lng": 72.8697, "name": "Andheri East"},
                "destination": {"lat": 19.0657, "lng": 72.8687, "name": "BKC"},
                "city": "Mumbai"
            }
            response = client.post("/api/routes/recommendations", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert len(data["routes"]) >= 1
            # Routes should have corridor names indicating fallback
            assert any("Route" in r["summary_name"] or "Corridor" in r["summary_name"] for r in data["routes"])
            assert data["routes"][0]["distance_km"] > 0
            assert data["routes"][0]["duration_minutes"] > 0


class TestSpatialMath:
    """Unit tests for spatial cross-track distance math."""

    def test_point_on_segment(self):
        dist = routing_service.point_to_segment_distance_meters(19.0, 72.0, 19.0, 71.0, 19.0, 73.0)
        assert dist < 1.0  # Should be practically 0

    def test_point_distance_to_polyline(self):
        polyline = [
            [19.0, 72.80],
            [19.0, 72.90]
        ]
        # Point 0.001 deg north of line (~111 meters)
        dist = routing_service.point_to_polyline_distance_meters(19.001, 72.85, polyline)
        assert 100.0 < dist < 125.0
