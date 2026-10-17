import { appConfig } from "../config";
import type { City } from "../data/geography";
import type { DemoReport } from "./reports";

const API_BASE = appConfig.apiUrl || "http://localhost:8000";

export interface PredictionInputFeatures {
  rainfall_mm: number;
  rainfall_intensity?: number;
  drainage_capacity_ratio?: number;
  elevation_m?: number;
  tide_level_m?: number;
  soil_saturation_index?: number;
  road_gradient_pct?: number;
  historical_incident_count?: number;
  extra_features?: Record<string, unknown>;
}

export interface PredictionRequest {
  city: City | string;
  location_id?: string;
  location_name?: string;
  latitude?: number;
  longitude?: number;
  forecast_horizon_hours?: number;
  features: PredictionInputFeatures;
}

export interface PredictionResponse {
  city: string;
  location_id?: string;
  location_name?: string;
  forecast_horizon_hours: number;
  risk_probability: number;
  risk_category: "Low" | "Moderate" | "High" | "Critical";
  model_id: string;
  prediction_timestamp: string;
  input_freshness: string;
  uncertainty_range?: string;
  is_demonstration_fallback: boolean;
  details: Record<string, unknown>;
}

export interface ForecastTimelineItem {
  horizon_hours: number;
  timestamp: string;
  risk_probability: number;
  risk_category: string;
  rainfall_forecast_mm?: number;
  confidence_level: string;
}

export interface ForecastTimelineResponse {
  city: string;
  location_name: string;
  timeline: ForecastTimelineItem[];
  generated_at: string;
  model_id: string;
  source: "model_prediction" | "model_unavailable";
}

export type MumbaiWarningStatus =
  | "NO_RAINFALL_SIGNAL"
  | "LOW_RAINFALL_SIGNAL"
  | "RAINFALL_WATCH"
  | "DATA_CHECK_REQUIRED";

export interface MumbaiHotspotEvidence {
  reported_evidence: string;
  match_status: string;
  source: string | null;
  source_date: string | null;
  risk_label_usable: boolean;
}

export interface MumbaiLocationScreening {
  location_name: string;
  location_id: string;
  latitude: number;
  longitude: number;
  elevation_m: number;
  warning_status: MumbaiWarningStatus;
  warning_1h?: MumbaiWarningStatus;
  warning_3h?: MumbaiWarningStatus;
  warning_6h?: MumbaiWarningStatus;
  overall_screening_status?: MumbaiWarningStatus;
  screening_status?: MumbaiWarningStatus;
  screening_basis?: string;
  recent_rainfall_mm: number | null;
  forecast_rainfall_mm: number | null;
  rain_last_1h_mm?: number | null;
  rain_last_3h_mm?: number | null;
  rain_last_6h_mm?: number | null;
  rain_last_24h_mm: number | null;
  rain_next_1h_mm?: number | null;
  rain_next_3h_mm?: number | null;
  rain_next_6h_mm?: number | null;
  thresholds: { forecast: number; recent: number };
  all_thresholds?: Record<number, { forecast: number; recent: number }>;
  explanation: string;
  data_status: string;
  data_source: string;
  observation_time: string;
  waterlogging_probability: null;
  model_validation_status?: string;
  warning_engine_status?: string;
  hotspot_evidence: MumbaiHotspotEvidence;
}

export interface MumbaiScreeningResponse {
  success: boolean;
  city: "mumbai";
  prediction_type: "rule_based_rainfall_screening";
  validation_status: "NOT_VALIDATED";
  warning_engine_status: string;
  horizon_hours: number;
  overall_screening_status: MumbaiWarningStatus;
  status_breakdown: Record<string, number>;
  generated_at: string;
  data_source: string;
  data_freshness: string;
  locations: MumbaiLocationScreening[];
  disclaimer: string;
}

export interface MumbaiLocationMetadata {
  location_id: string;
  location_name: string;
  latitude: number;
  longitude: number;
  elevation_m: number;
  hotspot_evidence: MumbaiHotspotEvidence;
}


export interface BackendHealthResponse {
  status: string;
  version: string;
  environment: string;
  models_all_ready: boolean;
  models: Record<string, {
    city: string;
    loaded: boolean;
    configured_path: string;
    model_type: string;
    status: string;
  }>;
  supported_cities: string[];
}

export interface AnalyticsOverviewResponse {
  city: string;
  total_reports: number;
  reports_by_status: Record<string, number>;
  reports_by_severity: Record<string, number>;
  total_predictions: number;
  latest_prediction?: {
    location_name: string;
    risk_score: number;
    risk_category: string;
    forecast_horizon_hours: number;
    created_at: string;
  };
  data_freshness_minutes: number;
  models_status: Record<string, unknown>;
}

async function fetchJson<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorDetail = typeof errorJson.detail === "string" ? errorJson.detail : JSON.stringify(errorJson.detail);
      }
    } catch {
      // Ignore json parse error
    }
    throw new Error(errorDetail);
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  /**
   * Inspect backend health and ML model status
   */
  async getHealth(): Promise<BackendHealthResponse> {
    return fetchJson<BackendHealthResponse>("/api/health");
  },

  /**
   * Get supported cities
   */
  async getCities(): Promise<{ supported_cities: string[]; models: Record<string, unknown> }> {
    return fetchJson<{ supported_cities: string[]; models: Record<string, unknown> }>("/api/cities");
  },

  /**
   * Submit input features for early-warning waterlogging prediction
   */
  async predict(request: PredictionRequest): Promise<PredictionResponse> {
    return fetchJson<PredictionResponse>("/api/predictions", {
      method: "POST",
      body: JSON.stringify(request),
    });
  },

  /**
   * Retrieve the latest stored prediction for a city
   */
  async getLatestPrediction(city: string): Promise<PredictionResponse | null> {
    try {
      return await fetchJson<PredictionResponse>(`/api/predictions/${encodeURIComponent(city)}/latest`);
    } catch {
      return null;
    }
  },

  /**
   * Generate 6-hour forecast timeline for a location
   */
  async getForecastTimeline(
    city: string,
    locationName: string = "Arterial Corridor",
    baseRainfallMm: number = 35.0,
    locationId?: string,
    latitude?: number,
    longitude?: number
  ): Promise<ForecastTimelineResponse> {
    const params = new URLSearchParams({
      location_name: locationName,
      base_rainfall_mm: String(baseRainfallMm),
    });
    if (locationId) params.append("location_id", locationId);
    if (latitude !== undefined) params.append("latitude", String(latitude));
    if (longitude !== undefined) params.append("longitude", String(longitude));
    return fetchJson<ForecastTimelineResponse>(`/api/predictions/${encodeURIComponent(city)}/forecast?${params}`);
  },

  /**
   * List citizen reports from backend database
   */
  async getReports(params?: {
    city?: string;
    status?: string;
    severity?: string;
    q?: string;
    skip?: number;
    limit?: number;
  }): Promise<{ total: number; reports: DemoReport[]; skip: number; limit: number }> {
    const searchParams = new URLSearchParams();
    if (params?.city) searchParams.append("city", params.city);
    if (params?.status && params.status !== "All") searchParams.append("status", params.status);
    if (params?.severity && params.severity !== "All") searchParams.append("severity", params.severity);
    if (params?.q) searchParams.append("q", params.q);
    if (params?.skip !== undefined) searchParams.append("skip", String(params.skip));
    if (params?.limit !== undefined) searchParams.append("limit", String(params.limit));

    const queryStr = searchParams.toString();
    return fetchJson(`/api/reports${queryStr ? `?${queryStr}` : ""}`);
  },

  /**
   * Upload an evidence photograph to the backend using multipart FormData
   * Automatically omits manual Content-Type so browser sets correct boundary
   */
  async uploadPhoto(file: File): Promise<{ photo_url: string; filename: string; size_bytes: number; content_type: string }> {
    const formData = new FormData();
    formData.append("file", file);

    const url = `${API_BASE}/api/reports/upload-photo`;
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let errorDetail = `Photo upload failed (HTTP ${response.status} ${response.statusText})`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorDetail = typeof errorJson.detail === "string" ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch {
        // ignore JSON parse error
      }
      throw new Error(errorDetail);
    }

    return response.json();
  },

  /**
   * Submit new report to backend database
   */
  async createReport(report: Omit<DemoReport, "createdAt" | "updatedAt">): Promise<DemoReport> {
    return fetchJson<DemoReport>("/api/reports", {
      method: "POST",
      body: JSON.stringify(report),
    });
  },

  /**
   * Update report status in backend database
   */
  async updateReportStatus(reportId: string, status: DemoReport["status"]): Promise<DemoReport> {
    return fetchJson<DemoReport>(`/api/reports/${encodeURIComponent(reportId)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  },

  /**
   * Fetch city analytics overview
   */
  async getAnalyticsOverview(city: string = "Mumbai"): Promise<AnalyticsOverviewResponse> {
    return fetchJson<AnalyticsOverviewResponse>(`/api/analytics/overview?city=${encodeURIComponent(city)}`);
  },

  /**
   * Fetch the 8 supported Mumbai monitoring locations and hotspot metadata
   */
  async getMumbaiLocations(): Promise<MumbaiLocationMetadata[]> {
    return fetchJson<MumbaiLocationMetadata[]>("/api/cities/mumbai/locations");
  },

  /**
   * Fetch rule-based rainfall screening results for Mumbai (horizon 1, 3, or 6 hours)
   */
  async getMumbaiWaterlogging(hours: number = 3, refresh: boolean = false): Promise<MumbaiScreeningResponse> {
    const params = new URLSearchParams({ hours: hours.toString() });
    if (refresh) params.append("refresh", "true");
    return fetchJson<MumbaiScreeningResponse>(`/api/cities/mumbai/waterlogging?${params}`);
  },

  /**
   * Run Hugging Face model inference on captured/uploaded incident image
   */
  async analyzeIncidentPhoto(file: File): Promise<IncidentAnalyzeResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const url = `${API_BASE}/api/incidents/analyze`;
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      let errorDetail = `AI analysis failed (HTTP ${response.status})`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) errorDetail = errorJson.detail;
      } catch {
        // ignore
      }
      throw new Error(errorDetail);
    }
    return response.json();
  },

  /**
   * Submit new confirmed incident to historical intelligence database
   */
  async createIncident(request: IncidentCreateRequest): Promise<IncidentResponse> {
    return fetchJson<IncidentResponse>("/api/incidents", {
      method: "POST",
      body: JSON.stringify(request),
    });
  },

  /**
   * Retrieve historical incident reports
   */
  async getIncidents(params?: {
    city?: string;
    status?: string;
    is_demo?: boolean;
    skip?: number;
    limit?: number;
  }): Promise<{ total: number; skip: number; limit: number; incidents: IncidentResponse[] }> {
    const searchParams = new URLSearchParams();
    if (params?.city) searchParams.append("city", params.city);
    if (params?.status && params.status !== "ALL") searchParams.append("status", params.status);
    if (params?.is_demo !== undefined) searchParams.append("is_demo", String(params.is_demo));
    if (params?.skip !== undefined) searchParams.append("skip", String(params.skip));
    if (params?.limit !== undefined) searchParams.append("limit", String(params.limit));

    const q = searchParams.toString();
    return fetchJson(`/api/incidents/history${q ? `?${q}` : ""}`);
  },

  /**
   * Retrieve single incident details
   */
  async getIncidentById(incidentId: string): Promise<IncidentResponse> {
    return fetchJson<IncidentResponse>(`/api/incidents/${encodeURIComponent(incidentId)}`);
  },

  /**
   * Submit reviewer ground truth label and verification status
   */
  async reviewIncident(incidentId: string, review: IncidentReviewRequest): Promise<IncidentResponse> {
    return fetchJson<IncidentResponse>(`/api/incidents/${encodeURIComponent(incidentId)}/review`, {
      method: "PATCH",
      body: JSON.stringify(review),
    });
  },

  /**
   * Calculate dynamic location risk with report-derived adjustments
   */
  async getAreaDynamicRisk(params: {
    city?: string;
    location_name?: string;
    latitude: number;
    longitude: number;
    radius_km?: number;
  }): Promise<DynamicRiskResponse> {
    const searchParams = new URLSearchParams({
      city: params.city || "Mumbai",
      location_name: params.location_name || "Location",
      latitude: String(params.latitude),
      longitude: String(params.longitude),
      radius_km: String(params.radius_km || 1.5),
    });
    return fetchJson<DynamicRiskResponse>(`/api/incidents/risk/area?${searchParams}`);
  },

  /**
   * Fetch model evaluation accuracy metrics
   */
  async getModelEvaluation(includeDemo: boolean = true): Promise<ModelEvaluationResponse> {
    return fetchJson<ModelEvaluationResponse>(`/api/incidents/models/evaluation?include_demo=${includeDemo}`);
  },

  /**
   * Fetch demonstration dataset summary
   */
  async getDemoSummary(): Promise<DemoSummaryResponse> {
    return fetchJson<DemoSummaryResponse>("/api/incidents/demo/summary");
  },

  /**
   * Seed demonstration dataset
   */
  async seedDemoIncidents(): Promise<{ success: boolean; message: string; demo_count: number }> {
    return fetchJson("/api/incidents/demo/seed", { method: "POST" });
  },

  /**
   * Reset demonstration dataset
   */
  async resetDemoIncidents(): Promise<{ success: boolean; message: string; deleted_count: number }> {
    return fetchJson("/api/incidents/demo/reset", { method: "POST" });
  },

  /**
   * Fetch commuter corridor presets for a city
   */
  async getRoutePresets(city?: string): Promise<RoutePreset[]> {
    const q = city ? `?city=${encodeURIComponent(city)}` : "";
    return fetchJson(`/api/routes/presets${q}`);
  },

  /**
   * Calculate waterlogging-aware route recommendations
   */
  async getRouteRecommendations(request: RouteRequest): Promise<RouteComparisonResponse> {
    return fetchJson("/api/routes/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  },
};

export interface IncidentAnalyzeResponse {
  success: boolean;
  model_name: string;
  predicted_class: "Flooded Scene" | "Non Flooded";
  model_score: number;
  class_probabilities: Record<string, number>;
  is_flooded: boolean;
  confidence_level: "HIGH" | "MODERATE" | "LOW";
  image_reference?: string;
  warning_note?: string;
}

export interface IncidentCreateRequest {
  city: string;
  location_name: string;
  latitude: number;
  longitude: number;
  captured_at?: string;
  image_reference?: string;
  predicted_class: string;
  model_score: number;
  source_type?: string;
  is_demo?: boolean;
  notes?: string;
}

export interface IncidentResponse {
  id: string;
  city: string;
  location_name: string;
  latitude: number;
  longitude: number;
  captured_at: string;
  submitted_at: string;
  image_reference?: string;
  predicted_class: string;
  model_score: number;
  model_name: string;
  verification_status: "PENDING" | "VERIFIED_GENUINE" | "VERIFIED_NON_WATERLOGGING" | "INCONCLUSIVE" | "REJECTED" | "DUPLICATE";
  source_type: string;
  is_demo: boolean;
  duplicate_of?: string;
  baseline_risk_score: number;
  report_risk_adjustment: number;
  final_risk_score: number;
  ground_truth_label?: string;
  reviewed_by?: string;
  reviewed_at?: string;
  reviewer_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface IncidentReviewRequest {
  verification_status: "VERIFIED_GENUINE" | "VERIFIED_NON_WATERLOGGING" | "INCONCLUSIVE" | "REJECTED" | "DUPLICATE";
  ground_truth_label?: "Flooded Scene" | "Non Flooded" | "Inconclusive";
  reviewed_by: string;
  reviewer_notes?: string;
}

export interface DynamicRiskResponse {
  city: string;
  location_name: string;
  latitude: number;
  longitude: number;
  baseline_risk_score: number;
  report_risk_adjustment: number;
  final_risk_score: number;
  active_incidents_count: number;
  verified_genuine_count: number;
  pending_ai_positive_count: number;
  calculation_basis: string;
  radius_km: number;
}

export interface ConfusionMatrixData {
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
}

export interface ModelEvaluationResponse {
  model_name: string;
  model_architecture: string;
  evaluation_status: string;
  dataset_type: string;
  dataset_version: string;
  total_samples: number;
  labeled_samples: number;
  confusion_matrix: ConfusionMatrixData;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1_score: number | null;
  disclaimer: string;
}

export interface DemoSummaryResponse {
  total_incidents: number;
  real_incidents_count: number;
  demo_incidents_count: number;
  verified_genuine_count: number;
  verified_non_waterlogging_count: number;
  pending_verification_count: number;
  rejected_or_duplicate_count: number;
  is_demo_mode_active: boolean;
}

export interface LatLngPoint {
  latitude: number;
  longitude: number;
  name?: string;
}

export interface RouteRequest {
  city: string;
  origin: LatLngPoint;
  destination: LatLngPoint;
  prefer_alternatives?: boolean;
  tolerance_meters?: number;
  horizon_hours?: number;
}

export interface HazardIntersection {
  hazard_type: "VERIFIED_WATERLOGGING" | "PENDING_AI_DETECTION" | "CITIZEN_REPORT" | "RAINFALL_WATCH";
  location_name: string;
  latitude: number;
  longitude: number;
  distance_to_route_meters: number;
  severity_or_status: string;
  reported_at?: string;
  age_hours?: number;
  description: string;
  risk_points_contributed: number;
}

export interface RouteOption {
  route_id: string;
  summary_name: string;
  distance_km: number;
  duration_minutes: number;
  coordinates: [number, number][];
  risk_score: number;
  risk_category: "LOWER_KNOWN_RISK" | "ELEVATED_RISK" | "HIGH_HAZARD" | "DATA_UNAVAILABLE";
  is_recommended: boolean;
  recommendation_reason: string;
  hazard_count: number;
  verified_waterlogging_count: number;
  pending_ai_reports_count: number;
  rainfall_watch_count: number;
  hazards: HazardIntersection[];
  data_freshness: string;
  data_source: string;
}

export interface RouteComparisonResponse {
  success: boolean;
  city: string;
  origin_name: string;
  destination_name: string;
  total_routes_found: number;
  routes: RouteOption[];
  recommended_route_id?: string;
  screening_status_summary?: string;
  calculation_methodology: string;
  safety_disclaimer: string;
  timestamp: string;
}

export interface RoutePreset {
  id: string;
  city: string;
  name: string;
  origin: LatLngPoint;
  destination: LatLngPoint;
  corridor_description: string;
}


