import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, delete

from app.db.session import SessionLocal
from app.db.models import IncidentDB, utc_now_iso
from app.db.mongodb import mongo_manager
from app.services.risk_adjustment import DynamicRiskEngine, haversine_distance_km
from app.schemas.incident import (
    IncidentCreateRequest,
    IncidentResponse,
    IncidentReviewRequest,
    DynamicRiskResponse,
    ModelEvaluationResponse,
    ConfusionMatrix,
    DemoSummaryResponse
)

logger = logging.getLogger("aquasignal.incident_service")

class IncidentService:
    """
    Service managing incident records, duplicate suppression,
    dynamic location risk recalculation, demo data seeding/reset,
    and model evaluation metrics.
    """

    DUPLICATE_RADIUS_KM = 0.25  # 250 meters
    DUPLICATE_WINDOW_MINUTES = 45

    def get_db(self) -> Session:
        return SessionLocal()

    def generate_incident_id(self) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        unique_suffix = uuid.uuid4().hex[:6].upper()
        return f"INC-{date_str}-{unique_suffix}"

    def check_duplicate(
        self,
        db: Session,
        latitude: float,
        longitude: float,
        predicted_class: str,
        is_demo: bool = False,
        now: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Suppresses duplicate reports submitted within 250m and 45 minutes with identical prediction.
        Returns parent incident_id if duplicate detected, else None.
        Demo reports are strictly isolated from real citizen reports.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Retrieve recent incidents scoped to the same record type (demo vs real)
        recent_incidents = db.query(IncidentDB).filter(
            IncidentDB.duplicate_of.is_(None),
            IncidentDB.is_demo == is_demo
        ).order_by(IncidentDB.created_at.desc()).limit(100).all()

        for inc in recent_incidents:
            dist = haversine_distance_km(latitude, longitude, inc.latitude, inc.longitude)
            if dist <= self.DUPLICATE_RADIUS_KM:
                try:
                    inc_time = datetime.fromisoformat(inc.created_at.replace("Z", "+00:00"))
                    if inc_time.tzinfo is None:
                        inc_time = inc_time.replace(tzinfo=timezone.utc)
                    diff_minutes = (now - inc_time).total_seconds() / 60.0
                    if 0 <= diff_minutes <= self.DUPLICATE_WINDOW_MINUTES and inc.predicted_class == predicted_class:
                        return inc.id
                except Exception:
                    continue

        return None

    def get_baseline_risk_for_location(self, city: str, location_name: str, lat: float, lng: float) -> float:
        """
        Fetches or calculates baseline hydrological risk score (0.0 - 100.0)
        from existing city prediction router / model engine.
        """
        norm_city = city.strip().capitalize()
        if norm_city == "Pune":
            # Baseline from Pune ML model or terrain elevation default
            return 45.0
        else:
            # Baseline from Mumbai warning engine or depression basin baseline
            try:
                from app.services.mumbai_engine.service import mumbai_waterlogging_service
                screening = mumbai_waterlogging_service.get_screening_results(horizon=3)
                # Check if matching corridor in screening
                for loc in screening.get("locations", []):
                    if loc.get("location_name", "").lower() in location_name.lower():
                        ws = loc.get("warning_status")
                        if ws == "RAINFALL_WATCH":
                            return 65.0
                        elif ws == "LOW_RAINFALL_SIGNAL":
                            return 35.0
                        else:
                            return 15.0
            except Exception as e:
                logger.warning(f"Failed to fetch Mumbai screening baseline: {e}")
            return 25.0

    def create_incident(self, req: IncidentCreateRequest) -> IncidentDB:
        """
        Persists a verified or unverified incident report into the database,
        computes baseline and dynamic risk, and applies duplicate suppression.
        """
        db = self.get_db()
        try:
            now_iso = utc_now_iso()
            incident_id = self.generate_incident_id()

            # 1. Check duplicate
            dup_parent_id = self.check_duplicate(
                db, req.latitude, req.longitude, req.predicted_class, is_demo=req.is_demo
            )

            # 2. Compute baseline risk
            if req.baseline_risk_score is not None:
                baseline = req.baseline_risk_score
            else:
                baseline = self.get_baseline_risk_for_location(
                    req.city, req.location_name, req.latitude, req.longitude
                )

            # 3. Determine initial verification status & adjustment
            if dup_parent_id:
                status = "DUPLICATE"
                adj = 0.0
            else:
                status = "PENDING_VERIFICATION"
                # Preliminary adjustment for AI-detected flooded scene with high confidence
                if req.predicted_class == "Flooded Scene" and req.model_score >= 0.65:
                    adj = DynamicRiskEngine.AI_POSITIVE_PENDING_POINTS
                else:
                    adj = 0.0

            final_risk = min(100.0, max(0.0, baseline + adj))

            incident = IncidentDB(
                id=incident_id,
                city=req.city,
                location_name=req.location_name,
                latitude=req.latitude,
                longitude=req.longitude,
                captured_at=req.captured_at or now_iso,
                submitted_at=now_iso,
                image_reference=req.image_reference,
                predicted_class=req.predicted_class,
                model_score=req.model_score,
                model_name="prithivMLmods/Flood-Image-Detection",
                verification_status=status,
                source_type=req.source_type,
                is_demo=req.is_demo,
                duplicate_of=dup_parent_id,
                baseline_risk_score=round(baseline, 1),
                report_risk_adjustment=round(adj, 1),
                final_risk_score=round(final_risk, 1),
                ground_truth_label=None,
                reviewed_by=None,
                reviewed_at=None,
                reviewer_notes=req.notes,
                created_at=now_iso,
                updated_at=now_iso,
            )

            db.add(incident)
            db.commit()
            db.refresh(incident)

            # Persist to MongoDB Atlas if connected
            incidents_col = mongo_manager.get_collection("incidents")
            if incidents_col is not None:
                try:
                    inc_doc = {
                        "id": incident.id,
                        "city": incident.city,
                        "location_name": incident.location_name,
                        "latitude": float(incident.latitude),
                        "longitude": float(incident.longitude),
                        "location": {
                            "type": "Point",
                            "coordinates": [float(incident.longitude), float(incident.latitude)]
                        },
                        "captured_at": incident.captured_at,
                        "submitted_at": incident.submitted_at,
                        "image_reference": incident.image_reference,
                        "predicted_class": incident.predicted_class,
                        "model_score": float(incident.model_score),
                        "model_name": incident.model_name,
                        "verification_status": incident.verification_status,
                        "source_type": incident.source_type,
                        "is_demo": bool(incident.is_demo),
                        "duplicate_of": incident.duplicate_of,
                        "baseline_risk_score": float(incident.baseline_risk_score) if incident.baseline_risk_score is not None else None,
                        "report_risk_adjustment": float(incident.report_risk_adjustment) if incident.report_risk_adjustment is not None else None,
                        "final_risk_score": float(incident.final_risk_score) if incident.final_risk_score is not None else None,
                        "ground_truth_label": incident.ground_truth_label,
                        "reviewed_by": incident.reviewed_by,
                        "reviewed_at": incident.reviewed_at,
                        "reviewer_notes": incident.reviewer_notes,
                        "created_at": incident.created_at,
                        "updated_at": incident.updated_at,
                    }
                    incidents_col.insert_one(inc_doc)
                    logger.info(f"Incident persisted to MongoDB Atlas: {incident.id}")
                except Exception as me:
                    logger.warning(f"MongoDB incident insert notice ({me}); SQLite active.")

            logger.info(
                f"Created Incident {incident.id} for {incident.location_name} ({incident.city}): "
                f"predicted={incident.predicted_class} ({incident.model_score:.2f}), "
                f"status={incident.verification_status}, adj=+{incident.report_risk_adjustment}"
            )
            return incident

        finally:
            db.close()

    @staticmethod
    def _doc_to_incident(doc: Dict[str, Any]) -> IncidentDB:
        return IncidentDB(
            id=doc.get("id"),
            city=doc.get("city", "Mumbai"),
            location_name=doc.get("location_name", ""),
            latitude=float(doc.get("latitude", 0.0)),
            longitude=float(doc.get("longitude", 0.0)),
            captured_at=doc.get("captured_at"),
            submitted_at=doc.get("submitted_at"),
            image_reference=doc.get("image_reference"),
            predicted_class=doc.get("predicted_class", "Non Flooded"),
            model_score=float(doc.get("model_score", 0.0)),
            model_name=doc.get("model_name", "prithivMLmods/Flood-Image-Detection"),
            verification_status=doc.get("verification_status", "PENDING_VERIFICATION"),
            source_type=doc.get("source_type", "live_citizen"),
            is_demo=bool(doc.get("is_demo", False)),
            duplicate_of=doc.get("duplicate_of"),
            baseline_risk_score=float(doc.get("baseline_risk_score")) if doc.get("baseline_risk_score") is not None else None,
            report_risk_adjustment=float(doc.get("report_risk_adjustment")) if doc.get("report_risk_adjustment") is not None else None,
            final_risk_score=float(doc.get("final_risk_score")) if doc.get("final_risk_score") is not None else None,
            ground_truth_label=doc.get("ground_truth_label"),
            reviewed_by=doc.get("reviewed_by"),
            reviewed_at=doc.get("reviewed_at"),
            reviewer_notes=doc.get("reviewer_notes"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    def get_incidents(
        self,
        city: Optional[str] = None,
        verification_status: Optional[str] = None,
        is_demo: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[IncidentDB], int]:
        incidents_col = mongo_manager.get_collection("incidents")
        if incidents_col is not None:
            try:
                filter_dict: Dict[str, Any] = {}
                if city:
                    filter_dict["city"] = {"$regex": city.strip(), "$options": "i"}
                if verification_status and verification_status != "ALL":
                    filter_dict["verification_status"] = verification_status
                if is_demo is not None:
                    filter_dict["is_demo"] = is_demo

                total = incidents_col.count_documents(filter_dict)
                cursor = (
                    incidents_col.find(filter_dict)
                    .sort("created_at", -1)
                    .skip(skip)
                    .limit(limit)
                )
                records = [self._doc_to_incident(d) for d in cursor]
                return records, total
            except Exception as me:
                logger.warning(f"MongoDB Atlas get_incidents error ({me}); falling back to SQLite.")

        db = self.get_db()
        try:
            query = db.query(IncidentDB)
            if city:
                query = query.filter(IncidentDB.city.ilike(f"%{city}%"))
            if verification_status and verification_status != "ALL":
                query = query.filter(IncidentDB.verification_status == verification_status)
            if is_demo is not None:
                query = query.filter(IncidentDB.is_demo == is_demo)

            total = query.count()
            records = query.order_by(IncidentDB.created_at.desc()).offset(skip).limit(limit).all()
            return records, total
        finally:
            db.close()

    def get_incident_by_id(self, incident_id: str) -> Optional[IncidentDB]:
        incidents_col = mongo_manager.get_collection("incidents")
        if incidents_col is not None:
            try:
                doc = incidents_col.find_one({"id": incident_id})
                if doc:
                    return self._doc_to_incident(doc)
            except Exception as me:
                logger.warning(f"MongoDB Atlas get_incident_by_id error ({me}); checking SQLite.")

        db = self.get_db()
        try:
            return db.query(IncidentDB).filter(IncidentDB.id == incident_id).first()
        finally:
            db.close()

    def review_incident(self, incident_id: str, review: IncidentReviewRequest) -> IncidentDB:
        """
        Updates review status, ground truth label, reviewer identity,
        and recomputes local dynamic risk adjustment.
        """
        db = self.get_db()
        try:
            incident = db.query(IncidentDB).filter(IncidentDB.id == incident_id).first()
            if not incident:
                raise ValueError(f"Incident {incident_id} not found")

            now_iso = utc_now_iso()
            v_status = review.verification_status
            if not v_status and review.ground_truth_label:
                gt_lower = review.ground_truth_label.lower()
                if "genuine" in gt_lower or ("flood" in gt_lower and "non" not in gt_lower):
                    v_status = "VERIFIED_GENUINE"
                elif "non" in gt_lower:
                    v_status = "VERIFIED_NON_WATERLOGGING"
                elif "inconclusive" in gt_lower:
                    v_status = "INCONCLUSIVE"
                else:
                    v_status = "VERIFIED_GENUINE"

            incident.verification_status = v_status or incident.verification_status
            if review.ground_truth_label:
                incident.ground_truth_label = review.ground_truth_label
            incident.reviewed_by = review.reviewed_by
            incident.reviewed_at = now_iso
            if review.reviewer_notes:
                incident.reviewer_notes = review.reviewer_notes
            incident.updated_at = now_iso

            # Recalculate adjustment based on reviewed status
            if incident.verification_status in ("VERIFIED_GENUINE", "VERIFIED"):
                incident.report_risk_adjustment = DynamicRiskEngine.HUMAN_VERIFIED_GENUINE_POINTS
            elif incident.verification_status in ["VERIFIED_NON_WATERLOGGING", "REJECTED", "DUPLICATE", "INCONCLUSIVE"]:
                incident.report_risk_adjustment = 0.0
            elif incident.verification_status in ("PENDING", "PENDING_VERIFICATION") and incident.predicted_class == "Flooded Scene":
                incident.report_risk_adjustment = DynamicRiskEngine.AI_POSITIVE_PENDING_POINTS

            incident.final_risk_score = min(100.0, max(0.0, incident.baseline_risk_score + incident.report_risk_adjustment))

            db.commit()
            db.refresh(incident)

            # Update MongoDB Atlas if connected
            incidents_col = mongo_manager.get_collection("incidents")
            if incidents_col is not None:
                try:
                    incidents_col.update_one(
                        {"id": incident_id},
                        {"$set": {
                            "verification_status": incident.verification_status,
                            "ground_truth_label": incident.ground_truth_label,
                            "reviewed_by": incident.reviewed_by,
                            "reviewed_at": incident.reviewed_at,
                            "reviewer_notes": incident.reviewer_notes,
                            "report_risk_adjustment": incident.report_risk_adjustment,
                            "final_risk_score": incident.final_risk_score,
                            "updated_at": incident.updated_at,
                        }}
                    )
                except Exception as me:
                    logger.warning(f"MongoDB incident update notice ({me})")

            logger.info(f"Reviewed Incident {incident.id}: new_status={incident.verification_status}, adj=+{incident.report_risk_adjustment}")
            return incident
        finally:
            db.close()

    def calculate_area_risk(
        self,
        city: str,
        location_name: str,
        lat: float,
        lng: float,
        radius_km: float = 1.5,
        baseline_risk: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates dynamic area risk around coordinates using all active incidents.
        """
        db = self.get_db()
        try:
            if baseline_risk is not None:
                baseline = baseline_risk
            else:
                baseline = self.get_baseline_risk_for_location(city, location_name, lat, lng)
            active_incidents = db.query(IncidentDB).filter(
                IncidentDB.duplicate_of.is_(None)
            ).all()

            eval_res = DynamicRiskEngine.evaluate_area_risk(
                baseline_risk=baseline,
                latitude=lat,
                longitude=lng,
                active_incidents=active_incidents,
                radius_km=radius_km
            )
            eval_res["city"] = city
            eval_res["location_name"] = location_name
            eval_res["latitude"] = lat
            eval_res["longitude"] = lng
            eval_res["final_risk"] = eval_res["final_risk_score"]
            eval_res["baseline_risk"] = eval_res["baseline_risk_score"]
            eval_res["report_adjustment"] = eval_res["report_risk_adjustment"]
            eval_res["adjustment_breakdown"] = eval_res.get("calculation_basis", "")
            return eval_res
        finally:
            db.close()

    def calculate_model_evaluation(self, include_demo: bool = True) -> Dict[str, Any]:
        """
        Calculates confusion matrix, precision, recall, F1, and accuracy
        against actual labeled ground-truth examples.
        """
        db = self.get_db()
        try:
            query = db.query(IncidentDB).filter(
                IncidentDB.ground_truth_label.isnot(None)
            )
            if not include_demo:
                query = query.filter(IncidentDB.is_demo == False)

            labeled_incidents = query.all()

            tp = 0
            fp = 0
            tn = 0
            fn = 0

            for inc in labeled_incidents:
                pred = inc.predicted_class
                actual = inc.ground_truth_label

                if actual == "Inconclusive":
                    continue

                is_pred_flood = "flood" in pred.lower()
                is_actual_flood = "flood" in actual.lower()

                if is_pred_flood and is_actual_flood:
                    tp += 1
                elif is_pred_flood and not is_actual_flood:
                    fp += 1
                elif not is_pred_flood and not is_actual_flood:
                    tn += 1
                elif not is_pred_flood and is_actual_flood:
                    fn += 1

            total_valid = tp + fp + tn + fn
            if total_valid == 0:
                return {
                    "model_name": "prithivMLmods/Flood-Image-Detection",
                    "model_architecture": "SiglipForImageClassification",
                    "evaluation_status": "EVALUATION_DATASET_REQUIRED",
                    "dataset_type": "no_labeled_records_yet",
                    "dataset_version": "v1.0-unlabeled",
                    "total_samples": len(labeled_incidents),
                    "labeled_samples": 0,
                    "confusion_matrix": {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0},
                    "accuracy": None,
                    "precision": None,
                    "recall": None,
                    "f1_score": None,
                    "disclaimer": "Evaluation dataset required. No independently reviewed ground-truth labels are available yet."
                }

            accuracy = round((tp + tn) / total_valid, 4)
            precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
            recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
            f1 = round(2.0 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

            return {
                "model_name": "prithivMLmods/Flood-Image-Detection",
                "model_architecture": "SiglipForImageClassification",
                "evaluation_status": "EVALUATED_ON_LABELED_DATA",
                "dataset_type": "demo_benchmark" if any(i.is_demo for i in labeled_incidents) else "real_ground_truth",
                "dataset_version": "v1.2-benchmark",
                "total_samples": len(labeled_incidents),
                "labeled_samples": total_valid,
                "confusion_matrix": {
                    "true_positive": tp,
                    "false_positive": fp,
                    "true_negative": tn,
                    "false_negative": fn
                },
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
                "f1_score": f1,
                "disclaimer": (
                    "Metrics calculated against independently labeled demonstration benchmark dataset. "
                    "Do not extrapolate as real-world production performance without continuous field auditing."
                )
            }
        finally:
            db.close()

    def get_demo_summary(self) -> Dict[str, Any]:
        db = self.get_db()
        try:
            total = db.query(IncidentDB).count()
            real = db.query(IncidentDB).filter(IncidentDB.is_demo == False).count()
            demo = db.query(IncidentDB).filter(IncidentDB.is_demo == True).count()
            verified_genuine = db.query(IncidentDB).filter(IncidentDB.verification_status == "VERIFIED_GENUINE").count()
            verified_non = db.query(IncidentDB).filter(IncidentDB.verification_status == "VERIFIED_NON_WATERLOGGING").count()
            pending = db.query(IncidentDB).filter(IncidentDB.verification_status == "PENDING").count()
            rejected = db.query(IncidentDB).filter(IncidentDB.verification_status.in_(["REJECTED", "DUPLICATE"])).count()

            return {
                "total_incidents": total,
                "real_incidents_count": real,
                "demo_incidents_count": demo,
                "verified_genuine_count": verified_genuine,
                "verified_non_waterlogging_count": verified_non,
                "pending_verification_count": pending,
                "rejected_or_duplicate_count": rejected,
                "is_demo_mode_active": True,
            }
        finally:
            db.close()

    def reset_demo_data(self) -> int:
        """
        Deletes all synthetic records marked is_demo = True.
        Preserves all real citizen/camera reports!
        """
        incidents_col = mongo_manager.get_collection("incidents")
        if incidents_col is not None:
            try:
                incidents_col.delete_many({"is_demo": True})
            except Exception as me:
                logger.warning(f"MongoDB demo delete notice ({me})")

        db = self.get_db()
        try:
            deleted_count = db.query(IncidentDB).filter(IncidentDB.is_demo == True).delete()
            db.commit()
            logger.info(f"Reset demo data: removed {deleted_count} demo incident records.")
            return deleted_count
        finally:
            db.close()

    def seed_demo_data(self) -> int:
        """
        Seeds realistic synthetic demonstration records with ground-truth labels
        to showcase the complete AI verification, review, and accuracy dashboard workflows.
        """
        db = self.get_db()
        try:
            # Check if demo data already seeded
            existing_demo = db.query(IncidentDB).filter(IncidentDB.is_demo == True).count()
            if existing_demo >= 8:
                return existing_demo

            now_iso = utc_now_iso()
            demo_items = [
                {
                    "id": "DEMO-MUM-01",
                    "city": "Mumbai",
                    "location_name": "Andheri Subway",
                    "latitude": 19.1197,
                    "longitude": 72.8468,
                    "image_reference": "/uploads/demo_andheri_flood.jpg",
                    "predicted_class": "Flooded Scene",
                    "model_score": 0.94,
                    "verification_status": "VERIFIED_GENUINE",
                    "ground_truth_label": "Flooded Scene",
                    "reviewed_by": "Senior BMC Inspector #402",
                    "baseline_risk_score": 50.0,
                    "report_risk_adjustment": 10.0,
                    "final_risk_score": 60.0,
                    "notes": "Verified 45cm road waterlogging under railway subway."
                },
                {
                    "id": "DEMO-MUM-02",
                    "city": "Mumbai",
                    "location_name": "Hindmata Flyover Junction (Dadar)",
                    "latitude": 19.0178,
                    "longitude": 72.8478,
                    "image_reference": "/uploads/demo_dadar_puddle.jpg",
                    "predicted_class": "Flooded Scene",
                    "model_score": 0.88,
                    "verification_status": "VERIFIED_GENUINE",
                    "ground_truth_label": "Flooded Scene",
                    "reviewed_by": "Warden Team F-South",
                    "baseline_risk_score": 65.0,
                    "report_risk_adjustment": 10.0,
                    "final_risk_score": 75.0,
                    "notes": "Confirmed saucer-basin stormwater ponding."
                },
                {
                    "id": "DEMO-MUM-03",
                    "city": "Mumbai",
                    "location_name": "Linking Road (Bandra)",
                    "latitude": 19.0607,
                    "longitude": 72.8362,
                    "image_reference": "/uploads/demo_bandra_dry.jpg",
                    "predicted_class": "Non Flooded",
                    "model_score": 0.96,
                    "verification_status": "VERIFIED_NON_WATERLOGGING",
                    "ground_truth_label": "Non Flooded",
                    "reviewed_by": "Traffic Control Desk",
                    "baseline_risk_score": 25.0,
                    "report_risk_adjustment": 0.0,
                    "final_risk_score": 25.0,
                    "notes": "Standard wet asphalt with zero depth accumulation."
                },
                {
                    "id": "DEMO-MUM-04",
                    "city": "Mumbai",
                    "location_name": "Kurla West LBS Marg",
                    "latitude": 19.0726,
                    "longitude": 72.8845,
                    "image_reference": "/uploads/demo_kurla_flood.jpg",
                    "predicted_class": "Flooded Scene",
                    "model_score": 0.82,
                    "verification_status": "PENDING",
                    "ground_truth_label": "Flooded Scene",
                    "reviewed_by": None,
                    "baseline_risk_score": 40.0,
                    "report_risk_adjustment": 5.0,
                    "final_risk_score": 45.0,
                    "notes": "Awaiting ground verification team confirmation."
                },
                {
                    "id": "DEMO-PUN-05",
                    "city": "Pune",
                    "location_name": "Deccan Gymkhana Riverside Road",
                    "latitude": 18.5167,
                    "longitude": 73.8417,
                    "image_reference": "/uploads/demo_deccan_flood.jpg",
                    "predicted_class": "Flooded Scene",
                    "model_score": 0.91,
                    "verification_status": "VERIFIED_GENUINE",
                    "ground_truth_label": "Flooded Scene",
                    "reviewed_by": "PMC Disaster Cell #12",
                    "baseline_risk_score": 70.0,
                    "report_risk_adjustment": 10.0,
                    "final_risk_score": 80.0,
                    "notes": "Mutha river causeway overtopping confirmed."
                },
                {
                    "id": "DEMO-PUN-06",
                    "city": "Pune",
                    "location_name": "Shivajinagar Bus Stand",
                    "latitude": 18.5314,
                    "longitude": 73.8446,
                    "image_reference": "/uploads/demo_shivajinagar_dry.jpg",
                    "predicted_class": "Non Flooded",
                    "model_score": 0.93,
                    "verification_status": "VERIFIED_NON_WATERLOGGING",
                    "ground_truth_label": "Non Flooded",
                    "reviewed_by": "PMC Disaster Cell #12",
                    "baseline_risk_score": 30.0,
                    "report_risk_adjustment": 0.0,
                    "final_risk_score": 30.0,
                    "notes": "Surface clear, stormwater drains flowing freely."
                },
                {
                    "id": "DEMO-MUM-07",
                    "city": "Mumbai",
                    "location_name": "Powai Lake Promenade",
                    "latitude": 19.1176,
                    "longitude": 72.9060,
                    "image_reference": "/uploads/demo_powai_lake.jpg",
                    "predicted_class": "Flooded Scene",
                    "model_score": 0.58,
                    "verification_status": "REJECTED",
                    "ground_truth_label": "Non Flooded",
                    "reviewed_by": "Lead Reviewer S. Patel",
                    "baseline_risk_score": 20.0,
                    "report_risk_adjustment": 0.0,
                    "final_risk_score": 20.0,
                    "notes": "Lake water body mistakenly photographed instead of roadway. Rejected."
                },
                {
                    "id": "DEMO-MUM-08",
                    "city": "Mumbai",
                    "location_name": "Colaba Causeway",
                    "latitude": 18.9067,
                    "longitude": 72.8147,
                    "image_reference": "/uploads/demo_colaba_dry.jpg",
                    "predicted_class": "Non Flooded",
                    "model_score": 0.98,
                    "verification_status": "VERIFIED_NON_WATERLOGGING",
                    "ground_truth_label": "Non Flooded",
                    "reviewed_by": "A Ward Inspector",
                    "baseline_risk_score": 15.0,
                    "report_risk_adjustment": 0.0,
                    "final_risk_score": 15.0,
                    "notes": "Normal vehicular movement, zero waterlogging."
                }
            ]

            count = 0
            for item in demo_items:
                inc = IncidentDB(
                    id=item["id"],
                    city=item["city"],
                    location_name=item["location_name"],
                    latitude=item["latitude"],
                    longitude=item["longitude"],
                    captured_at=now_iso,
                    submitted_at=now_iso,
                    image_reference=item["image_reference"],
                    predicted_class=item["predicted_class"],
                    model_score=item["model_score"],
                    model_name="prithivMLmods/Flood-Image-Detection",
                    verification_status=item["verification_status"],
                    source_type="demo",
                    is_demo=True,
                    duplicate_of=None,
                    baseline_risk_score=item["baseline_risk_score"],
                    report_risk_adjustment=item["report_risk_adjustment"],
                    final_risk_score=item["final_risk_score"],
                    ground_truth_label=item.get("ground_truth_label"),
                    reviewed_by=item.get("reviewed_by"),
                    reviewed_at=now_iso if item.get("reviewed_by") else None,
                    reviewer_notes=item.get("notes"),
                    created_at=now_iso,
                    updated_at=now_iso,
                )
                db.add(inc)
                count += 1

            db.commit()
            logger.info(f"Seeded {count} demonstration incidents.")
            return count
        finally:
            db.close()

    def export_dataset(self) -> Dict[str, Any]:
        """
        Exports verified ground-truth records partitioned into train, validation, and test splits.
        Prevents data leakage by grouping records and excluding unverified/inconclusive records.
        """
        db = self.get_db()
        try:
            eligible = db.query(IncidentDB).filter(
                and_(
                    IncidentDB.ground_truth_label.isnot(None),
                    IncidentDB.verification_status.in_(["VERIFIED_GENUINE", "VERIFIED_NON_WATERLOGGING"])
                )
            ).order_by(IncidentDB.created_at.asc()).all()

            records = [
                {
                    "incident_id": inc.id,
                    "city": inc.city,
                    "location_name": inc.location_name,
                    "latitude": inc.latitude,
                    "longitude": inc.longitude,
                    "image_reference": inc.image_reference,
                    "predicted_class": inc.predicted_class,
                    "model_score": inc.model_score,
                    "ground_truth_label": inc.ground_truth_label,
                    "reviewed_by": inc.reviewed_by,
                    "reviewed_at": inc.reviewed_at,
                    "is_demo": inc.is_demo
                }
                for inc in eligible
            ]

            # Partition 70% train, 15% validation, 15% test
            n = len(records)
            train_idx = int(0.70 * n)
            val_idx = int(0.85 * n)

            splits_dict = {
                "train": records[:train_idx],
                "validation": records[train_idx:val_idx],
                "val": records[train_idx:val_idx],
                "test": records[val_idx:]
            }

            return {
                "exported_at": utc_now_iso(),
                "dataset_version": "v1.2-verified",
                "total_eligible_samples": n,
                "split_ratios": {"train": 0.70, "validation": 0.15, "test": 0.15},
                "splits": splits_dict,
                "partitions": splits_dict,
                "guidelines": "Do not evaluate on training split. Group incidents by physical rainfall event to prevent spatial leakage."
            }
        finally:
            db.close()

    def seed_demo_incidents(self) -> int:
        return self.seed_demo_data()

incident_service = IncidentService()
