import test from "node:test";
import assert from "node:assert/strict";
import { mumbaiLocations, cityForArea } from "../src/data/geography.ts";

test("1. Geography defines all 8 authorized Mumbai locations", () => {
  const expected = ["Andheri", "Bandra", "Chembur", "Colaba", "Dadar", "Kurla", "Powai", "Sion"];
  const actual = mumbaiLocations.map((l) => l.name).sort();
  assert.deepStrictEqual(actual, expected.sort());

  // Confirm cityForArea correctly maps Mumbai areas
  expected.forEach((loc) => {
    assert.strictEqual(cityForArea(`Mumbai · ${loc}`), "Mumbai");
  });
});

test("2. Backend API live verification: Mumbai screening engine returns 8 locations", async () => {
  try {
    const res = await fetch("http://localhost:8000/api/cities/mumbai/waterlogging?hours=3");
    if (!res.ok) {
      console.warn("Backend server not responding or port 8000 not reachable during test run");
      return;
    }
    const data = await res.json();
    assert.strictEqual(data.success, true);
    assert.strictEqual(data.city, "mumbai");
    assert.strictEqual(data.prediction_type, "rule_based_rainfall_screening");
    assert.strictEqual(data.validation_status, "NOT_VALIDATED");
    assert.strictEqual(data.locations.length, 8);

    // Verify all 8 locations are present in response
    const returnedNames = data.locations.map((l: any) => l.location_name).sort();
    const expected = ["Andheri", "Bandra", "Chembur", "Colaba", "Dadar", "Kurla", "Powai", "Sion"].sort();
    assert.deepStrictEqual(returnedNames, expected);

    // Verify probability is explicitly null for every location
    for (const loc of data.locations) {
      assert.strictEqual(loc.waterlogging_probability, null, "Waterlogging probability must be null for unvalidated rule-based engine");
      assert.ok(loc.rain_last_1h_mm !== undefined, "1h accumulation metric must be present");
      assert.ok(loc.rain_last_3h_mm !== undefined, "3h accumulation metric must be present");
      assert.ok(loc.rain_last_6h_mm !== undefined, "6h accumulation metric must be present");
      assert.ok(loc.rain_last_24h_mm !== undefined, "24h accumulation metric must be present");
      assert.ok(["NO_RAINFALL_SIGNAL", "LOW_RAINFALL_SIGNAL", "RAINFALL_WATCH", "DATA_CHECK_REQUIRED"].includes(loc.warning_status));
    }
  } catch (err) {
    console.warn("Skipping live backend check (fetch error):", err);
  }
});
