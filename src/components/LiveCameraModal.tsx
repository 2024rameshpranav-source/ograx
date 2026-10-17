import React, { useState, useRef, useEffect } from "react";
import * as L from "leaflet";
import { apiClient, type IncidentAnalyzeResponse, type IncidentResponse } from "../services/api";
import { appConfig } from "../config";

interface LiveCameraModalProps {
  isOpen?: boolean;
  onClose: () => void;
  defaultCity?: string;
  currentCity?: string;
  onIncidentCreated?: (incident: IncidentResponse) => void;
}

export default function LiveCameraModal({
  isOpen = true,
  onClose,
  defaultCity = "Mumbai",
  currentCity,
  onIncidentCreated,
}: LiveCameraModalProps) {
  const activeCity = currentCity || defaultCity || "Mumbai";
  const [step, setStep] = useState<"camera" | "analyzing" | "preview" | "location" | "success">("camera");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [photoBlob, setPhotoBlob] = useState<Blob | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // Analysis result
  const [aiResult, setAiResult] = useState<IncidentAnalyzeResponse | null>(null);
  const [analyzingError, setAnalyzingError] = useState<string | null>(null);

  // Location state
  const [city, setCity] = useState<string>(activeCity);
  const [locationName, setLocationName] = useState<string>("");
  const [latitude, setLatitude] = useState<number>(activeCity === "Pune" ? 18.5204 : 19.0760);
  const [longitude, setLongitude] = useState<number>(activeCity === "Pune" ? 73.8567 : 72.8777);
  const [geoStatus, setGeoStatus] = useState<string>("Detecting location...");
  const [notes, setNotes] = useState<string>("");

  // Submission state
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [createdIncident, setCreatedIncident] = useState<IncidentResponse | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  // Start Camera
  const startCamera = async () => {
    setCameraError(null);
    try {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        await videoRef.current.play();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Camera access denied or unavailable";
      setCameraError(`${msg}. You can also choose or drag an image file below.`);
    }
  };

  // Stop Camera
  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      setStream(null);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setStep("camera");
      setAiResult(null);
      setPhotoBlob(null);
      setPhotoPreviewUrl(null);
      setCreatedIncident(null);
      startCamera();
      detectLocation();
    } else {
      stopCamera();
    }
    return () => {
      stopCamera();
    };
  }, [isOpen]);

  // Request browser geolocation
  const detectLocation = () => {
    setGeoStatus("Requesting browser GPS location...");
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = parseFloat(pos.coords.latitude.toFixed(5));
          const lng = parseFloat(pos.coords.longitude.toFixed(5));
          setLatitude(lat);
          setLongitude(lng);
          setGeoStatus(`GPS Acquired (±${Math.round(pos.coords.accuracy)}m)`);
          
          // Infer city from latitude
          if (lat < 18.8) {
            setCity("Pune");
            if (!locationName) setLocationName("Deccan Gymkhana Corridor");
          } else {
            setCity("Mumbai");
            if (!locationName) setLocationName("Andheri East S.V. Road");
          }
        },
        (err) => {
          setGeoStatus(`Location permission unavailable (${err.message}). Using manual map pin.`);
        },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    } else {
      setGeoStatus("Browser geolocation not supported. Using manual map pin.");
    }
  };

  // Capture snapshot from video
  const takeSnapshot = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob((blob) => {
      if (blob) {
        setPhotoBlob(blob);
        const url = URL.createObjectURL(blob);
        setPhotoPreviewUrl(url);
        stopCamera();
        runAiAnalysis(blob);
      }
    }, "image/jpeg", 0.92);
  };

  // File upload fallback
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPhotoBlob(file);
      const url = URL.createObjectURL(file);
      setPhotoPreviewUrl(url);
      stopCamera();
      runAiAnalysis(file);
    }
  };

  // Run real Hugging Face Model Inference
  const runAiAnalysis = async (fileOrBlob: Blob | File) => {
    setStep("analyzing");
    setAnalyzingError(null);
    try {
      const file = fileOrBlob instanceof File
        ? fileOrBlob
        : new File([fileOrBlob], "camera_capture.jpg", { type: "image/jpeg" });

      const resp = await apiClient.analyzeIncidentPhoto(file);
      setAiResult(resp);
      setStep("preview");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Inference service connection error";
      setAnalyzingError(msg);
      setStep("preview");
    }
  };

  // Retake photo
  const retakePhoto = () => {
    setPhotoBlob(null);
    setPhotoPreviewUrl(null);
    setAiResult(null);
    setAnalyzingError(null);
    setStep("camera");
    startCamera();
  };

  // Initialize interactive Leaflet map pin confirmation
  useEffect(() => {
    if (step === "location" && mapContainerRef.current) {
      if (!mapRef.current) {
        const map = L.map(mapContainerRef.current, {
          center: [latitude, longitude],
          zoom: 14,
          zoomControl: true,
        });

        L.tileLayer(appConfig.mapTileUrl, {
          attribution: appConfig.mapAttribution,
          maxZoom: 19,
        }).addTo(map);

        const marker = L.marker([latitude, longitude], { draggable: true }).addTo(map);
        marker.on("dragend", (e) => {
          const latLng = (e.target as L.Marker).getLatLng();
          setLatitude(parseFloat(latLng.lat.toFixed(5)));
          setLongitude(parseFloat(latLng.lng.toFixed(5)));
          setGeoStatus("Manually adjusted coordinates");
        });

        mapRef.current = map;
        markerRef.current = marker;
      } else {
        mapRef.current.setView([latitude, longitude], 14);
        markerRef.current?.setLatLng([latitude, longitude]);
      }
    }
  }, [step, latitude, longitude]);

  // Submit confirmed report
  const submitIncident = async () => {
    if (!aiResult) return;
    setSubmitting(true);
    try {
      const payload = {
        city,
        location_name: locationName.trim() || `${city} Incident Spot`,
        latitude,
        longitude,
        captured_at: new Date().toISOString(),
        image_reference: aiResult.image_reference,
        predicted_class: aiResult.predicted_class,
        model_score: aiResult.model_score,
        source_type: "live_citizen",
        is_demo: false,
        notes: notes.trim() || undefined,
      };

      const res = await apiClient.createIncident(payload);
      setCreatedIncident(res);
      setStep("success");
      if (onIncidentCreated) {
        onIncidentCreated(res);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Submission failed";
      alert(`Failed to submit incident: ${msg}`);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="camera-modal-backdrop">
      <div className="camera-modal-dialog">
        {/* Modal Header */}
        <div className="camera-modal-header">
          <div>
            <div className="camera-modal-tag">OGRAX AI VERIFIED INCIDENT REPORTING</div>
            <h2>Live Camera Flood Intelligence</h2>
          </div>
          <button className="camera-modal-close" onClick={onClose} aria-label="Close modal">×</button>
        </div>

        {/* Modal Body */}
        <div className="camera-modal-body">
          {/* STEP 1: Live Camera View */}
          {step === "camera" && (
            <div className="camera-step-frame">
              <div className="camera-viewfinder">
                <video ref={videoRef} playsInline autoPlay muted className="camera-video-stream" />
                <canvas ref={canvasRef} style={{ display: "none" }} />
                <div className="camera-reticle" />
                <div className="camera-live-badge">● LIVE SENSOR READY</div>
              </div>

              {cameraError && (
                <div className="camera-alert-warning">
                  ⚠️ {cameraError}
                </div>
              )}

              <div className="camera-controls-bar">
                <label className="camera-upload-btn">
                  📁 Upload Photo
                  <input type="file" accept="image/*" onChange={handleFileUpload} style={{ display: "none" }} />
                </label>
                <button type="button" className="camera-shutter-btn" onClick={takeSnapshot}>
                  📸 Capture & Analyze
                </button>
              </div>
            </div>
          )}

          {/* STEP 2: Analyzing Loading State */}
          {step === "analyzing" && (
            <div className="camera-analyzing-state">
              <div className="camera-spinner" />
              <h3>Running Hugging Face Flood Detection...</h3>
              <p>Model: <code>prithivMLmods/Flood-Image-Detection</code></p>
              <small>Preprocessing 224x224 RGB image, calculating class activations...</small>
            </div>
          )}

          {/* STEP 3: Preview & Model Classification Result */}
          {step === "preview" && (
            <div className="camera-preview-step">
              <div className="camera-preview-split">
                <div className="camera-preview-photo-wrap">
                  {photoPreviewUrl && (
                    <img src={photoPreviewUrl} alt="Captured incident" className="camera-preview-img" />
                  )}
                  <button type="button" className="camera-retake-btn" onClick={retakePhoto}>
                    ↻ Retake Photo
                  </button>
                </div>

                <div className="camera-ai-card">
                  <div className="camera-card-eyebrow">HUGGING FACE MODEL INFERENCE RESULT</div>
                  <div className="camera-model-badge">
                    <span>Model: <b>prithivMLmods/Flood-Image-Detection</b></span>
                    <span>Architecture: <b>SigLIP</b></span>
                  </div>

                  {analyzingError ? (
                    <div className="camera-alert-error">
                      ❌ {analyzingError}
                    </div>
                  ) : aiResult ? (
                    <>
                      <div className={`camera-prediction-banner ${aiResult.is_flooded ? "flood-detected" : "non-flood"}`}>
                        <div className="camera-pred-title">
                          {aiResult.is_flooded ? "⚠️ FLOODED SCENE DETECTED" : "✓ NON-FLOODED SCENE"}
                        </div>
                        <div className="camera-pred-score">
                          Model Confidence: <b>{(aiResult.model_score * 100).toFixed(1)}%</b> ({aiResult.confidence_level})
                        </div>
                      </div>

                      <div className="camera-prob-breakdown">
                        <div className="camera-prob-row">
                          <span>Flooded Scene Probability:</span>
                          <b>{(aiResult.class_probabilities["Flooded Scene"] * 100).toFixed(1)}%</b>
                        </div>
                        <div className="camera-bar-track">
                          <div
                            className="camera-bar-fill flood"
                            style={{ width: `${aiResult.class_probabilities["Flooded Scene"] * 100}%` }}
                          />
                        </div>

                        <div className="camera-prob-row" style={{ marginTop: "8px" }}>
                          <span>Non-Flooded Probability:</span>
                          <b>{(aiResult.class_probabilities["Non Flooded"] * 100).toFixed(1)}%</b>
                        </div>
                        <div className="camera-bar-track">
                          <div
                            className="camera-bar-fill safe"
                            style={{ width: `${aiResult.class_probabilities["Non Flooded"] * 100}%` }}
                          />
                        </div>
                      </div>

                      <div className="camera-notice-box">
                        <b>Dynamic Risk Impact:</b> If confirmed, this AI-positive visual report will adjust local area risk by <b>+5.0 points</b> pending reviewer verification.
                      </div>
                    </>
                  ) : null}

                  <button
                    type="button"
                    className="camera-next-btn"
                    onClick={() => setStep("location")}
                    disabled={!aiResult}
                  >
                    Confirm Location & Details →
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: Confirm Location & Metadata */}
          {step === "location" && (
            <div className="camera-location-step">
              <div className="camera-form-grid">
                <div>
                  <label className="camera-field-label">Monitored City</label>
                  <select
                    className="camera-select"
                    value={city}
                    onChange={(e) => {
                      setCity(e.target.value);
                      if (e.target.value === "Pune") {
                        setLatitude(18.5204);
                        setLongitude(73.8567);
                        setLocationName("Deccan Gymkhana Corridor");
                      } else {
                        setLatitude(19.0760);
                        setLongitude(72.8777);
                        setLocationName("Andheri East S.V. Road");
                      }
                    }}
                  >
                    <option value="Mumbai">Mumbai (8-Corridor Warning Engine)</option>
                    <option value="Pune">Pune (ML Classifier Pipeline)</option>
                  </select>
                </div>

                <div>
                  <label className="camera-field-label">Corridor or Landmark Name</label>
                  <input
                    type="text"
                    className="camera-text-input"
                    placeholder="e.g. Hindmata Junction, Milan Subway, Deccan Causeway"
                    value={locationName}
                    onChange={(e) => setLocationName(e.target.value)}
                  />
                </div>
              </div>

              <div className="camera-geo-bar">
                <span>🛰️ GPS Status: <b>{geoStatus}</b></span>
                <span>Coordinates: <code>{latitude.toFixed(5)}, {longitude.toFixed(5)}</code></span>
                <button type="button" className="camera-small-btn" onClick={detectLocation}>
                  ↻ Redetect GPS
                </button>
              </div>

              {/* Map Pin Frame */}
              <div className="camera-map-container" ref={mapContainerRef} />
              <small style={{ color: "#64748b", display: "block", marginTop: "4px" }}>
                💡 You can drag the marker on the map to pin the exact street inundation location.
              </small>

              <div style={{ marginTop: "12px" }}>
                <label className="camera-field-label">Field Notes / Observations (Optional)</label>
                <input
                  type="text"
                  className="camera-text-input"
                  placeholder="e.g. Water height approx 30cm, stormwater drain choked with plastic"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>

              <div className="camera-action-footer">
                <button type="button" className="camera-back-btn" onClick={() => setStep("preview")}>
                  ← Back to Preview
                </button>
                <button
                  type="button"
                  className="camera-submit-btn"
                  onClick={submitIncident}
                  disabled={submitting || !locationName.trim()}
                >
                  {submitting ? "Submitting to Database..." : "✓ Submit Verified Incident Report"}
                </button>
              </div>
            </div>
          )}

          {/* STEP 5: Success & Dynamic Risk Confirmation */}
          {step === "success" && createdIncident && (
            <div className="camera-success-step">
              <div className="camera-success-icon">🎉</div>
              <h3>Incident Report Successfully Created!</h3>
              <p>Your report has been persisted in the historical early-warning intelligence database.</p>

              <div className="camera-success-card">
                <div className="camera-success-row">
                  <span>Incident Identifier:</span>
                  <b>{createdIncident.id}</b>
                </div>
                <div className="camera-success-row">
                  <span>Location:</span>
                  <b>{createdIncident.location_name} ({createdIncident.city})</b>
                </div>
                <div className="camera-success-row">
                  <span>AI Classification:</span>
                  <b className={createdIncident.predicted_class === "Flooded Scene" ? "alert-text" : "safe-text"}>
                    {createdIncident.predicted_class} ({(createdIncident.model_score * 100).toFixed(1)}%)
                  </b>
                </div>
                <div className="camera-success-row">
                  <span>Verification Status:</span>
                  <span className="camera-status-pill">{createdIncident.verification_status}</span>
                </div>
                <hr style={{ margin: "10px 0", border: 0, borderTop: "1px dashed #cbd5e1" }} />
                <div className="camera-success-row">
                  <span>Baseline Area Risk:</span>
                  <b>{createdIncident.baseline_risk_score.toFixed(1)}%</b>
                </div>
                <div className="camera-success-row">
                  <span>Report Risk Adjustment:</span>
                  <b className="adj-text">+{createdIncident.report_risk_adjustment.toFixed(1)} points</b>
                </div>
                <div className="camera-success-row" style={{ fontSize: "14px" }}>
                  <span>Final Recalculated Area Risk:</span>
                  <b style={{ color: "#dc2626" }}>{createdIncident.final_risk_score.toFixed(1)}%</b>
                </div>
              </div>

              <div style={{ marginTop: "16px", display: "flex", gap: "10px", justifyContent: "center" }}>
                <button type="button" className="camera-done-btn" onClick={onClose}>
                  Done & Return to Workspace
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
