import React, { useState, useEffect, useMemo, useRef } from "react";
import * as L from "leaflet";
import {
  apiClient,
  type IncidentResponse,
  type ModelEvaluationResponse,
  type DemoSummaryResponse,
  type DynamicRiskResponse,
} from "../services/api";
import { appConfig } from "../config";
import LiveCameraModal from "./LiveCameraModal";

interface IncidentIntelligenceSectionProps {
  currentCity?: string;
  onOpenLiveCamera?: () => void;
}

export default function IncidentIntelligenceSection({
  currentCity = "Mumbai",
}: IncidentIntelligenceSectionProps) {
  const [incidents, setIncidents] = useState<IncidentResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [cityFilter, setCityFilter] = useState<string>(currentCity);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [demoFilter, setDemoFilter] = useState<"ALL" | "REAL" | "DEMO">("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Sub-tabs: "history" | "accuracy" | "dynamic-risk"
  const [activeTab, setActiveTab] = useState<"history" | "accuracy" | "dynamic-risk">("history");

  // Review modal
  const [reviewingIncident, setReviewingIncident] = useState<IncidentResponse | null>(null);
  const [reviewStatus, setReviewStatus] = useState<"VERIFIED_GENUINE" | "VERIFIED_NON_WATERLOGGING" | "INCONCLUSIVE" | "REJECTED" | "DUPLICATE">("VERIFIED_GENUINE");
  const [reviewerName, setReviewerName] = useState<string>("Authorized Reviewer #104");
  const [reviewerNotes, setReviewerNotes] = useState<string>("");
  const [reviewSubmitting, setReviewSubmitting] = useState<boolean>(false);

  // Evaluation & Demo summaries
  const [evaluation, setEvaluation] = useState<ModelEvaluationResponse | null>(null);
  const [demoSummary, setDemoSummary] = useState<DemoSummaryResponse | null>(null);
  const [dynamicRisk, setDynamicRisk] = useState<DynamicRiskResponse | null>(null);

  // Live Camera Modal State
  const [cameraModalOpen, setCameraModalOpen] = useState<boolean>(false);

  // Map refs
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersLayerRef = useRef<L.LayerGroup | null>(null);

  const fetchIncidentsAndMetrics = async () => {
    setLoading(true);
    setError(null);
    try {
      const isDemoParam = demoFilter === "REAL" ? false : (demoFilter === "DEMO" ? true : undefined);
      const [incResp, evalResp, summaryResp] = await Promise.all([
        apiClient.getIncidents({
          city: cityFilter === "ALL" ? undefined : cityFilter,
          status: statusFilter,
          is_demo: isDemoParam,
          limit: 100,
        }),
        apiClient.getModelEvaluation(true),
        apiClient.getDemoSummary(),
      ]);

      setIncidents(incResp.incidents);
      setEvaluation(evalResp);
      setDemoSummary(summaryResp);

      // Fetch dynamic risk for default corridor
      const riskResp = await apiClient.getAreaDynamicRisk({
        city: cityFilter === "Pune" ? "Pune" : "Mumbai",
        location_name: cityFilter === "Pune" ? "Deccan Gymkhana" : "Andheri Subway",
        latitude: cityFilter === "Pune" ? 18.5204 : 19.1197,
        longitude: cityFilter === "Pune" ? 73.8567 : 72.8468,
      });
      setDynamicRisk(riskResp);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load incident intelligence";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidentsAndMetrics();
  }, [cityFilter, statusFilter, demoFilter]);

  // Seed demo data
  const handleSeedDemo = async () => {
    try {
      await apiClient.seedDemoIncidents();
      await fetchIncidentsAndMetrics();
    } catch (err: unknown) {
      alert("Failed to seed demo data");
    }
  };

  // Reset demo data
  const handleResetDemo = async () => {
    if (confirm("Reset demo data? This will delete synthetic demonstration records while preserving all real citizen reports.")) {
      try {
        await apiClient.resetDemoIncidents();
        await fetchIncidentsAndMetrics();
      } catch (err: unknown) {
        alert("Failed to reset demo data");
      }
    }
  };

  // Submit human review
  const handleSubmitReview = async () => {
    if (!reviewingIncident) return;
    setReviewSubmitting(true);
    try {
      let groundTruth: "Flooded Scene" | "Non Flooded" | "Inconclusive" = "Inconclusive";
      if (reviewStatus === "VERIFIED_GENUINE") groundTruth = "Flooded Scene";
      else if (reviewStatus === "VERIFIED_NON_WATERLOGGING") groundTruth = "Non Flooded";

      await apiClient.reviewIncident(reviewingIncident.id, {
        verification_status: reviewStatus,
        ground_truth_label: groundTruth,
        reviewed_by: reviewerName,
        reviewer_notes: reviewerNotes,
      });

      setReviewingIncident(null);
      await fetchIncidentsAndMetrics();
    } catch (err: unknown) {
      alert("Failed to submit review");
    } finally {
      setReviewSubmitting(false);
    }
  };

  // Filtered incidents by search
  const filteredIncidents = useMemo(() => {
    if (!searchQuery.trim()) return incidents;
    const q = searchQuery.toLowerCase();
    return incidents.filter(
      (inc) =>
        inc.location_name.toLowerCase().includes(q) ||
        inc.id.toLowerCase().includes(q) ||
        inc.city.toLowerCase().includes(q)
    );
  }, [incidents, searchQuery]);

  // Map initialization & markers
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const defaultCenter: [number, number] = cityFilter === "Pune" ? [18.5204, 73.8567] : [19.076, 72.8777];
      const map = L.map(mapContainerRef.current, {
        center: defaultCenter,
        zoom: 11,
        zoomControl: true,
      });

      L.tileLayer(appConfig.mapTileUrl, {
        attribution: appConfig.mapAttribution,
        maxZoom: 19,
      }).addTo(map);

      markersLayerRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;
    }

    if (markersLayerRef.current && incidents.length > 0) {
      markersLayerRef.current.clearLayers();

      incidents.forEach((inc) => {
        let color = "#64748B"; // default
        if (inc.verification_status === "VERIFIED_GENUINE") color = "#DC2626"; // Red
        else if (inc.verification_status === "VERIFIED_NON_WATERLOGGING") color = "#0F766E"; // Teal
        else if (inc.verification_status === "PENDING") color = "#D97706"; // Amber
        else if (inc.verification_status === "DUPLICATE") color = "#94A3B8";

        const marker = L.circleMarker([inc.latitude, inc.longitude], {
          radius: inc.is_demo ? 7 : 9,
          fillColor: color,
          color: inc.is_demo ? "#F59E0B" : "#FFFFFF",
          weight: inc.is_demo ? 2 : 2,
          opacity: 1,
          fillOpacity: 0.85,
        });

        marker.bindTooltip(
          `<strong>${inc.location_name} (${inc.city})</strong><br/>` +
          `AI: <b>${inc.predicted_class}</b> (${(inc.model_score * 100).toFixed(0)}%)<br/>` +
          `Status: <b>${inc.verification_status}</b><br/>` +
          `Risk Adjustment: <b>+${inc.report_risk_adjustment} pts</b><br/>` +
          `${inc.is_demo ? "<span style='color:#d97706;'>[DEMO RECORD]</span>" : "<span style='color:#15803d;'>[LIVE CITIZEN]</span>"}`,
          { direction: "top", offset: [0, -6] }
        );

        markersLayerRef.current?.addLayer(marker);
      });
    }
  }, [incidents, cityFilter]);

  return (
    <div className="incident-intelligence-container">
      {/* Top Header Strip */}
      <div className="incident-header-bar">
        <div>
          <div className="incident-eyebrow">
            <span>OGRAX INTELLIGENCE SYSTEM</span>
            <span className="incident-pill ai">HUGGING FACE SigLIP MODEL</span>
            <span className="incident-pill dynamic">DYNAMIC RISK ENGINE</span>
            <span className="incident-pill demo">DEMO BENCHMARK DATASET</span>
          </div>
          <h2>Live AI Flood Verification & Historical Learning</h2>
          <p>
            Real-time inference using <code>prithivMLmods/Flood-Image-Detection</code>,
            ground-truth review auditing, and spatial risk adjustments with time decay.
          </p>
        </div>

        <div className="incident-header-actions">
          <button
            type="button"
            className="incident-camera-launch-btn"
            onClick={() => setCameraModalOpen(true)}
          >
            📸 Capture Live Incident Photo
          </button>
          <div className="incident-demo-controls">
            <button type="button" className="incident-btn outline" onClick={handleSeedDemo}>
              🌱 Seed Demo Incidents
            </button>
            <button type="button" className="incident-btn outline danger" onClick={handleResetDemo}>
              🗑️ Reset Demo Data
            </button>
          </div>
        </div>
      </div>

      {/* Mandatory Demo Data Transparency Notice */}
      <div className="incident-transparency-banner">
        <div className="incident-transparency-badge">DEMO DATA & AUDIT TRANSPARENCY</div>
        <p>
          Synthetic demo records are labeled with <code>is_demo = true</code> and separated from live citizen reports.
          Dynamic risk adjustments apply a bounded formula: <code>Final Risk = Clamp(Baseline + Adjustment, 0, 100)</code>.
          Zero visual evidence does not guarantee absence of subsurface pipe choking.
        </p>
      </div>

      {/* 4 Metric Summary Cards */}
      <div className="incident-kpi-grid">
        <div className="incident-kpi-card">
          <small>Total Recorded Incidents</small>
          <strong>{demoSummary?.total_incidents || incidents.length}</strong>
          <span>
            {demoSummary?.real_incidents_count || 0} Live Citizen · {demoSummary?.demo_incidents_count || 0} Demo Records
          </span>
        </div>

        <div className="incident-kpi-card">
          <small>Verified Genuine Floods</small>
          <strong style={{ color: "#dc2626" }}>
            {demoSummary?.verified_genuine_count || 0} Corroborated
          </strong>
          <span>Human-verified ground-truth waterlogging</span>
        </div>

        <div className="incident-kpi-card">
          <small>Pending AI-Positive Reports</small>
          <strong style={{ color: "#d97706" }}>
            {demoSummary?.pending_verification_count || 0} Awaiting Review
          </strong>
          <span>+5.0 preliminary area risk adjustment</span>
        </div>

        <div className="incident-kpi-card">
          <small>Model Benchmark Accuracy</small>
          <strong style={{ color: "#0f766e" }}>
            {evaluation?.accuracy !== null && evaluation?.accuracy !== undefined
              ? `${(evaluation.accuracy * 100).toFixed(1)}%`
              : "Dataset Required"}
          </strong>
          <span>
            F1: {evaluation?.f1_score ? (evaluation.f1_score * 100).toFixed(1) : "N/A"}% · Precision: {evaluation?.precision ? (evaluation.precision * 100).toFixed(1) : "N/A"}%
          </span>
        </div>
      </div>

      {/* Main Tab Navigation */}
      <div className="incident-nav-tabs">
        <button
          type="button"
          className={`incident-nav-tab ${activeTab === "history" ? "active" : ""}`}
          onClick={() => setActiveTab("history")}
        >
          📋 Incident Audit History & Review
        </button>
        <button
          type="button"
          className={`incident-nav-tab ${activeTab === "dynamic-risk" ? "active" : ""}`}
          onClick={() => setActiveTab("dynamic-risk")}
        >
          ⚡ Dynamic Location Risk Engine
        </button>
        <button
          type="button"
          className={`incident-nav-tab ${activeTab === "accuracy" ? "active" : ""}`}
          onClick={() => setActiveTab("accuracy")}
        >
          📈 Model Accuracy & Retraining Export
        </button>
      </div>

      {/* TAB 1: History & Review Table */}
      {activeTab === "history" && (
        <div className="incident-tab-body">
          {/* Filter Bar */}
          <div className="incident-filter-bar">
            <input
              type="text"
              className="incident-search-field"
              placeholder="🔍 Search by incident ID, corridor name, or ward..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />

            <div className="incident-filter-selects">
              <select value={cityFilter} onChange={(e) => setCityFilter(e.target.value)}>
                <option value="ALL">All Cities</option>
                <option value="Mumbai">Mumbai</option>
                <option value="Pune">Pune</option>
              </select>

              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="ALL">All Statuses</option>
                <option value="PENDING">Pending Review</option>
                <option value="VERIFIED_GENUINE">Verified Genuine</option>
                <option value="VERIFIED_NON_WATERLOGGING">Verified Non-Flood</option>
                <option value="REJECTED">Rejected</option>
                <option value="DUPLICATE">Duplicate</option>
              </select>

              <select value={demoFilter} onChange={(e) => setDemoFilter(e.target.value as any)}>
                <option value="ALL">All Datasets</option>
                <option value="REAL">Live Citizen Only</option>
                <option value="DEMO">Demo Benchmark Only</option>
              </select>
            </div>
          </div>

          {/* Incidents Table */}
          <div className="incident-table-wrapper">
            <table className="incident-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Location & City</th>
                  <th>Photo Reference</th>
                  <th>AI Prediction</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th>Baseline</th>
                  <th>Adj</th>
                  <th>Final Risk</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={10} style={{ textAlign: "center", padding: "30px" }}>
                      Loading incident audit records...
                    </td>
                  </tr>
                ) : filteredIncidents.length === 0 ? (
                  <tr>
                    <td colSpan={10} style={{ textAlign: "center", padding: "30px", color: "#64748b" }}>
                      No incident records match the active filters.
                    </td>
                  </tr>
                ) : (
                  filteredIncidents.map((inc) => (
                    <tr key={inc.id} className={inc.is_demo ? "demo-row" : "live-row"}>
                      <td>
                        <code>{inc.id}</code>
                        {inc.is_demo && <span className="incident-demo-tag">DEMO</span>}
                      </td>
                      <td>
                        <strong>{inc.location_name}</strong>
                        <small style={{ display: "block", color: "#64748b" }}>
                          {inc.city} · ({inc.latitude.toFixed(4)}, {inc.longitude.toFixed(4)})
                        </small>
                      </td>
                      <td>
                        {inc.image_reference ? (
                          <a
                            href={inc.image_reference}
                            target="_blank"
                            rel="noreferrer"
                            className="incident-photo-link"
                          >
                            📷 View Image
                          </a>
                        ) : (
                          <span style={{ color: "#94a3b8" }}>No Image</span>
                        )}
                      </td>
                      <td>
                        <span
                          className={`incident-pred-badge ${
                            inc.predicted_class === "Flooded Scene" ? "flood" : "dry"
                          }`}
                        >
                          {inc.predicted_class}
                        </span>
                      </td>
                      <td>
                        <b>{(inc.model_score * 100).toFixed(0)}%</b>
                      </td>
                      <td>
                        <span className={`incident-status-chip ${inc.verification_status.toLowerCase()}`}>
                          {inc.verification_status.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td>{inc.baseline_risk_score.toFixed(1)}%</td>
                      <td style={{ color: inc.report_risk_adjustment > 0 ? "#dc2626" : "#64748b" }}>
                        +{inc.report_risk_adjustment.toFixed(1)}
                      </td>
                      <td>
                        <strong style={{ color: inc.final_risk_score >= 60 ? "#dc2626" : "#0f766e" }}>
                          {inc.final_risk_score.toFixed(1)}%
                        </strong>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="incident-review-btn"
                          onClick={() => {
                            setReviewingIncident(inc);
                            setReviewerNotes("");
                          }}
                        >
                          Review →
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: Dynamic Location Risk Engine */}
      {activeTab === "dynamic-risk" && (
        <div className="incident-dynamic-risk-view">
          <div className="incident-risk-split">
            <div className="incident-risk-calc-card">
              <h3>Dynamic Spatial Risk Calculation</h3>
              <p>
                Calculates area flood probability adjustments based on corroborating live visual evidence
                within a 1.5 km spatial radius.
              </p>

              {dynamicRisk ? (
                <div className="incident-risk-formula-box">
                  <div className="formula-item">
                    <small>Baseline Model Risk</small>
                    <strong>{dynamicRisk.baseline_risk_score.toFixed(1)}%</strong>
                    <span>(From regional hydrological model)</span>
                  </div>
                  <div className="formula-op">+</div>
                  <div className="formula-item">
                    <small>Report Risk Adjustment</small>
                    <strong style={{ color: "#dc2626" }}>
                      +{dynamicRisk.report_risk_adjustment.toFixed(1)} pts
                    </strong>
                    <span>(Active visual evidence)</span>
                  </div>
                  <div className="formula-op">=</div>
                  <div className="formula-item">
                    <small>Final Clamped Area Risk</small>
                    <strong style={{ color: dynamicRisk.final_risk_score >= 60 ? "#dc2626" : "#0f766e" }}>
                      {dynamicRisk.final_risk_score.toFixed(1)}%
                    </strong>
                    <span>Clamp(0, 100)</span>
                  </div>
                </div>
              ) : null}

              {dynamicRisk && (
                <div className="incident-risk-basis-text">
                  <b>Calculation Basis:</b> {dynamicRisk.calculation_basis}
                </div>
              )}

              <div className="incident-policy-reference">
                <h4>Dynamic Adjustment Policy (Configurable Constants):</h4>
                <ul>
                  <li>AI-positive report awaiting verification: <b>+5.0 risk points</b></li>
                  <li>Human-verified genuine waterlogging: <b>+10.0 risk points</b></li>
                  <li>Multiple independent recent corroborating reports: <b>+3.0 bonus points per report</b></li>
                  <li>Maximum total report-derived adjustment cap: <b>+20.0 points maximum</b></li>
                  <li>Time decay policy: 100% influence &lt; 1h, decaying smoothly to 0% after 12 hours</li>
                  <li>AI-negative or rejected reports: <b>0.0 risk points added</b></li>
                </ul>
              </div>
            </div>

            {/* Spatial Map View */}
            <div className="incident-spatial-map-card">
              <div className="incident-map-header">
                <strong>Incident Spatial Cluster Map</strong>
                <span>Color-coded incidents (Red = Verified, Amber = Pending, Teal = Non-Flood)</span>
              </div>
              <div ref={mapContainerRef} className="incident-leaflet-map-frame" />
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: Model Accuracy & Retraining */}
      {activeTab === "accuracy" && (
        <div className="incident-accuracy-view">
          <div className="incident-eval-header">
            <div>
              <h3>Hugging Face Model Benchmark & Evaluation</h3>
              <p>
                Metrics computed from independently labeled ground-truth examples.
                Model: <code>{evaluation?.model_name || "prithivMLmods/Flood-Image-Detection"}</code>
              </p>
            </div>
            <a
              href="/api/incidents/models/export-dataset"
              target="_blank"
              rel="noreferrer"
              className="incident-export-btn"
            >
              📥 Export Retraining Dataset (Train/Val/Test Splits)
            </a>
          </div>

          <div className="incident-eval-metrics-grid">
            <div className="incident-eval-card">
              <small>Accuracy</small>
              <strong>
                {evaluation?.accuracy !== null && evaluation?.accuracy !== undefined
                  ? `${(evaluation.accuracy * 100).toFixed(1)}%`
                  : "N/A"}
              </strong>
              <span>Overall correct classifications</span>
            </div>
            <div className="incident-eval-card">
              <small>Precision (Flooded Scene)</small>
              <strong>
                {evaluation?.precision !== null && evaluation?.precision !== undefined
                  ? `${(evaluation.precision * 100).toFixed(1)}%`
                  : "N/A"}
              </strong>
              <span>True floods / Total predicted floods</span>
            </div>
            <div className="incident-eval-card">
              <small>Recall (Flooded Scene)</small>
              <strong>
                {evaluation?.recall !== null && evaluation?.recall !== undefined
                  ? `${(evaluation.recall * 100).toFixed(1)}%`
                  : "N/A"}
              </strong>
              <span>True floods / Actual ground-truth floods</span>
            </div>
            <div className="incident-eval-card">
              <small>F1-Score</small>
              <strong>
                {evaluation?.f1_score !== null && evaluation?.f1_score !== undefined
                  ? `${(evaluation.f1_score * 100).toFixed(1)}%`
                  : "N/A"}
              </strong>
              <span>Harmonic mean of precision & recall</span>
            </div>
          </div>

          {/* Confusion Matrix Table */}
          <div className="incident-confusion-matrix-card">
            <h4>Confusion Matrix (Binary Classification)</h4>
            <table className="confusion-matrix-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Predicted: Flooded Scene</th>
                  <th>Predicted: Non Flooded</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><b>Actual: Flooded Scene</b></td>
                  <td className="matrix-cell tp">
                    <b>TP: {evaluation?.confusion_matrix.true_positive || 0}</b>
                    <small>Genuine floods detected</small>
                  </td>
                  <td className="matrix-cell fn">
                    <b>FN: {evaluation?.confusion_matrix.false_negative || 0}</b>
                    <small>Missed flood events</small>
                  </td>
                </tr>
                <tr>
                  <td><b>Actual: Non Flooded</b></td>
                  <td className="matrix-cell fp">
                    <b>FP: {evaluation?.confusion_matrix.false_positive || 0}</b>
                    <small>False alarm puddle/shadow</small>
                  </td>
                  <td className="matrix-cell tn">
                    <b>TN: {evaluation?.confusion_matrix.true_negative || 0}</b>
                    <small>Correctly identified dry</small>
                  </td>
                </tr>
              </tbody>
            </table>

            <div className="incident-retraining-notes">
              <strong>Controlled Retraining Protocol:</strong>
              <p>
                To avoid spatial and temporal data leakage, training examples are partitioned
                (70% train, 15% validation, 15% test) grouped by physical meteorological storm events.
                Models must undergo held-out test evaluation before production weight replacement.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Human Review Modal Dialog */}
      {reviewingIncident && (
        <div className="camera-modal-backdrop">
          <div className="camera-modal-dialog review">
            <div className="camera-modal-header">
              <div>
                <div className="camera-modal-tag">AUTHORIZED HUMAN VERIFICATION</div>
                <h3>Review Incident Report: {reviewingIncident.id}</h3>
              </div>
              <button
                className="camera-modal-close"
                onClick={() => setReviewingIncident(null)}
              >
                ×
              </button>
            </div>

            <div className="camera-modal-body">
              <div className="review-incident-details">
                <div>
                  <small>Location</small>
                  <strong>{reviewingIncident.location_name} ({reviewingIncident.city})</strong>
                </div>
                <div>
                  <small>AI Classification</small>
                  <b>{reviewingIncident.predicted_class} ({(reviewingIncident.model_score * 100).toFixed(0)}%)</b>
                </div>
                <div>
                  <small>Current Risk Adjustment</small>
                  <b>+{reviewingIncident.report_risk_adjustment.toFixed(1)} pts</b>
                </div>
              </div>

              {reviewingIncident.image_reference && (
                <div style={{ textAlign: "center", margin: "14px 0" }}>
                  <img
                    src={reviewingIncident.image_reference}
                    alt="Incident evidence"
                    style={{ maxHeight: "200px", borderRadius: "8px", border: "1px solid #cbd5e1" }}
                  />
                </div>
              )}

              <div style={{ marginTop: "12px" }}>
                <label className="camera-field-label">Verification Decision</label>
                <select
                  className="camera-select"
                  value={reviewStatus}
                  onChange={(e) => setReviewStatus(e.target.value as any)}
                >
                  <option value="VERIFIED_GENUINE">✓ VERIFIED GENUINE (Confirmed waterlogging, +10.0 pts)</option>
                  <option value="VERIFIED_NON_WATERLOGGING">✗ VERIFIED NON-FLOOD (False alarm / dry, 0 pts)</option>
                  <option value="INCONCLUSIVE">? INCONCLUSIVE (Insufficient visual clarity, 0 pts)</option>
                  <option value="DUPLICATE">⧉ DUPLICATE REPORT (Suppress duplicate risk, 0 pts)</option>
                  <option value="REJECTED">🚫 REJECT (Irrelevant / camera malfunction, 0 pts)</option>
                </select>
              </div>

              <div style={{ marginTop: "12px" }}>
                <label className="camera-field-label">Reviewer Badge / ID</label>
                <input
                  type="text"
                  className="camera-text-input"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                />
              </div>

              <div style={{ marginTop: "12px" }}>
                <label className="camera-field-label">Review Notes</label>
                <input
                  type="text"
                  className="camera-text-input"
                  placeholder="e.g. Field inspection confirmed road impassable by two-wheelers"
                  value={reviewerNotes}
                  onChange={(e) => setReviewerNotes(e.target.value)}
                />
              </div>

              <div className="camera-action-footer">
                <button
                  type="button"
                  className="camera-back-btn"
                  onClick={() => setReviewingIncident(null)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="camera-submit-btn"
                  onClick={handleSubmitReview}
                  disabled={reviewSubmitting}
                >
                  {reviewSubmitting ? "Submitting..." : "Save Verification Decision"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Live Camera Modal */}
      <LiveCameraModal
        isOpen={cameraModalOpen}
        onClose={() => setCameraModalOpen(false)}
        defaultCity={cityFilter === "Pune" ? "Pune" : "Mumbai"}
        onIncidentCreated={() => {
          fetchIncidentsAndMetrics();
        }}
      />
    </div>
  );
}
