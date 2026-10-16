import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from fastapi import HTTPException, status
from pymongo import DESCENDING, ReturnDocument

from app.db.models import ReportDB, utc_now_iso
from app.db.mongodb import mongo_manager
from app.schemas.report import ReportCreate, ReportResponse
from app.utils.logging_config import logger

class ReportService:
    @staticmethod
    def _to_response(r: ReportDB) -> ReportResponse:
        return ReportResponse(
            id=r.id,
            city=r.city,
            area=r.area,
            latitude=r.latitude,
            longitude=r.longitude,
            landmark=r.landmark,
            severity=r.severity,
            description=r.description,
            access=r.access,
            evidenceReference=r.evidence_reference,
            coordinateSource=getattr(r, "coordinate_source", "area_centre") or "area_centre",
            accuracyM=getattr(r, "accuracy_m", None),
            photoUrl=getattr(r, "photo_url", None),
            status=r.status,
            createdAt=r.created_at,
            updatedAt=r.updated_at,
        )

    @staticmethod
    def _doc_to_response(d: Dict[str, Any]) -> ReportResponse:
        return ReportResponse(
            id=d.get("id"),
            city=d.get("city", "Mumbai"),
            area=d.get("area", ""),
            latitude=float(d.get("latitude", 0.0)),
            longitude=float(d.get("longitude", 0.0)),
            landmark=d.get("landmark", ""),
            severity=d.get("severity", "Moderate"),
            description=d.get("description", ""),
            access=d.get("access", "Normal traffic"),
            evidenceReference=d.get("evidence_reference") or d.get("evidenceReference"),
            coordinateSource=d.get("coordinate_source") or d.get("coordinateSource") or "area_centre",
            accuracyM=d.get("accuracy_m") if d.get("accuracy_m") is not None else d.get("accuracyM"),
            photoUrl=d.get("photo_url") or d.get("photoUrl"),
            status=d.get("status", "UNVERIFIED REPORT"),
            createdAt=d.get("created_at") or d.get("createdAt") or utc_now_iso(),
            updatedAt=d.get("updated_at") or d.get("updatedAt") or utc_now_iso(),
        )

    @staticmethod
    def create_report(req: ReportCreate, db: Session) -> ReportResponse:
        city_clean = req.city.strip().title()
        prefix = "MUM" if city_clean == "Mumbai" else "PUN"
        report_id = req.id if req.id else f"AQ-{prefix}-{str(int(time.time() * 1000))[-6:]}"
        now = utc_now_iso()

        # Check if MongoDB Atlas is connected and available
        reports_col = mongo_manager.get_collection("reports")
        if reports_col is not None:
            try:
                mongo_doc = {
                    "id": report_id,
                    "city": city_clean,
                    "area": req.area,
                    "latitude": req.latitude,
                    "longitude": req.longitude,
                    "location": {
                        "type": "Point",
                        "coordinates": [req.longitude, req.latitude]
                    },
                    "landmark": req.landmark,
                    "severity": req.severity,
                    "description": req.description,
                    "access": req.access,
                    "evidence_reference": req.evidenceReference,
                    "coordinate_source": req.coordinateSource or "area_centre",
                    "accuracy_m": req.accuracyM,
                    "photo_url": req.photoUrl,
                    "status": "UNVERIFIED REPORT",
                    "created_at": now,
                    "updated_at": now,
                }
                reports_col.insert_one(mongo_doc)
                logger.info(f"Report persisted to MongoDB Atlas: {report_id} ({city_clean})")

                # Also backup/mirror to SQLite for local fault tolerance
                try:
                    report_db = ReportDB(
                        id=report_id,
                        city=city_clean,
                        area=req.area,
                        latitude=req.latitude,
                        longitude=req.longitude,
                        landmark=req.landmark,
                        severity=req.severity,
                        description=req.description,
                        access=req.access,
                        evidence_reference=req.evidenceReference,
                        coordinate_source=req.coordinateSource or "area_centre",
                        accuracy_m=req.accuracyM,
                        photo_url=req.photoUrl,
                        status="UNVERIFIED REPORT",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(report_db)
                    db.commit()
                except Exception as sqle:
                    db.rollback()
                    logger.debug(f"SQLite mirror notice: {sqle}")

                return ReportService._doc_to_response(mongo_doc)
            except Exception as me:
                logger.warning(f"MongoDB Atlas write failed ({me}); falling back to SQLite.")

        # SQLite fallback
        report_db = ReportDB(
            id=report_id,
            city=city_clean,
            area=req.area,
            latitude=req.latitude,
            longitude=req.longitude,
            landmark=req.landmark,
            severity=req.severity,
            description=req.description,
            access=req.access,
            evidence_reference=req.evidenceReference,
            coordinate_source=req.coordinateSource or "area_centre",
            accuracy_m=req.accuracyM,
            photo_url=req.photoUrl,
            status="UNVERIFIED REPORT",
            created_at=now,
            updated_at=now,
        )

        try:
            db.add(report_db)
            db.commit()
            db.refresh(report_db)
            logger.info(f"Report created in SQLite: {report_id} ({city_clean})")
            return ReportService._to_response(report_db)
        except Exception as e:
            db.rollback()
            logger.error(f"Error persisting report to SQLite: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist report: {str(e)}"
            )

    @staticmethod
    def list_reports(
        db: Session,
        city: Optional[str] = None,
        status_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        query: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[ReportResponse], int]:
        reports_col = mongo_manager.get_collection("reports")
        if reports_col is not None:
            try:
                filter_dict: Dict[str, Any] = {}
                if city:
                    filter_dict["city"] = city.strip().title()

                if status_filter and status_filter != "All":
                    filter_dict["status"] = status_filter.strip()

                if severity_filter and severity_filter != "All":
                    filter_dict["severity"] = severity_filter.strip().title()

                if query and query.strip():
                    pattern = {"$regex": query.strip(), "$options": "i"}
                    filter_dict["$or"] = [
                        {"landmark": pattern},
                        {"description": pattern},
                        {"id": pattern},
                    ]

                total = reports_col.count_documents(filter_dict)
                cursor = (
                    reports_col.find(filter_dict)
                    .sort("created_at", DESCENDING)
                    .skip(skip)
                    .limit(limit)
                )
                reports = [ReportService._doc_to_response(d) for d in cursor]
                return reports, total
            except Exception as me:
                logger.warning(f"MongoDB Atlas list failed ({me}); falling back to SQLite.")

        # SQLite fallback
        q = db.query(ReportDB)

        if city:
            clean_city = city.strip().title()
            q = q.filter(ReportDB.city == clean_city)

        if status_filter and status_filter != "All":
            q = q.filter(ReportDB.status == status_filter.strip())

        if severity_filter and severity_filter != "All":
            q = q.filter(ReportDB.severity == severity_filter.strip().title())

        if query and query.strip():
            search = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    ReportDB.landmark.ilike(search),
                    ReportDB.description.ilike(search),
                    ReportDB.id.ilike(search),
                )
            )

        total = q.count()
        records = q.order_by(ReportDB.created_at.desc()).offset(skip).limit(limit).all()

        reports = [ReportService._to_response(r) for r in records]
        return reports, total

    @staticmethod
    def get_report(report_id: str, db: Session) -> ReportResponse:
        reports_col = mongo_manager.get_collection("reports")
        if reports_col is not None:
            try:
                doc = reports_col.find_one({"id": report_id})
                if doc:
                    return ReportService._doc_to_response(doc)
            except Exception as me:
                logger.warning(f"MongoDB Atlas get_report failed ({me}); checking SQLite.")

        # SQLite fallback
        record = db.query(ReportDB).filter(ReportDB.id == report_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID '{report_id}' was not found."
            )
        return ReportService._to_response(record)

    @staticmethod
    def update_status(report_id: str, new_status: str, db: Session) -> ReportResponse:
        now = utc_now_iso()
        reports_col = mongo_manager.get_collection("reports")
        mongo_updated = None

        if reports_col is not None:
            try:
                mongo_updated = reports_col.find_one_and_update(
                    {"id": report_id},
                    {"$set": {"status": new_status, "updated_at": now}},
                    return_document=ReturnDocument.AFTER
                )
            except Exception as me:
                logger.warning(f"MongoDB status update error ({me}); applying to SQLite.")

        # Also update SQLite
        record = db.query(ReportDB).filter(ReportDB.id == report_id).first()
        if record:
            record.status = new_status
            record.updated_at = now
            try:
                db.commit()
                db.refresh(record)
                logger.info(f"Report status updated in SQLite: {report_id} -> {new_status}")
            except Exception as e:
                db.rollback()
                logger.warning(f"Could not update status in SQLite: {e}")

        if mongo_updated:
            logger.info(f"Report status updated in MongoDB Atlas: {report_id} -> {new_status}")
            return ReportService._doc_to_response(mongo_updated)
        elif record:
            return ReportService._to_response(record)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID '{report_id}' was not found."
            )

report_service = ReportService()
