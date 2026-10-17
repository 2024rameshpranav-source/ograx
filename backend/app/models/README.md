# AquaSignal Model Directory

Place your trained machine learning model files in this directory.

## Active Engines
 
1. **Pune Waterlogging ML Model**:
   - Default path: `backend/app/models/pune_model.joblib`
   - Configurable environment variable: `PUNE_MODEL_PATH`
   - Trained machine learning model for Pune junction waterlogging risk.

2. **Mumbai Rainfall Warning Engine**:
   - Location: `backend/app/services/mumbai_engine/` and `backend/app/services/mumbai_prototype/`
   - Experimental rule-based screening engine evaluating 1h, 3h, 6h, and 24h rainfall thresholds across 8 Mumbai locations.
   - Does not require a .joblib model file; uses calibrated rainfall thresholds and Open-Meteo live/reanalysis feeds.

## Supported Formats

- `.joblib` (recommended for Scikit-Learn pipelines)
- `.pkl` / `.pickle`

## Model Interface Requirements

The loaded model object should implement either:
- `predict_proba(X)`: For classification models yielding class probabilities (index 1 = waterlogging probability).
- `predict(X)`: For regression or continuous risk score outputs.

If your model has specific feature names, ensure `feature_names_in_` is saved with the model or document the expected columns.
The backend will automatically adapt feature columns to `model.feature_names_in_`.
