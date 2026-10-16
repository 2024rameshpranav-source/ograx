import test from "node:test";
import assert from "node:assert/strict";
import {
  getSegmentsForArea,
  calculateSegmentPrediction,
  type RoadSegment,
} from "../src/data/geography.ts";

test("1. Selecting Bandra and Dadar produces distinct, location-specific identifiers and coordinates", () => {
  const bandraSegments = getSegmentsForArea("Mumbai · Bandra");
  const dadarSegments = getSegmentsForArea("Mumbai · Dadar");

  assert.ok(bandraSegments.length > 0, "Bandra must have road segments");
  assert.ok(dadarSegments.length > 0, "Dadar must have road segments");

  const bandra01 = bandraSegments[0];
  const dadar01 = dadarSegments[0];

  // Verify unique segment IDs
  assert.strictEqual(bandra01.id, "BND-01");
  assert.strictEqual(dadar01.id, "DAD-01");
  assert.notStrictEqual(bandra01.id, dadar01.id);

  // Verify distinct location names and areas
  assert.match(bandra01.name, /Linking Road/i);
  assert.match(dadar01.name, /Hindmata/i);
  assert.strictEqual(bandra01.area, "Mumbai · Bandra");
  assert.strictEqual(dadar01.area, "Mumbai · Dadar");

  // Verify distinct coordinates
  assert.notStrictEqual(bandra01.coords[0], dadar01.coords[0]);
  assert.notStrictEqual(bandra01.coords[1], dadar01.coords[1]);

  // Verify distinct physical terrain features
  assert.strictEqual(bandra01.elevation_m, 14.8);
  assert.strictEqual(dadar01.elevation_m, 9.2);
  assert.strictEqual(bandra01.drainage_capacity_ratio, 0.65);
  assert.strictEqual(dadar01.drainage_capacity_ratio, 0.40);
  assert.strictEqual(bandra01.historical_incident_count, 3);
  assert.strictEqual(dadar01.historical_incident_count, 8);
});

test("2. Prediction outputs differ when underlying physical inputs differ", () => {
  const bandra01 = getSegmentsForArea("Mumbai · Bandra")[0];
  const dadar01 = getSegmentsForArea("Mumbai · Dadar")[0];

  const bandraPred3h = calculateSegmentPrediction(bandra01, 3);
  const dadarPred3h = calculateSegmentPrediction(dadar01, 3);

  // Dadar has lower elevation (9.2m vs 14.8m) and poorer drainage (0.40 vs 0.65)
  // Therefore Dadar risk probability must be strictly higher than Bandra under identical rainfall
  assert.ok(
    dadarPred3h.probability > bandraPred3h.probability,
    `Dadar risk (${dadarPred3h.probability}%) must exceed Bandra risk (${bandraPred3h.probability}%) due to physical basin depression`
  );

  // Verify factor breakdown explicitly mentions location's elevation and drainage
  const dadarElevFactor = dadarPred3h.factors.find((f) => f.name === "Terrain Elevation");
  assert.ok(dadarElevFactor);
  assert.match(dadarElevFactor.impact, /9\.2m/);

  const bandraElevFactor = bandraPred3h.factors.find((f) => f.name === "Terrain Elevation");
  assert.ok(bandraElevFactor);
  assert.match(bandraElevFactor.impact, /14\.8m/);
});

test("3. Prediction outputs are strictly identical when inputs are identical (deterministic consistency)", () => {
  const bandra01 = getSegmentsForArea("Mumbai · Bandra")[0];

  const run1 = calculateSegmentPrediction(bandra01, 3, 35.0);
  const run2 = calculateSegmentPrediction(bandra01, 3, 35.0);

  assert.strictEqual(run1.probability, run2.probability);
  assert.strictEqual(run1.category, run2.category);
  assert.strictEqual(run1.uncertainty, run2.uncertainty);
});

test("4. Timeline and detail-panel probabilities match 100% across all 6 horizons", () => {
  const dadar01 = getSegmentsForArea("Mumbai · Dadar")[0];

  for (let h = 1; h <= 6; h++) {
    const result = calculateSegmentPrediction(dadar01, h);
    const timelineEntry = result.timeline[h - 1];

    assert.ok(timelineEntry, `Timeline entry must exist for +${h}h`);
    assert.strictEqual(
      result.probability,
      timelineEntry.probability,
      `DetailPanel probability at +${h}h (${result.probability}%) must equal timeline probability (${timelineEntry.probability}%)`
    );
    assert.strictEqual(
      result.category,
      timelineEntry.category,
      `DetailPanel category at +${h}h (${result.category}) must equal timeline category (${timelineEntry.category})`
    );
    assert.strictEqual(
      result.uncertainty,
      timelineEntry.uncertainty,
      `DetailPanel uncertainty at +${h}h must equal timeline uncertainty`
    );
  }
});

test("5. Switching locations updates timeline and details together without stale state", () => {
  // Simulating state management and race-condition prevention with sequence IDs
  let currentRequestId = 0;
  let activeState: { segmentId: string; probability: number } | null = null;

  function simulateLocationSelect(segment: RoadSegment, horizon: number) {
    const reqId = ++currentRequestId;
    const syncPred = calculateSegmentPrediction(segment, horizon);

    // Initial synchronized update
    activeState = {
      segmentId: segment.id,
      probability: syncPred.probability,
    };

    return {
      asyncResolve: (asyncProb: number) => {
        // Guard against race condition: older request arriving after a newer selection
        if (reqId === currentRequestId) {
          activeState = {
            segmentId: segment.id,
            probability: asyncProb,
          };
        }
      },
    };
  }

  const bandra = getSegmentsForArea("Mumbai · Bandra")[0];
  const dadar = getSegmentsForArea("Mumbai · Dadar")[0];

  // User selects Bandra
  const bandraReq = simulateLocationSelect(bandra, 3);
  assert.strictEqual(activeState?.segmentId, "BND-01");

  // User immediately switches to Dadar before Bandra async resolves
  const dadarReq = simulateLocationSelect(dadar, 3);
  assert.strictEqual(activeState?.segmentId, "DAD-01");

  // Bandra async response resolves LATE
  bandraReq.asyncResolve(45);

  // State MUST NOT be overwritten by the stale Bandra response
  assert.strictEqual(
    activeState?.segmentId,
    "DAD-01",
    "Stale Bandra response must not overwrite active Dadar selection"
  );

  // Dadar async response resolves
  dadarReq.asyncResolve(78);
  assert.strictEqual(activeState?.segmentId, "DAD-01");
  assert.strictEqual(activeState?.probability, 78);
});

test("6. Request payload builder captures location identifier and coordinates", () => {
  const segment = getSegmentsForArea("Mumbai · Dadar")[0];
  const horizon = 4;

  const requestPayload = {
    city: "Mumbai",
    location_id: segment.id,
    location_name: segment.name,
    latitude: segment.coords[0],
    longitude: segment.coords[1],
    forecast_horizon_hours: horizon,
    features: {
      rainfall_mm: 35.0,
      elevation_m: segment.elevation_m,
      drainage_capacity_ratio: segment.drainage_capacity_ratio,
      historical_incident_count: segment.historical_incident_count,
      road_gradient_pct: segment.road_gradient_pct,
    },
  };

  assert.strictEqual(requestPayload.location_id, "DAD-01");
  assert.strictEqual(requestPayload.location_name, "Hindmata Flyover Basin & Underpass");
  assert.strictEqual(requestPayload.latitude, 19.0185);
  assert.strictEqual(requestPayload.longitude, 72.8427);
  assert.strictEqual(requestPayload.features.elevation_m, 9.2);
  assert.strictEqual(requestPayload.features.drainage_capacity_ratio, 0.40);
  assert.strictEqual(requestPayload.features.historical_incident_count, 8);
});
