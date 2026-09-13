"""SETU_AI — Checkpoint 18: ML Dataset Construction.

Constructs the canonical tabular ML dataset for road network disruption risk prediction
across the Guwahati–Imphal corridor for calendar years 2019–2024.

Strict Architectural Guarantees:
- Pure Standard Library: Built using standard library only (csv, json, math, datetime, pathlib, collections).
  Zero pandas, zero numpy, zero networkx.
- Full Network & Temporal Coverage: Preserves all 8,007 eligible core segments across 2,192 days.
- Streaming Memory-Safety: Generates annual partitioned chunk files (ml_dataset_YYYY.csv).
- Data Honesty & Provenance: Label disruption_proxy is an engineered physical hazard indicator,
  never represented as observed physical road closures or police records.
- Zero Leakage: Downstream Risk Engine outputs (risk_score, risk_band), post-hoc delay ratios,
  and future-day weather observations are strictly excluded.
- Temporal Framing: Same-day historical classification / engineered-label replication data,
  not true future forecasting.
"""

from __future__ import annotations

import collections
import csv
import datetime
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

# Ensure repository root is in sys.path when module or script is executed
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.accessibility.accessibility_scorer import calculate_accessibility
from src.data.weather.weather_severity import calculate_weather_severity
from src.impact.network_impact import haversine_km

# ------------------------------------------------------------------------------
# File Paths & Constants
# ------------------------------------------------------------------------------
ROAD_ELEVATION_FILE = Path("datasets/processed/road_segments_with_elevation.csv")
CORE_ROADS_FILE = Path("datasets/processed/core_road_segments.csv")
WEATHER_POINTS_FILE = Path("datasets/raw/weather/weather_sampling_points.csv")
RAW_WEATHER_DIR = Path("datasets/raw/weather")
DISASTERS_DIR = Path("datasets/raw/disasters")
PROCESSED_ML_DIR = Path("datasets/processed/ml")
METADATA_FILE = PROCESSED_ML_DIR / "dataset_metadata.json"

CANONICAL_TOTAL_SEGMENTS = 8007
CANONICAL_TOTAL_DAYS = 2192
CANONICAL_EXPECTED_ROWS = CANONICAL_TOTAL_SEGMENTS * CANONICAL_TOTAL_DAYS  # 17,551,344

# Guwahati–Imphal study corridor geographical bounds
CORRIDOR_BOUNDS = {
    "lat_min": 23.0,
    "lat_max": 29.0,
    "lon_min": 90.0,
    "lon_max": 96.0,
}

ROAD_TYPE_RANKS: Dict[str, int] = {
    "motorway": 4,
    "trunk": 3,
    "primary": 2,
    "secondary": 1,
}

PAVED_SURFACES: Set[str] = {
    "asphalt", "paved", "concrete", "bitumen", "chipseal"
}

CANONICAL_SCHEMA: List[str] = [
    "segment_id",
    "date",
    "year",
    "month",
    "day",
    "day_of_week",
    "latitude",
    "longitude",
    "elevation_m",
    "road_type",
    "road_type_rank",
    "surface_paved",
    "lanes",
    "connectivity_degree",
    "accessibility_score",
    "nearest_weather_point_id",
    "weather_point_dist_km",
    "precipitation_mm",
    "rain_mm",
    "precipitation_hours",
    "temperature_c",
    "temperature_max_c",
    "temperature_min_c",
    "temp_range_c",
    "wind_speed_kmh",
    "wind_gust_kmh",
    "weather_code",
    "weather_severity_daily",
    "disruption_proxy",
    "disruption_score_continuous",
]


# ------------------------------------------------------------------------------
# 1. Coordinate & Source Schema Validation
# ------------------------------------------------------------------------------

def validate_coordinates(
    latitude: float,
    longitude: float,
    generic_wgs84_only: bool = False,
) -> bool:
    """Validate geographical coordinates against WGS84 bounds and study corridor.

    Args:
        latitude: Latitude in degrees.
        longitude: Longitude in degrees.
        generic_wgs84_only: If True, only verifies [-90, 90] and [-180, 180].
            If False, additionally verifies coordinates fall within the NER study corridor.

    Returns:
        True if valid.

    Raises:
        ValueError: If coordinates are non-finite, out of WGS84 range, or outside study corridor.
    """
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise ValueError(f"Coordinates must be finite numbers (non-finite detected): ({latitude}, {longitude})")

    if not (-90.0 <= latitude <= 90.0):
        raise ValueError(f"Invalid WGS84 latitude: {latitude} must be in [-90.0, 90.0]")

    if not (-180.0 <= longitude <= 180.0):
        raise ValueError(f"Invalid WGS84 longitude: {longitude} must be in [-180.0, 180.0]")

    if not generic_wgs84_only:
        if not (CORRIDOR_BOUNDS["lat_min"] <= latitude <= CORRIDOR_BOUNDS["lat_max"] and
                CORRIDOR_BOUNDS["lon_min"] <= longitude <= CORRIDOR_BOUNDS["lon_max"]):
            raise ValueError(
                f"Coordinates ({latitude}, {longitude}) outside Guwahati–Imphal corridor bounds "
                f"[{CORRIDOR_BOUNDS['lat_min']}, {CORRIDOR_BOUNDS['lat_max']}] x "
                f"[{CORRIDOR_BOUNDS['lon_min']}, {CORRIDOR_BOUNDS['lon_max']}]."
            )

    return True


def validate_source_schema(
    file_path: Path | str,
    required_columns: Sequence[str],
) -> bool:
    """Validate existence and header schema of a source CSV file.

    Args:
        file_path: Path to CSV file.
        required_columns: Sequence of column names that must be present.

    Returns:
        True if valid.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If any required column is missing.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Required source file not found: {path.resolve()}")

    with path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError(f"Source file {path} is empty.")

    header_set = set(col.strip() for col in header)
    for req in required_columns:
        if req not in header_set:
            raise ValueError(f"Missing required column: '{req}' in source file {path}")

    return True


# ------------------------------------------------------------------------------
# 2. Pure Standard-Library Spatial Density Hashing (Zero NetworkX)
# ------------------------------------------------------------------------------

def calculate_local_segment_density(
    segments: Iterable[Mapping[str, Any]],
    grid_resolution_deg: float = 0.01,
) -> Dict[str, int]:
    """Calculate local spatial midpoint density proxy using standard-library spatial hashing.

    Note: This metric is honestly designated as local_segment_density_proxy.
    In the tabular schema it populates connectivity_degree for specification compatibility,
    representing the count of other segment midpoints co-located in the same spatial cell
    (~1.1 km resolution), NOT exact graph junction topology.

    Args:
        segments: Iterable of segment dictionaries containing 'segment_id', 'latitude', 'longitude'.
        grid_resolution_deg: Quantization grid size in degrees (default 0.01 deg ~= 1.1 km).

    Returns:
        Dict mapping segment_id to integer local midpoint density count (0 = isolated).
    """
    grid: Dict[Tuple[int, int], List[str]] = collections.defaultdict(list)
    seg_cell_map: Dict[str, Tuple[int, int]] = {}

    for s in segments:
        s_id = str(s["segment_id"])
        lat = float(s["latitude"])
        lon = float(s["longitude"])
        cell = (
            round(lat / grid_resolution_deg),
            round(lon / grid_resolution_deg),
        )
        grid[cell].append(s_id)
        seg_cell_map[s_id] = cell

    density_map: Dict[str, int] = {}
    for s_id, cell in seg_cell_map.items():
        density_map[s_id] = max(0, len(grid[cell]) - 1)

    return density_map


# ------------------------------------------------------------------------------
# 3. Weather Station Mappings (Positional 1-to-1 & Spatial Many-to-One)
# ------------------------------------------------------------------------------

def map_sampling_points_positional(
    open_meteo_batch_results: List[Mapping[str, Any]],
    sampling_points: List[Mapping[str, Any]],
) -> Dict[int, str]:
    """Map Open-Meteo batch response array elements 1-to-1 to source sampling points.

    Preserves exact station identities (WX-001 through WX-040) despite Open-Meteo
    grid-coordinate snapping.

    Args:
        open_meteo_batch_results: List of station response objects from daily_00X.json.
        sampling_points: List of station dictionaries from weather_sampling_points.csv.

    Returns:
        Dict mapping integer array index (0..39) to station ID (e.g. {0: "WX-001", ...}).
    """
    mapping: Dict[int, str] = {}
    for i in range(len(open_meteo_batch_results)):
        if i < len(sampling_points):
            mapping[i] = str(sampling_points[i]["weather_point_id"])
        else:
            mapping[i] = f"WX-{i+1:03d}"
    return mapping


def map_segments_to_nearest_station(
    segments: Iterable[Mapping[str, Any]],
    stations: Iterable[Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Map road segments many-to-one to the nearest weather sampling station.

    Uses deterministic Haversine distance with lexicographical tie-breaking
    for equidistant stations.

    Args:
        segments: Iterable of segment dictionaries with 'segment_id', 'latitude', 'longitude'.
        stations: Iterable of station dictionaries with 'weather_point_id', 'latitude', 'longitude'.

    Returns:
        Dict mapping segment_id to:
        {"nearest_weather_point_id": station_id, "weather_point_dist_km": dist_km}
    """
    stations_list = list(stations)
    mapping: Dict[str, Dict[str, Any]] = {}

    for seg in segments:
        s_id = str(seg["segment_id"])
        lat = float(seg["latitude"])
        lon = float(seg["longitude"])

        best_id = ""
        min_dist = float("inf")

        for st in stations_list:
            st_id = str(st["weather_point_id"])
            d = haversine_km(lat, lon, float(st["latitude"]), float(st["longitude"]))

            if d < min_dist - 1e-6:
                min_dist = d
                best_id = st_id
            elif abs(d - min_dist) <= 1e-6:
                # Deterministic tie-break: choose lexicographically smaller ID
                if not best_id or st_id < best_id:
                    best_id = st_id
                    min_dist = d

        mapping[s_id] = {
            "nearest_weather_point_id": best_id,
            "weather_point_dist_km": round(min_dist, 3),
        }

    return mapping


# ------------------------------------------------------------------------------
# 4. Canonical disruption_proxy v0.1 Evaluation
# ------------------------------------------------------------------------------

def derive_disruption_proxy(
    precipitation_mm: float,
    wind_gust_kmh: float,
    accessibility_score: float,
    nearest_disaster_distance_km: float = 999.0,
    disaster_severity: float = 0.0,
) -> Tuple[int, float]:
    """Derive canonical disruption_proxy v0.1 binary label and continuous risk index.

    Canonical Rule:
      condition_a: nearest_disaster_distance_km <= 10.0 AND disaster_severity >= 0.50
      condition_b: precipitation_mm >= 50.0
      condition_c: wind_gust_kmh >= 65.0
      condition_d: accessibility_score < 0.40 AND precipitation_mm >= 25.0

      disruption_proxy = 1 if (a or b or c or d) else 0

    Args:
        precipitation_mm: Same-day total precipitation in mm.
        wind_gust_kmh: Same-day maximum wind gust in km/h.
        accessibility_score: Static road infrastructure accessibility in [0.0, 1.0].
        nearest_disaster_distance_km: Distance to nearest active disaster in km (default 999.0).
        disaster_severity: Severity of nearest active disaster in [0.0, 1.0] (default 0.0).

    Returns:
        Tuple of (binary_label: int, continuous_score: float).
    """
    precip = max(0.0, float(precipitation_mm))
    gust = max(0.0, float(wind_gust_kmh))
    acc = max(0.0, min(1.0, float(accessibility_score)))
    dist = float(nearest_disaster_distance_km)
    sev = float(disaster_severity)

    cond_a = (dist <= 10.0) and (sev >= 0.50)
    cond_b = (precip >= 50.0)
    cond_c = (gust >= 65.0)
    cond_d = (acc < 0.40) and (precip >= 25.0)

    label = 1 if (cond_a or cond_b or cond_c or cond_d) else 0

    # Auxiliary bounded continuous disruption index [0.0, 1.0]
    raw_score = (
        0.40 * (precip / 100.0) +
        0.30 * (gust / 100.0) +
        0.30 * (1.0 - acc)
    )
    score = round(max(0.0, min(1.0, raw_score)), 4)

    return label, score


# ------------------------------------------------------------------------------
# 5. Label Provenance & Schema Specification
# ------------------------------------------------------------------------------

def get_label_provenance() -> Dict[str, Any]:
    """Return machine-readable label provenance contract per DATASET_SPEC_v0.1.txt."""
    return {
        "label_type": "derived",
        "label_source": "GDACS + Open-Meteo + OSM",
        "label_derivation_method": "deterministic_threshold_rule_v0.1",
        "disaster_condition_a_active": False,
        "disaster_condition_a_notes": (
            "Local disaster directory datasets/raw/disasters is empty; condition (a) "
            "defaulted to inactive (dist=999.0, sev=0.0). Conditions b, c, d fully operational."
        ),
        "honesty_disclosure": (
            "disruption_proxy is an engineered physical hazard indicator derived from "
            "deterministic weather and infrastructure thresholds. Never claim it as observed "
            "road-closure ground truth, police closure confirmation, or traffic standstill."
        ),
    }


def get_dataset_feature_names() -> List[str]:
    """Return canonical 30-column dataset schema list."""
    return list(CANONICAL_SCHEMA)


# ------------------------------------------------------------------------------
# 6. Static Feature Enrichment & ML Record Assembly
# ------------------------------------------------------------------------------

def enrich_static_segment(
    raw_seg: Mapping[str, Any],
    density_proxy: int,
    station_info: Mapping[str, Any],
) -> Dict[str, Any]:
    """Enrich a single road segment with static infrastructure attributes.

    Reuses existing accessibility scoring engine without formula duplication.

    Args:
        raw_seg: Raw segment dictionary from road_segments_with_elevation.csv.
        density_proxy: Local spatial midpoint density count.
        station_info: Dict with 'nearest_weather_point_id' and 'weather_point_dist_km'.

    Returns:
        Dict with static segment attributes.
    """
    s_id = str(raw_seg["segment_id"])
    lat = float(raw_seg["latitude"])
    lon = float(raw_seg["longitude"])
    road_type = str(raw_seg.get("road_type", "secondary")).lower().strip()
    surface = str(raw_seg.get("surface", "")).lower().strip()

    road_rank = ROAD_TYPE_RANKS.get(road_type, 1)
    surface_paved = 1 if surface in PAVED_SURFACES else 0

    lanes_val = raw_seg.get("lanes")
    try:
        lanes = int(float(lanes_val)) if lanes_val not in (None, "", "nan", "NaN") else 1
    except (ValueError, TypeError):
        lanes = 1

    elev_val = raw_seg.get("elevation_m")
    try:
        elevation_m = float(elev_val) if elev_val not in (None, "", "nan", "NaN") else 0.0
    except (ValueError, TypeError):
        elevation_m = 0.0

    maxspeed_val = raw_seg.get("maxspeed")
    maxspeed = None
    if maxspeed_val not in (None, "", "nan", "NaN"):
        try:
            f_speed = float(maxspeed_val)
            if math.isfinite(f_speed) and f_speed > 0:
                maxspeed = f_speed
        except (ValueError, TypeError):
            pass

    # Deterministic accessibility score via existing engine
    acc_res = calculate_accessibility({
        "segment_id": s_id,
        "road_type": road_type,
        "surface": surface if surface else None,
        "lanes": lanes,
        "maxspeed": maxspeed,
    })
    accessibility_score = round(acc_res["accessibility_score"], 4)

    return {
        "segment_id": s_id,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "elevation_m": round(elevation_m, 2),
        "road_type": road_type,
        "road_type_rank": road_rank,
        "surface_paved": surface_paved,
        "lanes": lanes,
        "connectivity_degree": density_proxy,
        "accessibility_score": accessibility_score,
        "nearest_weather_point_id": str(station_info["nearest_weather_point_id"]),
        "weather_point_dist_km": float(station_info["weather_point_dist_km"]),
    }


def assemble_ml_record(
    static_seg: Mapping[str, Any],
    daily_weather: Mapping[str, Any],
    density_proxy: Optional[int] = None,
    nearest_dist_km: Optional[float] = None,
) -> Dict[str, Any]:
    """Assemble a single canonical 30-column ML record.

    Framing: Same-day historical classification record.
    Leakage Protection: Zero Risk Engine outputs; zero future lookahead features.

    Args:
        static_seg: Static segment attributes.
        daily_weather: Same-day historical weather dictionary.
        density_proxy: Optional override for local segment density proxy.
        nearest_dist_km: Optional override for weather point distance.

    Returns:
        Dict conforming to CANONICAL_SCHEMA in exact order.
    """
    date_str = str(daily_weather["date"])
    d = datetime.date.fromisoformat(date_str)

    precip_mm = round(float(daily_weather.get("precipitation_mm", 0.0)), 2)
    rain_mm = round(float(daily_weather.get("rain_mm", 0.0)), 2)
    precip_hrs = round(float(daily_weather.get("precipitation_hours", 0.0)), 2)
    temp_c = round(float(daily_weather.get("temperature_c", 0.0)), 2)
    temp_max_c = round(float(daily_weather.get("temperature_max_c", 0.0)), 2)
    temp_min_c = round(float(daily_weather.get("temperature_min_c", 0.0)), 2)
    temp_range_c = round(temp_max_c - temp_min_c, 2)
    wind_spd = round(float(daily_weather.get("wind_speed_kmh", 0.0)), 2)
    wind_gust = round(float(daily_weather.get("wind_gust_kmh", 0.0)), 2)
    weather_code = int(daily_weather.get("weather_code", 0))

    weather_sev = daily_weather.get("weather_severity_daily")
    if weather_sev is None:
        weather_sev = calculate_weather_severity({
            "weather_code": weather_code,
            "precipitation": precip_mm,
            "wind_speed_10m": wind_spd,
            "wind_gusts_10m": wind_gust,
        })
    weather_sev = round(float(weather_sev), 4)

    road_type = str(static_seg.get("road_type", "secondary")).lower().strip()
    road_type_rank = int(static_seg.get("road_type_rank", ROAD_TYPE_RANKS.get(road_type, 1)))
    surface = str(static_seg.get("surface", "")).lower().strip()
    surface_paved = int(static_seg.get("surface_paved", 1 if surface in PAVED_SURFACES else 0))
    lanes = int(static_seg.get("lanes", 1))
    elevation_m = float(static_seg.get("elevation_m", 0.0))

    acc_score_val = static_seg.get("accessibility_score")
    if acc_score_val is not None:
        acc_score = float(acc_score_val)
    else:
        acc_res = calculate_accessibility({
            "segment_id": str(static_seg.get("segment_id", "")),
            "road_type": road_type,
            "surface": surface if surface else None,
            "lanes": lanes,
            "maxspeed": static_seg.get("maxspeed"),
        })
        acc_score = round(acc_res["accessibility_score"], 4)

    label, score = derive_disruption_proxy(
        precipitation_mm=precip_mm,
        wind_gust_kmh=wind_gust,
        accessibility_score=acc_score,
    )

    connectivity = density_proxy if density_proxy is not None else static_seg.get("connectivity_degree", 0)
    station_dist = nearest_dist_km if nearest_dist_km is not None else static_seg.get("weather_point_dist_km", 0.0)

    record = {
        "segment_id": str(static_seg["segment_id"]),
        "date": date_str,
        "year": d.year,
        "month": d.month,
        "day": d.day,
        "day_of_week": d.weekday(),  # 0 = Monday, 6 = Sunday
        "latitude": static_seg["latitude"],
        "longitude": static_seg["longitude"],
        "elevation_m": elevation_m,
        "road_type": road_type,
        "road_type_rank": road_type_rank,
        "surface_paved": surface_paved,
        "lanes": lanes,
        "connectivity_degree": connectivity,
        "accessibility_score": acc_score,
        "nearest_weather_point_id": static_seg.get("nearest_weather_point_id", ""),
        "weather_point_dist_km": station_dist,
        "precipitation_mm": precip_mm,
        "rain_mm": rain_mm,
        "precipitation_hours": precip_hrs,
        "temperature_c": temp_c,
        "temperature_max_c": temp_max_c,
        "temperature_min_c": temp_min_c,
        "temp_range_c": temp_range_c,
        "wind_speed_kmh": wind_spd,
        "wind_gust_kmh": wind_gust,
        "weather_code": weather_code,
        "weather_severity_daily": weather_sev,
        "disruption_proxy": label,
        "disruption_score_continuous": score,
    }

    return record


# ------------------------------------------------------------------------------
# 7. Sorting & Duplicate Validation
# ------------------------------------------------------------------------------

def sort_records_deterministic(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort records deterministically: primary key = date (asc), secondary = segment_id (asc)."""
    return sorted(records, key=lambda r: (r["date"], r["segment_id"]))


def validate_no_duplicate_keys(records: Iterable[Mapping[str, Any]]) -> None:
    """Ensure no duplicate (segment_id, date) keys exist in record collection.

    Raises:
        ValueError: If duplicate key is found.
    """
    seen: Set[Tuple[str, str]] = set()
    for r in records:
        key = (str(r["segment_id"]), str(r["date"]))
        if key in seen:
            raise ValueError(f"Duplicate (segment_id, date) detected: {key}")
        seen.add(key)


# ------------------------------------------------------------------------------
# 8. Metadata Manifest Generation
# ------------------------------------------------------------------------------

def generate_dataset_metadata(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Generate comprehensive dataset metadata manifest adhering to contract.

    Separates reproducible core configuration from incidental run metadata.

    Args:
        stats: Dictionary of run statistics (total_rows, positive_labels, yearly_breakdown).

    Returns:
        Structured metadata dictionary.
    """
    return {
        "dataset_version": "v0.1",
        "target_geography": "Guwahati -> Imphal corridor",
        "total_road_segments": CANONICAL_TOTAL_SEGMENTS,
        "temporal_range": {
            "start_date": "2019-01-01",
            "end_date": "2024-12-31",
            "total_days": CANONICAL_TOTAL_DAYS,
        },
        "total_expected_rows": CANONICAL_EXPECTED_ROWS,
        "total_generated_rows": stats.get("total_rows", 0),
        "spatial_density_method": "midpoint_spatial_hash_grid_0.01deg",
        "spatial_density_notes": (
            "connectivity_degree represents local_segment_density_proxy: the count of other "
            "road segment midpoints occupying the same ~1.1 km spatial cell, NOT exact graph topology."
        ),
        "weather_station_mapping": {
            "total_stations": 40,
            "source_to_station_mapping": "positional_1_to_1",
            "segment_to_station_mapping": "deterministic_nearest_haversine_lexicographical_tie_break",
        },
        "label_provenance": get_label_provenance(),
        "leakage_safeguards": {
            "risk_engine_outputs_excluded": True,
            "post_incident_fields_excluded": True,
            "future_weather_excluded": True,
            "temporal_framing": "same_day_historical_classification_only",
            "disclaimer": (
                "Same-day historical classification dataset for pipeline verification. "
                "Does not claim genuine future disruption forecasting."
            ),
        },
        "actual_class_prevalence": {
            "total_positive_labels": stats.get("positive_labels", 0),
            "prevalence_ratio": round(
                stats.get("positive_labels", 0) / max(1, stats.get("total_rows", 1)), 6
            ),
            "yearly_breakdown": stats.get("yearly_breakdown", {}),
        },
        "schema": CANONICAL_SCHEMA,
        "run_metadata": {
            "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    }


# ------------------------------------------------------------------------------
# 9. Pipeline Loading & Streaming Yearly Dataset Generation
# ------------------------------------------------------------------------------

def load_sampling_points(points_path: Path | str = WEATHER_POINTS_FILE) -> List[Dict[str, Any]]:
    """Load weather sampling points from CSV."""
    path = Path(points_path)
    validate_source_schema(path, ["weather_point_id", "latitude", "longitude"])
    points: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            points.append({
                "weather_point_id": row["weather_point_id"].strip(),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
            })
    return points


def load_and_enrich_static_segments(
    road_path: Path | str = ROAD_ELEVATION_FILE,
    points_path: Path | str = WEATHER_POINTS_FILE,
) -> List[Dict[str, Any]]:
    """Load road segments with elevation and precompute all static features.

    Returns:
        List of enriched static segment dictionaries.
    """
    path = Path(road_path)
    validate_source_schema(path, ["segment_id", "latitude", "longitude", "road_type", "elevation_m"])
    raw_segments: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            validate_coordinates(float(row["latitude"]), float(row["longitude"]))
            raw_segments.append(row)

    if len(raw_segments) != CANONICAL_TOTAL_SEGMENTS:
        raise ValueError(
            f"Expected exactly {CANONICAL_TOTAL_SEGMENTS} segments in {path}, found {len(raw_segments)}"
        )

    stations = load_sampling_points(points_path)
    density_map = calculate_local_segment_density(raw_segments)
    nearest_station_map = map_segments_to_nearest_station(raw_segments, stations)

    enriched: List[Dict[str, Any]] = []
    for raw in raw_segments:
        s_id = str(raw["segment_id"])
        enriched.append(enrich_static_segment(
            raw,
            density_proxy=density_map[s_id],
            station_info=nearest_station_map[s_id],
        ))

    return enriched


def parse_weather_json_to_station_records(
    json_path: Path | str,
    sampling_points: List[Mapping[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Parse yearly Open-Meteo batch JSON file into nested daily station records.

    Returns:
        Mapping: station_id -> date_str -> daily_weather_dict
    """
    path = Path(json_path)
    if not path.is_file():
        raise FileNotFoundError(f"Weather JSON archive not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        batch_data = json.load(f)

    if len(batch_data) != len(sampling_points):
        raise ValueError(
            f"Weather file {path} contains {len(batch_data)} stations; expected {len(sampling_points)}"
        )

    station_id_map = map_sampling_points_positional(batch_data, sampling_points)
    station_weather: Dict[str, Dict[str, Dict[str, Any]]] = collections.defaultdict(dict)

    for idx, station_data in enumerate(batch_data):
        st_id = station_id_map[idx]
        daily = station_data.get("daily", {})
        dates = daily.get("time", [])
        codes = daily.get("weather_code", [])
        temp_means = daily.get("temperature_2m_mean", [])
        temp_maxs = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        precips = daily.get("precipitation_sum", [])
        rains = daily.get("rain_sum", [])
        precip_hrs = daily.get("precipitation_hours", [])
        winds = daily.get("wind_speed_10m_max", [])
        gusts = daily.get("wind_gusts_10m_max", [])

        num_days = len(dates)
        for i in range(num_days):
            date_str = str(dates[i])
            w_code = int(codes[i]) if i < len(codes) and codes[i] is not None else 0
            p_sum = float(precips[i]) if i < len(precips) and precips[i] is not None else 0.0
            r_sum = float(rains[i]) if i < len(rains) and rains[i] is not None else 0.0
            p_hrs = float(precip_hrs[i]) if i < len(precip_hrs) and precip_hrs[i] is not None else 0.0
            t_mean = float(temp_means[i]) if i < len(temp_means) and temp_means[i] is not None else 0.0
            t_max = float(temp_maxs[i]) if i < len(temp_maxs) and temp_maxs[i] is not None else 0.0
            t_min = float(temp_mins[i]) if i < len(temp_mins) and temp_mins[i] is not None else 0.0
            w_spd = float(winds[i]) if i < len(winds) and winds[i] is not None else 0.0
            w_gst = float(gusts[i]) if i < len(gusts) and gusts[i] is not None else 0.0

            w_sev = calculate_weather_severity({
                "weather_code": w_code,
                "precipitation": p_sum,
                "wind_speed_10m": w_spd,
                "wind_gusts_10m": w_gst,
            })

            station_weather[st_id][date_str] = {
                "date": date_str,
                "weather_code": w_code,
                "precipitation_mm": p_sum,
                "rain_mm": r_sum,
                "precipitation_hours": p_hrs,
                "temperature_c": t_mean,
                "temperature_max_c": t_max,
                "temperature_min_c": t_min,
                "wind_speed_kmh": w_spd,
                "wind_gust_kmh": w_gst,
                "weather_severity_daily": w_sev,
            }

    return station_weather


def build_yearly_partition(
    year: int,
    weather_json_path: Path | str,
    static_segments: List[Dict[str, Any]],
    sampling_points: List[Mapping[str, Any]],
    output_csv_path: Path | str,
) -> Dict[str, Any]:
    """Build and stream an annual partition CSV file directly to disk.

    Overwrites any existing partition file cleanly to prevent contamination.

    Returns:
        Dict with yearly summary metrics (rows, days, positive_labels, prevalence).
    """
    out_path = Path(output_csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    station_weather = parse_weather_json_to_station_records(weather_json_path, sampling_points)

    # Determine unique sorted dates in this year across stations
    dates_set: Set[str] = set()
    for st_records in station_weather.values():
        dates_set.update(st_records.keys())
    sorted_dates = sorted(dates_set)

    is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    expected_days = 366 if is_leap else 365
    if len(sorted_dates) != expected_days:
        raise ValueError(
            f"Year {year} has {len(sorted_dates)} dates in weather archive; expected {expected_days}"
        )

    # Sort segments by segment_id for deterministic row order within each day
    sorted_segments = sorted(static_segments, key=lambda s: s["segment_id"])

    total_rows = 0
    positive_labels = 0

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_SCHEMA)
        writer.writeheader()

        for date_str in sorted_dates:
            for seg in sorted_segments:
                st_id = seg["nearest_weather_point_id"]
                daily_w = station_weather[st_id].get(date_str)
                if daily_w is None:
                    raise ValueError(f"Missing weather observation for station {st_id} on {date_str}")

                rec = assemble_ml_record(seg, daily_w)
                writer.writerow(rec)

                total_rows += 1
                if rec["disruption_proxy"] == 1:
                    positive_labels += 1

    prevalence = round(positive_labels / max(1, total_rows), 6)
    return {
        "rows": total_rows,
        "days": len(sorted_dates),
        "positive_labels": positive_labels,
        "prevalence": prevalence,
    }


def build_canonical_ml_dataset(
    output_dir: Path | str = PROCESSED_ML_DIR,
) -> Dict[str, Any]:
    """Execute complete dataset construction across all 6 years (2019–2024).

    Emits ml_dataset_YYYY.csv for each year and dataset_metadata.json.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sampling_points = load_sampling_points()
    static_segments = load_and_enrich_static_segments()

    year_files = [
        (2019, RAW_WEATHER_DIR / "daily_001.json"),
        (2020, RAW_WEATHER_DIR / "daily_002.json"),
        (2021, RAW_WEATHER_DIR / "daily_003.json"),
        (2022, RAW_WEATHER_DIR / "daily_004.json"),
        (2023, RAW_WEATHER_DIR / "daily_005.json"),
        (2024, RAW_WEATHER_DIR / "daily_006.json"),
    ]

    total_rows = 0
    total_positives = 0
    yearly_breakdown: Dict[str, Dict[str, Any]] = {}

    for year, json_file in year_files:
        partition_path = out_dir / f"ml_dataset_{year}.csv"
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Processing year {year} from {json_file.name} -> {partition_path.name}...")
        metrics = build_yearly_partition(
            year=year,
            weather_json_path=json_file,
            static_segments=static_segments,
            sampling_points=sampling_points,
            output_csv_path=partition_path,
        )
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Completed {year}: {metrics['rows']:,} rows ({metrics['days']} days), {metrics['positive_labels']:,} positives (prevalence: {metrics['prevalence']:.4%})")
        total_rows += metrics["rows"]
        total_positives += metrics["positive_labels"]
        yearly_breakdown[str(year)] = metrics

    metadata = generate_dataset_metadata({
        "total_rows": total_rows,
        "positive_labels": total_positives,
        "yearly_breakdown": yearly_breakdown,
    })

    meta_path = out_dir / "dataset_metadata.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return metadata


if __name__ == "__main__":
    print("Building SETU canonical ML dataset...")
    meta = build_canonical_ml_dataset()
    print(f"Dataset generated successfully: {meta['total_generated_rows']} rows.")
    print(f"Metadata written to {METADATA_FILE}")
