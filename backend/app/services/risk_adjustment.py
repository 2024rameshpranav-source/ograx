import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees).
    """
    r = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c

class DynamicRiskEngine:
    """
    Ograx Dynamic Risk Adjustment Engine.
    Adjusts baseline risk based on corroborating AI-detected and human-verified incident reports.
    Formula: Final Area Risk = Clamp(Baseline Risk + Report Adjustment, 0, 100)
    """

    DEFAULT_RADIUS_KM = 1.5
    MAX_TOTAL_ADJUSTMENT = 20.0
    AI_POSITIVE_PENDING_POINTS = 5.0
    HUMAN_VERIFIED_GENUINE_POINTS = 10.0
    CORROBORATING_BONUS_PER_REPORT = 3.0

    @classmethod
    def get_time_decay_factor(cls, submitted_at_iso: str, now: Optional[datetime] = None) -> float:
        """
        Calculates time decay multiplier for an incident.
        Reports younger than 1h have 100% weight, decaying smoothly to 0% after 12h.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        try:
            # Handle ISO string with timezone or without
            clean_str = submitted_at_iso.replace("Z", "+00:00")
            submitted_time = datetime.fromisoformat(clean_str)
            if submitted_time.tzinfo is None:
                submitted_time = submitted_time.replace(tzinfo=timezone.utc)
            
            age_seconds = (now - submitted_time).total_seconds()
            age_hours = max(0.0, age_seconds / 3600.0)

            if age_hours <= 1.0:
                return 1.0
            elif age_hours <= 3.0:
                return 0.75
            elif age_hours <= 6.0:
                return 0.50
            elif age_hours <= 12.0:
                return 0.25
            else:
                return 0.0
        except Exception:
            return 0.5  # Fallback moderate weight if date parsing fails

    @classmethod
    def compute_incident_adjustment(cls, incident: Any, now: Optional[datetime] = None) -> float:
        """
        Computes the raw adjustment contributed by a single incident.
        Only positive waterlogging signals contribute to risk increases:
        - VERIFIED_GENUINE: +10 points (scaled by decay)
        - PENDING with predicted_class == 'Flooded Scene' and score >= 0.7: +5 points (scaled by decay)
        - All others (Non Flooded, REJECTED, DUPLICATE, INCONCLUSIVE): 0.0
        """
        status = getattr(incident, "verification_status", None) or incident.get("verification_status")
        pred_class = getattr(incident, "predicted_class", None) or incident.get("predicted_class")
        score = getattr(incident, "model_score", 0.0) or incident.get("model_score", 0.0)
        submitted_at = getattr(incident, "submitted_at", None) or incident.get("submitted_at") or incident.get("created_at", "")

        decay = cls.get_time_decay_factor(submitted_at, now)
        if decay <= 0.0:
            return 0.0

        base_pts = 0.0
        if status in ("VERIFIED_GENUINE", "VERIFIED"):
            base_pts = cls.HUMAN_VERIFIED_GENUINE_POINTS
        elif status in ("PENDING", "PENDING_VERIFICATION") and pred_class == "Flooded Scene" and score >= 0.65:
            base_pts = cls.AI_POSITIVE_PENDING_POINTS
        else:
            return 0.0

        return base_pts * decay

    @classmethod
    def evaluate_area_risk(
        cls,
        baseline_risk: float,
        latitude: float,
        longitude: float,
        active_incidents: List[Any],
        radius_km: float = DEFAULT_RADIUS_KM
    ) -> Dict[str, Any]:
        """
        Evaluates dynamic risk for a given coordinate by aggregating nearby incident reports.
        """
        now = datetime.now(timezone.utc)
        relevant_incidents = []
        verified_count = 0
        pending_ai_pos_count = 0
        total_adj = 0.0

        for inc in active_incidents:
            inc_lat = getattr(inc, "latitude", None) if hasattr(inc, "latitude") else inc.get("latitude")
            inc_lng = getattr(inc, "longitude", None) if hasattr(inc, "longitude") else inc.get("longitude")
            
            if inc_lat is None or inc_lng is None:
                continue

            dist = haversine_distance_km(latitude, longitude, float(inc_lat), float(inc_lng))
            if dist <= radius_km:
                adj = cls.compute_incident_adjustment(inc, now)
                status = getattr(inc, "verification_status", None) or inc.get("verification_status")
                pred_class = getattr(inc, "predicted_class", None) or inc.get("predicted_class")

                if adj > 0.0:
                    relevant_incidents.append(inc)
                    total_adj += adj
                    if status == "VERIFIED_GENUINE":
                        verified_count += 1
                    elif status == "PENDING" and pred_class == "Flooded Scene":
                        pending_ai_pos_count += 1

        # Multi-report corroboration bonus (if 2 or more distinct credible reports exist)
        if len(relevant_incidents) >= 2:
            corroboration_bonus = (len(relevant_incidents) - 1) * cls.CORROBORATING_BONUS_PER_REPORT
            total_adj += corroboration_bonus

        # Bounded cap: cannot exceed MAX_TOTAL_ADJUSTMENT (+20 points)
        final_adjustment = round(min(cls.MAX_TOTAL_ADJUSTMENT, max(0.0, total_adj)), 1)
        final_risk = round(min(100.0, max(0.0, baseline_risk + final_adjustment)), 1)

        # Factual explanation
        if final_adjustment > 0:
            explanation_parts = []
            if verified_count > 0:
                explanation_parts.append(f"{verified_count} human-verified waterlogging report(s)")
            if pending_ai_pos_count > 0:
                explanation_parts.append(f"{pending_ai_pos_count} AI-detected flooded scene report(s) awaiting verification")
            if len(relevant_incidents) >= 2:
                explanation_parts.append(f"multi-report spatial corroboration bonus applied")
            explanation = (
                f"Baseline risk ({baseline_risk:.1f}%) adjusted by +{final_adjustment:.1f} points "
                f"due to {', '.join(explanation_parts)} within {radius_km:.1f} km radius."
            )
        else:
            explanation = (
                f"Baseline risk ({baseline_risk:.1f}%) unchanged. No credible active waterlogging incidents "
                f"within {radius_km:.1f} km radius."
            )

        return {
            "baseline_risk_score": round(baseline_risk, 1),
            "report_risk_adjustment": final_adjustment,
            "final_risk_score": final_risk,
            "active_incidents_count": len(relevant_incidents),
            "verified_genuine_count": verified_count,
            "pending_ai_positive_count": pending_ai_pos_count,
            "calculation_basis": explanation,
            "radius_km": radius_km
        }

    def calculate_area_risk(
        self,
        baseline_risk: float,
        nearby_incidents: List[Any],
        radius_km: float = DEFAULT_RADIUS_KM
    ) -> Dict[str, Any]:
        """Convenience method directly accepting nearby incidents."""
        total_adj = 0.0
        verified_count = 0
        pending_ai_pos_count = 0
        relevant_incidents = []

        for inc in nearby_incidents:
            status = getattr(inc, "verification_status", None) or inc.get("verification_status")
            if getattr(inc, "duplicate_of", None) or inc.get("duplicate_of"):
                continue
            adj = self.compute_incident_adjustment(inc)
            if adj > 0.0:
                relevant_incidents.append(inc)
                total_adj += adj
                if status in ("VERIFIED_GENUINE", "VERIFIED"):
                    verified_count += 1
                elif status in ("PENDING", "PENDING_VERIFICATION"):
                    pending_ai_pos_count += 1

        if len(relevant_incidents) >= 2:
            total_adj += (len(relevant_incidents) - 1) * self.CORROBORATING_BONUS_PER_REPORT

        final_adj = round(min(self.MAX_TOTAL_ADJUSTMENT, max(0.0, total_adj)), 1)
        final_risk = round(min(100.0, max(0.0, baseline_risk + final_adj)), 1)

        return {
            "baseline_risk": round(baseline_risk, 1),
            "report_adjustment": final_adj,
            "final_risk": final_risk,
            "active_reports_count": len(relevant_incidents),
            "verified_genuine_count": verified_count,
            "pending_ai_positive_count": pending_ai_pos_count,
            "radius_km": radius_km
        }

dynamic_risk_engine = DynamicRiskEngine()
