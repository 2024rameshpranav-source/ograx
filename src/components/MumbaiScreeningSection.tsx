import React, { useEffect, useState } from "react";
import * as L from "leaflet";
import { apiClient, type MumbaiScreeningResponse, type MumbaiLocationScreening, type MumbaiWarningStatus } from "../services/api";
import { appConfig } from "../config";

interface MumbaiScreeningSectionProps {
  onLocationSelect?: (location: MumbaiLocationScreening) => void;
  selectedHorizon?: number;
  onHorizonChange?: (horizon: number) => void;
}

export default function MumbaiScreeningSection({
  onLocationSelect,
  selectedHorizon = 3,
  onHorizonChange,
}: MumbaiScreeningSectionProps) {
  const [horizon, setHorizon] = useState<number>(selectedHorizon);
  const [data, setData] = useState<MumbaiScreeningResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<MumbaiLocationScreening | null>(null);
  const mapContainerRef = React.useRef<HTMLDivElement>(null);
  const mapInstanceRef = React.useRef<L.Map | null>(null);
  const markersLayerRef = React.useRef<L.LayerGroup | null>(null);

  // Sync horizon with prop
  useEffect(() => {
    if (selectedHorizon && selectedHorizon !== horizon) {
      setHorizon(selectedHorizon);
    }
  }, [selectedHorizon]);

  const fetchScreening = async (h: number, refresh: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiClient.getMumbaiWaterlogging(h, refresh);
      setData(resp);
      if (resp.locations.length > 0 && !selectedLocation) {
        setSelectedLocation(resp.locations[0]);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load Mumbai screening data";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScreening(horizon);
  }, [horizon]);

  const handleHorizonClick = (h: number) => {
    setHorizon(h);
    if (onHorizonChange) onHorizonChange(h);
  };

  // Initialize and update Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!mapInstanceRef.current) {
      const map = L.map(mapContainerRef.current, {
        zoomControl: false,
        attributionControl: true,
      }).setView([19.05, 72.86], 11);

      L.tileLayer(appConfig.mapTileUrl, {
        attribution: appConfig.mapAttribution,
        maxZoom: 19,
      }).addTo(map);

      L.control.zoom({ position: "bottomright" }).addTo(map);
      markersLayerRef.current = L.layerGroup().addTo(map);
      mapInstanceRef.current = map;
    }

    // Update markers when data changes
    if (markersLayerRef.current && data) {
      markersLayerRef.current.clearLayers();

      const getStatusColor = (st: MumbaiWarningStatus) => {
        switch (st) {
          case "RAINFALL_WATCH":
            return "#E85D4A"; // Amber/Red
          case "LOW_RAINFALL_SIGNAL":
            return "#0284C7"; // Blue
          case "NO_RAINFALL_SIGNAL":
            return "#0F9D9A"; // Emerald/Teal
          case "DATA_CHECK_REQUIRED":
          default:
            return "#64748B"; // Slate
        }
      };

      data.locations.forEach((loc) => {
        const color = getStatusColor(loc.warning_status);
        const marker = L.circleMarker([loc.latitude, loc.longitude], {
          radius: 9,
          fillColor: color,
          color: "#FFFFFF",
          weight: 2,
          opacity: 1,
          fillOpacity: 0.9,
        });

        const statusLabel = loc.warning_status.replace(/_/g, " ");
        const fcText = loc.forecast_rainfall_mm !== null && loc.forecast_rainfall_mm !== undefined
          ? `${loc.forecast_rainfall_mm.toFixed(1)} mm`
          : "N/A";
        marker.bindTooltip(
          `<strong>${loc.location_name}</strong><br/>${statusLabel}<br/>Forecast: ${fcText}`,
          { direction: "top", offset: [0, -6] }
        );

        marker.on("click", () => {
          setSelectedLocation(loc);
          if (onLocationSelect) onLocationSelect(loc);
        });

        markersLayerRef.current?.addLayer(marker);
      });
    }
  }, [data]);

  // Center map on selected location
  useEffect(() => {
    if (selectedLocation && mapInstanceRef.current) {
      mapInstanceRef.current.setView([selectedLocation.latitude, selectedLocation.longitude], 13);
    }
  }, [selectedLocation]);

  const getStatusBadge = (status: MumbaiWarningStatus) => {
    switch (status) {
      case "RAINFALL_WATCH":
        return <span className="mumbai-chip watch">⚠️ Rainfall Watch</span>;
      case "LOW_RAINFALL_SIGNAL":
        return <span className="mumbai-chip low">💧 Low Rainfall Signal</span>;
      case "NO_RAINFALL_SIGNAL":
        return <span className="mumbai-chip none">✓ No Rainfall Signal</span>;
      case "DATA_CHECK_REQUIRED":
      default:
        return <span className="mumbai-chip check">ℹ️ Data Check Required</span>;
    }
  };

  return (
    <div className="mumbai-screening-container">
      {/* Top Banner / Prototype Transparency Eyebrow */}
      <div className="mumbai-header-strip">
        <div className="mumbai-eyebrow">
          <span>MUMBAI HYDROLOGICAL SCREENING ENGINE</span>
          <span className="mumbai-tag-pill">RULE-BASED PROTOTYPE</span>
          <span className="mumbai-tag-pill unvalidated">NOT AN ML MODEL</span>
          <span className="mumbai-tag-pill source">
            {data?.data_source.includes("Live") ? "● OPEN-METEO LIVE FORECAST" : "◷ LOCAL NOWCAST SNAPSHOT"}
          </span>
        </div>
        <div className="mumbai-header-actions">
          <div className="mumbai-horizon-btn-group">
            <span className="mumbai-horizon-label">Forecast Horizon:</span>
            {[1, 3, 6].map((h) => (
              <button
                key={h}
                type="button"
                className={`mumbai-horizon-btn ${horizon === h ? "active" : ""}`}
                onClick={() => handleHorizonClick(h)}
              >
                +{h} Hour{h > 1 ? "s" : ""}
                <small>{h === 1 ? "5mm" : h === 3 ? "10mm" : "20mm"} threshold</small>
              </button>
            ))}
          </div>
          <button
            type="button"
            className="mumbai-refresh-btn"
            onClick={() => fetchScreening(horizon, true)}
            title="Refresh weather data from Open-Meteo API"
            disabled={loading}
          >
            ↻ {loading ? "Refreshing…" : "Refresh Weather"}
          </button>
        </div>
      </div>

      {/* Mandatory Transparency Notice */}
      <div className="mumbai-transparency-callout">
        <div className="mumbai-callout-icon">ℹ️</div>
        <div className="mumbai-callout-body">
          <strong>Experimental Rule-Based Screening — 8 Mumbai Ground Locations</strong>
          <p>
            This engine screens forecast and recent rainfall against experimental thresholds.
            It does <strong>not</strong> calculate or claim a numerical waterlogging probability.
            Zero rainfall does not imply zero road waterlogging risk.
          </p>
        </div>
        {data && (
          <div className="mumbai-data-status-meta">
            <span>Overall Signal: <b>{data.overall_screening_status.replace(/_/g, " ")}</b></span>
            <span>Generated: {new Date(data.generated_at).toLocaleTimeString()} UTC</span>
            <span>Freshness: <b>{data.data_freshness}</b></span>
          </div>
        )}
      </div>

      {error && (
        <div className="mumbai-error-alert">
          <strong>Weather Data Notice:</strong> {error}. Showing baseline fallback.
          <button type="button" onClick={() => fetchScreening(horizon)}>Retry</button>
        </div>
      )}

      {/* Main 2-Column Layout: 8 Location Grid & Interactive Screening Map */}
      <div className="mumbai-dashboard-grid">
        {/* Left Column: 8 Location Cards */}
        <div className="mumbai-locations-col">
          <div className="mumbai-section-title">
            <h3>Monitored Corridors ({data?.locations.length || 8})</h3>
            <span className="mumbai-count-pill">+{horizon}h Outlook</span>
          </div>

          <div className="mumbai-cards-list">
            {loading && !data ? (
              <div className="mumbai-loading">Screening Mumbai locations…</div>
            ) : (
              data?.locations.map((loc) => {
                const isSelected = selectedLocation?.location_id === loc.location_id;
                return (
                  <div
                    key={loc.location_id}
                    className={`mumbai-location-card ${isSelected ? "selected" : ""}`}
                    onClick={() => {
                      setSelectedLocation(loc);
                      if (onLocationSelect) onLocationSelect(loc);
                    }}
                  >
                    <div className="mumbai-card-top">
                      <div>
                        <h4>{loc.location_name}</h4>
                        <span className="mumbai-elevation">Elevation: {loc.elevation_m}m · ({loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)})</span>
                      </div>
                      {getStatusBadge(loc.warning_status)}
                    </div>

                    <div className="mumbai-metrics-row">
                      <div className="mumbai-metric">
                        <small>Past {horizon}h Rain</small>
                        <strong>
                          {loc.recent_rainfall_mm !== null && loc.recent_rainfall_mm !== undefined
                            ? `${loc.recent_rainfall_mm.toFixed(1)} mm`
                            : "N/A"}
                        </strong>
                      </div>
                      <div className="mumbai-metric">
                        <small>Next {horizon}h Forecast</small>
                        <strong className={loc.forecast_rainfall_mm !== null && loc.forecast_rainfall_mm >= loc.thresholds.forecast ? "highlight-rain" : ""}>
                          {loc.forecast_rainfall_mm !== null && loc.forecast_rainfall_mm !== undefined
                            ? `${loc.forecast_rainfall_mm.toFixed(1)} mm`
                            : "N/A"}
                        </strong>
                      </div>
                      <div className="mumbai-metric">
                        <small>Watch Threshold</small>
                        <span>≥ {loc.thresholds.forecast} mm</span>
                      </div>
                      <div className="mumbai-metric">
                        <small>24h Total</small>
                        <span>
                          {loc.rain_last_24h_mm !== null && loc.rain_last_24h_mm !== undefined
                            ? `${loc.rain_last_24h_mm.toFixed(1)} mm`
                            : "N/A"}
                        </span>
                      </div>
                    </div>

                    {/* Factual human-readable explanation */}
                    <p className="mumbai-explanation">{loc.explanation}</p>

                    {/* Distinct Hotspot Context */}
                    <div className="mumbai-hotspot-box">
                      <div className="mumbai-hotspot-header">
                        <span className="mumbai-hotspot-title">REPORTED HOTSPOT CONTEXT</span>
                        <span className={`mumbai-match-badge ${loc.hotspot_evidence.match_status.toLowerCase()}`}>
                          {loc.hotspot_evidence.match_status.replace(/_/g, " ")}
                        </span>
                      </div>
                      <p className="mumbai-hotspot-text">{loc.hotspot_evidence.reported_evidence}</p>
                      {loc.hotspot_evidence.source && (
                        <small className="mumbai-hotspot-source">
                          Source: {loc.hotspot_evidence.source} ({loc.hotspot_evidence.source_date})
                        </small>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Spatial Map & Location Detail Inspector */}
        <div className="mumbai-map-col">
          <div className="mumbai-map-card">
            <div className="mumbai-map-header">
              <div>
                <strong>Spatial Screening Map</strong>
                <span>8 Coordinates with Real-Time Rainfall Screening Status</span>
              </div>
              <div className="mumbai-legend-mini">
                <span><i style={{ background: "#0F9D9A" }} /> No Signal</span>
                <span><i style={{ background: "#0284C7" }} /> Low Signal</span>
                <span><i style={{ background: "#E85D4A" }} /> Rainfall Watch</span>
              </div>
            </div>
            <div ref={mapContainerRef} className="mumbai-leaflet-frame" />
          </div>

          {selectedLocation && (
            <div className="mumbai-detail-inspector">
              <div className="mumbai-inspector-head">
                <div>
                  <span className="mumbai-inspector-label">INSPECTING CORRIDOR</span>
                  <h3>{selectedLocation.location_name}</h3>
                </div>
                {getStatusBadge(selectedLocation.warning_status)}
              </div>

              <div className="mumbai-inspector-grid">
                <div>
                  <small>Screening Model Type</small>
                  <strong>Rule-Driven Rainfall Threshold Engine</strong>
                </div>
                <div>
                  <small>Validation Status</small>
                  <strong className="mumbai-amber">UNVALIDATED PROTOTYPE</strong>
                </div>
                <div>
                  <small>Waterlogging Probability</small>
                  <strong className="mumbai-null">NOT APPLICABLE (NULL)</strong>
                </div>
                <div>
                  <small>Weather Provider</small>
                  <strong>{selectedLocation.data_source}</strong>
                </div>
              </div>

              <div className="mumbai-inspector-notice">
                <b>Field Responder Guidance:</b> This screening result represents meteorological precipitation accumulation.
                Ground waterlogging is additionally governed by micro-topography, storm-drain clearing, and tidal ingress.
                Verify ground conditions with citizen reports before vehicle dispatch.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
