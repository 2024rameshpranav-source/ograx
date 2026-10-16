export type City = "Mumbai" | "Pune";

export interface RoadSegment {
  id: string;
  name: string;
  area: string;
  grid: string;
  coords: [number, number];
  path: [number, number][];
  elevation_m: number;
  drainage_capacity_ratio: number;
  historical_incident_count: number;
  primary_factor: string;
  road_gradient_pct: number;
}

export const areaCentres: Record<string, [number, number]> = {
  "Mumbai · Mithi River Demonstration Area": [19.0759, 72.8776],
  "Mumbai · Western Suburbs Demonstration Area": [19.1197, 72.8468],
  "Mumbai · Andheri": [19.1197, 72.8464],
  "Mumbai · Bandra": [19.0607, 72.8362],
  "Mumbai · Chembur": [19.0522, 72.8990],
  "Mumbai · Colaba": [18.9067, 72.8147],
  "Mumbai · Dadar": [19.0178, 72.8478],
  "Mumbai · Kurla": [19.0726, 72.8845],
  "Mumbai · Powai": [19.1176, 72.9060],
  "Mumbai · Sion": [19.0434, 72.8619],
  "Pune · Central Demonstration Area": [18.5204, 73.8567],
  "Pune · Mula-Mutha Demonstration Area": [18.5354, 73.8797],
};

export const mumbaiLocations = [
  { name: "Andheri", coords: [19.1197, 72.8464] as [number, number], elev: 16.0 },
  { name: "Bandra", coords: [19.0607, 72.8362] as [number, number], elev: 15.0 },
  { name: "Chembur", coords: [19.0522, 72.8990] as [number, number], elev: 15.0 },
  { name: "Colaba", coords: [18.9067, 72.8147] as [number, number], elev: 12.0 },
  { name: "Dadar", coords: [19.0178, 72.8478] as [number, number], elev: 10.0 },
  { name: "Kurla", coords: [19.0726, 72.8845] as [number, number], elev: 7.0 },
  { name: "Powai", coords: [19.1176, 72.9060] as [number, number], elev: 43.0 },
  { name: "Sion", coords: [19.0434, 72.8619] as [number, number], elev: 8.0 },
];

export const defaultArea = "Mumbai · Mithi River Demonstration Area";

export const cityForArea = (area: string): City =>
  area.startsWith("Pune") ? "Pune" : "Mumbai";

/**
 * Returns location-specific road segments for a given monitoring area.
 * Each segment has distinct elevation, drainage capacity, historical incident history,
 * and geographic coordinates.
 */
export function getSegmentsForArea(area: string): RoadSegment[] {
  const centre = areaCentres[area] || areaCentres[defaultArea];
  const at = (latOffset: number, lngOffset: number): [number, number] => [
    centre[0] + latOffset,
    centre[1] + lngOffset,
  ];

  if (area.includes("Bandra")) {
    return [
      {
        id: "BND-01",
        name: "Linking Road - Turner Rd Junction",
        area: "Mumbai · Bandra",
        grid: "Grid 14B",
        coords: [19.0607, 72.8362],
        path: [at(0.004, -0.006), at(0.001, -0.002), at(-0.003, 0.003)],
        elevation_m: 14.8,
        drainage_capacity_ratio: 0.65,
        historical_incident_count: 3,
        primary_factor: "Moderate coastal junction with localized runoff dips",
        road_gradient_pct: 1.2,
      },
      {
        id: "BND-02",
        name: "SV Road Bandra Police Station Reach",
        area: "Mumbai · Bandra",
        grid: "Grid 14A",
        coords: [19.0585, 72.8390],
        path: [at(-0.004, 0.002), at(-0.001, 0.005), at(0.003, 0.008)],
        elevation_m: 15.2,
        drainage_capacity_ratio: 0.60,
        historical_incident_count: 2,
        primary_factor: "Commercial corridor with moderate shoulder capacity",
        road_gradient_pct: 1.5,
      },
      {
        id: "BND-03",
        name: "Bandra Terminus Access Underpass",
        area: "Mumbai · Bandra",
        grid: "Grid 15B",
        coords: [19.0645, 72.8420],
        path: [at(0.007, 0.002), at(0.004, 0.005), at(0.001, 0.007)],
        elevation_m: 12.8,
        drainage_capacity_ratio: 0.50,
        historical_incident_count: 5,
        primary_factor: "Railway subway depression collecting track runoff",
        road_gradient_pct: 0.8,
      },
      {
        id: "BND-04",
        name: "Hill Road Lower Junction",
        area: "Mumbai · Bandra",
        grid: "Grid 14C",
        coords: [19.0550, 72.8315],
        path: [at(-0.006, -0.007), at(-0.003, -0.004), at(0.001, -0.001)],
        elevation_m: 16.5,
        drainage_capacity_ratio: 0.70,
        historical_incident_count: 1,
        primary_factor: "Higher terrain slope leading to promenade outfall",
        road_gradient_pct: 2.1,
      },
      {
        id: "BND-05",
        name: "WEH Bandra Flyover Approach",
        area: "Mumbai · Bandra",
        grid: "Grid 15A",
        coords: [19.0680, 72.8450],
        path: [at(0.009, 0.006), at(0.005, 0.008), at(0.002, 0.010)],
        elevation_m: 17.5,
        drainage_capacity_ratio: 0.75,
        historical_incident_count: 1,
        primary_factor: "Elevated expressway deck with rapid discharge",
        road_gradient_pct: 2.5,
      },
    ];
  }

  if (area.includes("Dadar")) {
    return [
      {
        id: "DAD-01",
        name: "Hindmata Flyover Basin & Underpass",
        area: "Mumbai · Dadar",
        grid: "Grid 18B",
        coords: [19.0185, 72.8427],
        path: [at(0.005, -0.006), at(0.001, -0.003), at(-0.003, 0.001)],
        elevation_m: 9.2,
        drainage_capacity_ratio: 0.40,
        historical_incident_count: 8,
        primary_factor: "Natural depression bowl prone to rapid runoff ponding",
        road_gradient_pct: 0.5,
      },
      {
        id: "DAD-02",
        name: "Dadar TT Circle Tramway Stretch",
        area: "Mumbai · Dadar",
        grid: "Grid 18A",
        coords: [19.0178, 72.8478],
        path: [at(-0.004, 0.001), at(-0.001, 0.004), at(0.003, 0.007)],
        elevation_m: 10.1,
        drainage_capacity_ratio: 0.45,
        historical_incident_count: 7,
        primary_factor: "Low-gradient intersection with aged brick sewers",
        road_gradient_pct: 0.7,
      },
      {
        id: "DAD-03",
        name: "Dr. Babasaheb Ambedkar Road Connector",
        area: "Mumbai · Dadar",
        grid: "Grid 18C",
        coords: [19.0220, 72.8455],
        path: [at(0.006, 0.003), at(0.003, 0.005), at(0.000, 0.008)],
        elevation_m: 10.8,
        drainage_capacity_ratio: 0.50,
        historical_incident_count: 4,
        primary_factor: "Central arterial connector between Dadar and Parel",
        road_gradient_pct: 1.0,
      },
      {
        id: "DAD-04",
        name: "Tilak Bridge Western Approach",
        area: "Mumbai · Dadar",
        grid: "Grid 19A",
        coords: [19.0150, 72.8410],
        path: [at(-0.005, -0.005), at(-0.002, -0.002), at(0.001, 0.001)],
        elevation_m: 11.5,
        drainage_capacity_ratio: 0.55,
        historical_incident_count: 3,
        primary_factor: "Railway bridge ramp with restricted shoulder drainage",
        road_gradient_pct: 1.4,
      },
      {
        id: "DAD-05",
        name: "Senapati Bapat Marg Junction",
        area: "Mumbai · Dadar",
        grid: "Grid 19B",
        coords: [19.0125, 72.8385],
        path: [at(-0.008, -0.003), at(-0.004, 0.001), at(0.000, 0.004)],
        elevation_m: 11.0,
        drainage_capacity_ratio: 0.48,
        historical_incident_count: 5,
        primary_factor: "Low corridor carrying west-side drainage discharge",
        road_gradient_pct: 0.9,
      },
    ];
  }

  if (area.includes("Kurla")) {
    return [
      {
        id: "KRL-01",
        name: "Bail Bazar Low-lying Basin",
        area: "Mumbai · Kurla",
        grid: "Grid 22A",
        coords: [19.0726, 72.8845],
        path: [at(0.005, -0.007), at(0.001, -0.003), at(-0.003, 0.001)],
        elevation_m: 6.8,
        drainage_capacity_ratio: 0.35,
        historical_incident_count: 9,
        primary_factor: "Deep floodplain depression vulnerable to Mithi backflow",
        road_gradient_pct: 0.4,
      },
      {
        id: "KRL-02",
        name: "LBS Marg Sheet-flow Reach",
        area: "Mumbai · Kurla",
        grid: "Grid 22B",
        coords: [19.0684, 72.8793],
        path: [at(-0.004, 0.001), at(-0.001, 0.004), at(0.003, 0.007)],
        elevation_m: 7.4,
        drainage_capacity_ratio: 0.38,
        historical_incident_count: 8,
        primary_factor: "Major north-south arterial prone to curb overtopping",
        road_gradient_pct: 0.6,
      },
      {
        id: "KRL-03",
        name: "Kurla West Subway Approach",
        area: "Mumbai · Kurla",
        grid: "Grid 22C",
        coords: [19.0750, 72.8870],
        path: [at(0.007, 0.003), at(0.003, 0.006), at(0.000, 0.009)],
        elevation_m: 6.5,
        drainage_capacity_ratio: 0.30,
        historical_incident_count: 9,
        primary_factor: "Depressed railway subway collecting track runoff",
        road_gradient_pct: 0.5,
      },
      {
        id: "KRL-04",
        name: "Mithi River Bank Service Lane",
        area: "Mumbai · Kurla",
        grid: "Grid 23A",
        coords: [19.0650, 72.8720],
        path: [at(-0.006, -0.008), at(-0.003, -0.004), at(0.001, 0.000)],
        elevation_m: 7.1,
        drainage_capacity_ratio: 0.32,
        historical_incident_count: 7,
        primary_factor: "Direct riverfront lane subject to tidal high-water lock",
        road_gradient_pct: 0.5,
      },
      {
        id: "KRL-05",
        name: "CST Road Junction",
        area: "Mumbai · Kurla",
        grid: "Grid 23B",
        coords: [19.0790, 72.8810],
        path: [at(0.009, 0.002), at(0.005, 0.005), at(0.002, 0.008)],
        elevation_m: 8.5,
        drainage_capacity_ratio: 0.45,
        historical_incident_count: 4,
        primary_factor: "Elevated connection towards BKC corridor",
        road_gradient_pct: 1.1,
      },
    ];
  }

  if (area.includes("Andheri")) {
    return [
      {
        id: "AND-01",
        name: "Andheri Subway S-Curve",
        area: "Mumbai · Andheri",
        grid: "Grid 11A",
        coords: [19.1197, 72.8464],
        path: [at(0.005, -0.006), at(0.001, -0.002), at(-0.003, 0.002)],
        elevation_m: 14.0,
        drainage_capacity_ratio: 0.45,
        historical_incident_count: 7,
        primary_factor: "Steep railway underpass collecting dual-gradient runoff",
        road_gradient_pct: 0.6,
      },
      {
        id: "AND-02",
        name: "WEH Metro Pier Basin",
        area: "Mumbai · Andheri",
        grid: "Grid 11B",
        coords: [19.1160, 72.8520],
        path: [at(-0.004, 0.003), at(-0.001, 0.006), at(0.003, 0.009)],
        elevation_m: 16.2,
        drainage_capacity_ratio: 0.60,
        historical_incident_count: 3,
        primary_factor: "Highway median drain with localized pooling",
        road_gradient_pct: 1.5,
      },
      {
        id: "AND-03",
        name: "SV Road Near Andheri Market",
        area: "Mumbai · Andheri",
        grid: "Grid 11C",
        coords: [19.1220, 72.8430],
        path: [at(0.007, -0.005), at(0.003, -0.002), at(0.000, 0.001)],
        elevation_m: 15.5,
        drainage_capacity_ratio: 0.55,
        historical_incident_count: 4,
        primary_factor: "Commercial market stretch with heavy pedestrian runoff",
        road_gradient_pct: 1.2,
      },
      {
        id: "AND-04",
        name: "Sahar Road Approach",
        area: "Mumbai · Andheri",
        grid: "Grid 12A",
        coords: [19.1130, 72.8580],
        path: [at(-0.006, 0.007), at(-0.003, 0.010), at(0.001, 0.012)],
        elevation_m: 17.0,
        drainage_capacity_ratio: 0.65,
        historical_incident_count: 2,
        primary_factor: "Airport access corridor with modern box drains",
        road_gradient_pct: 1.8,
      },
      {
        id: "AND-05",
        name: "Veera Desai Industrial Low Point",
        area: "Mumbai · Andheri",
        grid: "Grid 12B",
        coords: [19.1260, 72.8370],
        path: [at(0.009, -0.008), at(0.005, -0.004), at(0.002, 0.000)],
        elevation_m: 15.0,
        drainage_capacity_ratio: 0.50,
        historical_incident_count: 4,
        primary_factor: "Flat industrial access road with restricted outfall",
        road_gradient_pct: 1.0,
      },
    ];
  }

  // Generic or Pune fallback segments relative to area centre
  const isPune = area.startsWith("Pune");
  const prefix = isPune ? "PUN" : "MUM";
  const baseElev = isPune ? 555.0 : 12.0;

  return [
    {
      id: `${prefix}-01`,
      name: isPune ? "Alka Talkies Chowk / Deccan Connector" : "Primary Central Arterial Corridor",
      area,
      grid: "Grid 01A",
      coords: at(0.002, -0.004),
      path: [at(0.006, -0.011), at(0.003, -0.005), at(0, 0)],
      elevation_m: baseElev - 1.5,
      drainage_capacity_ratio: 0.50,
      historical_incident_count: 4,
      primary_factor: "Major intersection carrying converging runoff",
      road_gradient_pct: 1.1,
    },
    {
      id: `${prefix}-02`,
      name: isPune ? "Shivajinagar Subway / Underpass Reach" : "Low-lying Railway Subway Approach",
      area,
      grid: "Grid 01B",
      coords: at(-0.002, -0.002),
      path: [at(-0.004, -0.010), at(-0.002, -0.003), at(-0.002, 0.006)],
      elevation_m: baseElev - 3.2,
      drainage_capacity_ratio: 0.42,
      historical_incident_count: 6,
      primary_factor: "Depression funneling storm runoff beneath rail embankment",
      road_gradient_pct: 0.7,
    },
    {
      id: `${prefix}-03`,
      name: isPune ? "Pulachi Wadi Riverside Road" : "Riverfront Drainage Collector Lane",
      area,
      grid: "Grid 02A",
      coords: at(0.006, 0.004),
      path: [at(0.010, 0.001), at(0.006, 0.004), at(0.002, 0.007)],
      elevation_m: baseElev - 4.0,
      drainage_capacity_ratio: 0.38,
      historical_incident_count: 7,
      primary_factor: "Low riverfront embankment subject to high water levels",
      road_gradient_pct: 0.5,
    },
    {
      id: `${prefix}-04`,
      name: isPune ? "Karve Road Low Junction" : "Commercial Spine Low Point",
      area,
      grid: "Grid 02B",
      coords: at(-0.002, 0.007),
      path: [at(-0.007, 0.003), at(-0.002, 0.007), at(0.003, 0.012)],
      elevation_m: baseElev + 1.0,
      drainage_capacity_ratio: 0.62,
      historical_incident_count: 2,
      primary_factor: "Commercial junction with adequate side drains",
      road_gradient_pct: 1.6,
    },
    {
      id: `${prefix}-05`,
      name: isPune ? "Tilak Road Drainage Channel Reach" : "High Terrace Bypass Corridor",
      area,
      grid: "Grid 03A",
      coords: at(0.004, -0.004),
      path: [at(0.009, -0.008), at(0.004, -0.004), at(-0.003, -0.003)],
      elevation_m: baseElev + 2.5,
      drainage_capacity_ratio: 0.68,
      historical_incident_count: 1,
      primary_factor: "Elevated bypass shedding storm runoff efficiently",
      road_gradient_pct: 2.0,
    },
  ];
}

/**
 * Deterministic location-specific heuristic risk calculator.
 * Strictly guarantees that probability and risk category match between
 * DetailPanel and Timeline for any selected segment and horizon.
 */
export function calculateSegmentPrediction(
  segment: RoadSegment,
  horizonHours: number,
  baseRainfallMm: number = 10.0
): {
  probability: number;
  category: "Low" | "Moderate" | "High" | "Severe";
  uncertainty: string;
  rainfallForecastMm: number;
  factors: { name: string; impact: string; weight: string }[];
  timeline: {
    hour: number;
    category: "Low" | "Moderate" | "High" | "Severe";
    probability: number;
    uncertainty: string;
    rainfallMm: number;
  }[];
} {
  const isPune = segment.area.startsWith("Pune");
  const elev = segment.elevation_m;
  const drain = segment.drainage_capacity_ratio;
  const hist = segment.historical_incident_count;

  // Elevation base vulnerability score
  let elevScore = 18;
  if (!isPune) {
    if (elev <= 7.0) elevScore = 35; // Kurla deep basin
    else if (elev <= 10.0) elevScore = 28; // Dadar Hindmata depression
    else if (elev <= 15.0) elevScore = 18; // Bandra coastal junction
    else elevScore = 8; // Powai / elevated
  } else {
    if (elev <= 552.0) elevScore = 32;
    else if (elev <= 556.0) elevScore = 24;
    else elevScore = 14;
  }

  // Generate 6-hour timeline
  const timeline = [1, 2, 3, 4, 5, 6].map((h) => {
    const hourlyRain = baseRainfallMm * (1.0 + (h - 1) * 0.15);
    const thresh = h <= 1 ? 5.0 : h <= 3 ? 10.0 : 20.0;
    const rainRatio = Math.min(3.0, Math.max(0.0, hourlyRain) / thresh);
    const rainScore = Math.min(45.0, rainRatio * 25.0);

    const drainDeficit = Math.max(0.0, 1.0 - drain);
    const drainScore = drainDeficit * 20.0;

    const histScore = Math.min(15.0, hist * 2.0);

    const rawTotal = elevScore + rainScore + drainScore + histScore;
    const horizonMultiplier = 1.0 + (h - 1) * 0.05;
    const prob = Math.max(5, Math.min(95, Math.round(rawTotal * horizonMultiplier)));

    let cat: "Low" | "Moderate" | "High" | "Severe" = "Low";
    if (prob >= 80) cat = "Severe";
    else if (prob >= 60) cat = "High";
    else if (prob >= 35) cat = "Moderate";

    return {
      hour: h,
      category: cat,
      probability: prob,
      uncertainty: `±${8 + h * 2}%`,
      rainfallMm: Math.round(hourlyRain * 10) / 10,
    };
  });

  const active = timeline[horizonHours - 1] || timeline[2];

  const factors = [
    {
      name: "Terrain Elevation",
      impact: `${elev.toFixed(1)}m AMSL · ${elev <= 10.0 ? "Low depression basin" : "Moderate elevation ground"}`,
      weight: `${Math.round((elevScore / (elevScore + 25 + (1 - drain) * 20 + hist * 2)) * 100)}%`,
    },
    {
      name: "Rainfall Accumulation",
      impact: `${active.rainfallMm.toFixed(1)} mm forecast across +${horizonHours}h`,
      weight: `${Math.round((25 / (elevScore + 25 + (1 - drain) * 20 + hist * 2)) * 100)}%`,
    },
    {
      name: "Drainage Capacity",
      impact: `${Math.round(drain * 100)}% capacity · ${drain < 0.5 ? "Discharge bottleneck" : "Standard outfall"}`,
      weight: `${Math.round((((1 - drain) * 20) / (elevScore + 25 + (1 - drain) * 20 + hist * 2)) * 100)}%`,
    },
    {
      name: "Historical Incidents",
      impact: `${hist} historical waterlogging occurrences recorded`,
      weight: `${Math.round(((hist * 2) / (elevScore + 25 + (1 - drain) * 20 + hist * 2)) * 100)}%`,
    },
  ];

  return {
    probability: active.probability,
    category: active.category,
    uncertainty: active.uncertainty,
    rainfallForecastMm: active.rainfallMm,
    factors,
    timeline,
  };
}
