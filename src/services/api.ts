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
  recent_rainfall_mm: number | null;
  forecast_rainfall_mm: number | null;
  rain_last_24h_mm: number | null;
  thresholds: { forecast: number; recent: number };
  explanation: string;
  data_status: string;
  data_source: string;
  observation_time: string;
  waterlogging_probability: null;
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
};

