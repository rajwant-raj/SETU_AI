import hashlib
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
CACHE_MANIFEST_FILE = RAW_DIR / "weather_cache_manifest.json"
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

CACHE_VERSION = 1
TIMEZONE = "Asia/Kolkata"
WIND_SPEED_UNIT = "kmh"
TEMPERATURE_UNIT = "celsius"
PRECIPITATION_UNIT = "mm"


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


def build_cache_config(points: pd.DataFrame) -> dict:
    """Build the configuration that determines whether a cached batch is reusable."""
    sampling_points = [
        {
            "latitude": round(float(row.latitude), 6),
            "longitude": round(float(row.longitude), 6),
        }
        for row in points.itertuples(index=False)
    ]

    return {
        "cache_version": CACHE_VERSION,
        "api_url": API_URL,
        "sampling_points": sampling_points,
        "target_points": TARGET_POINTS,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "date_chunk_years": DATE_CHUNK_YEARS,
        "daily_variables": DAILY_VARIABLES,
        "timezone": TIMEZONE,
        "wind_speed_unit": WIND_SPEED_UNIT,
        "temperature_unit": TEMPERATURE_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
    }


def configuration_hash(config: dict) -> str:
    payload = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_cache_manifest() -> dict | None:
    if not CACHE_MANIFEST_FILE.exists():
        return None

    with CACHE_MANIFEST_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_cache_manifest(config: dict, batches: dict) -> dict:
    manifest = {
        "cache_version": CACHE_VERSION,
        "configuration_hash": configuration_hash(config),
        "configuration": config,
        "batches": batches,
    }

    CACHE_MANIFEST_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with CACHE_MANIFEST_FILE.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, sort_keys=True)

    return manifest


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cached_batch_matches(
    manifest: dict | None,
    config: dict,
    batch_name: str,
    chunk_start: str,
    chunk_end: str,
    output_file: Path,
) -> bool:
    if manifest is None:
        return False

    if manifest.get("configuration_hash") != configuration_hash(config):
        return False

    batch = manifest.get("batches", {}).get(batch_name)
    if not batch or not output_file.exists():
        return False

    if (
        batch.get("start_date") != chunk_start
        or batch.get("end_date") != chunk_end
    ):
        return False

    return (
        batch.get("size_bytes") == output_file.stat().st_size
        and batch.get("sha256") == file_sha256(output_file)
    )


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

    config = build_cache_config(points)
    manifest = load_cache_manifest()

    if (
        manifest is None
        or manifest.get("configuration_hash") != configuration_hash(config)
    ):
        print("Weather cache configuration changed or manifest is missing; existing batches will be regenerated.")
        manifest = write_cache_manifest(config, {})
    else:
        print("Weather cache configuration matches the current sampling/configuration.")

    batches = dict(manifest.get("batches", {}))

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

        if cached_batch_matches(
            manifest,
            config,
            batch_name,
            chunk_start,
            chunk_end,
            output_file,
        ):

            print(
                f"[{index}/{len(chunks)}] "
                f"{batch_name} already cached and validated."
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
            "timezone": TIMEZONE,
            "wind_speed_unit": WIND_SPEED_UNIT,
            "temperature_unit": TEMPERATURE_UNIT,
            "precipitation_unit": PRECIPITATION_UNIT,
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

        batches[batch_name] = {
            "start_date": chunk_start,
            "end_date": chunk_end,
            "file": output_file.name,
            "size_bytes": output_file.stat().st_size,
            "sha256": file_sha256(output_file),
        }
        manifest = write_cache_manifest(config, batches)

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

    config = build_cache_config(points)
    manifest = load_cache_manifest()

    if manifest is None:
        raise RuntimeError(
            "Weather cache manifest is missing; cached batches cannot be trusted."
        )

    if manifest.get("configuration_hash") != configuration_hash(config):
        raise RuntimeError(
            "Weather cache manifest does not match the current sampling-point or selection configuration."
        )

    records = []

    chunks = list(
        date_chunks(
            START_DATE,
            END_DATE,
        )
    )

    if not chunks or not RAW_DIR.exists() or not any(RAW_DIR.glob("daily_*.json")):
        raise FileNotFoundError(
            "No cached weather batches found."
        )

    manifest_batches = manifest.get("batches", {})

    for index, (
        chunk_start,
        chunk_end,
    ) in enumerate(
        chunks,
        start=1,
    ):
        batch_name = f"daily_{index:03d}"
        expected_file = RAW_DIR / f"{batch_name}.json"

        if not expected_file.exists():
            raise FileNotFoundError(
                f"Expected cached batch file {expected_file.name} not found."
            )

        batch = manifest_batches.get(batch_name)
        if not batch:
            raise RuntimeError(
                f"Cached batch {expected_file.name} is not registered in the weather cache manifest."
            )

        if batch.get("file") != expected_file.name:
            raise RuntimeError(
                f"Weather cache manifest file mismatch for {expected_file.name}."
            )

        if (
            batch.get("start_date") != chunk_start
            or batch.get("end_date") != chunk_end
        ):
            raise RuntimeError(
                f"Weather cache manifest date range mismatch for {batch_name}: "
                f"expected {chunk_start} to {chunk_end}, got {batch.get('start_date')} to {batch.get('end_date')}."
            )

        if (
            batch.get("size_bytes") != expected_file.stat().st_size
            or batch.get("sha256") != file_sha256(expected_file)
        ):
            raise RuntimeError(
                f"Cached batch {expected_file.name} failed manifest integrity validation."
            )

        print(
            f"Processing {expected_file.name}"
        )

        with expected_file.open(
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
