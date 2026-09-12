import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.spatial.distance import cdist


INPUT_FILE = Path("datasets/processed/road_segments_with_elevation.csv")

RAW_DIR = Path("datasets/raw/weather")
PROCESSED_DIR = Path("datasets/processed/weather")

POINTS_FILE = RAW_DIR / "weather_sampling_points.csv"
FINAL_FILE = PROCESSED_DIR / "weather_daily_points.csv"

API_URL = "https://archive-api.open-meteo.com/v1/archive"

START_DATE = "2019-01-01"
END_DATE = "2025-12-31"

TARGET_POINTS = 40

# One year per request keeps the cache resumable while
# avoiding thousands of small API calls.
DATE_CHUNK_YEARS = 1

DAILY_VARIABLES = [
    "weather_code",
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "rain_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
]


def choose_weather_points(
    df: pd.DataFrame,
    target_points: int,
) -> pd.DataFrame:

    coords = (
        df[["latitude", "longitude"]]
        .dropna()
        .drop_duplicates()
        .to_numpy()
    )

    if len(coords) <= target_points:
        selected = coords
    else:
        centre = coords.mean(axis=0)

        distances_to_centre = np.sum(
            (coords - centre) ** 2,
            axis=1,
        )

        first_idx = int(
            np.argmin(distances_to_centre)
        )

        selected_indices = [first_idx]

        min_distances = cdist(
            coords,
            coords[[first_idx]],
            metric="euclidean",
        ).ravel()

        while len(selected_indices) < target_points:

            next_idx = int(
                np.argmax(min_distances)
            )

            if next_idx in selected_indices:
                break

            selected_indices.append(next_idx)

            new_distances = cdist(
                coords,
                coords[[next_idx]],
                metric="euclidean",
            ).ravel()

            min_distances = np.minimum(
                min_distances,
                new_distances,
            )

        selected = coords[selected_indices]

    result = pd.DataFrame(
        selected,
        columns=[
            "latitude",
            "longitude",
        ],
    )

    result.insert(
        0,
        "weather_point_id",
        [
            f"WX-{i + 1:03d}"
            for i in range(len(result))
        ],
    )

    return result


def create_sampling_points():

    print("Loading road network...")

    df = pd.read_csv(INPUT_FILE)

    required = {
        "segment_id",
        "latitude",
        "longitude",
        "elevation_m",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    points = choose_weather_points(
        df,
        TARGET_POINTS,
    )

    POINTS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    points.to_csv(
        POINTS_FILE,
        index=False,
    )

    print(
        f"Selected {len(points)} representative weather points."
    )

    print(
        f"Saved: {POINTS_FILE}"
    )

    return points


def date_chunks(
    start_date: str,
    end_date: str,
):

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    current = start

    while current <= end:

        chunk_end = min(
            pd.Timestamp(
                current.year + DATE_CHUNK_YEARS,
                current.month,
                current.day,
            ) - pd.Timedelta(days=1),
            pd.Timestamp(end),
        )

        yield (
            current.strftime("%Y-%m-%d"),
            chunk_end.strftime("%Y-%m-%d"),
        )

        current = chunk_end + pd.Timedelta(days=1)


def request_with_retry(
    params: dict,
    batch_name: str,
    max_retries: int = 5,
):

    for attempt in range(max_retries):

        try:

            response = requests.get(
                API_URL,
                params=params,
                timeout=180,
            )

            if response.status_code == 200:
                return response.json()

            if response.status_code == 429:

                wait_seconds = 20 * (
                    attempt + 1
                )

                print(
                    f"[429] {batch_name}: "
                    f"waiting {wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            print(
                f"[HTTP {response.status_code}] "
                f"{batch_name}: "
                f"{response.text[:500]}"
            )

        except requests.RequestException as exc:

            wait_seconds = 10 * (
                attempt + 1
            )

            print(
                f"[ERROR] {batch_name}: {exc}"
            )

            print(
                f"Retrying in {wait_seconds}s..."
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        f"Failed after {max_retries} attempts: "
        f"{batch_name}"
    )


def download_weather(
    points: pd.DataFrame,
):

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    chunks = list(
        date_chunks(
            START_DATE,
            END_DATE,
        )
    )

    print(
        f"Historical period: "
        f"{START_DATE} ? {END_DATE}"
    )

    print(
        f"Weather points: "
        f"{len(points)}"
    )

    print(
        f"API batches: "
        f"{len(chunks)}"
    )

    for index, (
        chunk_start,
        chunk_end,
    ) in enumerate(
        chunks,
        start=1,
    ):

        batch_name = (
            f"daily_{index:03d}"
        )

        output_file = (
            RAW_DIR
            / f"{batch_name}.json"
        )

        if output_file.exists():

            print(
                f"[{index}/{len(chunks)}] "
                f"{batch_name} already cached."
            )

            continue

        print(
            f"[{index}/{len(chunks)}] "
            f"Downloading "
            f"{chunk_start} ? {chunk_end}"
        )

        params = {
            "latitude": ",".join(
                f"{value:.6f}"
                for value
                in points["latitude"]
            ),
            "longitude": ",".join(
                f"{value:.6f}"
                for value
                in points["longitude"]
            ),
            "start_date": chunk_start,
            "end_date": chunk_end,
            "daily": ",".join(
                DAILY_VARIABLES
            ),
            "timezone": "Asia/Kolkata",
            "wind_speed_unit": "kmh",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        }

        data = request_with_retry(
            params,
            batch_name,
        )

        with output_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
            )

        print(
            f"  cached ? {output_file}"
        )

        # Gentle pacing.
        time.sleep(2)


def process_weather():

    print(
        "Processing cached weather..."
    )

    points = pd.read_csv(
        POINTS_FILE
    )

    records = []

    json_files = sorted(
        RAW_DIR.glob(
            "daily_*.json"
        )
    )

    if not json_files:

        raise FileNotFoundError(
            "No cached weather batches found."
        )

    for json_file in json_files:

        print(
            f"Processing {json_file.name}"
        )

        with json_file.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        responses = (
            data
            if isinstance(data, list)
            else [data]
        )

        for response in responses:

            latitude = response.get(
                "latitude"
            )

            longitude = response.get(
                "longitude"
            )

            if (
                latitude is None
                or longitude is None
            ):

                continue

            daily = response.get(
                "daily"
            )

            if not daily:
                continue

            frame = pd.DataFrame(
                daily
            )

            frame["date"] = pd.to_datetime(
                frame["time"]
            )

            frame = frame.drop(
                columns=["time"]
            )

            frame["latitude"] = latitude
            frame["longitude"] = longitude

            frame["weather_point_key"] = (
                frame["latitude"]
                .round(6)
                .astype(str)
                + "_"
                + frame["longitude"]
                .round(6)
                .astype(str)
            )

            records.append(
                frame
            )

    if not records:

        raise RuntimeError(
            "Weather processing produced no records."
        )

    result = pd.concat(
        records,
        ignore_index=True,
    )

    result = result.merge(
        points,
        on=[
            "latitude",
            "longitude",
        ],
        how="left",
    )

    rename_map = {
        "temperature_2m_mean": "temperature_c",
        "precipitation_sum": "precipitation_mm",
        "rain_sum": "rain_mm",
        "wind_speed_10m_max": "wind_speed_kmh",
        "wind_gusts_10m_max": "wind_gust_kmh",
        "weather_code": "weather_code",
    }

    result = result.rename(
        columns=rename_map
    )

    selected_columns = [
        "weather_point_id",
        "date",
        "latitude",
        "longitude",
        "temperature_c",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_mm",
        "rain_mm",
        "precipitation_hours",
        "wind_speed_kmh",
        "wind_gust_kmh",
        "weather_code",
    ]

    result = result[
        selected_columns
    ]

    result = (
        result
        .sort_values(
            [
                "weather_point_id",
                "date",
            ]
        )
        .drop_duplicates(
            [
                "weather_point_id",
                "date",
            ]
        )
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        FINAL_FILE,
        index=False,
    )

    print()
    print(
        f"Weather rows: "
        f"{len(result):,}"
    )

    print(
        f"Weather points: "
        f"{result['weather_point_id'].nunique()}"
    )

    print(
        f"Date range: "
        f"{result['date'].min().date()} ? "
        f"{result['date'].max().date()}"
    )

    print()
    print(
        "Missing values:"
    )

    print(
        result.isna().sum()
    )

    print()
    print(
        f"Saved: {FINAL_FILE}"
    )


def main():

    points = create_sampling_points()

    download_weather(
        points
    )

    process_weather()


if __name__ == "__main__":
    main()
