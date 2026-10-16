# AquaSignal Model Directory

Place your trained machine learning model files in this directory.

## Expected Files

1. **Mumbai Waterlogging Model**:
   - Default path: `backend/app/models/mumbai_model.joblib`
   - Configurable environment variable: `MUMBAI_MODEL_PATH`

2. **Pune Waterlogging Model**:
   - Default path: `backend/app/models/pune_model.joblib`
   - Configurable environment variable: `PUNE_MODEL_PATH`

## Supported Formats

- `.joblib` (recommended for Scikit-Learn pipelines)
- `.pkl` / `.pickle`

## Model Interface Requirements

The loaded model object should implement either:
- `predict_proba(X)`: For classification models yielding class probabilities (index 1 = waterlogging probability).
- `predict(X)`: For regression or continuous risk score outputs.

If your model has specific feature names, ensure `feature_names_in_` is saved with the model or document the expected columns.
The backend will automatically adapt feature columns to `model.feature_names_in_`.
