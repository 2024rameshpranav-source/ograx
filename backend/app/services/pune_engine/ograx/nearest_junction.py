import numpy as np
import pandas as pd

def nearest_junction(latitude, longitude, nodes):
    required = {"node_id", "latitude", "longitude"}
    if not required.issubset(nodes.columns):
        raise ValueError(f"CSV must contain: {required}")

    valid = nodes.dropna(subset=["latitude", "longitude"]).copy()
    if valid.empty:
        raise ValueError("No valid junction coordinates available")

    lat1 = np.radians(float(latitude))
    lon1 = np.radians(float(longitude))
    lat2 = np.radians(valid["latitude"].to_numpy(dtype=float))
    lon2 = np.radians(valid["longitude"].to_numpy(dtype=float))

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )
    a = np.clip(a, 0, 1)
    distances = 2 * 6371000 * np.arcsin(np.sqrt(a))

    idx = int(np.argmin(distances))
    nearest = valid.iloc[idx]

    return {
        "nearest_node_id": str(nearest["node_id"]),
        "distance_m": round(float(distances[idx]), 2),
        "junction_latitude": float(nearest["latitude"]),
        "junction_longitude": float(nearest["longitude"])
    }
