"""
Open-Meteo Live Rainfall Forecast & Archive Service for Mumbai.
Interacts with https://api.open-meteo.com/v1/forecast to fetch live hourly precipitation.
Implements in-memory TTL caching and controlled fallback to local nowcast data.
"""
import os
import math
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import httpx
import pandas as pd

from app.utils.logging_config import logger
from app.services.mumbai_engine.locations import MUMBAI_LOCATIONS

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 900  # 15 minutes

def _safe_float(val: Any) -> Optional[float]:
    """Safely converts input to float; returns None if missing, NaN, or negative."""
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or f < 0.0) else round(f, 2)
    except (ValueError, TypeError):
        return None

class MumbaiWeatherService:
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_timestamp: float = 0.0
        self._nowcast_csv_path = Path(__file__).resolve().parent.parent / "mumbai_prototype" / "mumbai_waterlogging_nowcast.csv"

    def get_weather_data(self, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves weather data for all 8 Mumbai locations.
        Uses cached responses if available and fresh (<15m).
        Attempts live fetch from Open-Meteo, falling back to local nowcast CSV if offline.
        If both fail, returns explicitly UNAVAILABLE data (never fabricated zeros).
        """
        now = time.time()
        if not force_refresh and self._cache and (now - self._cache_timestamp < CACHE_TTL_SECONDS):
            logger.debug("Serving Mumbai weather from in-memory cache.")
            return self._cache

        # Try live Open-Meteo fetch
        try:
            live_data = self._fetch_live_open_meteo()
            if live_data:
                self._cache = live_data
                self._cache_timestamp = now
                logger.info("Successfully refreshed Mumbai weather data from Open-Meteo API.")
                return self._cache
        except Exception as e:
            logger.warning(f"Live Open-Meteo fetch failed ({e}); falling back to local nowcast dataset.")

        # Fallback to local nowcast CSV
        fallback_data = self._load_local_nowcast()
        if fallback_data:
            self._cache = fallback_data
            self._cache_timestamp = now
            return self._cache

        # Provider completely unavailable: return explicit UNAVAILABLE state
        logger.warning("Both live weather and local archive unavailable. Returning explicit DATA_CHECK_REQUIRED status.")
        return self._generate_unavailable_data()

    def _fetch_live_open_meteo(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Fetches hourly precipitation from Open-Meteo API for each location."""
        results: Dict[str, Dict[str, Any]] = {}

        # Open-Meteo supports comma-separated coordinates for batch requests
        lats = [str(loc["latitude"]) for loc in MUMBAI_LOCATIONS]
        lngs = [str(loc["longitude"]) for loc in MUMBAI_LOCATIONS]

        params = {
            "latitude": ",".join(lats),
            "longitude": ",".join(lngs),
            "hourly": "precipitation,rain",
            "past_days": 1,
            "forecast_days": 1,
            "timezone": "Asia/Kolkata",
        }

        # Optional commercial API key from environment
        api_key = os.environ.get("OPEN_METEO_API_KEY")
        if api_key:
            params["apikey"] = api_key

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(OPEN_METEO_URL, params=params)
                if resp.status_code != 200:
                    logger.warning(f"Open-Meteo responded with status {resp.status_code}: {resp.text[:100]}")
                    return None

                json_resp = resp.json()
                responses_list = json_resp if isinstance(json_resp, list) else [json_resp]
                current_utc = datetime.now(timezone.utc).isoformat()

                for i, loc in enumerate(MUMBAI_LOCATIONS):
                    if i < len(responses_list):
                        data = responses_list[i]
                        hourly = data.get("hourly", {})
                        times = hourly.get("time", [])
                        precip = hourly.get("precipitation", [])

                        metrics = self._compute_rainfall_horizons(times, precip)
                        results[loc["location_name"]] = {
                            "location_name": loc["location_name"],
                            "observation_time": current_utc,
                            "data_status": "AVAILABLE",
                            "data_source": "Open-Meteo Live Forecast & Reanalysis",
                            "data_freshness_status": "FRESH_LIVE",
                            "is_live_open_meteo": True,
                            **metrics
                        }
                    else:
                        results[loc["location_name"]] = self._get_fallback_single_location(loc["location_name"])

            return results
        except httpx.TimeoutException:
            logger.warning("Open-Meteo request timed out after 8.0s. Falling back to local data.")
            return None
        except httpx.RequestError as req_err:
            logger.warning(f"Open-Meteo network request error: {req_err}. Falling back to local data.")
            return None
        except Exception as e:
            logger.error(f"Error parsing Open-Meteo live response: {e}. Falling back to local data.")
            return None

    def _compute_rainfall_horizons(self, times: list, precip: list) -> Dict[str, float]:
        """
        Calculates 1h, 3h, 6h, 24h past totals and 1h, 3h, 6h forecast totals.
        """
        if not times or not precip:
            return {
                "rain_last_1h_mm": 0.0,
                "rain_last_3h_mm": 0.0,
                "rain_last_6h_mm": 0.0,
                "rain_last_24h_mm": 0.0,
                "rain_next_1h_mm": 0.0,
                "rain_next_3h_mm": 0.0,
                "rain_next_6h_mm": 0.0,
            }

        cur_idx = 24 if len(times) >= 48 else len(times) // 2

        rain_last_1h = sum([p or 0.0 for p in precip[max(0, cur_idx - 1):cur_idx]])
        rain_last_3h = sum([p or 0.0 for p in precip[max(0, cur_idx - 3):cur_idx]])
        rain_last_6h = sum([p or 0.0 for p in precip[max(0, cur_idx - 6):cur_idx]])
        rain_last_24h = sum([p or 0.0 for p in precip[max(0, cur_idx - 24):cur_idx]])

        rain_next_1h = sum([p or 0.0 for p in precip[cur_idx:cur_idx + 1]])
        rain_next_3h = sum([p or 0.0 for p in precip[cur_idx:cur_idx + 3]])
        rain_next_6h = sum([p or 0.0 for p in precip[cur_idx:cur_idx + 6]])

        return {
            "rain_last_1h_mm": round(float(rain_last_1h), 2),
            "rain_last_3h_mm": round(float(rain_last_3h), 2),
            "rain_last_6h_mm": round(float(rain_last_6h), 2),
            "rain_last_24h_mm": round(float(rain_last_24h), 2),
            "rain_next_1h_mm": round(float(rain_next_1h), 2),
            "rain_next_3h_mm": round(float(rain_next_3h), 2),
            "rain_next_6h_mm": round(float(rain_next_6h), 2),
        }

    def _load_local_nowcast(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """Loads data from the prototype's mumbai_waterlogging_nowcast.csv."""
        if not self._nowcast_csv_path.exists():
            return None

        try:
            df = pd.read_csv(self._nowcast_csv_path)
            results = {}
            for _, row in df.iterrows():
                loc_name = str(row["location_name"])
                raw_status = row.get("data_status") or row.get("screening_data_status") or "AVAILABLE"

                r1 = _safe_float(row.get("rain_last_1h_mm"))
                r3 = _safe_float(row.get("rain_last_3h_mm"))
                r6 = _safe_float(row.get("rain_last_6h_mm"))
                r24 = _safe_float(row.get("rain_last_24h_mm"))
                f1 = _safe_float(row.get("rain_next_1h_mm"))
                f3 = _safe_float(row.get("rain_next_3h_mm"))
                f6 = _safe_float(row.get("rain_next_6h_mm"))

                # If raw_status is not AVAILABLE or essential columns are missing, flag DATA_CHECK_REQUIRED
                if raw_status != "AVAILABLE" or None in (r1, r3, r6, f1, f3, f6):
                    status = "DATA_CHECK_REQUIRED"
                else:
                    status = "AVAILABLE"

                results[loc_name] = {
                    "location_name": loc_name,
                    "observation_time": str(row.get("observation_time", datetime.now(timezone.utc).isoformat())),
                    "data_status": status,
                    "data_source": "Local Nowcast Snapshot (Open-Meteo Reanalysis/Forecast Archive)",
                    "data_freshness_status": str(row.get("data_freshness_status", "ARCHIVE_SNAPSHOT_FALLBACK")),
                    "is_live_open_meteo": False,
                    "rain_last_1h_mm": r1,
                    "rain_last_3h_mm": r3,
                    "rain_last_6h_mm": r6,
                    "rain_last_24h_mm": r24 if r24 is not None else 0.0,
                    "rain_next_1h_mm": f1,
                    "rain_next_3h_mm": f3,
                    "rain_next_6h_mm": f6,
                }
            return results
        except Exception as e:
            logger.error(f"Error reading local nowcast CSV: {e}")
            return None

    def _get_fallback_single_location(self, loc_name: str) -> Dict[str, Any]:
        """Explicitly denotes that data for this location is unavailable/requires check."""
        return {
            "location_name": loc_name,
            "observation_time": datetime.now(timezone.utc).isoformat(),
            "data_status": "DATA_CHECK_REQUIRED",
            "data_source": "Weather Provider Unavailable",
            "data_freshness_status": "UNAVAILABLE",
            "is_live_open_meteo": False,
            "rain_last_1h_mm": None,
            "rain_last_3h_mm": None,
            "rain_last_6h_mm": None,
            "rain_last_24h_mm": None,
            "rain_next_1h_mm": None,
            "rain_next_3h_mm": None,
            "rain_next_6h_mm": None,
        }

    def _generate_unavailable_data(self) -> Dict[str, Dict[str, Any]]:
        return {loc["location_name"]: self._get_fallback_single_location(loc["location_name"]) for loc in MUMBAI_LOCATIONS}

mumbai_weather_service = MumbaiWeatherService()
