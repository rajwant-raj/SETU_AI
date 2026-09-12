import json
from datetime import datetime
from pathlib import Path

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


if __name__ == "__main__":
    main()
