from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from pymongo import DESCENDING

from app.db.models import ReportDB, PredictionDB
from app.db.mongodb import mongo_manager
from app.schemas.analytics import (
    AnalyticsOverview,
    IncidentsAnalytics,
    LocationsAnalytics,
    LocationRiskItem,
)
from app.services.model_service import model_service
from app.utils.logging_config import logger

class AnalyticsService:
    @staticmethod
    def get_overview(city: str, db: Session) -> AnalyticsOverview:
        clean_city = model_service.normalize_city(city)

        reports_col = mongo_manager.get_collection("reports")
        predictions_col = mongo_manager.get_collection("predictions")

        if reports_col is not None and predictions_col is not None:
            try:
                # MongoDB aggregation
                total_reports = reports_col.count_documents({"city": clean_city})

                # Status aggregation
                status_pipeline = [
                    {"$match": {"city": clean_city}},
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}}
                ]
                status_counts_raw = list(reports_col.aggregate(status_pipeline))
                reports_by_status = {
                    "UNVERIFIED REPORT": 0,
                    "CORROBORATED": 0,
                    "ADMIN-VERIFIED": 0,
                }
                for s in status_counts_raw:
                    if s["_id"] in reports_by_status:
                        reports_by_status[s["_id"]] = s["count"]

                # Severity aggregation
                sev_pipeline = [
                    {"$match": {"city": clean_city}},
                    {"$group": {"_id": "$severity", "count": {"$sum": 1}}}
                ]
                sev_counts_raw = list(reports_col.aggregate(sev_pipeline))
                reports_by_severity = {
                    "Low": 0,
                    "Moderate": 0,
                    "High": 0,
                    "Severe": 0,
                }
                for sev in sev_counts_raw:
                    if sev["_id"] in reports_by_severity:
                        reports_by_severity[sev["_id"]] = sev["count"]

                # Predictions
                total_preds = predictions_col.count_documents({"city": clean_city})
                latest_pred_doc = predictions_col.find_one(
                    {"city": clean_city},
                    sort=[("created_at", DESCENDING)]
                )
                latest_dict = None
                if latest_pred_doc:
                    latest_dict = {
                        "location_name": latest_pred_doc.get("location_name"),
                        "risk_score": latest_pred_doc.get("risk_score"),
                        "risk_category": latest_pred_doc.get("risk_category"),
                        "forecast_horizon_hours": latest_pred_doc.get("forecast_horizon_hours", 1),
                        "created_at": latest_pred_doc.get("created_at"),
                    }

                return AnalyticsOverview(
                    city=clean_city,
                    total_reports=total_reports,
                    reports_by_status=reports_by_status,
                    reports_by_severity=reports_by_severity,
                    total_predictions=total_preds,
                    latest_prediction=latest_dict,
                    data_freshness_minutes=2,
                    models_status=model_service.get_status_summary(),
                )
            except Exception as me:
                logger.warning(f"MongoDB analytics aggregation error ({me}); using SQLite fallback.")

        # SQLite fallback
        total_reports = db.query(ReportDB).filter(ReportDB.city == clean_city).count()

        status_counts_raw = (
            db.query(ReportDB.status, func.count(ReportDB.id))
            .filter(ReportDB.city == clean_city)
            .group_by(ReportDB.status)
            .all()
        )
        reports_by_status = {
            "UNVERIFIED REPORT": 0,
            "CORROBORATED": 0,
            "ADMIN-VERIFIED": 0,
        }
        for s, count in status_counts_raw:
            reports_by_status[s] = count

        severity_counts_raw = (
            db.query(ReportDB.severity, func.count(ReportDB.id))
            .filter(ReportDB.city == clean_city)
            .group_by(ReportDB.severity)
            .all()
        )
        reports_by_severity = {
            "Low": 0,
            "Moderate": 0,
            "High": 0,
            "Severe": 0,
        }
        for sev, count in severity_counts_raw:
            reports_by_severity[sev] = count

        total_preds = db.query(PredictionDB).filter(PredictionDB.city == clean_city).count()
        latest_pred = (
            db.query(PredictionDB)
            .filter(PredictionDB.city == clean_city)
            .order_by(PredictionDB.id.desc())
            .first()
        )

        latest_dict = None
        if latest_pred:
            latest_dict = {
                "location_name": latest_pred.location_name,
                "risk_score": latest_pred.risk_score,
                "risk_category": latest_pred.risk_category,
                "forecast_horizon_hours": latest_pred.forecast_horizon_hours,
                "created_at": latest_pred.created_at,
            }

        return AnalyticsOverview(
            city=clean_city,
            total_reports=total_reports,
            reports_by_status=reports_by_status,
            reports_by_severity=reports_by_severity,
            total_predictions=total_preds,
            latest_prediction=latest_dict,
            data_freshness_minutes=2,
            models_status=model_service.get_status_summary(),
        )

    @staticmethod
    def get_incidents_analytics(city: str, db: Session) -> IncidentsAnalytics:
        clean_city = model_service.normalize_city(city)

        reports_col = mongo_manager.get_collection("reports")
        if reports_col is not None:
            try:
                cursor = (
                    reports_col.find({"city": clean_city})
                    .sort("created_at", DESCENDING)
                )
                reports_list = list(cursor)
                by_sev: Dict[str, int] = {}
                by_acc: Dict[str, int] = {}
                recent = []

                for r in reports_list[:5]:
                    recent.append({
                        "id": r.get("id"),
                        "landmark": r.get("landmark"),
                        "severity": r.get("severity"),
                        "status": r.get("status"),
                        "created_at": r.get("created_at"),
                    })

                for r in reports_list:
                    sev = r.get("severity", "Moderate")
                    acc = r.get("access", "Normal traffic")
                    by_sev[sev] = by_sev.get(sev, 0) + 1
                    by_acc[acc] = by_acc.get(acc, 0) + 1

                return IncidentsAnalytics(
                    city=clean_city,
                    total_incidents=len(reports_list),
                    by_severity=by_sev,
                    by_access=by_acc,
                    recent_incidents=recent,
                )
            except Exception as me:
                logger.warning(f"MongoDB incident analytics error ({me}); falling back to SQLite.")

        # SQLite fallback
        reports = db.query(ReportDB).filter(ReportDB.city == clean_city).all()
        by_sev: Dict[str, int] = {}
        by_acc: Dict[str, int] = {}

        recent = []
        for r in sorted(reports, key=lambda x: x.created_at, reverse=True)[:5]:
            recent.append({
                "id": r.id,
                "landmark": r.landmark,
                "severity": r.severity,
                "status": r.status,
                "created_at": r.created_at,
            })
            by_sev[r.severity] = by_sev.get(r.severity, 0) + 1
            by_acc[r.access] = by_acc.get(r.access, 0) + 1

        return IncidentsAnalytics(
            city=clean_city,
            total_incidents=len(reports),
            by_severity=by_sev,
            by_access=by_acc,
            recent_incidents=recent,
        )

    @staticmethod
    def get_locations_analytics(city: str, db: Session) -> LocationsAnalytics:
        clean_city = model_service.normalize_city(city)

        predictions_col = mongo_manager.get_collection("predictions")
        reports_col = mongo_manager.get_collection("reports")

        if predictions_col is not None and reports_col is not None:
            try:
                loc_names = predictions_col.distinct("location_name", {"city": clean_city})
                location_items: List[LocationRiskItem] = []

                for loc_name in loc_names:
                    if not loc_name:
                        continue
                    latest_p = predictions_col.find_one(
                        {"city": clean_city, "location_name": loc_name},
                        sort=[("created_at", DESCENDING)]
                    )
                    report_cnt = reports_col.count_documents({
                        "city": clean_city,
                        "landmark": {"$regex": loc_name, "$options": "i"}
                    })
                    if latest_p:
                        location_items.append(
                            LocationRiskItem(
                                location_id=latest_p.get("location_id"),
                                location_name=loc_name,
                                risk_score=float(latest_p.get("risk_score", 0.0)),
                                risk_category=latest_p.get("risk_category", "Low"),
                                forecast_horizon_hours=int(latest_p.get("forecast_horizon_hours", 1)),
                                last_updated=latest_p.get("created_at"),
                                report_count=report_cnt,
                            )
                        )

                return LocationsAnalytics(
                    city=clean_city,
                    total_monitored_locations=len(location_items),
                    locations=location_items,
                )
            except Exception as me:
                logger.warning(f"MongoDB locations analytics error ({me}); falling back to SQLite.")

        # SQLite fallback
        distinct_locs = (
            db.query(PredictionDB.location_name)
            .filter(PredictionDB.city == clean_city)
            .distinct()
            .all()
        )

        location_items: List[LocationRiskItem] = []
        for (loc_name,) in distinct_locs:
            if not loc_name:
                continue
            latest_p = (
                db.query(PredictionDB)
                .filter(PredictionDB.city == clean_city, PredictionDB.location_name == loc_name)
                .order_by(PredictionDB.id.desc())
                .first()
            )
            report_cnt = (
                db.query(ReportDB)
                .filter(ReportDB.city == clean_city, ReportDB.landmark.ilike(f"%{loc_name}%"))
                .count()
            )
            if latest_p:
                location_items.append(
                    LocationRiskItem(
                        location_id=latest_p.location_id,
                        location_name=loc_name,
                        risk_score=latest_p.risk_score,
                        risk_category=latest_p.risk_category,
                        forecast_horizon_hours=latest_p.forecast_horizon_hours,
                        last_updated=latest_p.created_at,
                        report_count=report_cnt,
                    )
                )

        return LocationsAnalytics(
            city=clean_city,
            total_monitored_locations=len(location_items),
            locations=location_items,
        )

analytics_service = AnalyticsService()
