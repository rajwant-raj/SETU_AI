import time
from pathlib import Path

import pandas as pd
import requests
from scipy.spatial import cKDTree

INPUT = Path("datasets/processed/core_road_segments.csv")
OUTPUT = Path("datasets/processed/road_segments_with_elevation.csv")

API_URL = "https://api.open-meteo.com/v1/elevation"

# Keep the external API workload small.
# Representative grid spacing is approximately 0.05 degrees.
GRID_STEP = 0.05
BATCH_SIZE = 100


def build_representative_points(df):
    points = (
        df.assign(
            grid_lat=(df["latitude"] / GRID_STEP).round() * GRID_STEP,
            grid_lon=(df["longitude"] / GRID_STEP).round() * GRID_STEP,
        )[["grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    return points


def fetch_elevation(points):
    elevations = []

    for start in range(0, len(points), BATCH_SIZE):
        batch = points.iloc[start:start + BATCH_SIZE]

        params = {
            "latitude": ",".join(batch["grid_lat"].astype(str)),
            "longitude": ",".join(batch["grid_lon"].astype(str)),
        }

        print(
            f"Elevation batch "
            f"{start + 1}-{min(start + BATCH_SIZE, len(points))} "
            f"/ {len(points)}"
        )

        for attempt in range(5):
            response = requests.get(API_URL, params=params, timeout=60)

            if response.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            data = response.json()
            elevations.extend(data["elevation"])
            break
        else:
            raise RuntimeError("Open-Meteo rate limit persisted after retries.")

        time.sleep(2)

    points = points.copy()
    points["elevation_m"] = elevations

    return points


def assign_nearest_elevation(df, points):
    source_coords = points[["grid_lat", "grid_lon"]].to_numpy()
    road_coords = df[["latitude", "longitude"]].to_numpy()

    tree = cKDTree(source_coords)
    _, indices = tree.query(road_coords, k=1)

    result = df.copy()
    result["elevation_m"] = points.iloc[indices]["elevation_m"].to_numpy()

    return result


def main():
    df = pd.read_csv(INPUT)

    print(f"Road segments: {len(df)}")

    points = build_representative_points(df)

    print(f"Representative elevation points: {len(points)}")

    elevation_points = fetch_elevation(points)

    result = assign_nearest_elevation(df, elevation_points)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False)

    print()
    print(f"Saved: {OUTPUT}")
    print(f"Rows: {len(result)}")
    print(
        "Missing elevation:",
        result["elevation_m"].isna().sum(),
    )


if __name__ == "__main__":
    main()
