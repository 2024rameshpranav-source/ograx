import { useState, useEffect, useRef, useId } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { appConfig } from "../config";

interface Hotspot {
  id: string;
  name: string;
  ward: string;
  coords: [number, number];
  baseRisk: "Low" | "Moderate" | "High" | "Critical";
  probabilities: number[]; // +1h to +6h
  rainfall: number[]; // mm/h
  elevation: string;
  primaryFactor: string;
  advisory: string;
  reportsCount: number;
}

interface IncidentItem {
  id: string;
  title: string;
  location: string;
  ward: string;
  timeAgo: string;
  waterDepth: string;
  severity: "Critical" | "High" | "Moderate";
  status: "ADMIN-VERIFIED" | "CORROBORATED" | "UNVERIFIED REPORT";
  corroborations: number;
  description: string;
  roadPassable: boolean;
}

interface PriorityAction {
  rank: number;
  location: string;
  ward: string;
  riskScore: number;
  urgency: string;
  etaToPeak: string;
  actionRequired: string;
  resourceAssigned: string;
  status: "Dispatched" | "Standby" | "Monitoring";
  matrixCoords: { x: number; y: number }; // 0 to 100 percentage
}

const MUMBAI_HOTSPOTS: Hotspot[] = [
  {
    id: "HND-01",
    name: "Hindmata Junction",
    ward: "F-South Ward (Dadar)",
    coords: [19.0185, 72.8427],
    baseRisk: "Critical",
    probabilities: [62, 74, 86, 92, 88, 79],
    rainfall: [32, 45, 58, 64, 48, 30],
    elevation: "1.9m AMSL (Depression)",
    primaryFactor: "Saucer-shaped topography + Mithi river backflow",
    advisory: "Deploy 2x 500 GPM dewatering pumps at flyover base immediately.",
    reportsCount: 9,
  },
  {
    id: "MLN-02",
    name: "Milan Subway",
    ward: "H-West Ward (Santacruz)",
    coords: [19.0837, 72.8415],
    baseRisk: "Critical",
    probabilities: [58, 69, 84, 89, 81, 70],
    rainfall: [28, 42, 54, 60, 44, 26],
    elevation: "1.2m AMSL (Railway Underpass)",
    primaryFactor: "Low-lying underpass runoff concentration",
    advisory: "Trigger automatic barrier closure. Divert vehicular traffic to SV Road flyover.",
    reportsCount: 6,
  },
  {
    id: "KRL-03",
    name: "Kurla Kamani & LBS Marg",
    ward: "L Ward (Kurla West)",
    coords: [19.0684, 72.8793],
    baseRisk: "High",
    probabilities: [45, 56, 72, 78, 73, 62],
    rainfall: [25, 36, 48, 52, 40, 24],
    elevation: "3.4m AMSL (River Catchment)",
    primaryFactor: "Mithi River high tide obstruction + stormwater drain choke",
    advisory: "Rapid response trash rake clearance on LBS culvert #4.",
    reportsCount: 4,
  },
  {
    id: "GND-04",
    name: "Gandhi Market (King's Circle)",
    ward: "F-North Ward (Matunga)",
    coords: [19.0308, 72.8598],
    baseRisk: "High",
    probabilities: [40, 52, 68, 75, 69, 58],
    rainfall: [22, 34, 46, 50, 38, 22],
    elevation: "2.1m AMSL (Arterial Basin)",
    primaryFactor: "High catchment inflow with slow gravity outfall",
    advisory: "Keep standby mobile pumps active; divert BEST bus route #22.",
    reportsCount: 5,
  },
  {
    id: "BKC-05",
    name: "BKC Connector / Mithi Bridge",
    ward: "H-East Ward (Bandra Kurla)",
    coords: [19.0596, 72.8656],
    baseRisk: "Moderate",
    probabilities: [28, 38, 49, 57, 51, 42],
    rainfall: [18, 28, 38, 42, 32, 18],
    elevation: "4.8m AMSL",
    primaryFactor: "Localized ponding on eastern approach ramp",
    advisory: "Clear catchpit gratings; inspect upstream Mithi river floodgate status.",
    reportsCount: 2,
  },
  {
    id: "AND-06",
    name: "Andheri Subway",
    ward: "K-West Ward (Andheri)",
    coords: [19.1197, 72.8468],
    baseRisk: "Critical",
    probabilities: [54, 68, 82, 88, 80, 68],
    rainfall: [26, 39, 52, 58, 42, 25],
    elevation: "1.4m AMSL",
    primaryFactor: "Culvert discharge bottleneck under rail corridor",
    advisory: "Engage submerged dewatering pumps; issue commuter alert.",
    reportsCount: 7,
  },
];

const ROAD_SEGMENTS: { name: string; path: [number, number][]; baseRiskIndex: number }[] = [
  {
    name: "Dadar-Hindmata Corridor",
    path: [
      [19.012, 72.841],
      [19.0185, 72.8427],
      [19.025, 72.844],
    ],
    baseRiskIndex: 3, // Critical
  },
  {
    name: "Santacruz-Milan Arterial",
    path: [
      [19.079, 72.8405],
      [19.0837, 72.8415],
      [19.089, 72.843],
    ],
    baseRiskIndex: 3,
  },
  {
    name: "LBS Marg Kurla Reach",
    path: [
      [19.062, 72.875],
      [19.0684, 72.8793],
      [19.076, 72.883],
    ],
    baseRiskIndex: 2, // High
  },
  {
    name: "King's Circle Tramway Stretch",
    path: [
      [19.026, 72.857],
      [19.0308, 72.8598],
      [19.036, 72.862],
    ],
    baseRiskIndex: 2,
  },
  {
    name: "BKC Link Highway",
    path: [
      [19.053, 72.861],
      [19.0596, 72.8656],
      [19.067, 72.871],
    ],
    baseRiskIndex: 1, // Moderate
  },
  {
    name: "Andheri SV Connector",
    path: [
      [19.112, 72.844],
      [19.1197, 72.8468],
      [19.126, 72.849],
    ],
    baseRiskIndex: 3,
  },
  {
    name: "Western Express High-Flyway",
    path: [
      [19.045, 72.847],
      [19.062, 72.853],
      [19.095, 72.857],
    ],
    baseRiskIndex: 0, // Low
  },
  {
    name: "Sion-Bandra Link Road",
    path: [
      [19.043, 72.862],
      [19.051, 72.868],
      [19.058, 72.874],
    ],
    baseRiskIndex: 1,
  },
];

const INCIDENT_REPORTS_DATA: IncidentItem[] = [
  {
    id: "INC-MUM-8921",
    title: "Severe water accumulation at underpass bowl",
    location: "Hindmata Flyover Underpass, Dadar TT",
    ward: "F-South Ward",
    timeAgo: "7 min ago",
    waterDepth: "1.5 ft (45 cm)",
    severity: "Critical",
    status: "ADMIN-VERIFIED",
    corroborations: 12,
    description: "Water depth rising above wheel level of passenger cars. High-capacity dewatering pump #2 operating at 70% capacity.",
    roadPassable: false,
  },
  {
    id: "INC-MUM-8919",
    title: "Traffic stalled due to storm drain backflow",
    location: "Milan Subway East-West Connector",
    ward: "H-West Ward",
    timeAgo: "14 min ago",
    waterDepth: "1.2 ft (36 cm)",
    severity: "Critical",
    status: "ADMIN-VERIFIED",
    corroborations: 9,
    description: "Subway drainage sump overflowed. Mumbai Traffic Police has placed barrier barricades on West approach.",
    roadPassable: false,
  },
  {
    id: "INC-MUM-8914",
    title: "Stormwater drain choke causing road overflow",
    location: "LBS Marg near Kurla Depot junction",
    ward: "L Ward",
    timeAgo: "23 min ago",
    waterDepth: "0.8 ft (24 cm)",
    severity: "High",
    status: "CORROBORATED",
    corroborations: 6,
    description: "Plastic debris accumulation at culvert intake. Slow-moving single lane traffic on central carriageway.",
    roadPassable: true,
  },
  {
    id: "INC-MUM-8908",
    title: "Kerb overflow onto pedestrian footpath",
    location: "Gandhi Market, King's Circle Matunga",
    ward: "F-North Ward",
    timeAgo: "38 min ago",
    waterDepth: "0.6 ft (18 cm)",
    severity: "High",
    status: "CORROBORATED",
    corroborations: 4,
    description: "Heavy surface ponding spreading across bus bays. Pedestrian crossing submerged.",
    roadPassable: true,
  },
  {
    id: "INC-MUM-8896",
    title: "Moderate localized ponding on slow lane",
    location: "BKC Eastern Expressway exit ramp",
    ward: "H-East Ward",
    timeAgo: "52 min ago",
    waterDepth: "0.3 ft (10 cm)",
    severity: "Moderate",
    status: "UNVERIFIED REPORT",
    corroborations: 2,
    description: "Water draining slowly through grated drains. Traffic flowing with slight reduction in speed.",
    roadPassable: true,
  },
];

const RESPONSE_PRIORITIES_DATA: PriorityAction[] = [
  {
    rank: 1,
    location: "Hindmata Flyover Junction",
    ward: "F-South Ward",
    riskScore: 94,
    urgency: "Immediate (Window: 20 min)",
    etaToPeak: "+1.5h",
    actionRequired: "Activate auxiliary diesel pump #3 & deploy sandbag bunding at subway ramp",
    resourceAssigned: "Unit Squad 04 (MCGM Stormwater Team)",
    status: "Dispatched",
    matrixCoords: { x: 88, y: 92 }, // High impact, high probability
  },
  {
    rank: 2,
    location: "Milan Subway Corridor",
    ward: "H-West Ward",
    riskScore: 91,
    urgency: "Immediate (Window: 30 min)",
    etaToPeak: "+2.0h",
    actionRequired: "Enforce automated flood barrier shutoff & redirect traffic to SV Flyover",
    resourceAssigned: "Traffic Police Div. H + Mobile Pump 08",
    status: "Dispatched",
    matrixCoords: { x: 82, y: 88 },
  },
  {
    rank: 3,
    location: "Kurla Kamani & LBS Culvert",
    ward: "L Ward",
    riskScore: 82,
    urgency: "Preemptive (Window: 45 min)",
    etaToPeak: "+3.0h",
    actionRequired: "Deploy mechanical trash-rake machine to clear plastic debris from main drain outlet",
    resourceAssigned: "Drain Maintenance Team L-East",
    status: "Standby",
    matrixCoords: { x: 74, y: 78 },
  },
  {
    rank: 4,
    location: "Gandhi Market King's Circle",
    ward: "F-North Ward",
    riskScore: 78,
    urgency: "Preemptive (Window: 1h 15m)",
    etaToPeak: "+3.5h",
    actionRequired: "Deploy suction tanker & test standby generator for stormwater sump",
    resourceAssigned: "Matunga Ward Emergency Patrol",
    status: "Standby",
    matrixCoords: { x: 68, y: 72 },
  },
  {
    rank: 5,
    location: "BKC Connector / Mithi Ramp",
    ward: "H-East Ward",
    riskScore: 58,
    urgency: "Active Monitoring",
    etaToPeak: "+4.0h",
    actionRequired: "Telemetry monitoring of Mithi River level gauge at high-tide peak (16:15 UTC)",
    resourceAssigned: "CCTV Control Room Hub",
    status: "Monitoring",
    matrixCoords: { x: 58, y: 54 },
  },
  {
    rank: 6,
    location: "Andheri SV Underpass",
    ward: "K-West Ward",
    riskScore: 89,
    urgency: "High Precaution",
    etaToPeak: "+2.5h",
    actionRequired: "Sound subway alert sirens and verify high-capacity submersible pump power relay",
    resourceAssigned: "Rapid Intervention Truck K-02",
    status: "Dispatched",
    matrixCoords: { x: 80, y: 84 },
  },
];

// Color definitions matching the prompt specifications
const RISK_COLORS = {
  Low: "#0F9D9A", // Teal
  Moderate: "#F59E0B", // Amber
  High: "#F97316", // Orange
  Critical: "#EF4444", // Coral Red
};

export default function OperationalPictureSection({ openApp }: { openApp: () => void }) {
  const [activeTab, setActiveTab] = useState<"Risk Map" | "Forecast Timeline" | "Incident Reports" | "Response Priorities">("Risk Map");
  const [activeHorizon, setActiveHorizon] = useState<number>(3); // +3 hours default
  const [selectedHotspot, setSelectedHotspot] = useState<Hotspot>(MUMBAI_HOTSPOTS[0]);
  const [radarActive, setRadarActive] = useState<boolean>(true);
  const [incidentFilter, setIncidentFilter] = useState<string>("All");
  const [selectedIncident, setSelectedIncident] = useState<IncidentItem | null>(null);
  const [selectedPriority, setSelectedPriority] = useState<PriorityAction | null>(RESPONSE_PRIORITIES_DATA[0]);
  const [hoveredPoint, setHoveredPoint] = useState<{ hour: number; prob: number; rain: number } | null>(null);

  // Map DOM refs
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);

  const filterId = useId();

  // Tab definitions
  const tabs = [
    { id: "Risk Map", label: "Risk Map", icon: "🗺️", badge: "Live Digital Twin" },
    { id: "Forecast Timeline", label: "Forecast Timeline", icon: "📈", badge: "1–6h Area Chart" },
    { id: "Incident Reports", label: "Incident Reports", icon: "📋", badge: "Crowd + Verified" },
    { id: "Response Priorities", label: "Response Priorities", icon: "⚡", badge: "Impact Matrix" },
  ] as const;

  // Initialize or update Leaflet Map
  useEffect(() => {
    if (activeTab !== "Risk Map") return;
    if (!mapContainerRef.current) return;

    if (!leafletMapRef.current) {
      // Create map centered on Mumbai Mithi/Dadar central basin
      const map = L.map(mapContainerRef.current, {
        center: [19.055, 72.855],
        zoom: 12,
        zoomControl: false,
        attributionControl: false,
        scrollWheelZoom: false,
      });

      // Use dark themed tile layer or standard tile layer with dark navy styling
      L.tileLayer(appConfig.mapTileUrl, {
        maxZoom: 18,
      }).addTo(map);

      L.control.zoom({ position: "bottomright" }).addTo(map);

      leafletMapRef.current = map;
    }

    const map = leafletMapRef.current;

    // Remove old overlay
    if (layerGroupRef.current) {
      layerGroupRef.current.remove();
    }

    const group = L.layerGroup().addTo(map);
    layerGroupRef.current = group;

    // Draw risk-colored road segments
    ROAD_SEGMENTS.forEach((segment) => {
      // Risk level escalates with forecast horizon
      const baseIdx = segment.baseRiskIndex;
      const adjustedRiskIndex = Math.min(3, baseIdx + (activeHorizon >= 4 ? 1 : 0));
      const riskNames: ("Low" | "Moderate" | "High" | "Critical")[] = ["Low", "Moderate", "High", "Critical"];
      const riskLevel = riskNames[adjustedRiskIndex];
      const color = RISK_COLORS[riskLevel];

      // Outer glow for dark mode
      L.polyline(segment.path, {
        color: color,
        weight: 12,
        opacity: 0.25,
      }).addTo(group);

      // Main crisp line
      const line = L.polyline(segment.path, {
        color: color,
        weight: 4.5,
        opacity: 0.95,
        lineCap: "round",
        lineJoin: "round",
      }).addTo(group);

      line.bindTooltip(
        `<div style="font-family:Inter,sans-serif;font-size:11px;padding:3px 6px;"><strong>${segment.name}</strong><br/><span style="color:${color};font-weight:700;">${riskLevel} Risk (+${activeHorizon}h)</span></div>`,
        { sticky: true }
      );
    });

    // Add Hotspot markers
    MUMBAI_HOTSPOTS.forEach((hotspot) => {
      const prob = hotspot.probabilities[activeHorizon - 1];
      const riskLevel: "Low" | "Moderate" | "High" | "Critical" =
        prob >= 80 ? "Critical" : prob >= 60 ? "High" : prob >= 35 ? "Moderate" : "Low";
      const color = RISK_COLORS[riskLevel];
      const isSelected = selectedHotspot.id === hotspot.id;

      // Custom pulsing HTML marker
      const markerHtml = `
        <div style="position:relative;width:28px;height:28px;cursor:pointer;">
          <div style="position:absolute;inset:0;border-radius:50%;background:${color};opacity:0.35;animation:op-pulse 2s infinite ease-out;"></div>
          <div style="position:absolute;top:5px;left:5px;width:18px;height:18px;border-radius:50%;background:${color};border:2px solid ${isSelected ? "#ffffff" : "#0d1b2a"};box-shadow:0 0 12px ${color};display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:9px;font-weight:800;">
            ${prob >= 80 ? "!" : "●"}
          </div>
        </div>
      `;

      const customIcon = L.divIcon({
        className: "op-custom-hotspot",
        html: markerHtml,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });

      const marker = L.marker(hotspot.coords, { icon: customIcon }).addTo(group);

      marker.on("click", () => {
        setSelectedHotspot(hotspot);
        map.panTo(hotspot.coords, { animate: true, duration: 0.5 });
      });

      marker.bindTooltip(
        `<div style="font-family:Inter,sans-serif;font-size:11px;padding:2px 4px;"><strong>${hotspot.name}</strong><br/>Probability: <b>${prob}%</b> (${riskLevel})</div>`,
        { direction: "top", offset: [0, -10] }
      );
    });

    // Invalidate size in case of tab change
    setTimeout(() => {
      map.invalidateSize();
    }, 150);

    return () => {
      // Clean up when component unmounts
    };
  }, [activeTab, activeHorizon, selectedHotspot]);

  // Clean up Leaflet on total unmount
  useEffect(() => {
    return () => {
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
      }
    };
  }, []);

  // Filtered incidents
  const filteredIncidents = INCIDENT_REPORTS_DATA.filter((item) => {
    if (incidentFilter === "All") return true;
    return item.status === incidentFilter;
  });

  // Calculate current risk category for selected hotspot
  const currentHotspotProb = selectedHotspot.probabilities[activeHorizon - 1];
  const currentHotspotRisk: "Low" | "Moderate" | "High" | "Critical" =
    currentHotspotProb >= 80 ? "Critical" : currentHotspotProb >= 60 ? "High" : currentHotspotProb >= 35 ? "Moderate" : "Low";
  const currentRiskColor = RISK_COLORS[currentHotspotRisk];

  // Forecast Area Chart calculations
  const chartWidth = 660;
  const chartHeight = 260;
  const padding = { top: 25, right: 30, bottom: 45, left: 45 };
  const graphWidth = chartWidth - padding.left - padding.right;
  const graphHeight = chartHeight - padding.top - padding.bottom;

  // Chart data based on selected location
  const chartData = [1, 2, 3, 4, 5, 6].map((hour) => {
    const prob = selectedHotspot.probabilities[hour - 1];
    const rain = selectedHotspot.rainfall[hour - 1];
    return { hour, prob, rain };
  });

  // SVG coordinate mapper
  const getX = (hour: number) => padding.left + ((hour - 1) / 5) * graphWidth;
  const getY = (prob: number) => padding.top + (1 - prob / 100) * graphHeight;

  // Smooth bezier curve generator
  const generateSmoothPath = (points: { x: number; y: number }[]) => {
    if (points.length === 0) return "";
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = i > 0 ? points[i - 1] : points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = i < points.length - 2 ? points[i + 2] : p2;

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
    }
    return d;
  };

  const curvePoints = chartData.map((d) => ({ x: getX(d.hour), y: getY(d.prob) }));
  const smoothCurvePath = generateSmoothPath(curvePoints);
  const areaPath = `${smoothCurvePath} L ${getX(6)} ${getY(0)} L ${getX(1)} ${getY(0)} Z`;

  return (
    <section className="op-showcase-section" id="forecasting" aria-label="One Operational Picture Platform Showcase">
      {/* Section Header */}
      <div className="op-header-container">
        <div className="op-eyebrow-tag">
          <span className="op-eyebrow-bullet"></span>
          ONE OPERATIONAL PICTURE
        </div>
        <h2 className="op-main-title">
          See the risk. <span className="op-gradient-text">Before the city feels it.</span>
        </h2>
        <p className="op-subtitle-text">
          An integrated view of rainfall, waterlogging forecasts, incident reports, and response priorities — designed to turn
          uncertainty into action.
        </p>
      </div>

      {/* Main Asymmetric Command Center Showcase */}
      <div className="op-command-card">
        {/* Top Control Bar with Segmented Tabs */}
        <div className="op-top-bar">
          <div className="op-segmented-nav" role="tablist" aria-label="Operational Picture Views">
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  role="tab"
                  id={`op-tab-${tab.id.replace(/\s+/g, "-")}`}
                  aria-selected={isActive}
                  aria-controls={`op-panel-${tab.id.replace(/\s+/g, "-")}`}
                  tabIndex={isActive ? 0 : -1}
                  className={`op-nav-pill ${isActive ? "active" : ""}`}
                  onClick={() => setActiveTab(tab.id as typeof activeTab)}
                >
                  <span className="op-pill-icon">{tab.icon}</span>
                  <span className="op-pill-label">{tab.label}</span>
                  <span className="op-pill-tag">{tab.badge}</span>
                </button>
              );
            })}
          </div>

          <div className="op-header-actions">
            <span className="op-demo-badge">
              <span className="op-demo-dot"></span>
              DEMONSTRATION DATA · MUMBAI TWIN
            </span>
            <button className="op-workspace-cta" onClick={openApp} aria-label="Open full workspace">
              Open in workspace <span className="op-cta-arrow">→</span>
            </button>
          </div>
        </div>

        {/* Tab 1: Risk Map Centerpiece */}
        {activeTab === "Risk Map" && (
          <div className="op-visual-container op-map-layout" id="op-panel-Risk-Map" role="tabpanel">
            {/* Map Canvas Frame */}
            <div className="op-map-canvas-wrapper">
              {/* Leaflet Host */}
              <div ref={mapContainerRef} className="op-leaflet-container" />

              {/* Subtle Meteorological Radar Overlay */}
              {radarActive && (
                <div className="op-radar-overlay" aria-hidden="true">
                  <div className="op-radar-sweep"></div>
                  <div className="op-radar-ring ring-1"></div>
                  <div className="op-radar-ring ring-2"></div>
                  <div className="op-radar-ring ring-3"></div>
                  <div className="op-radar-scan-line"></div>
                </div>
              )}

              {/* Top Map HUD Bar */}
              <div className="op-map-hud-top">
                <div className="op-hud-status">
                  <span className="op-radar-pulse"></span>
                  <strong>MUMBAI HYDROLOGICAL DIGITAL TWIN</strong>
                  <span className="op-hud-sub">Illustrative Scenario Demonstration · Prototype Spatial Grid</span>
                </div>
                <div className="op-hud-toggles">
                  <button
                    className={`op-toggle-btn ${radarActive ? "active" : ""}`}
                    onClick={() => setRadarActive(!radarActive)}
                    title="Toggle simulated radar sweep"
                  >
                    📡 Radar Sweep: {radarActive ? "ON" : "OFF"}
                  </button>
                </div>
              </div>

              {/* Floating Hotspot Inspector Panel */}
              <div className="op-floating-panel">
                <div className="op-panel-header">
                  <div>
                    <span className="op-panel-eyebrow">MONITORED HOTSPOT</span>
                    <h3 className="op-panel-name">{selectedHotspot.name}</h3>
                    <p className="op-panel-ward">{selectedHotspot.ward}</p>
                  </div>
                  <div
                    className="op-risk-badge"
                    style={{
                      backgroundColor: `${currentRiskColor}20`,
                      color: currentRiskColor,
                      borderColor: `${currentRiskColor}60`,
                    }}
                  >
                    {currentHotspotRisk.toUpperCase()} RISK
                  </div>
                </div>

                <div className="op-panel-stats">
                  <div className="op-stat-box">
                    <span className="op-stat-label">Event Probability</span>
                    <strong className="op-stat-value" style={{ color: currentRiskColor }}>
                      {currentHotspotProb}%
                    </strong>
                    <div className="op-stat-gauge">
                      <div
                        className="op-gauge-fill"
                        style={{
                          width: `${currentHotspotProb}%`,
                          backgroundColor: currentRiskColor,
                        }}
                      ></div>
                    </div>
                  </div>
                  <div className="op-stat-box">
                    <span className="op-stat-label">Forecast Horizon</span>
                    <strong className="op-stat-value">+{activeHorizon} Hours</strong>
                    <span className="op-stat-sub">Uncertainty ±{8 + activeHorizon * 2}%</span>
                  </div>
                </div>

                <div className="op-panel-factors">
                  <div className="op-factor-item">
                    <span className="op-factor-label">Topography / Sump:</span>
                    <strong className="op-factor-val">{selectedHotspot.elevation}</strong>
                  </div>
                  <div className="op-factor-item">
                    <span className="op-factor-label">Dominant Vector:</span>
                    <span className="op-factor-text">{selectedHotspot.primaryFactor}</span>
                  </div>
                </div>

                <div className="op-panel-advisory">
                  <div className="op-advisory-title">
                    <span className="op-advisory-icon">⚠️</span>
                    <strong>Priority Response Protocol</strong>
                  </div>
                  <p className="op-advisory-text">{selectedHotspot.advisory}</p>
                </div>

                {/* Hotspot Quick Selector Chips */}
                <div className="op-hotspot-switcher">
                  <span className="op-switcher-label">Switch Focus:</span>
                  <div className="op-chips-row">
                    {MUMBAI_HOTSPOTS.map((spot) => (
                      <button
                        key={spot.id}
                        className={`op-chip-btn ${selectedHotspot.id === spot.id ? "selected" : ""}`}
                        onClick={() => setSelectedHotspot(spot)}
                      >
                        {spot.name.split(" ")[0]}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Map Risk Legend */}
              <div className="op-map-legend">
                <span className="op-legend-title">Risk Severity Index:</span>
                <div className="op-legend-items">
                  <span className="op-legend-pill">
                    <i style={{ backgroundColor: RISK_COLORS.Low }}></i> Low (&lt;35%)
                  </span>
                  <span className="op-legend-pill">
                    <i style={{ backgroundColor: RISK_COLORS.Moderate }}></i> Moderate (35-59%)
                  </span>
                  <span className="op-legend-pill">
                    <i style={{ backgroundColor: RISK_COLORS.High }}></i> High (60-79%)
                  </span>
                  <span className="op-legend-pill">
                    <i style={{ backgroundColor: RISK_COLORS.Critical }}></i> Critical (≥80%)
                  </span>
                </div>
              </div>
            </div>

            {/* Compact Six-Hour Timeline Bar Beneath Map */}
            <div className="op-timeline-bar">
              <div className="op-timeline-info">
                <span className="op-timeline-label">PREDICTION HORIZON</span>
                <strong>Select Hour ({activeHorizon}h Active)</strong>
              </div>
              <div className="op-timeline-scrubber">
                {[1, 2, 3, 4, 5, 6].map((hour) => {
                  const prob = selectedHotspot.probabilities[hour - 1];
                  const level: "Low" | "Moderate" | "High" | "Critical" =
                    prob >= 80 ? "Critical" : prob >= 60 ? "High" : prob >= 35 ? "Moderate" : "Low";
                  const color = RISK_COLORS[level];
                  const isCurrent = activeHorizon === hour;

                  return (
                    <button
                      key={hour}
                      className={`op-scrubber-btn ${isCurrent ? "active" : ""}`}
                      onClick={() => setActiveHorizon(hour)}
                      aria-label={`Select forecast horizon +${hour} hours`}
                    >
                      <div className="op-scrubber-top">
                        <span className="op-scrubber-hour">+{hour}h</span>
                        <span className="op-scrubber-badge" style={{ color: color }}>
                          {prob}%
                        </span>
                      </div>
                      <div className="op-scrubber-meter">
                        <div className="op-scrubber-meter-fill" style={{ width: `${prob}%`, backgroundColor: color }}></div>
                      </div>
                      <span className="op-scrubber-level">{level}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Forecast Timeline Area Chart */}
        {activeTab === "Forecast Timeline" && (
          <div className="op-visual-container op-chart-layout" id="op-panel-Forecast-Timeline" role="tabpanel">
            <div className="op-chart-header">
              <div>
                <span className="op-panel-eyebrow">CONTINUOUS RISK TRAJECTORY</span>
                <h3 className="op-chart-title">Waterlogging Risk Evolution · {selectedHotspot.name}</h3>
                <p className="op-chart-desc">
                  Modelled event probability curve spanning +1h to +6h with critical operational thresholds.
                </p>
              </div>

              {/* Hotspot Picker */}
              <div className="op-chart-picker">
                <label htmlFor="hotspot-select" className="op-picker-label">
                  Location:
                </label>
                <select
                  id="hotspot-select"
                  className="op-picker-select"
                  value={selectedHotspot.id}
                  onChange={(e) => {
                    const found = MUMBAI_HOTSPOTS.find((h) => h.id === e.target.value);
                    if (found) setSelectedHotspot(found);
                  }}
                >
                  {MUMBAI_HOTSPOTS.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name} ({h.ward.split(" ")[0]})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Interactive SVG Area Chart */}
            <div className="op-svg-chart-wrapper">
              <svg
                viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                className="op-risk-svg-chart"
                preserveAspectRatio="xMidYMid meet"
              >
                <defs>
                  {/* Subtle Gradient Area Fill */}
                  <linearGradient id={`riskGradient-${filterId}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#EF4444" stopOpacity="0.45" />
                    <stop offset="50%" stopColor="#F97316" stopOpacity="0.25" />
                    <stop offset="85%" stopColor="#0F9D9A" stopOpacity="0.08" />
                    <stop offset="100%" stopColor="#0F9D9A" stopOpacity="0.0" />
                  </linearGradient>

                  {/* Line Stroke Gradient */}
                  <linearGradient id={`strokeGradient-${filterId}`} x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#0F9D9A" />
                    <stop offset="40%" stopColor="#F59E0B" />
                    <stop offset="70%" stopColor="#F97316" />
                    <stop offset="100%" stopColor="#EF4444" />
                  </linearGradient>
                </defs>

                {/* Horizontal Grid & Threshold Lines */}
                {[0, 25, 50, 75, 100].map((val) => {
                  const y = getY(val);
                  return (
                    <g key={val} className="op-grid-group">
                      <line
                        x1={padding.left}
                        y1={y}
                        x2={chartWidth - padding.right}
                        y2={y}
                        stroke="#22374e"
                        strokeDasharray={val === 75 || val === 50 ? "4 4" : "none"}
                        strokeWidth={val === 75 || val === 50 ? "1.2" : "0.7"}
                      />
                      <text
                        x={padding.left - 10}
                        y={y + 3}
                        fill="#748ba2"
                        fontSize="9"
                        textAnchor="end"
                        fontFamily="Inter, sans-serif"
                      >
                        {val}%
                      </text>
                    </g>
                  );
                })}

                {/* Risk Threshold Labels */}
                <g className="op-threshold-labels">
                  <text
                    x={chartWidth - padding.right}
                    y={getY(75) - 6}
                    fill="#EF4444"
                    fontSize="8.5"
                    fontWeight="700"
                    textAnchor="end"
                    fontFamily="Inter, sans-serif"
                  >
                    CRITICAL THRESHOLD (≥75%)
                  </text>
                  <text
                    x={chartWidth - padding.right}
                    y={getY(50) - 6}
                    fill="#F97316"
                    fontSize="8.5"
                    fontWeight="700"
                    textAnchor="end"
                    fontFamily="Inter, sans-serif"
                  >
                    HIGH RISK THRESHOLD (50%)
                  </text>
                </g>

                {/* Vertical Selection Indicator for Active Forecast Hour */}
                <g className="op-active-hour-line">
                  <line
                    x1={getX(activeHorizon)}
                    y1={padding.top}
                    x2={getX(activeHorizon)}
                    y2={chartHeight - padding.bottom}
                    stroke="#14B8A6"
                    strokeWidth="2"
                    strokeDasharray="4 3"
                  />
                  <rect
                    x={getX(activeHorizon) - 24}
                    y={padding.top - 18}
                    width="48"
                    height="18"
                    rx="4"
                    fill="#14B8A6"
                  />
                  <text
                    x={getX(activeHorizon)}
                    y={padding.top - 6}
                    fill="#0d1b2a"
                    fontSize="9.5"
                    fontWeight="800"
                    textAnchor="middle"
                    fontFamily="Inter, sans-serif"
                  >
                    +{activeHorizon}h Active
                  </text>
                </g>

                {/* Area Fill */}
                <path d={areaPath} fill={`url(#riskGradient-${filterId})`} />

                {/* Smooth Curve Stroke */}
                <path
                  d={smoothCurvePath}
                  fill="none"
                  stroke={`url(#strokeGradient-${filterId})`}
                  strokeWidth="3.5"
                  strokeLinecap="round"
                />

                {/* Interactive Data Points */}
                {chartData.map((d) => {
                  const x = getX(d.hour);
                  const y = getY(d.prob);
                  const isSelected = activeHorizon === d.hour;
                  const pointColor =
                    d.prob >= 80 ? RISK_COLORS.Critical : d.prob >= 60 ? RISK_COLORS.High : d.prob >= 35 ? RISK_COLORS.Moderate : RISK_COLORS.Low;

                  return (
                    <g
                      key={d.hour}
                      className="op-chart-point"
                      onClick={() => setActiveHorizon(d.hour)}
                      onMouseEnter={() => setHoveredPoint(d)}
                      onMouseLeave={() => setHoveredPoint(null)}
                      style={{ cursor: "pointer" }}
                    >
                      {/* Outer pulse for selected */}
                      {isSelected && (
                        <circle cx={x} cy={y} r="10" fill={pointColor} opacity="0.3" />
                      )}
                      <circle
                        cx={x}
                        cy={y}
                        r={isSelected ? 6 : 4.5}
                        fill={pointColor}
                        stroke="#0d1b2a"
                        strokeWidth="2"
                      />
                      {/* Label on point */}
                      <text
                        x={x}
                        y={y - 10}
                        fill="#ffffff"
                        fontSize="9"
                        fontWeight="700"
                        textAnchor="middle"
                        fontFamily="Inter, sans-serif"
                      >
                        {d.prob}%
                      </text>
                      {/* X-axis label */}
                      <text
                        x={x}
                        y={chartHeight - padding.bottom + 18}
                        fill={isSelected ? "#14B8A6" : "#748ba2"}
                        fontSize="10"
                        fontWeight={isSelected ? "800" : "500"}
                        textAnchor="middle"
                        fontFamily="Inter, sans-serif"
                      >
                        +{d.hour}h
                      </text>
                    </g>
                  );
                })}

                {/* Hover Tooltip Box */}
                {hoveredPoint && (
                  <g
                    transform={`translate(${Math.min(
                      chartWidth - 130,
                      Math.max(padding.left + 10, getX(hoveredPoint.hour) - 60)
                    )}, ${Math.max(padding.top + 5, getY(hoveredPoint.prob) - 65)})`}
                  >
                    <rect width="125" height="52" rx="6" fill="#10253f" stroke="#14B8A6" strokeWidth="1" />
                    <text x="10" y="18" fill="#14B8A6" fontSize="9.5" fontWeight="800" fontFamily="Inter, sans-serif">
                      Forecast: +{hoveredPoint.hour}h Horizon
                    </text>
                    <text x="10" y="32" fill="#ffffff" fontSize="9" fontFamily="Inter, sans-serif">
                      Probability: <tspan fontWeight="800">{hoveredPoint.prob}%</tspan>
                    </text>
                    <text x="10" y="44" fill="#aebdcc" fontSize="8.5" fontFamily="Inter, sans-serif">
                      Rainfall: {hoveredPoint.rain} mm/h · ±{8 + hoveredPoint.hour * 2}%
                    </text>
                  </g>
                )}
              </svg>
            </div>

            {/* Evolution Metrics & Insights Grid */}
            <div className="op-chart-metrics-row">
              <div className="op-metric-card">
                <span className="op-metric-label">Peak Escalation Window</span>
                <strong className="op-metric-val" style={{ color: "#EF4444" }}>
                  +4.0h (92% Risk)
                </strong>
                <span className="op-metric-sub">Runoff volume surpasses drainage threshold</span>
              </div>
              <div className="op-metric-card">
                <span className="op-metric-label">Predicted Rainfall Peak</span>
                <strong className="op-metric-val">64 mm/h at +4h</strong>
                <span className="op-metric-sub">Cum. 6-hour rainfall: 277 mm</span>
              </div>
              <div className="op-metric-card">
                <span className="op-metric-label">Drainage Margin</span>
                <strong className="op-metric-val" style={{ color: "#F97316" }}>
                  18% Residual Sump
                </strong>
                <span className="op-metric-sub">High tide obstruction: 16:15 UTC</span>
              </div>
              <div className="op-metric-card">
                <span className="op-metric-label">Model Confidence</span>
                <strong className="op-metric-val">High (94.2%)</strong>
                <span className="op-metric-sub">Fresh radar input (updated 2m ago)</span>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Incident Reports Stream */}
        {activeTab === "Incident Reports" && (
          <div className="op-visual-container op-reports-layout" id="op-panel-Incident-Reports" role="tabpanel">
            {/* Header & Filter Controls */}
            <div className="op-reports-head">
              <div>
                <span className="op-panel-eyebrow">FIELD VALIDATION FEED</span>
                <h3 className="op-reports-title">Citizen Submissions & Municipal Ground Truth</h3>
                <p className="op-reports-desc">
                  Separating crowdsourced citizen evidence from verified responder observations in real-time.
                </p>
              </div>

              {/* Status Filter Tabs */}
              <div className="op-filter-tabs">
                {["All", "ADMIN-VERIFIED", "CORROBORATED", "UNVERIFIED REPORT"].map((status) => (
                  <button
                    key={status}
                    className={`op-filter-chip ${incidentFilter === status ? "active" : ""}`}
                    onClick={() => setIncidentFilter(status)}
                  >
                    {status === "All" ? "All Incidents" : status.replace(" REPORT", "")}
                  </button>
                ))}
              </div>
            </div>

            {/* List & Detail Split View */}
            <div className="op-reports-split">
              {/* Incident List */}
              <div className="op-incident-list">
                {filteredIncidents.map((incident, idx) => {
                  const isSelected = selectedIncident?.id === incident.id;
                  const toneColor =
                    incident.status === "ADMIN-VERIFIED"
                      ? "#10B981"
                      : incident.status === "CORROBORATED"
                      ? "#38BDF8"
                      : "#F59E0B";

                  return (
                    <div
                      key={incident.id}
                      className={`op-incident-card ${isSelected ? "selected" : ""}`}
                      onClick={() => setSelectedIncident(incident)}
                    >
                      <div className="op-incident-top">
                        <span className="op-incident-rank">#{idx + 1}</span>
                        <span
                          className="op-incident-status-tag"
                          style={{
                            color: toneColor,
                            backgroundColor: `${toneColor}18`,
                            borderColor: `${toneColor}40`,
                          }}
                        >
                          {incident.status}
                        </span>
                        <span className="op-incident-time">{incident.timeAgo}</span>
                      </div>

                      <h4 className="op-incident-name">{incident.title}</h4>
                      <p className="op-incident-loc">
                        📍 {incident.location} · <b>{incident.ward}</b>
                      </p>

                      <div className="op-incident-meta">
                        <span className="op-meta-item">
                          Water Depth: <b>{incident.waterDepth}</b>
                        </span>
                        <span className="op-meta-item">
                          Corroborated by: <b>{incident.corroborations} Citizens</b>
                        </span>
                        <span
                          className={`op-passable-tag ${incident.roadPassable ? "passable" : "blocked"}`}
                        >
                          {incident.roadPassable ? "Passable w/ Caution" : "Road Blocked"}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Detail Sidebar / Protocol Card */}
              <div className="op-incident-detail-panel">
                {selectedIncident ? (
                  <div className="op-detail-content">
                    <div className="op-detail-banner">
                      <span className="op-detail-id">{selectedIncident.id}</span>
                      <span className="op-detail-badge">{selectedIncident.severity} Severity</span>
                    </div>

                    <h4 className="op-detail-title">{selectedIncident.title}</h4>
                    <p className="op-detail-desc">{selectedIncident.description}</p>

                    <div className="op-evidence-box">
                      <span className="op-evidence-title">Telemetry & Verification Chain</span>
                      <div className="op-chain-step">
                        <span className="op-chain-check">✓</span>
                        <div>
                          <strong>Initial Citizen Submission</strong>
                          <small>Submitted via mobile geofence · GPS Accuracy 8m</small>
                        </div>
                      </div>
                      <div className="op-chain-step">
                        <span className="op-chain-check">✓</span>
                        <div>
                          <strong>Cross-Corroboration</strong>
                          <small>{selectedIncident.corroborations} independent citizen reports within 250m</small>
                        </div>
                      </div>
                      <div className="op-chain-step">
                        <span className="op-chain-check">
                          {selectedIncident.status === "ADMIN-VERIFIED" ? "✓" : "○"}
                        </span>
                        <div>
                          <strong>Municipal Responder Verification</strong>
                          <small>
                            {selectedIncident.status === "ADMIN-VERIFIED"
                              ? "Field inspected and confirmed by Ward Traffic Inspector"
                              : "Queued for physical inspection by emergency team"}
                          </small>
                        </div>
                      </div>
                    </div>

                    <div className="op-detail-action-bar">
                      <button className="op-action-btn primary" onClick={openApp}>
                        Corroborate in Workspace →
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="op-detail-empty">
                    <span className="op-empty-icon">👈</span>
                    <h4>Select an Incident</h4>
                    <p>Click on any report to inspect its ground truth verification trail, water depth, and responder log.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tab 4: Response Priorities Matrix & Queue */}
        {activeTab === "Response Priorities" && (
          <div className="op-visual-container op-priorities-layout" id="op-panel-Response-Priorities" role="tabpanel">
            <div className="op-priorities-head">
              <div>
                <span className="op-panel-eyebrow">OPERATIONAL DISPATCH MATRIX</span>
                <h3 className="op-priorities-title">Resource Allocation & Escalation Watch</h3>
                <p className="op-priorities-desc">
                  Algorithmic ranking combining predicted flood severity, traffic density, and critical infrastructure proximity.
                </p>
              </div>
              <div className="op-matrix-summary">
                <span className="op-summary-stat">
                  <b>{RESPONSE_PRIORITIES_DATA.length}</b> Zones Triaged
                </span>
                <span className="op-summary-stat">
                  <b style={{ color: "#EF4444" }}>3</b> High-Priority Dispatches
                </span>
              </div>
            </div>

            <div className="op-priorities-split">
              {/* 2D Risk-Impact Matrix Visualizer */}
              <div className="op-matrix-visualizer">
                <div className="op-matrix-label-top">HIGH SEVERITY / WATERLOGGING PROBABILITY ▲</div>
                <div className="op-matrix-grid">
                  {/* Quadrant Backing */}
                  <div className="op-quadrant quad-tl">
                    <span className="op-quad-title">Preemptive Standby</span>
                  </div>
                  <div className="op-quadrant quad-tr">
                    <span className="op-quad-title">Immediate Deployment (Critical)</span>
                  </div>
                  <div className="op-quadrant quad-bl">
                    <span className="op-quad-title">Routine Surveillance</span>
                  </div>
                  <div className="op-quadrant quad-br">
                    <span className="op-quad-title">Active Monitoring</span>
                  </div>

                  {/* Plotted Priority Nodes */}
                  {RESPONSE_PRIORITIES_DATA.map((p) => {
                    const isSelected = selectedPriority?.rank === p.rank;
                    const nodeColor = p.riskScore >= 90 ? "#EF4444" : p.riskScore >= 75 ? "#F97316" : "#0F9D9A";

                    return (
                      <button
                        key={p.rank}
                        className={`op-matrix-node ${isSelected ? "selected" : ""}`}
                        style={{
                          left: `${p.matrixCoords.x}%`,
                          top: `${100 - p.matrixCoords.y}%`,
                          backgroundColor: nodeColor,
                        }}
                        onClick={() => setSelectedPriority(p)}
                        title={`Rank #${p.rank}: ${p.location} (${p.riskScore} Risk Score)`}
                      >
                        #{p.rank}
                      </button>
                    );
                  })}
                </div>
                <div className="op-matrix-label-bottom">INFRASTRUCTURE CRITICALITY / TRAFFIC DENSITY ▶</div>
              </div>

              {/* Action Queue List */}
              <div className="op-priority-queue">
                <div className="op-queue-header">
                  <span>DISPATCH QUEUE</span>
                  <span>ESCALATION WINDOW</span>
                </div>
                <div className="op-queue-items">
                  {RESPONSE_PRIORITIES_DATA.map((item) => {
                    const isSelected = selectedPriority?.rank === item.rank;
                    const tone = item.riskScore >= 90 ? "#EF4444" : item.riskScore >= 75 ? "#F97316" : "#0F9D9A";

                    return (
                      <div
                        key={item.rank}
                        className={`op-queue-card ${isSelected ? "selected" : ""}`}
                        onClick={() => setSelectedPriority(item)}
                      >
                        <div className="op-queue-card-top">
                          <span className="op-queue-rank" style={{ backgroundColor: `${tone}20`, color: tone }}>
                            #{item.rank}
                          </span>
                          <strong className="op-queue-location">{item.location}</strong>
                          <span className="op-queue-eta" style={{ color: tone }}>
                            {item.urgency}
                          </span>
                        </div>

                        <p className="op-queue-action">
                          <b>Action:</b> {item.actionRequired}
                        </p>

                        <div className="op-queue-footer">
                          <span className="op-queue-resource">Assigned: {item.resourceAssigned}</span>
                          <span className={`op-queue-status ${item.status.toLowerCase()}`}>{item.status}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
