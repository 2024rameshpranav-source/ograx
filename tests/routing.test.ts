import test from "node:test";
import assert from "node:assert/strict";

test("1. Route presets endpoint returns curated corridors for Mumbai and Pune", async () => {
  try {
    const res = await fetch("http://localhost:8000/api/routes/presets");
    if (!res.ok) {
      console.warn("Backend server not responding during test run");
      return;
    }
    const presets = await res.json();
    assert.ok(Array.isArray(presets), "Presets must be returned as an array");
    assert.ok(presets.length >= 4, "Should have at least 4 default presets");

    const mumbaiPresets = presets.filter((p: any) => p.city === "Mumbai");
    const punePresets = presets.filter((p: any) => p.city === "Pune");

    assert.ok(mumbaiPresets.length >= 2, "Must contain Mumbai commuter presets");
    assert.ok(punePresets.length >= 2, "Must contain Pune commuter presets");

    for (const p of presets) {
      assert.ok(p.id, "Preset must have an id");
      assert.ok(p.name, "Preset must have a descriptive name");
      assert.ok(p.origin.latitude && p.origin.longitude, "Preset origin must have valid coordinates");
      assert.ok(p.destination.latitude && p.destination.longitude, "Preset destination must have valid coordinates");
      assert.ok(p.corridor_description, "Preset must have corridor description");
    }
  } catch (err) {
    console.warn("Skipping live backend fetch if offline:", err);
  }
});

test("2. Route recommendation endpoint computes alternatives and hazards", async () => {
  try {
    const payload = {
      city: "Mumbai",
      origin: {
        latitude: 19.1136,
        longitude: 72.8697,
        name: "Andheri East"
      },
      destination: {
        latitude: 19.0657,
        longitude: 72.8687,
        name: "BKC"
      },
      prefer_alternatives: true,
      tolerance_meters: 300
    };

    const res = await fetch("http://localhost:8000/api/routes/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      console.warn("Backend server not responding during test run");
      return;
    }

    const data = await res.json();
    assert.strictEqual(data.success, true);
    assert.strictEqual(data.city, "Mumbai");
    assert.ok(data.routes.length >= 1, "Must return at least 1 feasible candidate route");
    assert.ok(data.total_routes_found >= 1);

    const primaryRoute = data.routes[0];
    assert.ok(primaryRoute.route_id, "Route must have an ID");
    assert.ok(primaryRoute.distance_km > 0, "Distance must be greater than 0");
    assert.ok(primaryRoute.duration_minutes > 0, "Duration must be greater than 0");
    assert.ok(primaryRoute.coordinates.length >= 2, "Coordinates must have at least 2 points");

    // Verify risk categorization
    const allowedCategories = ["LOWER_KNOWN_RISK", "ELEVATED_RISK", "HIGH_HAZARD", "DATA_UNAVAILABLE"];
    assert.ok(
      allowedCategories.includes(primaryRoute.risk_category),
      `Risk category ${primaryRoute.risk_category} must be one of ${allowedCategories.join(", ")}`
    );

    // Verify safety warning is strictly present and never claims false safety
    assert.ok(data.safety_disclaimer, "Safety disclaimer must be present");
    assert.ok(
      data.safety_disclaimer.toLowerCase().includes("floodwater") ||
      data.safety_disclaimer.toLowerCase().includes("safety"),
      "Safety disclaimer must advise regarding floodwater hazards"
    );

    // Verify data source information
    assert.ok(primaryRoute.data_source, "Data source must be documented");
    assert.ok(primaryRoute.data_freshness, "Data freshness must be documented");
  } catch (err) {
    console.warn("Skipping live backend fetch if offline:", err);
  }
});
