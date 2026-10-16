OG RAX — MODEL AND GIS HANDOFF

Contents:
- ograx_flood_classifier.joblib: trained classifier
- ograx_feature_list.json: required model features
- ograx_preprocessing_metadata.json: preprocessing metadata
- ograx_static_node_features.csv: pilot junction coordinates and attributes
- nearest_junction.py: nearest mapped-junction distance function

Integration:
1. Install the dependencies required by the model and backend.
2. Read the feature list and preprocessing metadata before making predictions.
3. Load the CSV with pandas and import nearest_junction from nearest_junction.py.
4. Call nearest_junction(latitude, longitude, nodes) for a selected map location.
5. Keep the distance calculation separate from model prediction.

Important:
- The model was trained using simulated data; real-world performance is not yet validated.
- Verify the junction coordinates and their meaning before calling them physical drains.
- Distance is straight-line distance, not pipe-network distance.
- Do not claim distance is a model input unless the model was trained with it.
