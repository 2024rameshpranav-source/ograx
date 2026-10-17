import { useEffect, useRef, useState, useMemo } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { appConfig, hasBackend } from "./config";
import {
  areaCentres,
  cityForArea,
  defaultArea,
  type City,
  type RoadSegment,
  getSegmentsForArea,
  calculateSegmentPrediction,
} from "./data/geography";
import { authService } from "./services/auth";
import { apiClient } from "./services/api";
import { reportService, type DemoReport } from "./services/reports";
import OperationalPictureSection from "./components/OperationalPictureSection";
import MumbaiScreeningSection from "./components/MumbaiScreeningSection";
import LiveCameraModal from "./components/LiveCameraModal";
import IncidentIntelligenceSection from "./components/IncidentIntelligenceSection";
import RouteAdvisorySection from "./components/RouteAdvisorySection";


const navGroups = [
  ["MONITOR", ["Waterlogging Intelligence", "Forecast Explorer", "Geographic Coverage"]],
  ["COMMUNITY", ["Citizen Reports", "Incident Timeline"]],
  ["RESPONSE", ["Response Intelligence", "Route Advisory"]],
  ["INTELLIGENCE", ["Intelligence Centre", "AI Incident Intelligence", "Model Performance"]],
  ["SYSTEM", ["Settings"]],
] as const;
const loadReports=()=>reportService.list();
const risks = ["Low", "Moderate", "High", "Severe"];
const riskClass: Record<string, string> = { Low: "low", Moderate: "moderate", High: "high", Severe: "severe" };

function Icon({ children }: { children: string }) { return <span className="icon">{children}</span> }
function Badge({ children, tone = "blue" }: { children: React.ReactNode; tone?: string }) { return <span className={`badge ${tone}`}>{children}</span> }
function formatRiskCategoryTitle(category: string, probability?: number | null): string {
  const upper = (category || "").toUpperCase();
  if (upper.includes("NO_RAINFALL") || upper.includes("NO_SIGNAL")) {
    return "NO RAINFALL SIGNAL";
  }
  if (upper.includes("LOW_RAINFALL")) {
    return "LOW RAINFALL SIGNAL";
  }
  if (upper.includes("RAINFALL_WATCH")) {
    return "RAINFALL WATCH";
  }
  return upper;
}

function formatRiskBadgeText(category: string): string {
  const upper = (category || "").toUpperCase();
  if (upper.includes("NO_RAINFALL") || upper.includes("NO_SIGNAL") || upper.startsWith("NO_")) {
    return "CLEAR";
  }
  if (upper.includes("LOW_RAINFALL")) {
    return "LOW";
  }
  if (upper.includes("WATCH")) {
    return "WATCH";
  }
  if (upper.includes("SEVERE")) {
    return "SEVERE";
  }
  if (upper.includes("HIGH")) {
    return "HIGH";
  }
  if (upper.includes("MODERATE") || upper.includes("MOD")) {
    return "MOD";
  }
  return upper.slice(0, 4);
}

function formatProbabilityText(probability?: number | null): string {
  if (probability !== null && probability !== undefined && !isNaN(probability)) {
    return `${probability}%`;
  }
  return "0%";
}

function Spark({ values, color = "#dc4d32" }: { values: (number | null | undefined)[]; color?: string }) {
  const pts = values.map((v, i) => `${i * 28},${38 - Math.min(35, (v || 0) * 0.35)}`).join(" ");
  return <svg className="spark" viewBox="0 0 140 42"><polyline points={pts} fill="none" stroke={color} strokeWidth="2.5" /><polyline points={`0,42 ${pts} 140,42`} fill={color} opacity=".08" /></svg>
}

function Map({
  horizon,
  onSelect,
  layers,
  area = defaultArea,
  userLocation,
  reportsList,
  onReportClick,
  focusCoords,
  segments: propSegments,
  selectedSegmentId,
  onSelectSegment,
}: {
  horizon: number;
  onSelect?: () => void;
  layers: string[];
  area?: string;
  userLocation?: { lat: number; lng: number; accuracy?: number } | null;
  reportsList?: DemoReport[];
  onReportClick?: (report: DemoReport) => void;
  focusCoords?: [number, number] | null;
  segments?: RoadSegment[];
  selectedSegmentId?: string;
  onSelectSegment?: (segment: RoadSegment) => void;
}) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const overlay = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!node.current || map.current) return;
    map.current = L.map(node.current, { zoomControl: false, attributionControl: true }).setView(areaCentres[area] || areaCentres[defaultArea], 14);
    L.tileLayer(appConfig.mapTileUrl, { attribution: appConfig.mapAttribution, maxZoom: 19 }).addTo(map.current);
    L.control.zoom({ position: "bottomright" }).addTo(map.current);
    return () => { map.current?.remove(); map.current = null };
  }, []);

  useEffect(() => {
    if (!focusCoords) {
      map.current?.setView(areaCentres[area] || areaCentres[defaultArea], 14);
    }
  }, [area, focusCoords]);

  useEffect(() => {
    if (focusCoords && map.current) {
      map.current.setView(focusCoords, 16);
    }
  }, [focusCoords]);

  useEffect(() => {
    if (!map.current) return;
    overlay.current?.remove();
    const group = L.layerGroup().addTo(map.current);
    overlay.current = group;

    const roadSegments = propSegments || (area ? getSegmentsForArea(area) : []);
    const colors: Record<string, string> = {
      Low: "#0F9D9A",
      Moderate: "#F2A60C",
      High: "#E85D4A",
      Severe: "#991B1B",
    };

    if (layers.includes("Predicted risk")) {
      roadSegments.forEach((s) => {
        const pred = calculateSegmentPrediction(s, horizon);
        const color = colors[pred.category] || "#0F9D9A";
        const isSelected = s.id === selectedSegmentId;

        // Outer halo / selection border
        if (isSelected) {
          L.polyline(s.path as L.LatLngExpression[], {
            color: "#0284c7",
            weight: 14,
            opacity: 0.9,
          }).addTo(group);
        }

        // Crisp white backing
        L.polyline(s.path as L.LatLngExpression[], {
          color: "#ffffff",
          weight: isSelected ? 8 : 6,
          opacity: 0.95,
        }).addTo(group);

        // Colored risk polyline
        const line = L.polyline(s.path as L.LatLngExpression[], {
          color: color,
          weight: isSelected ? 5 : 4,
          opacity: 0.95,
        });

        line.bindTooltip(
          `<strong>${s.id} · ${s.name}</strong><br/>` +
          `Predicted Risk: <strong>${pred.category.toUpperCase()} (${pred.probability}%)</strong> · +${horizon}h<br/>` +
          `Elevation: ${s.elevation_m}m · Drainage: ${Math.round(s.drainage_capacity_ratio * 100)}%`
        );

        line.on("click", () => {
          if (onSelectSegment) onSelectSegment(s);
          if (onSelect) onSelect();
        });

        line.addTo(group);
      });
    }

    if (layers.includes("Citizen reports")) {
      const activeReports = reportsList || loadReports();
      if (activeReports && activeReports.length > 0) {
        activeReports.forEach((r) => {
          const isGps = r.coordinateSource === "gps";
          const markerColor = r.severity === "Severe" ? "#991B1B" : r.severity === "High" ? "#E85D4A" : r.severity === "Moderate" ? "#F2A60C" : "#0F9D9A";
          const marker = L.circleMarker([r.latitude, r.longitude], {
            radius: 8,
            color: "#ffffff",
            weight: 2,
            fillColor: markerColor,
            fillOpacity: 0.95,
          });
          const sourceText = isGps ? `📍 Live GPS (±${r.accuracyM ? Math.round(r.accuracyM) + 'm' : 'accurate'})` : "⌖ Area centre pin";
          marker.bindTooltip(`<strong>${r.landmark}</strong><br/>${r.severity} · ${r.status}<br/>${sourceText}${r.photoUrl ? '<br/>📷 Photo attached' : ''}`);
          marker.on("click", () => {
            if (onReportClick) onReportClick(r);
            else if (onSelect) onSelect();
          });
          marker.addTo(group);
        });
      } else {
        const centre = L.latLng(areaCentres[area] || areaCentres[defaultArea]);
        const at = (y: number, x: number): L.LatLngExpression => [centre.lat + y, centre.lng + x];
        [at(0,.002),at(.006,-.007),at(-.004,.008)].forEach((p, i) =>
          L.circleMarker(p as L.LatLngExpression, { radius: 8, color: "#fff", weight: 2, fillColor: "#6d4aaa", fillOpacity: 1 }).bindTooltip(`${i ? "Unverified" : "Corroborated"} citizen report`).on("click", () => { if (onSelect) onSelect(); }).addTo(group)
        );
      }
    }

    if (userLocation) {
      L.circle([userLocation.lat, userLocation.lng], {
        radius: Math.max(userLocation.accuracy || 15, 10),
        color: "#0284c7",
        fillColor: "#38bdf8",
        fillOpacity: 0.16,
        weight: 1.5,
        dashArray: "4, 4",
      }).addTo(group);

      const userMarker = L.circleMarker([userLocation.lat, userLocation.lng], {
        radius: 9,
        color: "#ffffff",
        weight: 3,
        fillColor: "#0284c7",
        fillOpacity: 1,
      });
      userMarker.bindTooltip(`<strong>📍 Your Live Position</strong><br/>Accuracy: ±${Math.round(userLocation.accuracy || 0)}m`);
      userMarker.addTo(group);
    }
  }, [horizon, layers, onSelect, area, userLocation, reportsList, onReportClick, propSegments, selectedSegmentId, onSelectSegment]);

  return <div className="map" aria-label="Interactive OpenStreetMap risk map">
    <div className="leaflet-host" ref={node} />
    <div className="map-search"><Icon>⌖</Icon><span>Search road, ward or coordinates</span><kbd>⌘ K</kbd></div>
    <div className="map-meta"><Badge tone="blue">PHYSICAL HEURISTIC MODEL</Badge><span>Updated 14:32 · 200 m</span></div>
  </div>;
}

function LayerControl({ layers, setLayers }: { layers: string[]; setLayers: (v: string[]) => void }) {
  const all = ["Predicted risk", "Citizen reports", "Rainfall radar", "Terrain", "Historical incidents"];
  return <div className="layer-control"><div className="section-title">Map layers <span>2 active</span></div>{all.map(x =>
    <label key={x}><input type="checkbox" checked={layers.includes(x)} onChange={() => setLayers(layers.includes(x) ? layers.filter(l => l !== x) : [...layers, x])} /><span>{x}</span></label>
  )}</div>
}

function Sidebar({ page, setPage, area, onArea, user, logout }: { page: string; setPage: (p: string) => void; area: string; onArea: () => void; user:string; logout:()=>void }) {
  const [profileOpen,setProfileOpen]=useState(false);
  const icons: Record<string,string> = {
    "Waterlogging Intelligence":"⌂",
    "Forecast Explorer":"↗",
    "Geographic Coverage":"⌖",
    "Citizen Reports":"◉",
    "Incident Timeline":"◷",
    "Response Intelligence":"△",
    "Route Advisory":"⌁",
    "Intelligence Centre":"◎",
    "AI Incident Intelligence":"📷",
    "Model Performance":"▥",
    "Settings":"◇"
  };
  return <aside className="sidebar">
    <div className="brand"><span className="brandmark">A</span><span>AquaSignal<small>WATER INTELLIGENCE</small></span></div>
    <nav>{navGroups.map(([group,items])=><div className="nav-group" key={group}><div className="nav-label">{group}</div>{items.map(n=><button className={page===n?"active":""} onClick={()=>setPage(n)} key={n}><Icon>{icons[n]}</Icon><span>{n}</span>{n==="Citizen Reports"&&<b>7</b>}{n==="AI Incident Intelligence"&&<b style={{ background: "#0ea5e9" }}>AI</b>}</button>)}</div>)}</nav>
    <button className="area-card" onClick={onArea}><div className="pulse" /><div><small>GEOGRAPHIC WORKSPACE</small><strong>{area}</strong><span>Demonstration coverage · Change →</span></div></button>
    <div className="side-profile"><button onClick={()=>setProfileOpen(!profileOpen)}><span className="profile-avatar">{user.slice(0,2).toUpperCase()}</span><span><strong>{user}</strong><small>Demo account · Manage</small></span><i>⌃</i></button>{profileOpen&&<div className="profile-menu"><button onClick={()=>setPage("Settings")}>⚙ Account settings</button><button onClick={logout}>↪ Log Out</button><small>Local demo session</small></div>}</div>
  </aside>
}

function Header({ horizon, setHorizon, live, setLive, onArea, area, user, logout, settings, onOpenLiveCamera }: { horizon: number; setHorizon: (n: number) => void; live: boolean; setLive: (v: boolean) => void; onArea: () => void; area: string; user:string; logout:()=>void; settings:()=>void; onOpenLiveCamera?: () => void }) {
  const [open,setOpen]=useState(false);
  return <header><button className="location" onClick={onArea}><Icon>⌖</Icon><span>{area}<small>Country → Region → City → Monitoring area</small></span><b>⌄</b></button>
    <div className="horizon compact"><span>Forecast</span><select value={horizon} onChange={e => setHorizon(+e.target.value)}>{[1,2,3,4,5,6].map(x => <option key={x} value={x}>+{x} hours</option>)}</select></div>
    <button
      className="env"
      style={{
        background: "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)",
        color: "#ffffff",
        fontWeight: 700,
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        cursor: "pointer",
        padding: "6px 12px",
        borderRadius: "6px",
        border: "1px solid #38bdf8",
      }}
      onClick={onOpenLiveCamera}
      title="Capture live camera photo and run Hugging Face flood verification"
    >
      <span>📸</span>
      <span>Live Camera Flood AI</span>
    </button>
    <button className={`env ${live ? "live" : ""}`} onClick={() => setLive(!live)}><i />{live ? "DATA UNAVAILABLE" : "DEMO MODE"}</button>
    <div className="fresh"><i /> Data fresh <small>Updated 2m ago</small></div>
    <button className="round" onClick={()=>alert("3 demonstration notifications: one escalation, two report updates.")}>◔<em>3</em></button><button className="avatar" onClick={()=>setOpen(!open)}>{user.slice(0,2).toUpperCase()}</button>{open&&<div className="header-profile"><strong>{user}</strong><small>Local demo account</small><button onClick={settings}>Account settings</button><button onClick={logout}>Log Out</button></div>}
  </header>
}

function DetailPanel({
  segment,
  prediction,
  horizon,
  close,
  analytics,
  area,
  loading,
  error,
}: {
  segment: RoadSegment;
  prediction: {
    probability: number;
    category: string;
    uncertainty: string;
    rainfallForecastMm: number;
    factors: { name: string; impact: string; weight: string }[];
    explanation?: string;
    modelId?: string;
    timestamp?: string;
    freshness?: string;
  };
  horizon: number;
  close: () => void;
  analytics: () => void;
  area: string;
  loading?: boolean;
  error?: string | null;
}) {
  const [explain, setExplain] = useState(false);
  const prob = prediction.probability;
  const cat = prediction.category.toUpperCase();

  return (
    <aside className="detail">
      <div className="detail-head">
        <div>
          <div className="panel-label">01 · LOCATION</div>
          <Badge tone="blue">PHYSICAL HEURISTIC</Badge>
          <h3>{segment.id} · {segment.name}</h3>
          <p>{segment.area} · {segment.grid} · +{horizon}h</p>
          {loading && <small style={{ color: "#0284c7", fontWeight: 600 }}>Refreshing location prediction…</small>}
          {error && <small style={{ color: "#ef4444" }}>{error}</small>}
        </div>
        <button onClick={close}>×</button>
      </div>

      <div className="panel-label">02 · PREDICTION</div>
      <div className="prob">
        <div>
          <span>Event probability</span>
          <strong>{prob !== null && prob !== undefined ? `${prob}%` : "0% (Clear)"}</strong>
          <small>
            Category:{" "}
            <b className={cat.includes("SEVERE") ? "severe" : cat.includes("HIGH") || cat.includes("WATCH") ? "high" : "blue"}>
              {formatRiskCategoryTitle(prediction.category, prob)}
            </b>
          </small>
        </div>
        <div className="gauge">
          <i style={{ width: `${prob ?? 0}%` }} />
        </div>
      </div>

      <div className="metric-grid">
        <div>
          <span>Model uncertainty</span>
          <strong>{prediction.uncertainty}</strong>
        </div>
        <div>
          <span>Prediction time</span>
          <strong>{prediction.timestamp ? new Date(prediction.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "14:32 UTC"}</strong>
        </div>
        <div>
          <span>Input freshness</span>
          <strong className="green">{prediction.freshness || "FRESH · 2m"}</strong>
        </div>
        <div>
          <span>Forecast horizon</span>
          <strong>+{horizon} hours</strong>
        </div>
      </div>

      <div className="panel-label">03 · WHY THIS LOCATION ({segment.id})</div>
      {prediction.factors.map((x) => (
        <div className="factor" key={x.name}>
          <span>
            {x.name}
            <small>{x.impact}</small>
          </span>
          <div>
            <i style={{ width: x.weight }} />
          </div>
        </div>
      ))}
      <button className="explain-btn" onClick={() => setExplain(true)}>
        ◎ Explain this prediction
      </button>

      <div className="panel-label">04 · COMMUNITY EVIDENCE</div>
      <div className="notice amber">
        <Icon>!</Icon>
        <div>
          <strong>Local corridor · {segment.grid}</strong>
          <span>{segment.historical_incident_count} historical waterlogging occurrences recorded. Live citizen verification active.</span>
        </div>
      </div>

      <div className="panel-label">05 · RECOMMENDED ACTION</div>
      <div className="advisory">
        <Badge tone={cat === "SEVERE" ? "red" : cat === "HIGH" ? "amber" : "blue"}>
          {cat === "SEVERE" ? "CRITICAL MITIGATION" : cat === "HIGH" ? "INSPECTION · HIGH PRIORITY" : "STANDARD MONITORING"}
        </Badge>
        <p>
          {cat === "SEVERE"
            ? "Immediate de-watering pump deployment and traffic diversion recommended. Low depression zone."
            : cat === "HIGH"
            ? "Verify drainage obstruction before escalation window. Route guidance is ADVISORY ONLY."
            : "Surface water within standard drainage threshold at current precipitation rates."}
        </p>
      </div>

      <button className="primary" onClick={analytics}>Open Forecast Explorer →</button>
      <small className="provenance">
        Physical Heuristic Demonstration v1.2 · Calibrated for local terrain & drainage · Reports do not alter probability · Not a certified operational flood model
      </small>

      {explain && (
        <div className="explain-drawer">
          <div className="detail-head">
            <div>
              <Badge tone="blue">PHYSICAL HEURISTIC AUDIT</Badge>
              <h3>Why {prob}% at +{horizon}h for {segment.id}?</h3>
            </div>
            <button onClick={() => setExplain(false)}>×</button>
          </div>
          <p>
            Calculated from {segment.name}'s specific terrain elevation ({segment.elevation_m}m AMSL),
            drainage capacity ({Math.round(segment.drainage_capacity_ratio * 100)}%), and forecast rainfall accumulation ({prediction.rainfallForecastMm} mm).
          </p>
          <div className="explain-row">
            <span>Terrain Elevation</span>
            <b>{segment.elevation_m}m AMSL ({segment.elevation_m <= 10.0 ? "Severe depression basin" : segment.elevation_m <= 15.0 ? "Moderate elevation" : "High ground"})</b>
          </div>
          <div className="explain-row">
            <span>Drainage Capacity</span>
            <b>{Math.round(segment.drainage_capacity_ratio * 100)}% ({segment.drainage_capacity_ratio < 0.5 ? "Sub-optimal / bottleneck" : "Adequate discharge"})</b>
          </div>
          <div className="explain-row">
            <span>Historical Incidents</span>
            <b>{segment.historical_incident_count} recorded waterlogging events</b>
          </div>
          <div className="explain-row">
            <span>Road Gradient</span>
            <b>{segment.road_gradient_pct}% slope</b>
          </div>
          <div className="explain-row">
            <span>Primary Local Factor</span>
            <b>{segment.primary_factor}</b>
          </div>
          <div className="notice blue">
            <Icon>i</Icon>
            <div>
              <strong>Uncertainty {prediction.uncertainty}</strong>
              <span>This prediction is computed deterministically from physical topography, drainage capacity, and weather forecasts. It is not an unvalidated black-box AI output.</span>
            </div>
          </div>
          <button className="primary" onClick={() => setExplain(false)}>Done</button>
        </div>
      )}
    </aside>
  );
}

function Dashboard({ horizon, setHorizon, go, area, onOpenLiveCamera }: { horizon: number; setHorizon: (n: number) => void; go: (p:string)=>void; area: string; onOpenLiveCamera?: () => void }) {
  const [detail, setDetail] = useState(true);
  const [layers, setLayers] = useState(["Predicted risk","Citizen reports"]);
  const [mumbaiMode, setMumbaiMode] = useState<"screening" | "map">("screening");

  const segments = useMemo(() => getSegmentsForArea(area), [area]);
  const [selectedSegment, setSelectedSegment] = useState<RoadSegment>(segments[0]);

  // When area changes, update selected segment to the first segment of the new area
  useEffect(() => {
    setSelectedSegment(segments[0]);
  }, [area, segments]);

  // Maintain prediction and synchronized 6-hour timeline
  const [predictionData, setPredictionData] = useState(() =>
    calculateSegmentPrediction(segments[0], horizon)
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const currentReqId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    // Development logging as specified in prompt item 5
    console.log("[AquaSignal:PredictionPipeline] Selected location & parameters:", {
      area,
      segmentId: selectedSegment.id,
      segmentName: selectedSegment.name,
      coords: selectedSegment.coords,
      elevation_m: selectedSegment.elevation_m,
      drainage_ratio: selectedSegment.drainage_capacity_ratio,
      horizon,
    });

    const localSync = calculateSegmentPrediction(selectedSegment, horizon);

    const city = cityForArea(area);
    Promise.all([
      apiClient.predict({
        city,
        location_id: selectedSegment.id,
        location_name: selectedSegment.name,
        latitude: selectedSegment.coords[0],
        longitude: selectedSegment.coords[1],
        forecast_horizon_hours: horizon,
        features: {
          rainfall_mm: 35.0,
          elevation_m: selectedSegment.elevation_m,
          drainage_capacity_ratio: selectedSegment.drainage_capacity_ratio,
          historical_incident_count: selectedSegment.historical_incident_count,
          road_gradient_pct: selectedSegment.road_gradient_pct,
        },
      }),
      apiClient.getForecastTimeline(
        city,
        selectedSegment.name,
        35.0,
        selectedSegment.id,
        selectedSegment.coords[0],
        selectedSegment.coords[1]
      ),
    ])
      .then(([predRes, timelineRes]) => {
        // Prevent stale responses overwriting newer selections
        if (currentReqId !== requestIdRef.current) return;

        console.log("[AquaSignal:PredictionPipeline] Backend prediction response:", {
          source: predRes.model_id,
          probability: predRes.risk_probability,
          category: predRes.risk_category,
          timelineSource: timelineRes.source,
          timelineCount: timelineRes.timeline.length,
        });

        const mappedTimeline = timelineRes.timeline.map((item) => ({
          hour: item.horizon_hours,
          category: (item.risk_category.charAt(0).toUpperCase() +
            item.risk_category.slice(1).toLowerCase()) as "Low" | "Moderate" | "High" | "Severe",
          probability: item.risk_probability,
          uncertainty: item.confidence_level,
          rainfallMm: item.rainfall_forecast_mm || 0,
        }));

        const activeItem = mappedTimeline[horizon - 1] || mappedTimeline[0];

        setPredictionData({
          probability: activeItem.probability,
          category: activeItem.category,
          uncertainty: activeItem.uncertainty,
          rainfallForecastMm: activeItem.rainfallMm,
          factors: localSync.factors,
          timeline: mappedTimeline,
        });
        setLoading(false);
      })
      .catch((err) => {
        if (currentReqId !== requestIdRef.current) return;
        console.warn("[AquaSignal:PredictionPipeline] Backend fetch error, using physical heuristic fallback:", err);
        setPredictionData(localSync);
        setLoading(false);
      });
  }, [area, selectedSegment, horizon]);

  const pune = area.startsWith("Pune");
  const currentRain = pune ? 10.0 : (predictionData?.rainfallForecastMm ?? 0.0);
  const kpiData = pune
    ? [
        ["High-risk locations", `${segments.filter(s => calculateSegmentPrediction(s, horizon, 10.0).probability >= 60).length}`, "Pune demo dataset", "high"],
        ["Severe-risk locations", `${segments.filter(s => calculateSegmentPrediction(s, horizon, 10.0).probability >= 80).length}`, "Review after +4h", "severe"],
        ["Pending reports", "4", "1 possible duplicate", "moderate"],
        ["Last successful update", "14:28", "6 minutes ago", "blue"],
      ]
    : [
        ["High-risk locations", `${segments.filter(s => calculateSegmentPrediction(s, horizon, currentRain).probability >= 60).length}`, "Mumbai dataset", "high"],
        ["Severe-risk locations", `${segments.filter(s => calculateSegmentPrediction(s, horizon, currentRain).probability >= 80).length}`, "Immediate review", "severe"],
        ["Pending reports", "7", "2 possible duplicates", "moderate"],
        ["Last successful update", "14:32", "2 minutes ago", "blue"],
      ];

  if (!pune && mumbaiMode === "screening") {
    return (
      <main>
        <div className="page-title">
          <div>
            <div className="eyebrow">MUMBAI HYDROLOGICAL INTELLIGENCE · 8 DESIGNATED CORRIDORS</div>
            <h1>Waterlogging Intelligence</h1>
            <p>{area} · Real-time precipitation screening (+1h, +3h, +6h) with Open-Meteo live forecast.</p>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button className="outline" onClick={() => setMumbaiMode("map")}>
              Area Segment Map →
            </button>
            <button className="outline" onClick={() => go("Forecast Explorer")}>
              Forecast Explorer →
            </button>
          </div>
        </div>

        <MumbaiScreeningSection
          selectedHorizon={horizon === 1 || horizon === 3 || horizon === 6 ? horizon : 3}
          onHorizonChange={setHorizon}
        />
      </main>
    );
  }

  return (
    <main>
      <div className="page-title">
        <div>
          <div className="eyebrow">UNIFIED MONITORING WORKSPACE · PHYSICAL HEURISTIC MODEL</div>
          <h1>Waterlogging Intelligence</h1>
          <p>Location-specific surface-water risk for {selectedSegment.name} ({area}) over the next {horizon} hours.</p>
        </div>
        {!pune && (
          <button className="outline" onClick={() => setMumbaiMode("screening")} style={{ background: "#f0f9ff", borderColor: "#0284c7", color: "#0369a1", fontWeight: 700 }}>
            💧 Open 8-Corridor Screening Engine
          </button>
        )}
        <button
          className="outline"
          onClick={() => onOpenLiveCamera?.()}
          style={{ background: "#f0fdf4", borderColor: "#16a34a", color: "#15803d", fontWeight: 700 }}
          title="Capture photo or upload field evidence to verify with Hugging Face AI"
        >
          📸 Live Camera AI Report
        </button>
        <button className="outline">↗ Export situation brief</button>
      </div>

      <section className="operational-snapshot">
        <div className="risk-overview">
          <div>
            <span>AREA RISK OVERVIEW</span>
            <strong className={
              predictionData.category.toUpperCase().includes("SEVERE") ? "severe" :
              predictionData.category.toUpperCase().includes("HIGH") || predictionData.category.toUpperCase().includes("WATCH") ? "orange" : "blue"
            }>
              {formatRiskCategoryTitle(predictionData.category, predictionData.probability)} ({
                predictionData.probability !== null && predictionData.probability !== undefined
                  ? `${predictionData.probability}%`
                  : "0mm Rain"
              })
            </strong>
            <small>{selectedSegment.name} · +{horizon}h · updated {pune ? "6" : "2"}m ago</small>
          </div>
          <div className="composition-bar" title="Monitored location composition">
            <i className="low" style={{ width: `${pune ? 42 : currentRain > 15 ? 34 : 85}%` }} />
            <i className="moderate" style={{ width: `${pune ? 31 : currentRain > 15 ? 29 : 15}%` }} />
            <i className="high" style={{ width: `${pune ? 21 : currentRain > 15 ? 27 : 0}%` }} />
            <i className="severe" style={{ width: `${pune ? 6 : currentRain > 15 ? 10 : 0}%` }} />
          </div>
          <div className="composition-legend">
            <span>Low {pune ? "42" : currentRain > 15 ? "34" : "85"}%</span>
            <span>Moderate {pune ? "31" : currentRain > 15 ? "29" : "15"}%</span>
            <span>High {pune ? "21" : currentRain > 15 ? "27" : "0"}%</span>
            <span>Severe {pune ? "6" : currentRain > 15 ? "10" : "0"}%</span>
          </div>
        </div>

        <div className="attention-queue">
          <div className="snapshot-title">
            Corridors requiring attention <button onClick={() => go("Response Intelligence")}>View queue →</button>
          </div>
          {segments.slice(0, 2).map((s, i) => {
            const sPred = calculateSegmentPrediction(s, horizon, currentRain);
            const isSevere = sPred.category === "Severe" || sPred.probability >= 80;
            const isHigh = sPred.category === "High" || sPred.probability >= 60;
            const isMod = sPred.category === "Moderate" || sPred.probability >= 35;
            const badgeClass = isSevere ? "severe" : isHigh ? "orange" : isMod ? "blue" : "moderate";

            return (
              <button
                onClick={() => {
                  setSelectedSegment(s);
                  setDetail(true);
                }}
                key={s.id}
              >
                <b>{i + 1}</b>
                <span>
                  <strong>{s.name}</strong>
                  <small>
                    <b className={badgeClass} style={{ marginRight: "4px" }}>
                      {formatRiskBadgeText(sPred.category)}
                    </b>
                    ({formatProbabilityText(sPred.probability)}) · {s.grid}
                  </small>
                </span>
                <i>View on map</i>
              </button>
            );
          })}
        </div>

        <div className="review-snapshot">
          <div className="snapshot-title">Report review queue</div>
          <div><strong>{kpiData[2][1]}</strong><span>Unverified</span></div>
          <div><strong>{pune ? "2" : "3"}</strong><span>Under review</span></div>
          <div><strong>{pune ? "1" : "2"}</strong><span>Corroborated</span></div>
          <button onClick={() => go("Citizen Reports")}>Review reports →</button>
        </div>

        <div className="forecast-change">
          <span>FORECAST CHANGE</span>
          <strong>
            {(() => {
              const p6 = predictionData.timeline[5]?.probability;
              const p1 = predictionData.timeline[0]?.probability;
              if (p6 !== null && p6 !== undefined && p1 !== null && p1 !== undefined) {
                const diff = p6 - p1;
                return diff >= 0 ? `↗ +${diff}%` : `↘ ${diff}%`;
              }
              const r6 = predictionData.timeline[5]?.rainfallMm ?? 0;
              const r1 = predictionData.timeline[0]?.rainfallMm ?? 0;
              const rDiff = Math.round((r6 - r1) * 10) / 10;
              return rDiff > 0 ? `↗ +${rDiff}mm` : `→ 0mm`;
            })()}
          </strong>
          <small>Change from +1h to +6h</small>
          <Spark values={predictionData.timeline.map(t => t.probability ?? t.rainfallMm ?? 0)} color="#e75b45" />
        </div>
      </section>

      <section className="risk-timeline">
        <div className="timeline-title">
          <span>
            <b>Rainfall-to-Risk Timeline</b>
            <small>Selected location: {selectedSegment.name} ({selectedSegment.id}) · {selectedSegment.grid}</small>
          </span>
          <Badge tone="blue">PHYSICAL HEURISTIC</Badge>
        </div>
        <div className="timeline-items">
          {predictionData.timeline.map((x, i) => {
            const isSevere = x.category.toUpperCase().includes("SEVERE") || (x.probability !== null && x.probability !== undefined && x.probability >= 80);
            const isHigh = x.category.toUpperCase().includes("HIGH") || x.category.toUpperCase().includes("WATCH") || (x.probability !== null && x.probability !== undefined && x.probability >= 60);
            const isMod = x.category.toUpperCase().includes("MOD") || (x.probability !== null && x.probability !== undefined && x.probability >= 35);
            const toneClass = isSevere ? "severe" : isHigh ? "high" : isMod ? "orange" : "moderate";

            return (
              <button
                className={horizon === i + 1 ? "active" : ""}
                onClick={() => setHorizon(i + 1)}
                key={i}
              >
                <small>+{i + 1} HOUR</small>
                <strong className={toneClass}>
                  {formatRiskBadgeText(x.category)}
                </strong>
                <span>
                  {formatProbabilityText(x.probability)} <em>+{x.rainfallMm}mm</em>
                </span>
                <i>uncertainty {x.uncertainty}</i>
              </button>
            );
          })}
        </div>
      </section>

      <div className={`workspace ${detail ? "" : "full"}`}>
        <section className="map-card">
          <div className="map-toolbar">
            <div className="horizon">
              <span>Prediction horizon</span>
              {[1, 2, 3, 4, 5, 6].map((x) => (
                <button
                  className={horizon === x ? "selected" : ""}
                  onClick={() => setHorizon(x)}
                  key={x}
                >
                  +{x}h
                </button>
              ))}
            </div>
            <button className="layers">▱ Layers</button>
          </div>
          <Map
            horizon={horizon}
            onSelect={() => setDetail(true)}
            layers={layers}
            area={area}
            segments={segments}
            selectedSegmentId={selectedSegment.id}
            onSelectSegment={(seg) => {
              setSelectedSegment(seg);
              setDetail(true);
            }}
          />
          <LayerControl layers={layers} setLayers={setLayers} />
          <div className="legend">
            <strong>Predicted risk</strong>
            {risks.map((r) => (
              <span key={r}>
                <i className={riskClass[r]} />
                {r}
              </span>
            ))}
          </div>
        </section>
        {detail && (
          <DetailPanel
            segment={selectedSegment}
            prediction={predictionData}
            horizon={horizon}
            area={area}
            loading={loading}
            error={error}
            close={() => setDetail(false)}
            analytics={() => go("Forecast Explorer")}
          />
        )}
      </div>

      <div className="intelligence-row">
        <section className="escalation-card">
          <div className="card-head">
            <div>
              <h3>Risk Escalation Detection</h3>
              <p>Locations predicted to cross a risk threshold</p>
            </div>
            <Badge tone="slate">ILLUSTRATIVE</Badge>
          </div>
          {segments.slice(0, 2).map((s, i) => {
            const pred1 = calculateSegmentPrediction(s, 1);
            const pred3 = calculateSegmentPrediction(s, 3);
            return (
              <div className="escalation-row" key={s.id}>
                <span className="rank">{i + 1}</span>
                <strong>
                  {s.name}
                  <small>{s.primary_factor}</small>
                </strong>
                <span>
                  {pred1.category.toUpperCase()} → <b>{pred3.category.toUpperCase()}</b>
                </span>
                <Badge tone={pred3.probability >= 80 ? "red" : "amber"}>
                  +3h · {pred3.probability >= 80 ? "IMMEDIATE" : "HIGH"} PRIORITY
                </Badge>
              </div>
            );
          })}
        </section>

        <section className="fingerprint">
          <div className="card-head">
            <div>
              <h3>Neighbourhood Risk Fingerprint</h3>
              <p>Topography & Drainage Profile · {selectedSegment.name}</p>
            </div>
            <Badge tone="blue">PHYSICAL METRICS</Badge>
          </div>
          {[
            ["Terrain Elevation", Math.min(100, Math.round(selectedSegment.elevation_m * 3)), `${selectedSegment.elevation_m}m AMSL`],
            ["Drainage Capacity", Math.round(selectedSegment.drainage_capacity_ratio * 100), `${Math.round(selectedSegment.drainage_capacity_ratio * 100)}% capacity`],
            ["Incident Density", Math.min(100, selectedSegment.historical_incident_count * 12), `${selectedSegment.historical_incident_count} events`],
            ["Road Gradient", Math.min(100, Math.round(selectedSegment.road_gradient_pct * 30)), `${selectedSegment.road_gradient_pct}% slope`],
          ].map((x) => (
            <div className="finger-row" key={x[0]}>
              <span>
                {x[0]}
                <small>{x[2]}</small>
              </span>
              <div>
                <i style={{ width: `${x[1]}%` }} />
              </div>
              <b>{x[1]}</b>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}

function Forecasts({area,horizon,setHorizon}:{area:string;horizon:number;setHorizon:(n:number)=>void}) {
  const city=cityForArea(area);
  const pune=city==="Pune";
  const evolution=pune?[31,39,48,57,68,74]:[36,47,59,69,77,85];

  if (!pune) {
    return (
      <main>
        <div className="page-title">
          <div>
            <div className="eyebrow">RULE-BASED SCREENING · UNVALIDATED PROTOTYPE · MUMBAI</div>
            <h1>Forecast Explorer</h1>
            <p>{area} · +1h, +3h, +6h rainfall screening against calibrated watch thresholds.</p>
          </div>
          <Badge tone="slate">NOT AN ML MODEL</Badge>
        </div>

        <MumbaiScreeningSection
          selectedHorizon={horizon === 1 || horizon === 3 || horizon === 6 ? horizon : 3}
          onHorizonChange={setHorizon}
        />
      </main>
    );
  }

  return <main><div className="page-title"><div><div className="eyebrow">MODEL OUTPUT · ILLUSTRATIVE · PUNE</div><h1>Forecast Explorer</h1><p>{area} · Select a horizon to update all visualisations.</p></div><Badge tone="slate">DEMONSTRATION DATA</Badge></div>
    <div className="forecast-selector">{[1,2,3,4,5,6].map(x=><button className={horizon===x?"active":""} onClick={()=>setHorizon(x)} key={x}>+{x}h <small>{evolution[x-1]}%</small></button>)}</div>
    <div className="analytics-grid"><section className="chart-card wide"><div className="card-head"><div><h3>High-risk locations over time</h3><p>Predicted locations by risk category</p></div><Badge>MODEL PREDICTION</Badge></div><div className="bar-chart">{[8,11,13,17,19,23].map((v,i)=><div key={i}><span>{v}</span><i style={{height:`${v*6}px`}}/><small>+{i+1}h</small></div>)}</div></section>
    <section className="chart-card"><div className="card-head"><div><h3>Risk distribution</h3><p>Locations at selected +{horizon}h horizon</p></div></div><div className="risk-bars">{risks.map((r,i)=><button key={r}><span><i className={riskClass[r]}/>{r}</span><div><i className={riskClass[r]} style={{width:`${[70-horizon*3,30+horizon*2,13+horizon*4,horizon*3][i]}%`}}/></div><b>{[52-horizon,18+horizon,8+horizon*2,horizon][i]}</b></button>)}</div></section>
    <section className="chart-card wide"><div className="card-head"><div><h3>Six-hour risk evolution</h3><p>Probability (%) with illustrative uncertainty band · R-042</p></div><div className="chart-legend"><span>━ Prediction</span><span>▒ Uncertainty</span></div></div><div className="evolution-chart"><div className="y-axis"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div>{evolution.map((v,i)=><button className={horizon===i+1?"selected":""} onClick={()=>setHorizon(i+1)} key={i}><i style={{height:`${v}%`}}/><b>{v}%</b><small>+{i+1}h</small></button>)}</div></section>
    <section className="chart-card quality"><h3>Rainfall–risk relationship</h3><p>Forecast rainfall (mm/h) and probability (%) use separate conceptual scales.</p><div className="dual-series">{[18,24,31,38,29,21].map((v,i)=><div key={i}><i style={{height:`${v*2}px`}}/><span style={{bottom:`${evolution[i]}%`}}>●</span><small>+{i+1}h</small></div>)}</div><div className="chart-legend"><span>▮ Rainfall mm/h</span><span>● Risk %</span></div></section>
    <section className="chart-card matrix-card"><div className="card-head"><div><h3>Risk Escalation Watch</h3><p>Roads × forecast horizons · Click a cell to select horizon</p></div><Badge tone="amber">MODEL-DERIVED · ILLUSTRATIVE</Badge></div><div className="risk-matrix"><div/><>{[1,2,3,4,5,6].map(x=><b key={x}>+{x}h</b>)}</>{["Market underpass","Canal service road","Station approach","Low-lying connector"].map((road,r)=><div className="matrix-row" key={road}><strong>{road}<small>{r<2?"Escalation detected":"Stable outlook"}</small></strong>{[0,1,2,3,4,5].map((_,i)=>{const level=Math.min(3,Math.floor((i+r)/2));return <button title={`${road}: ${risks[level]} at +${i+1}h`} onClick={()=>setHorizon(i+1)} className={`${riskClass[risks[level]]} ${horizon===i+1?"selected":""}`} key={i}>{risks[level][0]}</button>})}</div>)}</div></section>
    <section className="chart-card quality"><h3>Model confidence context</h3><div className="notice amber"><Icon>!</Icon><div><strong>Uncertainty increases after +4h</strong><span>Confidence is separate from event probability.</span></div></div><p><b>Input freshness</b><span>Radar 2m · Terrain static · Reports 8m</span></p><p><b>Missing input</b><span>Live drainage sensors</span></p></section></div></main>
}


function Reports({area,goMap}:{area:string;goMap:()=>void}) {
  const [tab, setTab] = useState<"submit" | "history">("submit");
  const [reports, setReports] = useState<DemoReport[]>(loadReports);
  const [severity, setSeverity] = useState("Moderate");
  const [landmark, setLandmark] = useState("");
  const [description, setDescription] = useState("");
  const [access, setAccess] = useState("Passable with caution");
  const [error, setError] = useState("");
  const [sent, setSent] = useState<DemoReport | null>(null);
  const [selected, setSelected] = useState<DemoReport | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All");

  // Live GPS state
  const [gpsStatus, setGpsStatus] = useState<"idle" | "locating" | "success" | "error">("idle");
  const [gpsCoords, setGpsCoords] = useState<{ lat: number; lng: number; accuracy: number } | null>(null);
  const [gpsError, setGpsError] = useState("");

  // Photo state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Map focus coords
  const [focusCoords, setFocusCoords] = useState<[number, number] | null>(null);

  const city = cityForArea(area);

  // Synchronize reports from backend on mount and area/city change
  useEffect(() => {
    if (hasBackend) {
      reportService.syncFromBackend(city).then((items) => {
        if (items && items.length > 0) setReports(items);
      });
    }
  }, [city]);

  // Clean up preview object URL on component unmount
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // GPS geolocation handler
  const handleGetLocation = () => {
    if (!("geolocation" in navigator)) {
      setGpsStatus("error");
      setGpsError("Geolocation is not supported by your browser. You can confirm the area centre coordinates instead.");
      return;
    }

    setGpsStatus("locating");
    setGpsError("");

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const coords = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        };
        setGpsCoords(coords);
        setGpsStatus("success");
        setFocusCoords([coords.lat, coords.lng]);
        setGpsError("");
      },
      (err) => {
        setGpsStatus("error");
        setGpsCoords(null);
        let msg = "Could not obtain GPS position.";
        if (err.code === err.PERMISSION_DENIED) {
          msg = "Location permission denied. Please enable location permissions in your browser or device settings, or use the area centre location.";
        } else if (err.code === err.POSITION_UNAVAILABLE) {
          msg = "GPS position unavailable from your device hardware. Please check reception and retry.";
        } else if (err.code === err.TIMEOUT) {
          msg = "Location request timed out. Please check device GPS and retry.";
        }
        setGpsError(msg);
      },
      {
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 0, // Prevent stale cached coordinates
      }
    );
  };

  const clearGps = () => {
    setGpsCoords(null);
    setGpsStatus("idle");
    setGpsError("");
    const [lat, lng] = areaCentres[area] || areaCentres[defaultArea];
    setFocusCoords([lat, lng]);
  };

  // Photo handlers
  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPhotoError("");
    const file = e.target.files?.[0];
    if (!file) return;

    const validTypes = ["image/jpeg", "image/png", "image/webp", "image/gif"];
    if (!validTypes.includes(file.type)) {
      setPhotoError("Please select a valid image file (JPEG, PNG, WebP, or GIF).");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    const maxSizeBytes = 5 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      setPhotoError(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)} MB). Maximum allowed size is 5 MB.`);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setPhotoFile(file);
  };

  const handleRemovePhoto = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
    setPreviewUrl(null);
    setPhotoFile(null);
    setPhotoError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleReplacePhoto = () => {
    fileInputRef.current?.click();
  };

  // Submit handler
  const submit = async () => {
    if (!landmark.trim() || description.trim().length < 10) {
      setError("Add a road or landmark and a description of at least 10 characters.");
      return;
    }

    setSubmitting(true);
    setError("");

    let uploadedPhotoUrl: string | undefined = undefined;

    // 1. Photo upload via FormData if image attached
    if (photoFile && hasBackend) {
      try {
        const uploadRes = await apiClient.uploadPhoto(photoFile);
        uploadedPhotoUrl = uploadRes.photo_url;
      } catch (uploadErr: any) {
        setSubmitting(false);
        setError(`Photo upload failed: ${uploadErr.message || "Network error"}. Please retry or remove photo.`);
        return;
      }
    }

    // 2. Prepare coordinate payload
    const isGps = Boolean(gpsCoords);
    const now = new Date().toISOString();
    const [defaultLat, defaultLng] = areaCentres[area] || areaCentres[defaultArea];
    const latitude = gpsCoords ? gpsCoords.lat : defaultLat;
    const longitude = gpsCoords ? gpsCoords.lng : defaultLng;
    const coordinateSource = isGps ? "gps" : "area_centre";
    const accuracyM = gpsCoords ? Math.round(gpsCoords.accuracy * 10) / 10 : undefined;

    const reportPayload: Omit<DemoReport, "createdAt" | "updatedAt"> = {
      id: `AQ-${city.slice(0, 3).toUpperCase()}-${Date.now().toString().slice(-6)}`,
      city,
      area,
      latitude,
      longitude,
      landmark: landmark.trim(),
      severity,
      description: description.trim(),
      access,
      coordinateSource,
      accuracyM,
      photoUrl: uploadedPhotoUrl,
      status: "UNVERIFIED REPORT",
    };

    if (hasBackend) {
      try {
        const saved = await reportService.submitToBackend(reportPayload);
        setReports(reportService.list());
        setSent(saved);
        setError("");
      } catch (apiErr: any) {
        // Display genuine failure rather than silently claiming success
        setError(`Backend persistence failed: ${apiErr.message || "Network error"}. The report was NOT submitted. Please retry.`);
      } finally {
        setSubmitting(false);
      }
    } else {
      // Offline local demo storage
      const fullReport: DemoReport = {
        ...reportPayload,
        createdAt: now,
        updatedAt: now,
      };
      const next = reportService.saveLocal(fullReport);
      setReports(next);
      setSent(fullReport);
      setError("");
      setSubmitting(false);
    }
  };

  const filtered = reports.filter(
    (r) =>
      (status === "All" || r.status === status) &&
      `${r.id} ${r.landmark} ${r.city}`.toLowerCase().includes(query.toLowerCase())
  );

  if (sent) {
    const isGps = sent.coordinateSource === "gps";
    return (
      <main className="center">
        <div className="success report-success">
          <span>✓</span>
          <div style={{ display: "flex", gap: "8px", justifyContent: "center", marginBottom: "12px", flexWrap: "wrap" }}>
            <Badge tone="amber">UNVERIFIED REPORT</Badge>
            <Badge tone={isGps ? "blue" : "slate"}>
              {isGps ? `📍 GPS (±${sent.accuracyM ? Math.round(sent.accuracyM) + "m" : "accurate"})` : "⌖ AREA CENTRE PIN"}
            </Badge>
            {hasBackend ? <Badge tone="green">SERVER PERSISTED</Badge> : <Badge tone="slate">LOCAL DEMO STORAGE</Badge>}
          </div>
          <h1>{isGps ? "Ground Observation Recorded" : "Report Saved Successfully"}</h1>
          <p>
            Reference <b>{sent.id}</b>
            <br />
            <b>{sent.landmark}</b> · {sent.area}
            <br />
            Coordinates: {sent.latitude.toFixed(5)}, {sent.longitude.toFixed(5)}
            <br />
            {new Date(sent.createdAt).toLocaleString()}
          </p>

          {previewUrl && (
            <div style={{ margin: "14px auto", maxWidth: "220px", textAlign: "center" }}>
              <img
                src={previewUrl}
                alt="Submitted ground evidence"
                style={{ width: "100%", maxHeight: "150px", objectFit: "cover", borderRadius: "8px", border: "1px solid #cbd5e1" }}
              />
              <small style={{ display: "block", color: "#64748b", marginTop: "4px" }}>Evidence photograph attached</small>
            </div>
          )}

          {hasBackend ? (
            <div className="notice blue">
              <Icon>i</Icon>
              <div>
                <strong>Persisted in AquaSignal Database</strong>
                <span>Observation saved in backend database. Coordinates and evidence logged for dispatch.</span>
              </div>
            </div>
          ) : (
            <div className="notice blue">
              <Icon>i</Icon>
              <div>
                <strong>Local demo storage only</strong>
                <span>This report persists in this browser session only. Real backend server URL is not configured.</span>
              </div>
            </div>
          )}

          <div className="success-actions">
            <button
              className="outline"
              onClick={() => {
                setSent(null);
                setTab("history");
              }}
            >
              View My Reports
            </button>
            <button className="primary" onClick={goMap}>
              Return to Map
            </button>
          </div>
        </div>
      </main>
    );
  }

  const [defaultLat, defaultLng] = areaCentres[area] || areaCentres[defaultArea];
  const activeLat = gpsCoords ? gpsCoords.lat : defaultLat;
  const activeLng = gpsCoords ? gpsCoords.lng : defaultLng;

  return (
    <main>
      <div className="page-title">
        <div>
          <div className="eyebrow">
            {hasBackend ? "COMMUNITY EVIDENCE · BACKEND PERSISTENCE ACTIVE" : "COMMUNITY EVIDENCE · LOCAL DEMO STORAGE"}
          </div>
          <h1>Citizen Reports</h1>
          <p>Submit live observations with verified GPS and optional photo evidence.</p>
        </div>
        <div style={{ display: "flex", gap: "6px" }}>
          {hasBackend && <Badge tone="green">LIVE API CONNECTED</Badge>}
          <Badge tone="amber">NOT AUTOMATICALLY VERIFIED</Badge>
        </div>
      </div>

      <div className="report-tabs">
        <button className={tab === "submit" ? "active" : ""} onClick={() => setTab("submit")}>
          Submit Report
        </button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>
          Report History <b>{reports.length}</b>
        </button>
      </div>

      {tab === "submit" ? (
        <div className="report-layout">
          <section className="form-card">
            <h3>Observation details</h3>
            <div className="two">
              <label>
                City
                <input value={city} readOnly />
              </label>
              <label>
                Geographic area
                <input value={area} readOnly />
              </label>
            </div>

            <label>
              Road or nearby landmark *
              <input
                value={landmark}
                onChange={(e) => setLandmark(e.target.value)}
                placeholder="e.g. underpass near railway station"
              />
            </label>

            {/* GPS Location Section */}
            <div className="gps-control-card">
              <div className="gps-header">
                <div>
                  <strong style={{ fontSize: "11px", color: "#1e293b" }}>Incident Coordinates</strong>
                  <span style={{ display: "block", fontSize: "9px", color: "#64748b" }}>
                    {gpsCoords ? "Using high-accuracy device GPS" : "Currently using default area centre"}
                  </span>
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button
                    type="button"
                    className="gps-btn"
                    onClick={handleGetLocation}
                    disabled={gpsStatus === "locating"}
                  >
                    <span>⌖</span>
                    {gpsStatus === "locating" ? "Acquiring GPS…" : "Get My Live Location"}
                  </button>
                  {gpsCoords && (
                    <button type="button" className="gps-btn secondary" onClick={clearGps}>
                      Reset
                    </button>
                  )}
                </div>
              </div>

              {gpsError && (
                <div className="form-error" style={{ margin: "6px 0", fontSize: "10px" }}>
                  {gpsError}{" "}
                  <button
                    type="button"
                    onClick={handleGetLocation}
                    style={{ textDecoration: "underline", background: "none", border: 0, color: "inherit", cursor: "pointer", fontWeight: 700 }}
                  >
                    Retry
                  </button>
                </div>
              )}

              <div className="gps-coords-display">
                <span>Latitude: <b>{activeLat.toFixed(6)}</b></span>
                <span>Longitude: <b>{activeLng.toFixed(6)}</b></span>
                {gpsCoords ? (
                  <span style={{ color: "#0369a1" }}>Accuracy: <b>±{Math.round(gpsCoords.accuracy)} m</b></span>
                ) : (
                  <span style={{ color: "#64748b" }}>Mode: <b>Area Centre</b></span>
                )}
                {gpsCoords && (
                  <button
                    type="button"
                    onClick={() => setFocusCoords([gpsCoords.lat, gpsCoords.lng])}
                    style={{ marginLeft: "auto", border: 0, background: "none", color: "#0284c7", fontSize: "10px", fontWeight: 600, cursor: "pointer" }}
                  >
                    View on Map →
                  </button>
                )}
              </div>

              <small style={{ display: "block", color: "#64748b", fontSize: "9px", marginTop: "6px" }}>
                Location permission is requested only to position this waterlogging report. Coordinates are captured once upon clicking and the user is not continuously tracked.
              </small>
            </div>

            <div className="two" style={{ marginTop: "10px" }}>
              <label>
                Report time
                <input type="text" value={new Date().toLocaleString()} readOnly />
              </label>
              <label>
                Road accessibility
                <select value={access} onChange={(e) => setAccess(e.target.value)}>
                  <option>Passable with caution</option>
                  <option>Not passable</option>
                  <option>Unknown</option>
                </select>
              </label>
            </div>

            <label>
              Observed severity
              <div className="severity">
                {risks.map((r) => (
                  <button
                    type="button"
                    key={r}
                    className={severity === r ? riskClass[r] : ""}
                    onClick={() => setSeverity(r)}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </label>

            <label>
              Description *
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe water depth, flow speed, and affected vehicles or pedestrians..."
              />
            </label>

            {/* Photo Upload Section */}
            <label>
              Photo Evidence (optional)
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                style={{ display: "none" }}
                onChange={handlePhotoSelect}
              />
              {!previewUrl ? (
                <div className="photo-dropzone" onClick={() => fileInputRef.current?.click()}>
                  <Icon>↑</Icon>
                  <strong style={{ fontSize: "11px", color: "#1e293b", margin: "4px 0" }}>
                    Take photo or choose from library
                  </strong>
                  <span style={{ fontSize: "9px", color: "#64748b", display: "block" }}>
                    Camera capture supported on mobile browsers · Max 5 MB (JPEG, PNG, WebP)
                  </span>
                </div>
              ) : (
                <div className="photo-preview-container">
                  <img src={previewUrl} alt="Preview" className="photo-thumbnail" />
                  <div className="photo-meta">
                    <strong>{photoFile?.name || "Evidence Photo"}</strong>
                    <span>
                      {photoFile ? `${(photoFile.size / 1024).toFixed(0)} KB · ${photoFile.type}` : "Ready for submission"}
                    </span>
                    <div className="photo-actions">
                      <button type="button" className="photo-btn" onClick={handleReplacePhoto}>
                        Replace
                      </button>
                      <button type="button" className="photo-btn danger" onClick={handleRemovePhoto}>
                        Remove
                      </button>
                    </div>
                  </div>
                </div>
              )}
              {photoError && <div className="form-error" style={{ fontSize: "10px", marginTop: "4px" }}>{photoError}</div>}
            </label>

            {error && <div className="form-error">{error}</div>}

            <div className="notice blue">
              <Icon>i</Icon>
              <div>
                <strong>Privacy and verification</strong>
                <span>
                  Reports are logged for municipal review. No personal identifiable contact details are displayed publicly.
                </span>
              </div>
            </div>

            <button className="primary" onClick={submit} disabled={submitting}>
              {submitting ? "Submitting Report…" : "Submit Ground Observation Report"}
            </button>
          </section>

          <section className="report-map">
            <Map
              horizon={2}
              onSelect={() => {}}
              layers={["Citizen reports"]}
              area={area}
              userLocation={gpsCoords}
              focusCoords={focusCoords}
              reportsList={reports}
            />
            <div className="location-confirm">
              <strong>
                {gpsCoords ? "📍 Live GPS Position Active" : "⌖ Area Centre Reference Active"}
              </strong>
              <span>
                {gpsCoords
                  ? `Captured at ${activeLat.toFixed(5)}, ${activeLng.toFixed(5)} (±${Math.round(gpsCoords.accuracy)} m)`
                  : `${area} · Demonstration centre coordinates`}
              </span>
            </div>
          </section>
        </div>
      ) : (
        <section className="history-panel">
          <div className="history-tools">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search reference or landmark…"
            />
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option>All</option>
              <option>UNVERIFIED REPORT</option>
              <option>CORROBORATED</option>
              <option>ADMIN-VERIFIED</option>
            </select>
          </div>
          {filtered.length ? (
            <div className="report-list">
              {filtered.map((r) => (
                <button key={r.id} onClick={() => setSelected(r)}>
                  <div>
                    <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                      <Badge tone={r.status === "UNVERIFIED REPORT" ? "amber" : "blue"}>{r.status}</Badge>
                      {r.coordinateSource === "gps" && <Badge tone="gps">📍 GPS</Badge>}
                      {r.photoUrl && <Badge tone="green">📷 Photo</Badge>}
                    </div>
                    <strong>{r.landmark}</strong>
                    <small>
                      {r.id} · {r.city} · {new Date(r.createdAt).toLocaleString()}
                    </small>
                  </div>
                  <span className={riskClass[r.severity]}>{r.severity}</span>
                  <i>View details →</i>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <Icon>◉</Icon>
              <h3>No saved reports</h3>
              <p>Reports submitted in this workspace will appear here.</p>
              <button className="primary" onClick={() => setTab("submit")}>
                Submit Your First Report
              </button>
            </div>
          )}
        </section>
      )}

      {selected && (
        <div className="report-detail">
          <div className="detail-head">
            <div>
              <div style={{ display: "flex", gap: "6px", marginBottom: "4px" }}>
                <Badge tone="amber">{selected.status}</Badge>
                {selected.coordinateSource === "gps" && <Badge tone="gps">📍 GPS (±{selected.accuracyM ? Math.round(selected.accuracyM) + 'm' : ''})</Badge>}
              </div>
              <h3>{selected.landmark}</h3>
              <p>
                {selected.id} · {selected.area}
              </p>
            </div>
            <button onClick={() => setSelected(null)}>×</button>
          </div>

          <Map
            horizon={2}
            onSelect={() => {}}
            layers={["Citizen reports"]}
            area={selected.area}
            focusCoords={[selected.latitude, selected.longitude]}
            userLocation={selected.coordinateSource === "gps" ? { lat: selected.latitude, lng: selected.longitude, accuracy: selected.accuracyM } : undefined}
          />

          {selected.photoUrl && (
            <div style={{ margin: "12px 0" }}>
              <strong style={{ fontSize: "10px", color: "#64748b", display: "block", marginBottom: "4px" }}>
                Evidence Photograph
              </strong>
              <img
                src={selected.photoUrl.startsWith("http") ? selected.photoUrl : `${appConfig.apiUrl || ""}${selected.photoUrl}`}
                alt="Report evidence"
                style={{ width: "100%", maxHeight: "200px", objectFit: "cover", borderRadius: "8px", border: "1px solid #cbd5e1" }}
              />
            </div>
          )}

          <dl>
            <dt>Submitted</dt>
            <dd>{new Date(selected.createdAt).toLocaleString()}</dd>
            <dt>Severity</dt>
            <dd>{selected.severity}</dd>
            <dt>Coordinates</dt>
            <dd>{selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)} ({selected.coordinateSource || "area_centre"})</dd>
            <dt>Road access</dt>
            <dd>{selected.access}</dd>
            <dt>Description</dt>
            <dd>{selected.description}</dd>
          </dl>

          <div className="status-track">
            <b>● Submitted</b>
            <span>○ Under Review</span>
            <span>○ Corroborated</span>
            <span>○ Admin-Verified</span>
          </div>

          <div className="notice amber">
            <Icon>!</Icon>
            <div>
              <strong>Awaiting human review</strong>
              <span>No verified outcome is available yet.</span>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function ResponseIntelligence({area,horizon,setHorizon,viewMap}:{area:string;horizon:number;setHorizon:(n:number)=>void;viewMap:()=>void}) {
  const [tab,setTab]=useState("Escalation Watch"),[severity,setSeverity]=useState("All"),[sort,setSort]=useState("Priority");
  const city=cityForArea(area);
  const locations=city==="Pune"?[["Nal Stop underpass","MODERATE","HIGH","+2h","Rainfall · low terrain"],["Deccan connector","HIGH","SEVERE","+4h","Drainage gap · rainfall"],["Station approach","MODERATE","HIGH","+5h","Incident history"]]:[["Mithi approach","HIGH","SEVERE","+2h","Rainfall · low terrain"],["Western arterial","MODERATE","HIGH","+3h","Drainage gap · rainfall"],["Suburban underpass","HIGH","SEVERE","+4h","Reports · low terrain"]];
  return <main><div className="page-title"><div><div className="eyebrow">MODEL-DERIVED OPERATIONS · ADVISORY ONLY</div><h1>Response Intelligence</h1><p>Understand which {city} demonstration locations may require attention and why.</p></div><Badge tone="slate">NOT AN OFFICIAL INSTRUCTION</Badge></div><div className="response-tabs">{["Escalation Watch","Inspection Priorities","Report Review"].map(x=><button className={tab===x?"active":""} onClick={()=>setTab(x)} key={x}>{x}</button>)}</div><div className="response-toolbar"><label>City<select value={city} disabled><option>{city}</option></select></label><label>Severity<select value={severity} onChange={e=>setSeverity(e.target.value)}><option>All</option><option>HIGH</option><option>SEVERE</option></select></label><label>Horizon<select value={horizon} onChange={e=>setHorizon(+e.target.value)}>{[1,2,3,4,5,6].map(x=><option key={x} value={x}>+{x}h</option>)}</select></label><label>Sort<select value={sort} onChange={e=>setSort(e.target.value)}><option>Priority</option><option>Escalation time</option><option>Freshness</option></select></label></div>
  {tab==="Escalation Watch"?<div className="response-layout"><section className="escalation-watch"><div className="response-heading"><div><h3>Risk Escalation Watch</h3><p>Sorted by forecast category, escalation time and freshness.</p></div><Badge tone="amber">ILLUSTRATIVE</Badge></div>{locations.filter(x=>severity==="All"||x[2]===severity).map((x,i)=><div className="watch-row" key={x[0]}><span className="priority-rank">{i+1}</span><div><strong>{x[0]}</strong><small>{area} · fresh {i+2}m ago</small></div><span>{x[1]} <i>→</i> <b>{x[2]}</b><small>Escalates {x[3]} · uncertainty ±{10+i}%</small></span><span>{x[4]}</span><button onClick={viewMap}>View on Map →</button></div>)}</section><section className="priority-method"><h3>Priority method</h3><p>Demonstration ranking combines predicted category, escalation horizon, report corroboration and input freshness.</p>{[["Predicted severity","40%"],["Escalation proximity","30%"],["Corroborated evidence","20%"],["Data freshness","10%"]].map(x=><div key={x[0]}><span>{x[0]}</span><b>{x[1]}</b></div>)}<small>Weights are illustrative and configurable. They are not municipal policy.</small></section></div>:tab==="Inspection Priorities"?<div className="ops"><div className="table-head"><span>Ranked location</span><span>Reason</span><span>Evidence</span><span>Freshness</span><span>Action</span></div>{locations.map((x,i)=><div className="table-row" key={x[0]}><strong>{i+1}<span>{x[0]}</span></strong><span>{x[2]} at {x[3]}</span><span>{i===0?"CORROBORATED":"MODEL ONLY"}</span><span className="green">● {i+2}m</span><button onClick={viewMap}>Inspect on map →</button></div>)}</div>:<div className="report-review-summary">{["UNVERIFIED REPORT","UNDER REVIEW","CORROBORATED","ADMIN-VERIFIED"].map((x,i)=><button key={x}><span>{[loadReports().filter(r=>r.status==="UNVERIFIED REPORT").length,2,1,0][i]}</span><strong>{x}</strong><small>{i<2?"Requires human review":"Decision recorded"}</small></button>)}<div className="notice blue"><Icon>i</Icon><div><strong>Reports never alter model probability silently</strong><span>Community evidence is displayed separately unless a validated model explicitly consumes it.</span></div></div></div>}</main>
}

function IntelligenceCentre({area,horizon,setHorizon}:{area:string;horizon:number;setHorizon:(n:number)=>void}) {
  const city=cityForArea(area),[section,setSection]=useState("Forecast"),[densityMode,setDensityMode]=useState("Risk density");
  return <main><div className="page-title"><div><div className="eyebrow">DEEP ANALYSIS · DEMONSTRATION DATA</div><h1>Intelligence Centre</h1><p>Explore distinct forecast, spatial, community and model signals for {area}.</p></div><Badge tone="slate">LIMITATIONS DISCLOSED</Badge></div><div className="intel-toolbar"><div>{["Forecast","Spatial","Community","Model"].map(x=><button className={section===x?"active":""} onClick={()=>setSection(x)} key={x}>{x} Intelligence</button>)}</div><select value={horizon} onChange={e=>setHorizon(+e.target.value)}>{[1,2,3,4,5,6].map(x=><option key={x} value={x}>+{x} hour forecast</option>)}</select></div>
  {section==="Forecast"?<div className="intel-grid"><section className="forecast-river"><div className="response-heading"><div><h3>Forecast River</h3><p>Discrete risk outlook · road segment R-042 · probability (%)</p></div><Badge>+{horizon}H SELECTED</Badge></div><svg viewBox="0 0 700 210" role="img" aria-label="Six-hour forecast river"><defs><linearGradient id="river" x1="0" x2="1"><stop stopColor="#e5a12b"/><stop offset=".55" stopColor="#e75b45"/><stop offset="1" stopColor="#a92d3a"/></linearGradient></defs><path d="M30 145 C130 130,160 100,260 112 S390 48,480 70 S590 28,670 42 L670 162 C570 150,530 175,440 150 S300 180,220 158 S100 180,30 165Z" fill="url(#river)" opacity=".88"/>{[1,2,3,4,5,6].map((x,i)=><g key={x} transform={`translate(${55+i*118} 0)`}><line y1="28" y2="180" stroke={horizon===x?"#182538":"#ffffff66"} strokeDasharray="3 4"/><text y="198" textAnchor="middle">+{x}h</text><circle cy={145-i*19} r={horizon===x?7:4} fill="#fff"/><text y={130-i*19} textAnchor="middle">{[43,51,63,70,79,84][i]}%</text></g>)}</svg><div className="river-legend"><span>Moderate</span><span>High</span><span>Severe</span></div></section><section className="confidence-panel"><h3>Forecast confidence context</h3>{[["Input freshness","Fresh · 2m","good"],["Input completeness","Terrain missing locally","warn"],["Model uncertainty",`±${8+horizon}%`,"warn"],["Coverage","Demonstration area only","neutral"]].map(x=><div key={x[0]}><span>{x[0]}</span><b className={x[2]}>{x[1]}</b></div>)}<p>Completeness describes available inputs, not prediction accuracy.</p></section></div>:section==="Spatial"?<div className="intel-grid"><section className="density-map"><Map area={area} horizon={horizon} onSelect={()=>{}} layers={densityMode==="Risk density"?["Predicted risk","Historical incidents"]:["Predicted risk"]}/><div className="density-toggle">{["Risk density","Road segments"].map(x=><button className={densityMode===x?"active":""} onClick={()=>setDensityMode(x)} key={x}>{x}</button>)}</div></section><section className="coverage-gaps"><h3>{city} coverage gaps</h3><p>Known limitations in this demonstration area.</p>{["Live drainage sensors","Ward-level incident archive","Real-time road closures"].map((x,i)=><div key={x}><i style={{width:`${[72,46,28][i]}%`}}/><span>{x}</span><b>{["Unavailable","Partial","Unavailable"][i]}</b></div>)}</section></div>:section==="Community"?<div className="community-intel"><section><h3>Verification progress</h3><div className="verification-flow">{["Submitted","Under review","Corroborated","Admin-verified"].map((x,i)=><span key={x}><b>{[loadReports().length,2,1,0][i]}</b>{x}</span>)}</div></section><section><h3>Possible duplicate clusters</h3><p>Spatial proximity and report timing suggest review candidates; automated matching is not verification.</p>{["Station underpass · 3 reports / 22 min","River approach · 2 reports / 11 min"].map(x=><button onClick={()=>alert(`${x}. Detailed cluster review requires a shared backend.`)} key={x}>{x}<span>Review cluster →</span></button>)}</section></div>:<div className="model-empty"><Badge tone="slate">AWAITING VALIDATION RESULTS</Badge><h3>Model evaluation is not yet available</h3><p>Precision, recall, F1, PR-AUC, Brier score, false-alarm rate, calibration, temporal validation and spatial holdout results will appear only after a documented evaluation run.</p><div>{["Precision","Recall","F1-score","PR-AUC","Brier score","Calibration"].map(x=><span key={x}><b>—</b>{x}<small>Not yet evaluated</small></span>)}</div></div>}</main>
}

function Generic({ page }: { page:string }) {
  const isModel=page==="Model Performance"; const isAdmin=page==="Administration";
  const [adminReports,setAdminReports]=useState<DemoReport[]>(loadReports);
  const review=(id:string,status:DemoReport["status"])=>{const next=adminReports.map(r=>r.id===id?{...r,status,updatedAt:new Date().toISOString()}:r);setAdminReports(next);reportService.replace(next)};
  const descriptions:Record<string,string>={"Incident Timeline":"Compare predictions with subsequent verified outcomes.","Response Priorities":"Rank inspections using risk, freshness and corroboration.","Route Advisory":"Compare route alternatives by predicted risk exposure.","Administration":"Review reports, duplicates and human verification history.","Settings":"Manage authorised workspace and notification preferences."};
  if(page==="Incident Timeline") return <main><div className="page-title"><div><div className="eyebrow">PREDICTION VS OBSERVATION</div><h1>Incident Timeline</h1><p>{descriptions[page]}</p></div><Badge tone="slate">DEMONSTRATION DATA</Badge></div><div className="ops comparison">{[["14:00","HIGH · 68%","+2h prediction","Awaiting observation"],["12:20","MODERATE · 46%","+1h prediction","ADMIN-VERIFIED · No waterlogging"],["09:10","HIGH · 71%","+1h prediction","CORROBORATED · Restricted access"]].map((x,i)=><div className="compare-row" key={x[0]}><span>{x[0]}<small>Prediction timestamp</small></span><strong>{x[1]}<small>{x[2]}</small></strong><i>→</i><span className={i?"green":"moderate"}>{x[3]}<small>{i?"Verified independently · 13:22":"No verified outcome yet"}</small></span></div>)}</div></main>;
  if(page==="Route Advisory") return <main><div className="page-title"><div><div className="eyebrow">ROUTE-RISK COMPARISON</div><h1>Route Advisory</h1><p>{descriptions[page]}</p></div><Badge tone="amber">ADVISORY ONLY</Badge></div><div className="route-grid">{[["Route A","18 min","2 high-risk segments","Not recommended"],["Route B","24 min","1 moderate-risk segment","Lower exposure"],["Route C","27 min","Risk data incomplete","Use caution"]].map((x,i)=><div className={`route-card ${i===1?"recommended":""}`} key={x[0]}><Badge tone={i===1?"blue":i===0?"red":"slate"}>{i===1?"LOWER MODELLED EXPOSURE":"ADVISORY ONLY"}</Badge><h3>{x[0]} <span>{x[1]}</span></h3><p>{x[2]}</p><strong>{x[3]}</strong><button>Inspect route on map →</button></div>)}</div><div className="notice amber"><Icon>!</Icon><div><strong>No route is guaranteed safe</strong><span>Advisories depend on available road-network data, demonstration predictions and input freshness.</span></div></div></main>;
  if(page==="Settings") return <main><div className="page-title"><div><div className="eyebrow">SYSTEM PREFERENCES</div><h1>Settings</h1><p>{descriptions[page]}</p></div></div><div className="settings-panel">{["Severe-risk escalation alerts","Stale input warnings","New corroborated report alerts","Daily operational briefing"].map((x,i)=><label key={x}><span><b>{x}</b><small>{i===0?"Notify authorised responders immediately":"Configure workspace notification behaviour"}</small></span><input type="checkbox" defaultChecked={i<3}/></label>)}</div></main>;
  if(isAdmin) return <main><div className="page-title"><div><div className="eyebrow">SIMULATED ADMINISTRATIVE PERMISSIONS</div><h1>Administration</h1><p>Review locally stored reports and record demonstration decisions.</p></div><Badge tone="amber">HUMAN REVIEW REQUIRED</Badge></div>{adminReports.length?<div className="ops admin-queue"><div className="table-head"><span>Report & location</span><span>Severity</span><span>Status</span><span>Updated</span><span>Review decision</span></div>{adminReports.map(r=><div className="table-row" key={r.id}><strong><span>{r.landmark}<small>{r.id} · {r.city}</small></span></strong><span className={riskClass[r.severity]}>{r.severity}</span><Badge tone={r.status==="UNVERIFIED REPORT"?"amber":"blue"}>{r.status}</Badge><span>{new Date(r.updatedAt).toLocaleString()}</span><span className="admin-actions"><button onClick={()=>review(r.id,"CORROBORATED")}>Corroborate</button><button onClick={()=>review(r.id,"ADMIN-VERIFIED")}>Verify</button></span></div>)}</div>:<div className="empty-state"><h3>No reports awaiting review</h3><p>Citizen reports saved in this browser will appear here.</p></div>}<div className="notice blue"><Icon>i</Icon><div><strong>Local demonstration audit</strong><span>Status changes persist in this browser. Production review requires authenticated roles and a server audit trail.</span></div></div></main>;
  return <main><div className="page-title"><div><div className="eyebrow">{isAdmin?"HUMAN VERIFICATION & AUDIT":isModel?"VALIDATION & PROVENANCE":"OPERATIONAL PRIORITISATION"}</div><h1>{page}</h1><p>{isModel?"Transparent quality, coverage and model validation.":descriptions[page]||"Prioritised actions linked to predicted risk and field evidence."}</p></div><Badge tone={isModel?"slate":isAdmin?"amber":"blue"}>{isModel?"SYNTHETIC DEMO DATA":isAdmin?"HUMAN REVIEW REQUIRED":"MODEL-DERIVED"}</Badge></div>
  {isModel?<><div className="metrics">{["Precision","Recall","F1 score","PR-AUC","Brier score","False-alarm rate"].map(x=><div className="kpi" key={x}><span>{x}</span><strong className="tbd">TO BE MEASURED</strong><small>Awaiting temporal validation</small></div>)}</div><div className="notice blue"><Icon>i</Icon><div><strong>Model v0.9-demo · Synthetic demonstration dataset</strong><span>Temporal validation, spatial holdout evaluation and calibration have not yet been completed.</span></div></div></>:
  <div className="ops"><div className="table-head"><span>{isAdmin?"Report & location":"Priority location"}</span><span>Risk / horizon</span><span>Evidence</span><span>Freshness</span><span>Action</span></div>{["Riverfront arterial · R-042","Market underpass · G-18","North canal road · R-117","Station access · G-22"].map((x,i)=><div className="table-row" key={x}><strong>{i+1}<span>{x}</span></strong><span><Badge tone={i<2?"red":"amber"}>{i<2?"SEVERE":"HIGH"} · +{i+1}h</Badge></span><span>{i===0?"CORROBORATED":"UNVERIFIED REPORT"}</span><span className="green">● {i+2}m ago</span><button>{isAdmin?"Review evidence":"Assign team"} →</button></div>)}</div>}</main>
}

function SignIn({success,back,signup}:{success:()=>void;back:()=>void;signup:()=>void}) {
  const [email,setEmail]=useState(""),[password,setPassword]=useState(""),[show,setShow]=useState(false),[remember,setRemember]=useState(true),[error,setError]=useState(""),[loading,setLoading]=useState(false);
  const submit=(e:React.FormEvent)=>{e.preventDefault();if(!email.includes("@")||password.length<6){setError("Enter a valid email and a password of at least 6 characters.");return}setLoading(true);setTimeout(()=>{authService.signIn(email,remember);success()},650)};
  return <div className="signin"><section className="signin-visual"><button className="landing-brand" onClick={back}><span className="brandmark">A</span><b>AquaSignal</b></button><div><div className="eyebrow">MONSOON DECISION SUPPORT</div><h1>Make informed decisions during the monsoon.</h1><p>Explore location-specific forecasts, community evidence and explainable risk across Mumbai and Pune.</p><div className="signin-map"><Map horizon={3} onSelect={()=>{}} layers={["Predicted risk","Citizen reports"]} area="Mumbai · Mithi River Demonstration Area"/></div></div><small>Forecasts are advisory and demonstration outputs are clearly labelled.</small></section><section className="signin-form"><form onSubmit={submit}><Badge>DEMO AUTHENTICATION</Badge><h2>Welcome back</h2><p>Sign in to open your geographic workspace.</p><div className="notice amber"><Icon>i</Icon><div><strong>Hackathon demo mode</strong><span>No authentication provider is connected. Any valid email and 6+ character password starts a local session. Passwords are never stored.</span></div></div><label>Email address<input value={email} onChange={e=>setEmail(e.target.value)} type="email" autoComplete="email" placeholder="you@example.com"/></label><label>Password<div className="password-field"><input value={password} onChange={e=>setPassword(e.target.value)} type={show?"text":"password"} autoComplete="current-password" placeholder="6+ characters"/><button type="button" onClick={()=>setShow(!show)}>{show?"Hide":"Show"}</button></div></label><div className="remember"><label><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/> Remember this demo session</label><button type="button" onClick={()=>setError("Password recovery requires a configured authentication provider.")}>Forgot password?</button></div>{error&&<div className="form-error">{error}</div>}<button className="cta signin-button" disabled={loading}>{loading?"Opening workspace…":"Sign In"}</button><small>Need access? <button type="button" onClick={signup}>Create an account</button></small></form></section></div>
}

function SignUp({success,signin,back}:{success:(name:string)=>void;signin:()=>void;back:()=>void}) {
  const [name,setName]=useState(""),[email,setEmail]=useState(""),[password,setPassword]=useState(""),[confirm,setConfirm]=useState(""),[show,setShow]=useState(false),[terms,setTerms]=useState(false),[error,setError]=useState(""),[loading,setLoading]=useState(false);
  const submit=(e:React.FormEvent)=>{e.preventDefault();if(name.trim().length<2){setError("Enter your full name.");return}if(!email.includes("@")){setError("Enter a valid email address.");return}if(password.length<8||!/[A-Z]/.test(password)||!/[0-9]/.test(password)){setError("Password must have 8+ characters, one uppercase letter and one number.");return}if(password!==confirm){setError("Passwords do not match.");return}if(!terms){setError("Accept the demo terms and privacy acknowledgement.");return}setLoading(true);setTimeout(()=>{authService.signUp(name,email);success(name)},650)};
  return <div className="signin"><section className="signin-visual signup-visual"><button className="landing-brand" onClick={back}><span className="brandmark">A</span><b>AquaSignal</b></button><div><div className="eyebrow">CREATE YOUR WORKSPACE</div><h1>Intelligence designed for decisions under pressure.</h1><p>Set up a local demonstration account, then choose a Mumbai or Pune monitoring area.</p><div className="auth-features"><span>✓ 1–6 hour forecast explorer</span><span>✓ Persistent local report history</span><span>✓ Explainable demonstration risk</span></div></div><small>Demo registration is local to this browser and is not production identity security.</small></section><section className="signin-form"><form onSubmit={submit}><Badge>DEMO REGISTRATION</Badge><h2>Create account</h2><p>Start a local AquaSignal demonstration session.</p><label>Full name<input value={name} onChange={e=>setName(e.target.value)} autoComplete="name" placeholder="Your name"/></label><label>Email address<input value={email} onChange={e=>setEmail(e.target.value)} type="email" autoComplete="email" placeholder="you@example.com"/></label><label>Password<div className="password-field"><input value={password} onChange={e=>setPassword(e.target.value)} type={show?"text":"password"} placeholder="8+ characters"/><button type="button" onClick={()=>setShow(!show)}>{show?"Hide":"Show"}</button></div><small className="password-hint">8+ characters · uppercase letter · number</small></label><label>Confirm password<input value={confirm} onChange={e=>setConfirm(e.target.value)} type={show?"text":"password"}/></label><label className="terms"><input type="checkbox" checked={terms} onChange={e=>setTerms(e.target.checked)}/> I acknowledge the demo terms and privacy notice.</label>{error&&<div className="form-error">{error}</div>}<button className="cta signin-button" disabled={loading}>{loading?"Creating local account…":"Create Account"}</button><small>Already have an account? <button type="button" onClick={signin}>Sign In</button></small></form></section></div>
}

function Landing({ openApp, exploreArea, signup, authenticated }: { openApp: () => void; exploreArea:(city:"Mumbai"|"Pune")=>void; signup:()=>void; authenticated:boolean }) {
  const [tab,setTab]=useState("Risk Map"),[menu,setMenu]=useState(false);
  return <div className="landing">
    <div className="landing-nav"><button className="landing-brand" onClick={()=>window.scrollTo({top:0,behavior:"smooth"})}><span className="brandmark">A</span><b>AquaSignal</b></button>
      <nav className={menu?"open":""}>{[["Platform","platform"],["Forecasting","forecasting"],["How It Works","how-it-works"],["Coverage","geographic-coverage"],["About","about"]].map(x=><button key={x[0]} onClick={()=>document.getElementById(x[1])?.scrollIntoView({behavior:"smooth"})}>{x[0]}</button>)}</nav>
      <div className="nav-actions">{authenticated?<><button onClick={openApp}>Demo Profile</button><button className="cta" onClick={openApp}>Open Application</button></>:<><button onClick={openApp}>Sign In</button><button className="cta" onClick={signup}>Create Account</button></>}<button className="menu" onClick={()=>setMenu(!menu)}>☰</button></div>
    </div>
    <section className="hero" id="platform"><div className="hero-copy"><div className="eyebrow">AI-POWERED MONSOON INTELLIGENCE</div><h1>Know the risk before you reach the road.</h1><p>Explore potential waterlogging, understand changing local conditions and identify locations that may require attention across Mumbai and Pune.</p><div className="hero-actions"><button className="cta big" onClick={openApp}>Explore Live Intelligence <span>→</span></button><button className="secondary" onClick={()=>document.getElementById("how-it-works")?.scrollIntoView({behavior:"smooth"})}>Discover How It Works</button></div><div className="hero-capabilities"><span><b>1–6 hours</b>Forecast horizon</span><span><b>Mumbai + Pune</b>Geographic focus</span><span><b>Location-specific</b>Risk intelligence</span></div></div>
      <div className="hero-map"><Map horizon={3} onSelect={openApp} layers={["Predicted risk","Citizen reports"]}/><div className="hero-risk"><Badge tone="red">HIGH RISK · +3H</Badge><strong>Riverfront arterial</strong><span>72% predicted probability</span><button onClick={openApp}>View explanation →</button></div><div className="hero-horizon"><span>Forecast</span>{[1,2,3,4,5,6].map(x=><b className={x===3?"active":""} key={x}>+{x}h</b>)}</div></div>
    </section>
    <section className="monsoon-landscape"><div><div className="eyebrow">THE CHANGING MONSOON LANDSCAPE</div><h2>Conditions change road by road, hour by hour.</h2><p>City-wide rainfall does not create uniform impact. Terrain, drainage information, road form and recent evidence can shape local vulnerability—when those inputs are available.</p></div><div className="landscape-visual"><span>OBSERVE<small>Rainfall · terrain · roads</small></span><i>→</i><span>PREDICT<small>Discrete +1h to +6h outputs</small></span><i>→</i><span>VERIFY<small>Reviewed community evidence</small></span></div></section>
    <section className="capabilities">{[["01","1–6 hour forecasts","Compare risk as conditions evolve."],["02","Location-based risk","Inspect roads and operational areas."],["03","Explainable AI","Understand inputs and uncertainty."],["04","Community reporting","Add field evidence responsibly."]].map(x=><div key={x[0]}><span>{x[0]}</span><strong>{x[1]}</strong><small>{x[2]}</small></div>)}</section>
    <section className="how" id="how-it-works"><div className="section-heading"><div className="eyebrow">FROM SIGNAL TO ACTION</div><h2>Built for decisions, not just predictions.</h2><p>Every forecast remains traceable to its inputs, freshness and evidence state.</p></div><div className="steps">{[["Observe","Collect available rainfall, terrain, road and incident signals."],["Predict","Estimate waterlogging probability for each forecast horizon."],["Verify","Combine predictions with reviewed community observations."],["Respond","Prioritise inspections and route-risk advisories."]].map((x,i)=><div key={x[0]}><i>{i+1}</i><strong>{x[0]}</strong><p>{x[1]}</p></div>)}</div></section>
    <OperationalPictureSection openApp={openApp} />
    <section className="coverage-section" id="geographic-coverage"><div className="section-heading"><div className="eyebrow">GEOGRAPHIC COVERAGE</div><h2>Built for local decisions across Mumbai and Pune.</h2><p>Explore separate illustrative datasets scoped to each city. Live coverage is not implied.</p></div><div className="city-cards">{[["Mumbai","City and suburban coverage options","Mithi River and western suburbs demonstration areas"],["Pune","City, ward and neighbourhood selection","Central and Mula-Mutha demonstration areas"]].map(x=><div className="city-card" key={x[0]}><span className="city-index">{x[0]==="Mumbai"?"M":"P"}</span><Badge tone="slate">DEMONSTRATION COVERAGE</Badge><h3>{x[0]}</h3><p>{x[1]}</p><small>{x[2]}</small><button onClick={()=>exploreArea(x[0] as "Mumbai"|"Pune")}>Explore {x[0]} →</button></div>)}</div></section>
    <section className="audiences" id="for-cities"><div><div className="eyebrow">FOR COMMUNITIES</div><h2>Local context, clearly explained.</h2>{["Understand nearby risk","See forecast changes","Submit waterlogging reports","Review location advisories"].map(x=><p key={x}>✓ {x}</p>)}</div><div className="ops-audience"><div className="eyebrow">FOR OPERATIONAL TEAMS</div><h2>Turn signals into priorities.</h2>{["Prioritise high-risk locations","Review and corroborate reports","Monitor input freshness","Inspect model factors and quality"].map(x=><p key={x}>✓ {x}</p>)}</div></section>
    <section className="transparency" id="about"><div><div className="eyebrow">DATA TRANSPARENCY</div><h2>A forecast is not a confirmed flood.</h2><p>Outputs depend on model validation, source availability and input freshness. AquaSignal keeps prediction, community evidence and verified observations distinct.</p></div><div className="trust-badges"><Badge>PREDICTED</Badge><Badge tone="amber">UNVERIFIED REPORT</Badge><Badge>ADMIN-VERIFIED</Badge><Badge tone="slate">DATA UNAVAILABLE</Badge><Badge tone="slate">DEMONSTRATION DATA</Badge></div></section>
    <section className="final-cta"><div className="eyebrow">ADVISORY INTELLIGENCE</div><h2>Make your next monsoon decision with better information.</h2><p>Explore potential waterlogging risk, review local reports and understand the forecast for your selected area.</p><button className="cta big" onClick={openApp}>Open Waterlogging Intelligence →</button></section>
    <footer><div className="landing-brand"><span className="brandmark">A</span><b>AquaSignal</b></div><div><button onClick={()=>document.getElementById("platform")?.scrollIntoView({behavior:"smooth"})}>Platform</button><button onClick={()=>document.getElementById("how-it-works")?.scrollIntoView({behavior:"smooth"})}>How It Works</button><button onClick={()=>document.getElementById("about")?.scrollIntoView({behavior:"smooth"})}>Data Transparency</button><button onClick={openApp}>Sign In</button><button onClick={()=>alert("Privacy documentation is a placeholder for this local hackathon demonstration.")}>Privacy</button><button onClick={()=>alert("Contact integration is not configured in this demonstration.")}>Contact</button></div><p>Map data © OpenStreetMap contributors. Forecasts are advisory, depend on data availability and model performance, and must not be used as confirmed observations.</p></footer>
  </div>
}

function AreaModal({ close, area, select, preferredCity }: { close: () => void; area: string; select: (area:string)=>void; preferredCity?:"Mumbai"|"Pune" }) {
  const initialCity: City=preferredCity||cityForArea(area);
  const [city,setCity]=useState(initialCity),[candidate,setCandidate]=useState(preferredCity==="Pune"?"Pune · Central Demonstration Area":areaCentres[area]?area:`${initialCity} · ${initialCity==="Mumbai"?"Mithi River":"Central"} Demonstration Area`),[query,setQuery]=useState(""),[demo,setDemo]=useState(true);
  const available=Object.keys(areaCentres).filter(x=>x.startsWith(city)&&(!query||x.toLowerCase().includes(query.toLowerCase())));
  return <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="area-modal geo-modal"><div className="modal-head"><div><Badge>GEOGRAPHIC WORKSPACE SELECTOR</Badge><h2>Choose a monitoring area</h2><p>City → Geographic level → Monitoring area → Confirm</p></div><button onClick={close}>×</button></div>
    <label className="geo-search">Search place, ward or coordinates<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search geographic areas…" /></label>
    <div className="city-choice"><button className={city==="Mumbai"?"selected":""} onClick={()=>{setCity("Mumbai");setCandidate("Mumbai · Mithi River Demonstration Area")}}><b>Mumbai</b><span>2 demonstration areas</span></button><button className={city==="Pune"?"selected":""} onClick={()=>{setCity("Pune");setCandidate("Pune · Central Demonstration Area")}}><b>Pune</b><span>2 demonstration areas</span></button></div>
    <div className="geo-grid"><div><div className="area-form"><label>Geographic level<select><option>City demonstration area</option><option>District / municipal area</option><option>Ward / neighbourhood</option><option>Custom monitoring boundary</option></select></label><label>Map extent<select><option>Selected monitoring area</option><option>City extent</option></select></label></div>
    <div className="recent-areas"><strong>AVAILABLE MONITORING AREAS</strong>{available.map((x,i)=><button className={candidate===x?"selected":""} onClick={()=>{setCandidate(x);setDemo(true)}} key={x}><span>{i?"☆":"★"}</span><div><b>{x}</b><small>{i?"Recent area":"Saved monitoring area"} · Separate {city} demo data</small></div><i>→</i></button>)}</div><div className="coverage-facts"><span><b>Forecast</b>+1h to +6h</span><span><b>Latest input</b>14:32 UTC · Demo</span><span><b>Missing</b>Live drainage sensors</span></div></div>
    <div className="geo-preview"><Map horizon={3} onSelect={()=>{}} layers={["Predicted risk"]} area={candidate}/><Badge tone="slate">MAP-BASED SELECTION</Badge><button>＋ Draw custom boundary</button></div></div>
    <div className="availability"><div><i className={demo?"ok":""}>{demo?"✓":"!"}</i><span><strong>{demo?"Demonstration dataset available":"Validated forecast unavailable"}</strong><small>{demo?"Horizons +1h to +6h · Street map · Demo risk · Reports":"Use demonstration mode to explore product functionality."}</small></span></div><button onClick={()=>setDemo(!demo)}>{demo?"Check live availability":"Use demo data"}</button></div>
    <div className="modal-actions"><button onClick={close}>Cancel</button><button className="cta" disabled={!demo} onClick={()=>select(candidate)}>Open selected area</button></div></div></div>
}

export default function App() {
  const initialAuth=!!authService.getSession();
  const [view,setView]=useState<"landing"|"signin"|"signup"|"app">(()=>location.pathname.startsWith("/app")?(initialAuth?"app":"signin"):location.pathname==="/signup"?(initialAuth?"app":"signup"):location.pathname==="/signin"?(initialAuth?"app":"signin"):"landing"),[authenticated,setAuthenticated]=useState(initialAuth),[page,setPage]=useState("Waterlogging Intelligence"),[horizon,setHorizon]=useState(3),[live,setLive]=useState(false),[areaOpen,setAreaOpen]=useState(false),[liveCameraOpen,setLiveCameraOpen]=useState(false),[area,setArea]=useState(()=>localStorage.getItem("aquasignal-area")||"Mumbai · Mithi River Demonstration Area"),[preferredCity,setPreferredCity]=useState<"Mumbai"|"Pune"|undefined>();
  const authData=authService.getSession();const user=authData?.name||authData?.email?.split("@")[0]||"Demo User";
  useEffect(()=>{const pop=()=>{const p=location.pathname;if(p==="/signup"&&!authenticated)setView("signup");else if(p==="/signin"&&!authenticated)setView("signin");else if(p.startsWith("/app")&&authenticated)setView("app");else setView("landing")};addEventListener("popstate",pop);return()=>removeEventListener("popstate",pop)},[authenticated]);
  const route=(next:"landing"|"signin"|"signup"|"app")=>{const path=next==="landing"?"/":next==="signin"?"/signin":next==="signup"?"/signup":"/app";history.pushState({},"",path);setView(next)};
  const requestApp=()=>authenticated?route("app"):route("signin");
  const authenticatedSuccess=()=>{setAuthenticated(true);route("app");setAreaOpen(true)};
  const logout=()=>{authService.signOut();setAuthenticated(false);setPage("Waterlogging Intelligence");setAreaOpen(false);route("landing")};
  if(view==="landing") return <Landing authenticated={authenticated} signup={()=>route("signup")} openApp={requestApp} exploreArea={city=>{setPreferredCity(city);if(authenticated){route("app");setAreaOpen(true)}else route("signin")}}/>;
  if(view==="signin") return <SignIn back={()=>route("landing")} signup={()=>route("signup")} success={authenticatedSuccess}/>;
  if(view==="signup") return <SignUp back={()=>route("landing")} signin={()=>route("signin")} success={()=>authenticatedSuccess()}/>;
  if(!authenticated){route("signin");return null}
  const navigate=(p:string)=>{setPage(p);if(p==="Geographic Coverage")setAreaOpen(true)};
  return (
    <div className="app">
      <Sidebar page={page} setPage={navigate} area={area} onArea={()=>setAreaOpen(true)} user={user} logout={logout}/>
      <div className="shell">
        <Header horizon={horizon} setHorizon={setHorizon} live={live} setLive={setLive} onArea={()=>setAreaOpen(true)} area={area} user={user} logout={logout} settings={()=>setPage("Settings")} onOpenLiveCamera={()=>setLiveCameraOpen(true)}/>
        {page==="Waterlogging Intelligence" ? (
          <Dashboard horizon={horizon} setHorizon={setHorizon} go={navigate} area={area} onOpenLiveCamera={()=>setLiveCameraOpen(true)}/>
        ) : page==="Forecast Explorer" ? (
          <Forecasts area={area} horizon={horizon} setHorizon={setHorizon}/>
        ) : page==="Citizen Reports" ? (
          <Reports area={area} goMap={()=>setPage("Waterlogging Intelligence")}/>
        ) : page==="AI Incident Intelligence" ? (
          <IncidentIntelligenceSection currentCity={cityForArea(area)} onOpenLiveCamera={()=>setLiveCameraOpen(true)}/>
        ) : page==="Response Intelligence" ? (
          <ResponseIntelligence area={area} horizon={horizon} setHorizon={setHorizon} viewMap={()=>setPage("Waterlogging Intelligence")}/>
        ) : page==="Route Advisory" ? (
          <RouteAdvisorySection currentCity={cityForArea(area)} onOpenLiveCamera={()=>setLiveCameraOpen(true)}/>
        ) : page==="Intelligence Centre" ? (
          <IntelligenceCentre area={area} horizon={horizon} setHorizon={setHorizon}/>
        ) : (
          <Generic page={page}/>
        )}
      </div>
      {areaOpen && (
        <AreaModal area={area} preferredCity={preferredCity} close={()=>{setAreaOpen(false);if(page==="Geographic Coverage")setPage("Waterlogging Intelligence")}} select={x=>{setArea(x);localStorage.setItem("aquasignal-area",x);setPreferredCity(undefined);setAreaOpen(false);setPage("Waterlogging Intelligence")}}/>
      )}
      {liveCameraOpen && (
        <LiveCameraModal
          isOpen={true}
          currentCity={cityForArea(area)}
          onClose={()=>setLiveCameraOpen(false)}
          onIncidentCreated={(incident)=>{
            console.log("New incident submitted:", incident);
            setPage("AI Incident Intelligence");
          }}
        />
      )}
    </div>
  );
}
