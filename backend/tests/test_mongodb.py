import pytest
from unittest.mock import MagicMock, patch
from app.db.mongodb import MongoDBManager, mongo_manager
from app.db.models import ReportDB, PredictionDB, utc_now_iso
from app.db.migrate_to_mongo import migrate_sqlite_to_mongodb
from app.services.report_service import report_service
from app.schemas.report import ReportCreate

def test_placeholder_uri_detection():
    mgr = MongoDBManager()
    assert mgr.is_placeholder_uri("mongodb+srv://<USERNAME>:<PASSWORD>@cluster.mongodb.net/aquasignal") is True
    assert mgr.is_placeholder_uri("mongodb+srv://user:<PASSWORD>@cluster.mongodb.net/aquasignal") is True
    assert mgr.is_placeholder_uri("mongodb+srv://user:pass@<CLUSTER_HOST>/aquasignal") is True
    assert mgr.is_placeholder_uri("mongodb+srv://realuser:realpass@cluster0.abcde.mongodb.net/aquasignal") is False
    assert mgr.is_placeholder_uri("") is True
    assert mgr.is_placeholder_uri(None) is True

def test_ping_unconfigured():
    # Test ping response when URI is unconfigured or placeholder
    with patch.object(mongo_manager, "is_configured", return_value=False):
        result = mongo_manager.ping()
        assert result["configured"] is False
        assert result["connected"] is False
        assert result["status"] == "unconfigured_or_placeholder"
        assert "placeholders" in result["message"]

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
    # Add a sample report and prediction to SQLite
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
    db_session.add(report)
    db_session.add(pred)
    db_session.commit()

    mock_reports_col = MagicMock()
    mock_upsert_res = MagicMock()
    mock_upsert_res.upserted_id = "mock_obj_id"
    mock_reports_col.update_one.return_value = mock_upsert_res

    mock_preds_col = MagicMock()
    mock_preds_col.update_one.return_value = mock_upsert_res

    with patch.object(mongo_manager, "is_configured", return_value=True), \
         patch.object(mongo_manager, "connect", return_value=True), \
         patch.object(mongo_manager, "get_collection", side_effect=lambda name: mock_reports_col if name == "reports" else mock_preds_col), \
         patch("app.db.migrate_to_mongo.SessionLocal", return_value=db_session):

        res = migrate_sqlite_to_mongodb()
        assert res["success"] is True
        assert res["migrated_reports"] >= 1
        assert res["migrated_predictions"] >= 1

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
