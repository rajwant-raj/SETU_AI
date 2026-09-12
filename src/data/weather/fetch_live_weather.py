import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests


POINTS_FILE = Path(
    "datasets/raw/weather/weather_sampling_points.csv"
)

OUTPUT_DIR = Path(
    "datasets/processed/weather"
)

OUTPUT_FILE = OUTPUT_DIR / "live_weather.json"

API_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
]

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
]


def load_points():
    points = pd.read_csv(POINTS_FILE)

    required = {
        "weather_point_id",
        "latitude",
        "longitude",
    }

    missing = required - set(points.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    return points


def fetch_live_weather(points):
    params = {
        "latitude": ",".join(
            f"{value:.6f}"
            for value in points["latitude"]
        ),
        "longitude": ",".join(
            f"{value:.6f}"
            for value in points["longitude"]
        ),
        "current": ",".join(CURRENT_VARIABLES),
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_hours": 24,
        "timezone": "Asia/Kolkata",
        "wind_speed_unit": "kmh",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()


def normalize_response(points, data):
    responses = (
        data
        if isinstance(data, list)
        else [data]
    )

    point_lookup = {
        (
            round(row.latitude, 6),
            round(row.longitude, 6),
        ): row.weather_point_id
        for row in points.itertuples()
    }

    normalized = []

    for response in responses:
        latitude = response.get("latitude")
        longitude = response.get("longitude")

        if latitude is None or longitude is None:
            continue

        point_id = point_lookup.get(
            (
                round(latitude, 6),
                round(longitude, 6),
            )
        )

        normalized.append(
            {
                "weather_point_id": point_id,
                "latitude": latitude,
                "longitude": longitude,
                "current": response.get("current"),
                "current_units": response.get(
                    "current_units"
                ),
                "hourly": response.get("hourly"),
                "hourly_units": response.get(
                    "hourly_units"
                ),
            }
        )

    return normalized


def main():
    print("Loading weather sampling points...")

    points = load_points()

    print(
        f"Weather points: {len(points)}"
    )

    print(
        "Requesting current + next 24h weather..."
    )

    data = fetch_live_weather(points)

    normalized = normalize_response(
        points,
        data,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "fetched_at": datetime.now().astimezone().isoformat(),
        "source": "Open-Meteo Forecast API",
        "forecast_hours": 24,
        "points": normalized,
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
        )

    print()
    print(
        f"Saved live weather for "
        f"{len(normalized)} points."
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )


class LiveWeatherUnavailableError(RuntimeError):
    """Raised when verified live weather is strictly required but unavailable from API or cache."""
    pass


def load_cached_weather(
    cache_file: Optional[Path | str] = None,
    max_age_seconds: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Load local cached weather snapshot if present and within max_age_seconds."""
    target_file = Path(cache_file) if cache_file else OUTPUT_FILE
    if not target_file.exists():
        return None

    try:
        with target_file.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    if not isinstance(payload, dict) or "points" not in payload:
        return None

    if max_age_seconds is not None and "fetched_at" in payload and payload["fetched_at"]:
        try:
            fetched_time = datetime.fromisoformat(payload["fetched_at"])
            age = (datetime.now().astimezone() - fetched_time).total_seconds()
            if age > max_age_seconds:
                return None
        except Exception:
            pass

    return payload


def get_live_weather_snapshot(
    points: Optional[Any] = None,
    cache_file: Optional[Path | str] = None,
    max_cache_age_seconds: Optional[float] = 3600.0,
    allow_network: bool = True,
    strict: bool = False,
) -> Dict[str, Any]:
    """Retrieve weather snapshot with explicit fallback state: LIVE, CACHED, or NOMINAL_FALLBACK.

    Batched retrieval only: never requests Open-Meteo per segment or per route candidate.
    """
    target_cache = Path(cache_file) if cache_file else OUTPUT_FILE

    def _to_points_df(p: Any) -> pd.DataFrame:
        if p is None:
            return load_points()
        if isinstance(p, pd.DataFrame):
            return p
        return pd.DataFrame(p)

    # 1. Attempt Live Fetch (if allowed)
    if allow_network:
        try:
            pts = _to_points_df(points)
            data = fetch_live_weather(pts)
            normalized = normalize_response(pts, data)

            target_cache.parent.mkdir(parents=True, exist_ok=True)
            iso_now = datetime.now().astimezone().isoformat()
            payload = {
                "fetched_at": iso_now,
                "source": "Open-Meteo Forecast API",
                "forecast_hours": 24,
                "points": normalized,
            }
            with target_cache.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)

            return {
                "state": "LIVE",
                "status": "LIVE",
                "is_live": True,
                "source": "Open-Meteo Forecast API",
                "fetched_at": iso_now,
                "points": normalized,
            }
        except Exception:
            pass

    # 2. Attempt Local Cache
    cached = load_cached_weather(cache_file=target_cache, max_age_seconds=max_cache_age_seconds)
    if cached is not None and cached.get("points"):
        return {
            "state": "CACHED",
            "status": "CACHED",
            "is_live": False,
            "source": "Local Snapshot Cache",
            "fetched_at": cached.get("fetched_at"),
            "points": cached.get("points", []),
        }

    # 3. Handle Strict Failure vs. Nominal Fallback
    if strict:
        raise LiveWeatherUnavailableError(
            "Live weather is unavailable and no valid cached snapshot exists"
        )

    # Build nominal fallback (severity 0.0) without claiming live verification
    try:
        pts = points if points is not None else load_points()
    except Exception:
        pts = []

    nominal_points = []
    if hasattr(pts, "itertuples"):
        for row in pts.itertuples():
            nominal_points.append({
                "weather_point_id": getattr(row, "weather_point_id", None),
                "latitude": getattr(row, "latitude", None),
                "longitude": getattr(row, "longitude", None),
                "current": {
                    "weather_code": 0,
                    "precipitation": 0.0,
                    "wind_speed_10m": 0.0,
                    "wind_gusts_10m": 0.0,
                },
            })
    elif isinstance(pts, Iterable):
        for p in pts:
            if isinstance(p, Mapping):
                nominal_points.append({
                    "weather_point_id": p.get("weather_point_id"),
                    "latitude": p.get("latitude"),
                    "longitude": p.get("longitude"),
                    "current": {
                        "weather_code": 0,
                        "precipitation": 0.0,
                        "wind_speed_10m": 0.0,
                        "wind_gusts_10m": 0.0,
                    },
                })

    return {
        "state": "NOMINAL_FALLBACK",
        "status": "NOMINAL_FALLBACK",
        "is_live": False,
        "source": "Nominal Fallback (Zero Adverse Hazard)",
        "fetched_at": None,
        "points": nominal_points,
        "notes": "Unverified nominal weather; live API and local cache are unavailable.",
    }


if __name__ == "__main__":
    main()
