import pytest
from unittest.mock import MagicMock, patch
from bson import ObjectId
from app.db.mongodb import MongoDBManager, mongo_manager
from app.db.models import ReportDB, PredictionDB, IncidentDB, utc_now_iso
from app.db.migrate_to_mongo import migrate_sqlite_to_mongodb
from app.services.report_service import report_service
from app.services.incident_service import incident_service
from app.schemas.report import ReportCreate
from app.schemas.incident import IncidentCreateRequest, IncidentReviewRequest

def test_placeholder_uri_detection():
    mgr = MongoDBManager()
    assert mgr.is_placeholder_uri("mongodb+srv://<USERNAME>:<PASSWORD>@cluster.mongodb.net/aquasignal") is True
    assert mgr.is_placeholder_uri("mongodb+srv://user:<PASSWORD>@cluster.mongodb.net/aquasignal") is True
    assert mgr.is_placeholder_uri("mongodb+srv://user:pass@<CLUSTER_HOST>/aquasignal") is True
    assert mgr.is_placeholder_uri("mongodb+srv://realuser:realpass@cluster0.abcde.mongodb.net/aquasignal") is False
    assert mgr.is_placeholder_uri("") is True
    assert mgr.is_placeholder_uri(None) is True

def test_sanitize_error_redacts_credentials():
    err_with_secret = "Authentication failed for user at mongodb+srv://myuser:superSecretPassword123@cluster0.mongodb.net/db"
    sanitized = MongoDBManager.sanitize_error(err_with_secret)
    assert "superSecretPassword123" not in sanitized
    assert "myuser:***@" in sanitized

def test_ping_unconfigured():
    # Test ping response when URI is unconfigured or placeholder
    with patch.object(mongo_manager, "is_configured", return_value=False):
        result = mongo_manager.ping()
        assert result["configured"] is False
        assert result["connected"] is False
        assert result["status"] == "unconfigured_or_placeholder"
        assert "placeholders" in result["message"]

def test_ping_failure_handling():
    with patch.object(mongo_manager, "is_configured", return_value=True), \
         patch.object(mongo_manager, "connect", return_value=False):
        mongo_manager._connection_error = "mongodb+srv://admin:secretPass@cluster0.net failed: connection timed out"
        result = mongo_manager.ping()
        assert result["configured"] is True
        assert result["connected"] is False
        assert result["status"] == "connection_failed"
        assert "secretPass" not in result["message"]

def test_ping_success_mock():
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1}

    with patch.object(mongo_manager, "is_configured", return_value=True):
        mongo_manager.client = mock_client
        mongo_manager._connected = True
        result = mongo_manager.ping()
        assert result["configured"] is True
        assert result["connected"] is True
        assert result["status"] == "active"
        assert result["ping_ms"] is not None
        assert "active and healthy" in result["message"]

        # Cleanup
        mongo_manager.client = None
        mongo_manager._connected = False

def test_health_endpoint_includes_mongodb_info(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "database" in data
    assert "active_mode" in data["database"]
    assert "mongodb" in data["database"]
    assert "status" in data["database"]["mongodb"]

def test_mongodb_ping_endpoint(client):
    response = client.get("/api/health/mongodb")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert "connected" in data
    assert "database" in data

def test_sqlite_to_mongodb_migration_with_mock(db_session):
    # Add a sample report, prediction, and incident to SQLite
    now = utc_now_iso()
    report = ReportDB(
        id="AQ-MUM-999001",
        city="Mumbai",
        area="Kurla West",
        latitude=19.0657,
        longitude=72.8794,
        landmark="Near Station Bridge",
        severity="High",
        description="Water 2 feet deep near railway bridge",
        access="Vehicles stopped",
        coordinate_source="live_browser_gps",
        accuracy_m=8.5,
        photo_url="/uploads/test.jpg",
        status="UNVERIFIED REPORT",
        created_at=now,
        updated_at=now,
    )
    pred = PredictionDB(
        city="Mumbai",
        location_id="loc_1",
        location_name="Kurla West",
        forecast_horizon_hours=1,
        risk_score=78.5,
        risk_category="High",
        model_version="1.0.0",
        features_snapshot="{}",
        created_at=now,
    )
    inc = IncidentDB(
        id="INC-20261017-TEST01",
        city="Mumbai",
        location_name="Kurla Subway",
        latitude=19.0657,
        longitude=72.8794,
        captured_at=now,
        submitted_at=now,
        predicted_class="Flooded Scene",
        model_score=0.92,
        model_name="prithivMLmods/Flood-Image-Detection",
        verification_status="VERIFIED",
        source_type="live_citizen",
        is_demo=False,
    )
    db_session.add(report)
    db_session.add(pred)
    db_session.add(inc)
    db_session.commit()

    mock_col = MagicMock()
    mock_upsert_res = MagicMock()
    mock_upsert_res.upserted_id = "mock_obj_id"
    mock_col.update_one.return_value = mock_upsert_res

    with patch.object(mongo_manager, "is_configured", return_value=True), \
         patch.object(mongo_manager, "connect", return_value=True), \
         patch.object(mongo_manager, "get_collection", return_value=mock_col), \
         patch("app.db.migrate_to_mongo.SessionLocal", return_value=db_session):

        res = migrate_sqlite_to_mongodb()
        assert res["success"] is True
        assert res["migrated_reports"] >= 1
        assert res["migrated_predictions"] >= 1
        assert res["migrated_incidents"] >= 1

        # Verify SQLite still has the original records (non-destructive)
        sqlite_check = db_session.query(ReportDB).filter(ReportDB.id == "AQ-MUM-999001").first()
        assert sqlite_check is not None
        assert sqlite_check.landmark == "Near Station Bridge"

def test_report_service_writes_to_mongodb_when_active(db_session):
    mock_reports_col = MagicMock()

    with patch.object(mongo_manager, "get_collection", return_value=mock_reports_col):
        req = ReportCreate(
            city="Mumbai",
            area="Dadar",
            latitude=19.0178,
            longitude=72.8478,
            landmark="Hindmata Cinema",
            severity="Severe",
            description="Severe waterlogging, bypass road",
            access="Pedestrians only",
            coordinateSource="live_browser_gps",
            accuracyM=5.0,
            photoUrl="/uploads/photo_123.jpg",
        )

        resp = report_service.create_report(req, db_session)
        assert resp.id.startswith("AQ-MUM-")
        assert resp.city == "Mumbai"
        assert resp.severity == "Severe"
        assert resp.coordinateSource == "live_browser_gps"
        assert resp.accuracyM == 5.0
        assert resp.photoUrl == "/uploads/photo_123.jpg"

        # Verify insert_one was called on MongoDB collection
        mock_reports_col.insert_one.assert_called_once()
        inserted_doc = mock_reports_col.insert_one.call_args[0][0]
        assert inserted_doc["id"] == resp.id
        assert inserted_doc["location"]["type"] == "Point"
        assert inserted_doc["location"]["coordinates"] == [72.8478, 19.0178]

def test_report_service_reads_from_mongodb_and_strips_objectid(db_session):
    mock_reports_col = MagicMock()
    mock_doc = {
        "_id": ObjectId(),
        "id": "AQ-MUM-TEST001",
        "city": "Mumbai",
        "area": "Sion",
        "latitude": 19.0400,
        "longitude": 72.8600,
        "landmark": "Sion Circle",
        "severity": "High",
        "description": "Flooded roundabout",
        "access": "Restricted",
        "coordinate_source": "manual",
        "accuracy_m": None,
        "photo_url": None,
        "status": "VERIFIED WATERLOGGING",
        "created_at": "2026-10-17T10:00:00+00:00",
        "updated_at": "2026-10-17T10:00:00+00:00"
    }
    mock_reports_col.find_one.return_value = mock_doc

    with patch.object(mongo_manager, "get_collection", return_value=mock_reports_col):
        report = report_service.get_report("AQ-MUM-TEST001", db_session)
        assert report.id == "AQ-MUM-TEST001"
        assert report.city == "Mumbai"
        assert report.status == "VERIFIED WATERLOGGING"
        # Ensure ObjectId was not passed through into Pydantic model
        assert not hasattr(report, "_id")

def test_report_service_updates_status_in_mongodb(db_session):
    mock_reports_col = MagicMock()
    updated_doc = {
        "_id": ObjectId(),
        "id": "AQ-MUM-TEST002",
        "city": "Mumbai",
        "area": "Andheri",
        "latitude": 19.1136,
        "longitude": 72.8697,
        "landmark": "Andheri East",
        "severity": "Moderate",
        "description": "Water receded",
        "access": "Open",
        "coordinate_source": "manual",
        "accuracy_m": None,
        "photo_url": None,
        "status": "WATER RECEDED / CLEAR",
        "created_at": "2026-10-17T09:00:00+00:00",
        "updated_at": "2026-10-17T11:00:00+00:00"
    }
    mock_reports_col.find_one_and_update.return_value = updated_doc

    with patch.object(mongo_manager, "get_collection", return_value=mock_reports_col):
        res = report_service.update_status("AQ-MUM-TEST002", "WATER RECEDED / CLEAR", db_session)
        assert res.id == "AQ-MUM-TEST002"
        assert res.status == "WATER RECEDED / CLEAR"
        mock_reports_col.find_one_and_update.assert_called_once()

def test_incident_service_persists_to_mongodb_when_active():
    mock_incidents_col = MagicMock()

    with patch.object(mongo_manager, "get_collection", return_value=mock_incidents_col):
        req = IncidentCreateRequest(
            city="Mumbai",
            location_name="Milan Subway",
            latitude=19.0880,
            longitude=72.8450,
            predicted_class="Flooded Scene",
            model_score=0.95,
            source_type="field_responder",
            is_demo=False,
            notes="Field observation"
        )
        inc = incident_service.create_incident(req)
        assert inc.id.startswith("INC-")
        assert inc.city == "Mumbai"
        mock_incidents_col.insert_one.assert_called_once()
        inserted = mock_incidents_col.insert_one.call_args[0][0]
        assert inserted["id"] == inc.id
        assert inserted["location"]["coordinates"] == [72.8450, 19.0880]
