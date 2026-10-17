import React, { useState, useEffect, useRef, useMemo } from "react";
import * as L from "leaflet";
import {
  apiClient,
  type RouteRequest,
  type RouteOption,
  type RouteComparisonResponse,
  type RoutePreset,
  type LatLngPoint,
} from "../services/api";
import { appConfig } from "../config";

interface RouteAdvisorySectionProps {
  currentCity?: string;
  onOpenLiveCamera?: () => void;
}

const CITY_LANDMARKS: Record<string, LatLngPoint[]> = {
  Mumbai: [
    { name: "Andheri West (Subway)", latitude: 19.1197, longitude: 72.8464 },
    { name: "Bandra Kurla Complex (BKC)", latitude: 19.0601, longitude: 72.8550 },
    { name: "Kurla West (Station Junction)", latitude: 19.0726, longitude: 72.8845 },
    { name: "Dadar TT Circle", latitude: 19.0178, longitude: 72.8478 },
    { name: "Sion Circle", latitude: 19.0434, longitude: 72.8619 },
    { name: "Chembur Monorail", latitude: 19.0522, longitude: 72.8990 },
    { name: "Powai Lake", latitude: 19.1176, longitude: 72.9060 },
    { name: "Colaba Causeway", latitude: 18.9067, longitude: 72.8147 },
  ],
  Pune: [
    { name: "Shivajinagar Station", latitude: 18.5314, longitude: 73.8446 },
    { name: "Kothrud Stand", latitude: 18.5074, longitude: 73.8077 },
    { name: "Swargate Bus Terminus", latitude: 18.5018, longitude: 73.8636 },
    { name: "Viman Nagar (Phoenix)", latitude: 18.5679, longitude: 73.9143 },
    { name: "Pune Station", latitude: 18.5284, longitude: 73.8739 },
    { name: "Deccan Gymkhana", latitude: 18.5173, longitude: 73.8415 },
  ],
};

export default function RouteAdvisorySection({
  currentCity = "Mumbai",
  onOpenLiveCamera,
}: RouteAdvisorySectionProps) {
  const city = currentCity.includes("Pune") ? "Pune" : "Mumbai";

  // Form State
  const [origin, setOrigin] = useState<LatLngPoint>(
    CITY_LANDMARKS[city][0] || { latitude: 19.1197, longitude: 72.8464, name: "Andheri West" }
  );
  const [destination, setDestination] = useState<LatLngPoint>(
    CITY_LANDMARKS[city][1] || { latitude: 19.0601, longitude: 72.8550, name: "Bandra Kurla Complex" }
  );
  const [horizonHours, setHorizonHours] = useState<number>(3);
  const [toleranceMeters, setToleranceMeters] = useState<number>(250);
  const [preferAlternatives, setPreferAlternatives] = useState<boolean>(true);
  const [gpsLoading, setGpsLoading] = useState<boolean>(false);
  const [gpsError, setGpsError] = useState<string | null>(null);

  // Presets
  const [presets, setPresets] = useState<RoutePreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>("");

  // Results State
  const [comparison, setComparison] = useState<RouteComparisonResponse | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSort, setActiveSort] = useState<"recommended" | "fastest" | "shortest">("recommended");

  // Map Refs
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const routesLayerGroupRef = useRef<L.LayerGroup | null>(null);
  const hazardsLayerGroupRef = useRef<L.LayerGroup | null>(null);

  // Fetch presets for current city
  useEffect(() => {
    let mounted = true;
    apiClient.getRoutePresets(city)
      .then((data) => {
        if (mounted) {
          setPresets(data);
          if (data.length > 0) {
            setSelectedPresetId(data[0].id);
          }
        }
      })
      .catch((err) => console.warn("Failed to load route presets:", err));
    return () => { mounted = false; };
  }, [city]);

  // Initial calculation on load or when city changes
  useEffect(() => {
    const landmarks = CITY_LANDMARKS[city];
    if (landmarks && landmarks.length >= 2) {
      setOrigin(landmarks[0]);
      setDestination(landmarks[1]);
      calculateRoutes(landmarks[0], landmarks[1]);
    }
  }, [city]);

  // Request browser GPS
  const handleUseCurrentLocation = () => {
    setGpsLoading(true);
    setGpsError(null);
    if (!navigator.geolocation) {
      setGpsError("Geolocation is not supported by your browser.");
      setGpsLoading(false);
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const userPt: LatLngPoint = {
          latitude: parseFloat(pos.coords.latitude.toFixed(5)),
          longitude: parseFloat(pos.coords.longitude.toFixed(5)),
          name: "My Current Location (GPS)",
        };
        setOrigin(userPt);
        setSelectedPresetId("");
        setGpsLoading(false);
        calculateRoutes(userPt, destination);
      },
      (err) => {
        setGpsError(`GPS Access Denied: ${err.message}. Using selected landmark.`);
        setGpsLoading(false);
      },
      { timeout: 8000, enableHighAccuracy: true }
    );
  };

  // Calculate routes
  const calculateRoutes = async (startPoint: LatLngPoint, endPoint: LatLngPoint) => {
    setLoading(true);
    setError(null);
    try {
      const payload: RouteRequest = {
        city,
        origin: startPoint,
        destination: endPoint,
        prefer_alternatives: preferAlternatives,
        tolerance_meters: toleranceMeters,
        horizon_hours: horizonHours,
      };

      const resp = await apiClient.getRouteRecommendations(payload);
      setComparison(resp);
      if (resp.routes.length > 0) {
        setSelectedRouteId(resp.recommended_route_id || resp.routes[0].route_id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Routing calculation failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Preset selection handler
  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId);
    const p = presets.find((x) => x.id === presetId);
    if (p) {
      setOrigin(p.origin);
      setDestination(p.destination);
      calculateRoutes(p.origin, p.destination);
    }
  };

  // Swap Origin and Destination
  const handleSwapWaypoints = () => {
    const temp = origin;
    setOrigin(destination);
    setDestination(temp);
    calculateRoutes(destination, temp);
  };

  // Map Initialization
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const initialCenter: [number, number] = city === "Pune" ? [18.5204, 73.8567] : [19.0760, 72.8777];
    const map = L.map(mapContainerRef.current, {
      center: initialCenter,
      zoom: 13,
      zoomControl: true,
      attributionControl: true,
    });

    L.tileLayer(appConfig.mapTileUrl, {
      attribution: appConfig.mapAttribution,
      maxZoom: 19,
    }).addTo(map);

    routesLayerGroupRef.current = L.layerGroup().addTo(map);
    hazardsLayerGroupRef.current = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Map Layers whenever comparison or selected route changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    const routesGroup = routesLayerGroupRef.current;
    const hazardsGroup = hazardsLayerGroupRef.current;
    if (!map || !routesGroup || !hazardsGroup || !comparison) return;

    routesGroup.clearLayers();
    hazardsGroup.clearLayers();

    const allRouteBounds: L.LatLngBounds = L.latLngBounds([]);

    // 1. Draw Origin and Destination Markers
    const originIcon = L.divIcon({
      className: "custom-route-marker origin",
      html: `<div class="route-pin start" title="Start Point">📍<span>START</span></div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 36],
    });

    const destIcon = L.divIcon({
      className: "custom-route-marker dest",
      html: `<div class="route-pin end" title="Destination">🏁<span>END</span></div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 36],
    });

    const origMarker = L.marker([origin.latitude, origin.longitude], { icon: originIcon }).addTo(routesGroup);
    origMarker.bindPopup(`<b>Start Point:</b><br/>${origin.name || "Origin"}`);

    const destMarker = L.marker([destination.latitude, destination.longitude], { icon: destIcon }).addTo(routesGroup);
    destMarker.bindPopup(`<b>Destination:</b><br/>${destination.name || "Destination"}`);

    allRouteBounds.extend([origin.latitude, origin.longitude]);
    allRouteBounds.extend([destination.latitude, destination.longitude]);

    // 2. Draw Route Polylines
    comparison.routes.forEach((rt) => {
      const isSelected = rt.route_id === selectedRouteId;
      const isRec = rt.is_recommended;

      // Color scheme based on risk
      let strokeColor = "#3b82f6"; // Blue default
      if (rt.risk_category === "HIGH_HAZARD") {
        strokeColor = "#ef4444"; // Red
      } else if (rt.risk_category === "ELEVATED_RISK") {
        strokeColor = "#f59e0b"; // Amber
      } else if (isRec) {
        strokeColor = "#10b981"; // Green/Teal for lower risk
      }

      // Base Polyline
      const polyline = L.polyline(rt.coordinates, {
        color: isSelected ? strokeColor : "#94a3b8",
        weight: isSelected ? 6 : 4,
        opacity: isSelected ? 0.95 : 0.45,
        dashArray: isSelected ? undefined : "6, 8",
        lineCap: "round",
        lineJoin: "round",
      }).addTo(routesGroup);

      // Click to select route
      polyline.on("click", () => {
        setSelectedRouteId(rt.route_id);
      });

      polyline.bindTooltip(
        `<b>${rt.summary_name}</b><br/>${rt.duration_minutes} min · ${rt.distance_km} km<br/>Risk: ${rt.risk_category}`,
        { sticky: true }
      );

      rt.coordinates.forEach((coord) => allRouteBounds.extend(coord));

      // 3. Draw Hazards for Selected Route
      if (isSelected && rt.hazards) {
        rt.hazards.forEach((hz) => {
          const isVerified = hz.hazard_type === "VERIFIED_WATERLOGGING";
          const isAi = hz.hazard_type === "PENDING_AI_DETECTION";
          const iconColor = isVerified ? "#dc2626" : isAi ? "#f97316" : "#eab308";
          const iconChar = isVerified ? "🌊" : isAi ? "📸" : "⚠️";

          const hazardIcon = L.divIcon({
            className: "custom-hazard-pin",
            html: `<div class="hazard-dot" style="background:${iconColor}">${iconChar}</div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13],
          });

          const hzMarker = L.marker([hz.latitude, hz.longitude], { icon: hazardIcon }).addTo(hazardsGroup);
          hzMarker.bindPopup(`
            <div class="route-hazard-popup">
              <strong style="color:${iconColor}">${hz.hazard_type.replace(/_/g, " ")}</strong>
              <p><b>${hz.location_name}</b></p>
              <small>${hz.description}</small>
              <div style="margin-top:6px; font-size:11px;">
                Distance to road: <b>${hz.distance_to_route_meters}m</b><br/>
                Hazard Impact: <b>+${hz.risk_points_contributed} pts</b>
              </div>
            </div>
          `);
        });
      }
    });

    if (allRouteBounds.isValid()) {
      map.fitBounds(allRouteBounds, { padding: [40, 40], maxZoom: 15 });
    }
  }, [comparison, selectedRouteId, origin, destination]);

  // Selected route object
  const selectedRoute = useMemo(() => {
    if (!comparison) return null;
    return comparison.routes.find((r) => r.route_id === selectedRouteId) || comparison.routes[0] || null;
  }, [comparison, selectedRouteId]);

  // Sorted routes according to tab filter
  const sortedRoutes = useMemo(() => {
    if (!comparison) return [];
    const list = [...comparison.routes];
    if (activeSort === "recommended") {
      return list.sort((a, b) => a.risk_score - b.risk_score || a.duration_minutes - b.duration_minutes);
    }
    if (activeSort === "fastest") {
      return list.sort((a, b) => a.duration_minutes - b.duration_minutes);
    }
    if (activeSort === "shortest") {
      return list.sort((a, b) => a.distance_km - b.distance_km);
    }
    return list;
  }, [comparison, activeSort]);

  return (
    <main className="route-advisory-page">
      {/* Title & Headline */}
      <div className="page-title">
        <div>
          <div className="eyebrow">MONSOON RESPONSE INTELLIGENCE · WATERLOGGING-AWARE ROUTING</div>
          <h1>Route Advisory & Hazard Avoidance</h1>
          <p>
            Evaluate alternative travel corridors across {city}. Compare travel times, distances,
            and known waterlogging hazards before you travel.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            className="outline"
            onClick={onOpenLiveCamera}
            style={{ background: "#f0fdf4", borderColor: "#16a34a", color: "#15803d", fontWeight: 700 }}
          >
            📸 Field Report AI
          </button>
          <span className="badge amber">ADVISORY ONLY</span>
        </div>
      </div>

      {/* Safety Banner */}
      <div className="route-safety-banner">
        <span className="banner-icon">⚠️</span>
        <div>
          <strong>Safety Critical: Do Not Drive Into Floodwater</strong>
          <p>
            "Lower known risk" indicates fewer recorded waterlogging incidents in system records at the time of calculation.
            It does not guarantee a road is dry or impassable. Monsoon water levels can rise rapidly.
          </p>
        </div>
      </div>

      <div className="route-workspace-grid">
        {/* Left Column: Form & Route Cards */}
        <div className="route-controls-column">
          {/* Preset Corridor Selector */}
          <div className="route-card-panel">
            <label className="route-label">
              <span>COMMUTER CORRIDOR PRESETS ({city})</span>
              <select
                className="route-select"
                value={selectedPresetId}
                onChange={(e) => handleSelectPreset(e.target.value)}
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            {selectedPresetId && (
              <small className="route-preset-desc">
                {presets.find((x) => x.id === selectedPresetId)?.corridor_description}
              </small>
            )}
          </div>

          {/* Waypoints Selection Form */}
          <div className="route-card-panel">
            <div className="waypoints-container">
              {/* Origin */}
              <div className="waypoint-row">
                <div className="waypoint-badge origin">A</div>
                <div className="waypoint-inputs">
                  <div className="waypoint-header">
                    <label>Starting Point</label>
                    <button
                      type="button"
                      className="btn-gps-locate"
                      onClick={handleUseCurrentLocation}
                      disabled={gpsLoading}
                    >
                      {gpsLoading ? "Locating…" : "📍 Use My GPS"}
                    </button>
                  </div>
                  <input
                    type="text"
                    className="route-input"
                    value={origin.name || `${origin.latitude}, ${origin.longitude}`}
                    onChange={(e) => setOrigin({ ...origin, name: e.target.value })}
                  />
                  {/* Quick landmark chips */}
                  <div className="landmark-chips">
                    {CITY_LANDMARKS[city]?.slice(0, 4).map((lm) => (
                      <button
                        key={lm.name || `${lm.latitude}-${lm.longitude}`}
                        type="button"
                        className={origin.name === lm.name ? "active" : ""}
                        onClick={() => {
                          setOrigin(lm);
                          calculateRoutes(lm, destination);
                        }}
                      >
                        {(lm.name || "").split(" ")[0]}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Swap Button */}
              <div className="swap-waypoints-divider">
                <button
                  type="button"
                  className="btn-swap-waypoints"
                  onClick={handleSwapWaypoints}
                  title="Swap Starting Point and Destination"
                >
                  ⇅
                </button>
              </div>

              {/* Destination */}
              <div className="waypoint-row">
                <div className="waypoint-badge destination">B</div>
                <div className="waypoint-inputs">
                  <div className="waypoint-header">
                    <label>Destination</label>
                  </div>
                  <input
                    type="text"
                    className="route-input"
                    value={destination.name || `${destination.latitude}, ${destination.longitude}`}
                    onChange={(e) => setDestination({ ...destination, name: e.target.value })}
                  />
                  {/* Quick landmark chips */}
                  <div className="landmark-chips">
                    {CITY_LANDMARKS[city]?.slice(2, 6).map((lm) => (
                      <button
                        key={lm.name || `${lm.latitude}-${lm.longitude}`}
                        type="button"
                        className={destination.name === lm.name ? "active" : ""}
                        onClick={() => {
                          setDestination(lm);
                          calculateRoutes(origin, lm);
                        }}
                      >
                        {(lm.name || "").split(" ")[0]}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {gpsError && <div className="route-alert-warn">{gpsError}</div>}

            {/* Additional parameters */}
            <div className="route-params-row">
              <label>
                <span>Horizon</span>
                <select
                  value={horizonHours}
                  onChange={(e) => {
                    setHorizonHours(+e.target.value);
                    calculateRoutes(origin, destination);
                  }}
                >
                  <option value={1}>+1 hour</option>
                  <option value={3}>+3 hours</option>
                  <option value={6}>+6 hours</option>
                </select>
              </label>

              <label>
                <span>Hazard Radius</span>
                <select
                  value={toleranceMeters}
                  onChange={(e) => {
                    setToleranceMeters(+e.target.value);
                    calculateRoutes(origin, destination);
                  }}
                >
                  <option value={150}>150 m</option>
                  <option value={250}>250 m (Standard)</option>
                  <option value={500}>500 m (Wide buffer)</option>
                </select>
              </label>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={preferAlternatives}
                  onChange={(e) => {
                    setPreferAlternatives(e.target.checked);
                    calculateRoutes(origin, destination);
                  }}
                />
                <span>Alternatives</span>
              </label>
            </div>

            <button
              className="cta route-calc-btn"
              disabled={loading}
              onClick={() => calculateRoutes(origin, destination)}
            >
              {loading ? "Calculating Live Route Risk…" : "🔍 Compare Alternative Routes"}
            </button>
          </div>

          {/* Route Comparison List */}
          <div className="route-comparison-header">
            <h3>Candidate Travel Corridors ({sortedRoutes.length})</h3>
            <div className="route-sort-tabs">
              <button
                className={activeSort === "recommended" ? "active" : ""}
                onClick={() => setActiveSort("recommended")}
              >
                Lower Risk
              </button>
              <button
                className={activeSort === "fastest" ? "active" : ""}
                onClick={() => setActiveSort("fastest")}
              >
                Fastest
              </button>
              <button
                className={activeSort === "shortest" ? "active" : ""}
                onClick={() => setActiveSort("shortest")}
              >
                Shortest
              </button>
            </div>
          </div>

          {error && <div className="route-alert-error">Failed to calculate routes: {error}</div>}

          <div className="routes-cards-stack">
            {sortedRoutes.map((rt) => {
              const isSelected = rt.route_id === selectedRouteId;
              const isLowerRisk = rt.risk_category === "LOWER_KNOWN_RISK";
              const isHigh = rt.risk_category === "HIGH_HAZARD";

              return (
                <div
                  key={rt.route_id}
                  className={`route-item-card ${isSelected ? "selected" : ""} ${isLowerRisk ? "low-risk" : isHigh ? "high-risk" : ""}`}
                  onClick={() => setSelectedRouteId(rt.route_id)}
                >
                  <div className="route-item-top">
                    <div>
                      {rt.is_recommended && (
                        <span className="badge green" style={{ marginBottom: "4px" }}>
                          RECOMMENDED ROUTE
                        </span>
                      )}
                      <h4>{rt.summary_name}</h4>
                    </div>
                    <span className={`risk-badge ${rt.risk_category.toLowerCase()}`}>
                      {rt.risk_category.replace(/_/g, " ")}
                    </span>
                  </div>

                  <div className="route-item-stats">
                    <span>
                      ⏱ <b>{rt.duration_minutes} min</b>
                    </span>
                    <span>
                      📏 <b>{rt.distance_km} km</b>
                    </span>
                    <span>
                      ⚠️ <b>{rt.hazard_count} hazards</b>
                    </span>
                  </div>

                  <p className="route-rec-reason">{rt.recommendation_reason}</p>

                  <div className="route-hazard-pills">
                    {rt.verified_waterlogging_count > 0 && (
                      <span className="hazard-pill danger">
                        🌊 {rt.verified_waterlogging_count} Verified Inundation
                      </span>
                    )}
                    {rt.pending_ai_reports_count > 0 && (
                      <span className="hazard-pill warning">
                        📸 {rt.pending_ai_reports_count} AI Flood Reports
                      </span>
                    )}
                    {rt.rainfall_watch_count > 0 && (
                      <span className="hazard-pill info">
                        💧 {rt.rainfall_watch_count} Rainfall Alert
                      </span>
                    )}
                    {rt.hazard_count === 0 && (
                      <span className="hazard-pill safe">
                        ✓ 0 known recorded hazards on corridor
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Interactive Map & Selected Route Detail */}
        <div className="route-map-column">
          <div className="route-map-container" ref={mapContainerRef} />

          {/* Selected Route Detailed Hazard Inspector */}
          {selectedRoute && (
            <div className="selected-route-inspector">
              <div className="inspector-head">
                <div>
                  <div className="inspector-tag">SELECTED CORRIDOR ANALYSIS</div>
                  <h3>{selectedRoute.summary_name}</h3>
                </div>
                <div className="inspector-quick-metrics">
                  <span><b>{selectedRoute.duration_minutes}</b> min</span>
                  <span><b>{selectedRoute.distance_km}</b> km</span>
                  <span className={`risk-chip ${selectedRoute.risk_category.toLowerCase()}`}>
                    {selectedRoute.risk_category.replace(/_/g, " ")} ({selectedRoute.risk_score} pts)
                  </span>
                </div>
              </div>

              {/* Hazard Breakdown List */}
              <div className="inspector-hazards-list">
                <h4>Identified Hazards Along Corridor ({selectedRoute.hazards.length})</h4>
                {selectedRoute.hazards.length === 0 ? (
                  <div className="no-hazards-box">
                    <p>✓ No verified waterlogging incidents or rainfall watches detected within {toleranceMeters}m of this route.</p>
                    <small>Remember to exercise caution during heavy cloudbursts as drains may saturate without prior reporting.</small>
                  </div>
                ) : (
                  <div className="hazards-table">
                    {selectedRoute.hazards.map((h, i) => (
                      <div key={i} className="hazard-table-row">
                        <div className="hz-icon">
                          {h.hazard_type === "VERIFIED_WATERLOGGING" ? "🌊" : h.hazard_type === "PENDING_AI_DETECTION" ? "📸" : "⚠️"}
                        </div>
                        <div className="hz-info">
                          <strong>{h.location_name}</strong>
                          <small>{h.description}</small>
                        </div>
                        <div className="hz-metrics">
                          <span>{h.distance_to_route_meters}m off route</span>
                          <b>+{h.risk_points_contributed} pts</b>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="inspector-footer">
                <small>
                  Source: {selectedRoute.data_source} · Freshness: {selectedRoute.data_freshness} · Horizon: +{horizonHours}h
                </small>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
