# AquaSignal — AI Waterlogging Early-Warning Backend

High-performance, production-ready REST API built with FastAPI, SQLite, Pydantic v2, and Scikit-Learn/Joblib for serving machine learning waterlogging models across **Mumbai** and **Pune**.

---

## 1. Quick Start on macOS

### Prerequisites
- Python 3.9+ (Python 3.11 recommended)
- macOS terminal (zsh)

### Setup & Launch in 3 Commands

```bash
# 1. Create a Python virtual environment
python3 -m venv backend/.venv

# 2. Install requirements
backend/.venv/bin/pip install -r backend/requirements.txt

# 3. Start the FastAPI development server
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000
```

Once started:
- API Server: `http://localhost:8000`
- Interactive OpenAPI / Swagger Documentation: `http://localhost:8000/docs`
- Alternative Documentation (ReDoc): `http://localhost:8000/redoc`

---

## 2. Machine Learning Model Placement

Place your trained machine learning model files in:

```
backend/app/models/
  ├── mumbai_model.joblib   <-- Mumbai prediction model
  └── pune_model.joblib     <-- Pune prediction model
```

### Configurable Paths
Model paths can be customized via environment variables in `backend/.env`:
```ini
MUMBAI_MODEL_PATH=backend/app/models/mumbai_model.joblib
PUNE_MODEL_PATH=backend/app/models/pune_model.joblib
```

### Supported Serialization Formats
- `joblib` (`.joblib`) — recommended for Scikit-Learn pipelines
- `pickle` (`.pkl`, `.pickle`)

### Model Requirements
The backend dynamically adapts to your model interface:
1. **Classifier**: If `predict_proba(X)` is implemented, the backend extracts the positive class probability ($P(\text{waterlogging})$) as a percentage (0–100%).
2. **Regressor / Scorer**: If `predict(X)` is implemented, continuous outputs are mapped to risk percentages.
3. **Feature Names**: If the model was fitted with feature names (e.g., `model.feature_names_in_`), the backend automatically aligns input columns to that exact feature order.

---

## 3. Expected Model Input Schema

The prediction endpoint accepts a structured JSON payload:

```json
{
  "city": "Mumbai",
  "location_id": "LOC-MUM-01",
  "location_name": "Hindmata Junction",
  "latitude": 19.0185,
  "longitude": 72.8427,
  "forecast_horizon_hours": 3,
  "features": {
    "rainfall_mm": 52.0,
    "rainfall_intensity": 17.3,
    "drainage_capacity_ratio": 0.45,
    "elevation_m": 1.9,
    "tide_level_m": 3.6,
    "soil_saturation_index": 0.82,
    "road_gradient_pct": 0.5,
    "historical_incident_count": 8,
    "extra_features": {
      "catchment_area_sqkm": 2.4
    }
  }
}
```

### Feature Definitions:
| Feature | Type | Unit / Range | Description |
|---|---|---|---|
| `rainfall_mm` | float | $\ge 0.0$ mm | **Required.** Cumulative rainfall for the horizon |
| `rainfall_intensity` | float | $\ge 0.0$ mm/h | Peak intensity rate |
| `drainage_capacity_ratio` | float | $0.0 - 1.0$ | Available stormwater drain discharge efficiency |
| `elevation_m` | float | meters AMSL | Ground elevation / depression depth |
| `tide_level_m` | float | meters | Coastal tidal height (crucial for Mumbai Mithi/outfalls) |
| `soil_saturation_index` | float | $0.0 - 1.0$ | Antecedent soil moisture saturation |
| `road_gradient_pct` | float | $\%$ | Longitudinal slope of road carriageway |
| `historical_incident_count` | int | $\ge 0$ | Past waterlogging frequency in local ward |
| `extra_features` | dict | arbitrary | Any additional custom columns your trained model expects |

---

## 4. REST API Endpoints Catalog

### Health & Capabilities
- `GET /api/health` — Returns application status and checks if Mumbai and Pune model files are loaded.
- `GET /api/cities` — Lists supported cities (`Mumbai`, `Pune`) and model availability.

### Predictions & Forecasting
- `POST /api/predictions` — Executes prediction using the city's trained model.
  - Returns `HTTP 422` for invalid/missing features.
  - Returns `HTTP 503` if the model file is not yet placed in `backend/app/models/`.
- `GET /api/predictions/{city}/latest` — Returns the most recent persisted prediction for the city.
- `GET /api/predictions/{city}` — Lists historical predictions.
- `GET /api/predictions/{city}/forecast?location_name=Hindmata&base_rainfall_mm=40` — Generates a 6-hour forecast trajectory (+1h to +6h).

### Citizen Incident Reports
- `POST /api/reports` — Submits a ground observation report. Persisted in SQLite.
- `GET /api/reports` — Lists reports with pagination (`skip`, `limit`) and filters (`city`, `severity`, `status`, `q`).
- `GET /api/reports/{report_id}` — Retrieves an individual report.
- `PATCH /api/reports/{report_id}/status` — Updates status (`UNVERIFIED REPORT`, `CORROBORATED`, `ADMIN-VERIFIED`).

### Operational Analytics
- `GET /api/analytics/overview?city=Mumbai` — Summary dashboard metrics (report count, status breakdown, model status, data freshness).
- `GET /api/analytics/incidents?city=Mumbai` — Incident breakdown by severity and road accessibility.
- `GET /api/analytics/locations?city=Mumbai` — Monitored hotspot locations with latest risk values.

---

## 5. Running the Automated Test Suite

```bash
backend/.venv/bin/pytest backend/tests -v
```

The test suite includes 20 comprehensive unit and integration tests:
- Health and CORS configuration tests.
- Model selection and city normalization (`mumbai` -> `Mumbai`).
- Missing model file handling (`HTTP 503` error handling).
- Feature validation and input error responses (`HTTP 422`).
- Inference execution using test doubles and failure isolation (`HTTP 500`).
- SQLite persistence of citizen reports and administrative reviews.
- Analytics calculations on empty and populated datasets.

---

## 6. Connecting Frontend to Backend

In the root repository directory, copy `.env.example` or create `.env`:

```ini
VITE_API_URL=http://localhost:8000
VITE_REPORT_STORAGE=api
```

When `npm run dev` runs, the frontend will automatically connect to `http://localhost:8000` via the typed API client `src/services/api.ts`. If the backend is temporarily offline, the frontend gracefully falls back to browser-local demo storage.
