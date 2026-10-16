
import pandas as pd

THRESHOLDS = {
    1: {"forecast": 5.0, "recent": 5.0},
    3: {"forecast": 10.0, "recent": 10.0},
    6: {"forecast": 20.0, "recent": 20.0},
}

def classify_warning(row, horizon):
    # Support both 'screening_data_status' and 'data_status'
    data_status = row.get("screening_data_status") or row.get("data_status")
    if data_status != "AVAILABLE":
        return "DATA_CHECK_REQUIRED"

    forecast = row.get(f"rain_next_{horizon}h_mm")
    recent = row.get(f"rain_last_{horizon}h_mm")

    if pd.isna(forecast) or pd.isna(recent):
        return "DATA_CHECK_REQUIRED"

    try:
        forecast = float(forecast)
        recent = float(recent)
    except (TypeError, ValueError):
        return "DATA_CHECK_REQUIRED"

    if forecast < 0.0 or recent < 0.0:
        return "DATA_CHECK_REQUIRED"

    threshold = THRESHOLDS[horizon]

    if forecast >= threshold["forecast"] or recent >= threshold["recent"]:
        return "RAINFALL_WATCH"
    if forecast > 0 or recent > 0:
        return "LOW_RAINFALL_SIGNAL"
    return "NO_RAINFALL_SIGNAL"

def overall_status(row):
    results = [
        row["warning_1h"],
        row["warning_3h"],
        row["warning_6h"],
    ]
    if "DATA_CHECK_REQUIRED" in results:
        return "DATA_CHECK_REQUIRED"
    if "RAINFALL_WATCH" in results:
        return "RAINFALL_WATCH"
    if "LOW_RAINFALL_SIGNAL" in results:
        return "LOW_RAINFALL_SIGNAL"
    return "NO_RAINFALL_SIGNAL"

def main(input_path="mumbai_waterlogging_nowcast.csv",
         output_path="mumbai_waterlogging_warning_engine.csv"):
    df = pd.read_csv(input_path)

    # Reconcile schema: support either 'screening_data_status' or 'data_status'
    if "screening_data_status" not in df.columns:
        if "data_status" in df.columns:
            df["screening_data_status"] = df["data_status"]
        else:
            raise ValueError("Input CSV is missing required data status column: neither 'screening_data_status' nor 'data_status' found")

    required = [
        "location_name", "screening_data_status",
        "rain_last_1h_mm", "rain_last_3h_mm", "rain_last_6h_mm",
        "rain_next_1h_mm", "rain_next_3h_mm", "rain_next_6h_mm",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {missing}")

    for horizon in (1, 3, 6):
        df[f"warning_{horizon}h"] = df.apply(
            lambda row: classify_warning(row, horizon), axis=1
        )

    df["overall_screening_status"] = df.apply(overall_status, axis=1)
    df["waterlogging_probability"] = pd.NA
    df["model_validation_status"] = "NOT_VALIDATED"
    df["warning_engine_status"] = "RULE_BASED_PROTOTYPE_NOT_VALIDATED"

    df.to_csv(output_path, index=False)
    print(df[[
        "location_name", "warning_1h", "warning_3h",
        "warning_6h", "overall_screening_status"
    ]].to_string(index=False))
    print(f"\nSaved results to {output_path}")

if __name__ == "__main__":
    main()
