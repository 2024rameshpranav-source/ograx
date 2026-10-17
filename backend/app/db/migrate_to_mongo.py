"""
Safe SQLite to MongoDB Atlas Migration Utility for AquaSignal AI.
Transfers existing records from SQLite into MongoDB Atlas without deleting
or modifying the original SQLite database.
"""
import sys
import logging
from typing import Dict, Any

from app.db.session import SessionLocal, init_db
from app.db.models import ReportDB, PredictionDB, IncidentDB
from app.db.mongodb import mongo_manager
from app.utils.logging_config import logger

def migrate_sqlite_to_mongodb() -> Dict[str, Any]:
    """
    Safely exports records from SQLite and upserts them into MongoDB Atlas collections.
    Does NOT delete or modify SQLite records.
    """
    logger.info("Initiating SQLite to MongoDB Atlas migration check...")

    if not mongo_manager.is_configured():
        msg = "MongoDB Atlas is not configured. Please set a valid MONGODB_URI in backend/.env before migrating."
        logger.warning(msg)
        return {
            "success": False,
            "message": msg,
            "migrated_reports": 0,
            "migrated_predictions": 0,
        }

    # Ensure MongoDB is connected
    connected = mongo_manager.connect()
    if not connected:
        msg = f"Failed to connect to MongoDB Atlas: {mongo_manager._connection_error}"
        logger.error(msg)
        return {
            "success": False,
            "message": msg,
            "migrated_reports": 0,
            "migrated_predictions": 0,
        }

    reports_col = mongo_manager.get_collection("reports")
    predictions_col = mongo_manager.get_collection("predictions")
    incidents_col = mongo_manager.get_collection("incidents")

    if reports_col is None or predictions_col is None or incidents_col is None:
        return {
            "success": False,
            "message": "Could not access MongoDB collections.",
            "migrated_reports": 0,
            "migrated_predictions": 0,
            "migrated_incidents": 0,
        }

    # Open read-only SQLite session
    db_session = SessionLocal()
    reports_migrated = 0
    predictions_migrated = 0
    incidents_migrated = 0
    reports_existing = 0
    incidents_existing = 0

    try:
        sqlite_reports = db_session.query(ReportDB).all()
        logger.info(f"Found {len(sqlite_reports)} report(s) in SQLite database.")

        for r in sqlite_reports:
            doc = {
                "id": r.id,
                "city": r.city,
                "area": r.area,
                "latitude": float(r.latitude) if r.latitude is not None else 0.0,
                "longitude": float(r.longitude) if r.longitude is not None else 0.0,
                "location": {
                    "type": "Point",
                    "coordinates": [
                        float(r.longitude) if r.longitude is not None else 0.0,
                        float(r.latitude) if r.latitude is not None else 0.0
                    ]
                },
                "landmark": r.landmark,
                "severity": r.severity,
                "description": r.description,
                "access": r.access,
                "evidence_reference": r.evidence_reference,
                "coordinate_source": getattr(r, "coordinate_source", "area_centre") or "area_centre",
                "accuracy_m": getattr(r, "accuracy_m", None),
                "photo_url": getattr(r, "photo_url", None),
                "status": r.status,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            # Idempotent upsert: if document already exists by id, setOnInsert ensures no overwrite
            res = reports_col.update_one(
                {"id": r.id},
                {"$setOnInsert": doc},
                upsert=True
            )
            if res.upserted_id is not None:
                reports_migrated += 1
            else:
                reports_existing += 1

        sqlite_predictions = db_session.query(PredictionDB).all()
        logger.info(f"Found {len(sqlite_predictions)} prediction record(s) in SQLite database.")

        for p in sqlite_predictions:
            p_doc = {
                "city": p.city,
                "location_id": p.location_id,
                "location_name": p.location_name,
                "forecast_horizon_hours": p.forecast_horizon_hours,
                "risk_score": p.risk_score,
                "risk_category": p.risk_category,
                "model_version": p.model_version,
                "features_snapshot": p.features_snapshot,
                "created_at": p.created_at,
            }
            # Avoid duplicate prediction records with same city, location, and timestamp
            res = predictions_col.update_one(
                {"city": p.city, "location_name": p.location_name, "created_at": p.created_at},
                {"$setOnInsert": p_doc},
                upsert=True
            )
            if res.upserted_id is not None:
                predictions_migrated += 1

        sqlite_incidents = db_session.query(IncidentDB).all()
        logger.info(f"Found {len(sqlite_incidents)} incident record(s) in SQLite database.")

        for inc in sqlite_incidents:
            inc_doc = {
                "id": inc.id,
                "city": inc.city,
                "location_name": inc.location_name,
                "latitude": float(inc.latitude) if inc.latitude is not None else 0.0,
                "longitude": float(inc.longitude) if inc.longitude is not None else 0.0,
                "location": {
                    "type": "Point",
                    "coordinates": [
                        float(inc.longitude) if inc.longitude is not None else 0.0,
                        float(inc.latitude) if inc.latitude is not None else 0.0
                    ]
                },
                "captured_at": inc.captured_at,
                "submitted_at": inc.submitted_at,
                "image_reference": inc.image_reference,
                "predicted_class": inc.predicted_class,
                "model_score": float(inc.model_score) if inc.model_score is not None else 0.0,
                "model_name": inc.model_name,
                "verification_status": inc.verification_status,
                "source_type": inc.source_type,
                "is_demo": bool(inc.is_demo),
                "duplicate_of": inc.duplicate_of,
                "baseline_risk_score": float(inc.baseline_risk_score) if inc.baseline_risk_score is not None else None,
                "report_risk_adjustment": float(inc.report_risk_adjustment) if inc.report_risk_adjustment is not None else None,
                "final_risk_score": float(inc.final_risk_score) if inc.final_risk_score is not None else None,
                "ground_truth_label": inc.ground_truth_label,
                "reviewed_by": inc.reviewed_by,
                "reviewed_at": inc.reviewed_at,
                "reviewer_notes": inc.reviewer_notes,
                "created_at": inc.created_at,
                "updated_at": inc.updated_at,
            }
            res = incidents_col.update_one(
                {"id": inc.id},
                {"$setOnInsert": inc_doc},
                upsert=True
            )
            if res.upserted_id is not None:
                incidents_migrated += 1
            else:
                incidents_existing += 1

        summary = (
            f"Migration completed successfully: "
            f"Migrated {reports_migrated} new report(s) ({reports_existing} already present in Atlas); "
            f"Migrated {predictions_migrated} prediction record(s); "
            f"Migrated {incidents_migrated} incident record(s) ({incidents_existing} already present in Atlas). "
            f"Original SQLite database was safely preserved."
        )
        logger.info(summary)
        return {
            "success": True,
            "message": summary,
            "migrated_reports": reports_migrated,
            "existing_reports": reports_existing,
            "migrated_predictions": predictions_migrated,
            "migrated_incidents": incidents_migrated,
            "existing_incidents": incidents_existing,
        }

    except Exception as e:
        logger.error(f"Error during SQLite to MongoDB migration: {str(e)}")
        return {
            "success": False,
            "message": f"Migration failed with error: {str(e)}",
            "migrated_reports": reports_migrated,
            "migrated_predictions": predictions_migrated,
            "migrated_incidents": incidents_migrated,
        }
    finally:
        db_session.close()

if __name__ == "__main__":
    init_db()
    res = migrate_sqlite_to_mongodb()
    print("\n--- Migration Result ---")
    print("Success:", res["success"])
    print("Message:", res["message"])
    if not res["success"]:
        sys.exit(1)
