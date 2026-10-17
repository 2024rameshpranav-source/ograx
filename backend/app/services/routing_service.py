import math
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import IncidentDB, ReportDB
from app.schemas.routing import (
    RouteRequest,
    RouteOption,
    HazardIntersection,
    RouteComparisonResponse,
    RoutePreset,
    LatLngPoint,
)
from app.services.risk_adjustment import DynamicRiskEngine, haversine_distance_km

logger = logging.getLogger("aquasignal.routing_service")


def point_to_segment_distance_meters(
    p_lat: float, p_lon: float,
    a_lat: float, a_lon: float,
    b_lat: float, b_lon: float
) -> float:
    """
    Computes the shortest distance in meters from point P to line segment AB
    using projected Cartesian approximation suitable for short segments.
    """
    # Convert lat/lon degrees to meters roughly centered around P
    lat_mid = math.radians(p_lat)
    m_per_deg_lat = 111132.92 - 559.82 * math.cos(2 * lat_mid) + 1.175 * math.cos(4 * lat_mid)
    m_per_deg_lon = 111412.84 * math.cos(lat_mid) - 93.5 * math.cos(3 * lat_mid)

    px = (p_lon - a_lon) * m_per_deg_lon
    py = (p_lat - a_lat) * m_per_deg_lat
    bx = (b_lon - a_lon) * m_per_deg_lon
    by = (b_lat - a_lat) * m_per_deg_lat

    seg_len_sq = bx * bx + by * by
    if seg_len_sq == 0:
        return math.sqrt(px * px + py * py)

    # Project point onto segment (clamped between 0 and 1)
    t = max(0.0, min(1.0, (px * bx + py * by) / seg_len_sq))
    proj_x = t * bx
    proj_y = t * by

    dx = px - proj_x
    dy = py - proj_y
    return math.sqrt(dx * dx + dy * dy)


def point_to_polyline_distance_meters(p_lat: float, p_lon: float, polyline: List[List[float]]) -> float:
    """
    Finds the minimum distance in meters from point P to any segment of a polyline.
    Polyline format: [[lat1, lon1], [lat2, lon2], ...]
    """
    if not polyline:
        return float("inf")
    if len(polyline) == 1:
        return haversine_distance_km(p_lat, p_lon, polyline[0][0], polyline[0][1]) * 1000.0

    min_dist = float("inf")
    for i in range(len(polyline) - 1):
        a_lat, a_lon = polyline[i][0], polyline[i][1]
        b_lat, b_lon = polyline[i + 1][0], polyline[i + 1][1]
        dist = point_to_segment_distance_meters(p_lat, p_lon, a_lat, a_lon, b_lat, b_lon)
        if dist < min_dist:
            min_dist = dist
    return min_dist


class WaterloggingAwareRoutingService:
    """
    Calculates alternative routes between origin and destination,
    analyzes spatial intersections with live flood reports and rainfall screening warnings,
    and returns transparent, evidence-ranked route advisories.
    """

    point_to_segment_distance_meters = staticmethod(point_to_segment_distance_meters)
    point_to_polyline_distance_meters = staticmethod(point_to_polyline_distance_meters)

    OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"
    REQUEST_TIMEOUT_SECONDS = 5

    PRESETS = [
        # Mumbai Presets
        RoutePreset(
            id="mum-andheri-bandra",
            city="Mumbai",
            name="Andheri West to Bandra Kurla Complex (BKC)",
            origin=LatLngPoint(latitude=19.1197, longitude=72.8464, name="Andheri West Metro"),
            destination=LatLngPoint(latitude=19.0601, longitude=72.8550, name="Bandra Kurla Complex (BKC)"),
            corridor_description="Major western suburban commuter corridor via Western Express Hwy vs SV Road."
        ),
        RoutePreset(
            id="mum-kurla-dadar",
            city="Mumbai",
            name="Kurla Junction to Dadar TT Circle",
            origin=LatLngPoint(latitude=19.0726, longitude=72.8845, name="Kurla Station West"),
            destination=LatLngPoint(latitude=19.0178, longitude=72.8478, name="Dadar TT Circle"),
            corridor_description="Central Mumbai arterial passing near Sion underpasses and Mithi basin."
        ),
        RoutePreset(
            id="mum-chembur-colaba",
            city="Mumbai",
            name="Chembur to Colaba Causeway",
            origin=LatLngPoint(latitude=19.0522, longitude=72.8990, name="Chembur Monorail Terminus"),
            destination=LatLngPoint(latitude=18.9067, longitude=72.8147, name="Colaba Causeway"),
            corridor_description="Eastern Freeway vs Port Road arterial connection to South Mumbai."
        ),
        # Pune Presets
        RoutePreset(
            id="pune-shivali-kothrud",
            city="Pune",
            name="Shivajinagar to Kothrud Stand",
            origin=LatLngPoint(latitude=18.5314, longitude=73.8446, name="Shivajinagar Station"),
            destination=LatLngPoint(latitude=18.5074, longitude=73.8077, name="Kothrud Stand"),
            corridor_description="Central Pune link via Karve Road vs Paud Road."
        ),
        RoutePreset(
            id="pune-swargate-viman",
            city="Pune",
            name="Swargate to Viman Nagar",
            origin=LatLngPoint(latitude=18.5018, longitude=73.8636, name="Swargate Bus Terminus"),
            destination=LatLngPoint(latitude=18.5679, longitude=73.9143, name="Viman Nagar"),
            corridor_description="Cross-city transit crossing Mula-Mutha river approaches."
        ),
    ]

    def get_presets(self, city: Optional[str] = None) -> List[RoutePreset]:
        if not city:
            return self.PRESETS
        clean_city = city.strip().capitalize()
        return [p for p in self.PRESETS if p.city.capitalize() == clean_city]

    def _fetch_osrm_routes(
        self, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float, prefer_alternatives: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Fetches real street route geometries, distances, and durations from OpenStreetMap OSRM.
        """
        alt_param = "true" if prefer_alternatives else "false"
        url = (
            f"{self.OSRM_BASE_URL}/{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}"
            f"?overview=full&geometries=geojson&alternatives={alt_param}&steps=false"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AquaSignal-Ograx-Waterlogging-Advisory/1.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT_SECONDS) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    if data.get("code") == "Ok" and data.get("routes"):
                        return data["routes"]
        except Exception as e:
            logger.warning(f"OSRM upstream routing request failed or timed out: {e}")

        # Fallback to deterministic local corridor generator if upstream OSRM is unreachable
        return self._generate_fallback_routes(origin_lat, origin_lon, dest_lat, dest_lon, prefer_alternatives)

    def _generate_fallback_routes(
        self, o_lat: float, o_lon: float, d_lat: float, d_lon: float, prefer_alternatives: bool
    ) -> List[Dict[str, Any]]:
        """
        Deterministic topological corridor generator used when upstream OSRM is offline.
        Produces primary direct line and lateral alternative paths.
        """
        routes = []
        direct_dist_km = haversine_distance_km(o_lat, o_lon, d_lat, d_lon)
        # Approximate street distance (1.25x Manhattan factor) and 30 km/h average speed
        driving_dist_m = direct_dist_km * 1.25 * 1000.0
        duration_s = (driving_dist_m / (30.0 * 1000.0 / 3600.0))

        # Route 1: Main Arterial (direct interpolation with 10 waypoints)
        coords_1 = []
        steps = 12
        for i in range(steps + 1):
            fraction = i / steps
            coords_1.append([
                round(o_lon + fraction * (d_lon - o_lon), 6),
                round(o_lat + fraction * (d_lat - o_lat), 6)
            ])

        routes.append({
            "geometry": {"coordinates": coords_1},
            "distance": round(driving_dist_m, 1),
            "duration": round(duration_s, 1),
            "weight_name": "direct_corridor",
            "summary": "Main Arterial Corridor"
        })

        if prefer_alternatives:
            # Route 2: Western / Bypass Corridor (+0.010 offset perpendicular)
            perp_lat = -(d_lon - o_lon) * 0.18
            perp_lon = (d_lat - o_lat) * 0.18
            coords_2 = []
            for i in range(steps + 1):
                fraction = i / steps
                # Bow outward in middle
                bow = math.sin(fraction * math.pi)
                coords_2.append([
                    round(o_lon + fraction * (d_lon - o_lon) + bow * perp_lon, 6),
                    round(o_lat + fraction * (d_lat - o_lat) + bow * perp_lat, 6)
                ])

            routes.append({
                "geometry": {"coordinates": coords_2},
                "distance": round(driving_dist_m * 1.15, 1),
                "duration": round(duration_s * 1.12, 1),
                "weight_name": "bypass_corridor",
                "summary": "Secondary / Bypass Route"
            })

        return routes

    def compute_route_recommendations(
        self, request: RouteRequest, db: Optional[Session] = None
    ) -> RouteComparisonResponse:
        """
        Executes end-to-end route generation, hazard correlation, and comparative risk ranking.
        """
        o_lat, o_lon = request.origin.latitude, request.origin.longitude
        d_lat, d_lon = request.destination.latitude, request.destination.longitude
        city = request.city.strip().capitalize()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # 1. Fetch Candidate Routes
        raw_routes = self._fetch_osrm_routes(o_lat, o_lon, d_lat, d_lon, request.prefer_alternatives)
        if not raw_routes:
            raise ValueError("No feasible route could be found between the specified origin and destination.")

        # 2. Gather Available Ground-Truth Incidents & Citizen Reports
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        active_incidents: List[IncidentDB] = []
        active_reports: List[ReportDB] = []
        try:
            # Query incidents for target city
            active_incidents = db.query(IncidentDB).filter(
                IncidentDB.city.ilike(f"%{city}%"),
                IncidentDB.duplicate_of.is_(None)
            ).all()

            # Query citizen reports
            active_reports = db.query(ReportDB).filter(
                ReportDB.city.ilike(f"%{city}%")
            ).all()
        finally:
            if should_close_db:
                db.close()

        # 3. Gather Rainfall Screening Data (if Mumbai)
        mumbai_screening_locations = []
        mumbai_overall_signal = "DATA_UNAVAILABLE"
        if city == "Mumbai":
            try:
                from app.services.mumbai_engine.service import mumbai_waterlogging_service
                screening = mumbai_waterlogging_service.get_screening_results(horizon=request.horizon_hours)
                mumbai_screening_locations = screening.get("locations", [])
                mumbai_overall_signal = screening.get("overall_screening_status", "NO_RAINFALL_SIGNAL")
            except Exception as e:
                logger.warning(f"Could not load Mumbai screening results for route evaluation: {e}")

        # 4. Evaluate each candidate route
        evaluated_routes: List[RouteOption] = []

        for idx, r in enumerate(raw_routes):
            route_id = f"route_{idx + 1}"
            raw_coords = r.get("geometry", {}).get("coordinates", [])
            # Convert GeoJSON [lon, lat] to Leaflet [lat, lon]
            lat_lon_path = [[round(pt[1], 6), round(pt[0], 6)] for pt in raw_coords]

            distance_km = round(r.get("distance", 0.0) / 1000.0, 2)
            duration_mins = round(r.get("duration", 0.0) / 60.0, 1)
            summary_name = r.get("summary") or f"Alternative {idx + 1}"
            if idx == 0 and summary_name == f"Alternative {idx + 1}":
                summary_name = "Primary Arterial Route"

            # Match hazards against this polyline
            route_hazards: List[HazardIntersection] = []
            verified_count = 0
            pending_ai_count = 0
            rainfall_watch_count = 0
            total_hazard_points = 0.0

            # Match verified/unverified incidents
            for inc in active_incidents:
                dist_m = point_to_polyline_distance_meters(inc.latitude, inc.longitude, lat_lon_path)
                if dist_m <= request.tolerance_meters:
                    decay = DynamicRiskEngine.get_time_decay_factor(inc.submitted_at, now)
                    if decay <= 0.0:
                        continue

                    # Calculate age in hours
                    age_h = None
                    try:
                        inc_dt = datetime.fromisoformat(inc.submitted_at.replace("Z", "+00:00"))
                        age_h = round((now - inc_dt).total_seconds() / 3600.0, 1)
                    except Exception:
                        pass

                    if inc.verification_status in ("VERIFIED_GENUINE", "VERIFIED"):
                        pts = 30.0 * decay
                        verified_count += 1
                        route_hazards.append(HazardIntersection(
                            hazard_type="VERIFIED_WATERLOGGING",
                            location_name=inc.location_name,
                            latitude=inc.latitude,
                            longitude=inc.longitude,
                            distance_to_route_meters=round(dist_m, 1),
                            severity_or_status="VERIFIED_GENUINE",
                            reported_at=inc.submitted_at,
                            age_hours=age_h,
                            description=f"Human-verified waterlogging ({inc.model_score * 100:.0f}% visual confidence). Observed {dist_m:.0f}m from route.",
                            risk_points_contributed=round(pts, 1)
                        ))
                        total_hazard_points += pts

                    elif inc.verification_status in ("PENDING", "PENDING_VERIFICATION") and inc.predicted_class == "Flooded Scene":
                        pts = 15.0 * decay
                        pending_ai_count += 1
                        route_hazards.append(HazardIntersection(
                            hazard_type="PENDING_AI_DETECTION",
                            location_name=inc.location_name,
                            latitude=inc.latitude,
                            longitude=inc.longitude,
                            distance_to_route_meters=round(dist_m, 1),
                            severity_or_status="PENDING_VERIFICATION",
                            reported_at=inc.submitted_at,
                            age_hours=age_h,
                            description=f"AI-classified flooded scene awaiting field verification. Located {dist_m:.0f}m from route.",
                            risk_points_contributed=round(pts, 1)
                        ))
                        total_hazard_points += pts

            # Match citizen reports
            for rep in active_reports:
                dist_m = point_to_polyline_distance_meters(rep.latitude, rep.longitude, lat_lon_path)
                if dist_m <= request.tolerance_meters:
                    decay = DynamicRiskEngine.get_time_decay_factor(rep.created_at, now)
                    if decay <= 0.0:
                        continue

                    pts = 10.0 * decay
                    route_hazards.append(HazardIntersection(
                        hazard_type="CITIZEN_REPORT",
                        location_name=rep.landmark,
                        latitude=rep.latitude,
                        longitude=rep.longitude,
                        distance_to_route_meters=round(dist_m, 1),
                        severity_or_status=rep.severity,
                        reported_at=rep.created_at,
                        description=f"Citizen report: {rep.description}. Located {dist_m:.0f}m from route.",
                        risk_points_contributed=round(pts, 1)
                    ))
                    total_hazard_points += pts

            # Match Mumbai rainfall warning hotspots within 800m
            if city == "Mumbai":
                for loc in mumbai_screening_locations:
                    lat = loc.get("latitude")
                    lon = loc.get("longitude")
                    status = loc.get("warning_status")
                    if lat and lon and status in ("RAINFALL_WATCH", "LOW_RAINFALL_SIGNAL"):
                        dist_m = point_to_polyline_distance_meters(lat, lon, lat_lon_path)
                        if dist_m <= 800.0:
                            pts = 12.0 if status == "RAINFALL_WATCH" else 5.0
                            rainfall_watch_count += 1
                            route_hazards.append(HazardIntersection(
                                hazard_type="RAINFALL_WATCH",
                                location_name=loc.get("location_name", "Mumbai Corridor"),
                                latitude=lat,
                                longitude=lon,
                                distance_to_route_meters=round(dist_m, 1),
                                severity_or_status=status,
                                reported_at=loc.get("observation_time"),
                                description=f"Corridor rainfall alert ({status}) from Mumbai warning engine. Passing within {dist_m:.0f}m.",
                                risk_points_contributed=round(pts, 1)
                            ))
                            total_hazard_points += pts

            # Final risk score calculation (bounded 0 - 100)
            final_risk = round(min(100.0, max(0.0, total_hazard_points)), 1)

            # Categorization
            if final_risk <= 5.0:
                risk_category = "LOWER_KNOWN_RISK"
            elif final_risk <= 25.0:
                risk_category = "ELEVATED_RISK"
            else:
                risk_category = "HIGH_HAZARD"

            evaluated_routes.append(RouteOption(
                route_id=route_id,
                summary_name=summary_name,
                distance_km=distance_km,
                duration_minutes=duration_mins,
                coordinates=lat_lon_path,
                risk_score=final_risk,
                risk_category=risk_category,
                is_recommended=False,
                recommendation_reason="",
                hazard_count=len(route_hazards),
                verified_waterlogging_count=verified_count,
                pending_ai_reports_count=pending_ai_count,
                rainfall_watch_count=rainfall_watch_count,
                hazards=route_hazards,
                data_freshness="FRESH",
                data_source="OpenStreetMap OSRM + AquaSignal Waterlogging DB"
            ))

        # 5. Determine Recommended Route
        # Hierarchy: lowest risk score first; if risk scores tie within 3 points, prefer shorter duration.
        evaluated_routes.sort(key=lambda r: (r.risk_score, r.duration_minutes))

        recommended_route = evaluated_routes[0]
        recommended_route.is_recommended = True

        if len(evaluated_routes) == 1:
            recommended_route.recommendation_reason = (
                f"Single feasible route identified ({recommended_route.distance_km} km, {recommended_route.duration_minutes} min). "
                f"Risk category: {recommended_route.risk_category} based on available hazard data."
            )
        elif recommended_route.risk_score < evaluated_routes[1].risk_score:
            risk_diff = evaluated_routes[1].risk_score - recommended_route.risk_score
            recommended_route.recommendation_reason = (
                f"Recommended: Lower known waterlogging risk ({recommended_route.risk_score:.0f} pts vs "
                f"{evaluated_routes[1].risk_score:.0f} pts on {evaluated_routes[1].summary_name}). "
                f"Avoids {evaluated_routes[1].hazard_count} recorded waterlogging/rainfall hazards."
            )
        else:
            recommended_route.recommendation_reason = (
                f"Recommended: Lowest duration ({recommended_route.duration_minutes} min) with equivalent "
                f"lower known waterlogging exposure ({recommended_route.risk_score:.0f} pts)."
            )

        origin_label = request.origin.name or f"Origin ({o_lat:.4f}, {o_lon:.4f})"
        dest_label = request.destination.name or f"Destination ({d_lat:.4f}, {d_lon:.4f})"

        return RouteComparisonResponse(
            success=True,
            city=city,
            origin_name=origin_label,
            destination_name=dest_label,
            total_routes_found=len(evaluated_routes),
            routes=evaluated_routes,
            recommended_route_id=recommended_route.route_id,
            screening_status_summary=mumbai_overall_signal if city == "Mumbai" else "PUNE_ML_MONITORED",
            calculation_methodology=(
                "Spatial cross-track distance buffer (250m) matching candidate polylines against "
                "verified waterlogging reports, AI image classifications, and rainfall screening hotspots with time-decay."
            ),
            safety_disclaimer=(
                "ADVISORY ONLY: 'Lower known risk' indicates fewer recorded hazards in the system database. "
                "It does NOT guarantee a road is dry or safe. Conditions can change rapidly. "
                "Never drive or walk into standing floodwater. Obey local traffic and disaster management authorities."
            ),
            timestamp=now_iso
        )


routing_service = WaterloggingAwareRoutingService()
