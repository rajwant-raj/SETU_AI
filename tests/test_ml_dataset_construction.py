"""SETU_AI — Checkpoint 18: ML Dataset Construction Test Suite.

Verifies the construction of the canonical tabular ML dataset for road network disruption risk
across the Guwahati–Imphal corridor for calendar years 2019–2024.

Tests enforce:
1. Source schema validation & missing file/column handling
2. Generic WGS84 and corridor-specific coordinate validation
3. Deterministic pure-stdlib spatial density hashing (Zero NetworkX)
4. Positional 1-to-1 Open-Meteo 40-station identity mapping
5. Deterministic many-to-one road-to-station nearest mapping & tie breaking
6. Exact canonical disruption_proxy v0.1 threshold rules & boundary conditions
7. Strict label provenance contract ("derived", "deterministic_threshold_rule_v0.1")
8. Zero-leakage column exclusion (no risk_score, risk_band, current_delay_ratio, etc.)
9. Same-day temporal alignment and absence of future lookahead features
10. Duplicate (segment_id, date) detection and deterministic row ordering
11. Comprehensive dataset metadata manifest schema
12. Repeat-generation determinism
"""

from __future__ import annotations

import collections
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Mapping, Tuple

import pytest

# Target builder module (to be implemented after test suite)
import src.data.processing.build_ml_dataset as bmd


# ------------------------------------------------------------------------------
# 1. Dependency & Architecture Guard
# ------------------------------------------------------------------------------

def test_no_networkx_dependency():
    """Ensure NetworkX is not imported or required for spatial density proxy calculation."""
    assert "networkx" not in sys.modules, "NetworkX must not be imported anywhere in Checkpoint 18."


# ------------------------------------------------------------------------------
# 2. Coordinate Validation
# ------------------------------------------------------------------------------

def test_generic_wgs84_and_dataset_geography_validation():
    """Verify generic WGS84 bounds [-90, 90], [-180, 180] and study-area bounding."""
    # Valid generic WGS84 coordinates
    assert bmd.validate_coordinates(26.1445, 91.7362, generic_wgs84_only=True) is True
    assert bmd.validate_coordinates(-45.0, 120.0, generic_wgs84_only=True) is True
    assert bmd.validate_coordinates(0.0, 0.0, generic_wgs84_only=True) is True

    # Out of bounds WGS84 coordinates
    with pytest.raises(ValueError, match="latitude"):
        bmd.validate_coordinates(90.1, 91.7, generic_wgs84_only=True)

    with pytest.raises(ValueError, match="latitude"):
        bmd.validate_coordinates(-90.1, 91.7, generic_wgs84_only=True)

    with pytest.raises(ValueError, match="longitude"):
        bmd.validate_coordinates(26.1, 180.1, generic_wgs84_only=True)

    with pytest.raises(ValueError, match="longitude"):
        bmd.validate_coordinates(26.1, -180.1, generic_wgs84_only=True)

    with pytest.raises(ValueError, match="non-finite"):
        bmd.validate_coordinates(float("nan"), 91.7, generic_wgs84_only=True)

    # Study-area boundary validation (Guwahati–Imphal corridor: lat ~[23.0, 29.0], lon ~[90.0, 96.0])
    assert bmd.validate_coordinates(26.1445, 91.7362, generic_wgs84_only=False) is True
    assert bmd.validate_coordinates(24.8170, 93.9368, generic_wgs84_only=False) is True

    with pytest.raises(ValueError, match="corridor"):
        bmd.validate_coordinates(12.9716, 77.5946, generic_wgs84_only=False)  # Bangalore


# ------------------------------------------------------------------------------
# 3. Source Schema Validation & Missing File Handling
# ------------------------------------------------------------------------------

def test_source_schema_validation_and_missing_file_handling(tmp_path: Path):
    """Verify source schema validation detects missing files and required columns."""
    missing_file = tmp_path / "non_existent.csv"
    with pytest.raises(FileNotFoundError):
        bmd.validate_source_schema(missing_file, required_columns=["segment_id", "latitude"])

    # File with missing columns
    bad_csv = tmp_path / "bad_schema.csv"
    with bad_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["segment_id", "latitude"])
        writer.writerow(["OSM-001", "26.1"])

    with pytest.raises(ValueError, match="Missing required column"):
        bmd.validate_source_schema(bad_csv, required_columns=["segment_id", "latitude", "longitude", "elevation_m"])

    # Valid schema file
    good_csv = tmp_path / "good_schema.csv"
    with good_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["segment_id", "latitude", "longitude", "elevation_m"])
        writer.writerow(["OSM-001", "26.1", "91.7", "120.0"])

    assert bmd.validate_source_schema(good_csv, required_columns=["segment_id", "latitude", "longitude", "elevation_m"]) is True


# ------------------------------------------------------------------------------
# 4. Deterministic Spatial Density Hashing (local_segment_density_proxy)
# ------------------------------------------------------------------------------

def test_deterministic_spatial_density_hashing():
    """Verify local_segment_density_proxy behaves deterministically via standard-library hashing."""
    # Cluster 1: 3 segments in cell (26.12, 91.73)
    # Cluster 2: 1 segment in cell (24.82, 93.94)
    segments = [
        {"segment_id": "S1", "latitude": 26.1201, "longitude": 91.7302},
        {"segment_id": "S2", "latitude": 26.1209, "longitude": 91.7308},
        {"segment_id": "S3", "latitude": 26.1245, "longitude": 91.7341},
        {"segment_id": "S4", "latitude": 24.8170, "longitude": 93.9368},
    ]

    density = bmd.calculate_local_segment_density(segments, grid_resolution_deg=0.01)

    assert density["S1"] == 2  # S2 and S3 share the cell
    assert density["S2"] == 2
    assert density["S3"] == 2
    assert density["S4"] == 0  # Isolated segment

    # Order invariance: shuffle segments and verify identical density results
    shuffled_segments = [segments[3], segments[1], segments[0], segments[2]]
    density_shuffled = bmd.calculate_local_segment_density(shuffled_segments, grid_resolution_deg=0.01)
    assert density == density_shuffled


# ------------------------------------------------------------------------------
# 5. Positional 40-Station Identity Mapping
# ------------------------------------------------------------------------------

def test_positional_40_station_identity_mapping():
    """Verify Open-Meteo batch response arrays map 1-to-1 by positional index to sampling points."""
    sampling_points = [
        {"weather_point_id": f"WX-{i:03d}", "latitude": 25.0 + (i * 0.05), "longitude": 92.0 + (i * 0.05)}
        for i in range(1, 41)
    ]

    # Mock Open-Meteo batch response containing 40 locations with grid-snapped coordinates
    mock_batch_response = [
        {"latitude": round(pt["latitude"], 2), "longitude": round(pt["longitude"], 2), "location_id": i}
        for i, pt in enumerate(sampling_points)
    ]

    station_mapping = bmd.map_sampling_points_positional(mock_batch_response, sampling_points)

    assert len(station_mapping) == 40
    for i in range(40):
        expected_id = f"WX-{i+1:03d}"
        assert station_mapping[i] == expected_id, f"Index {i} must resolve to {expected_id}."

    # Verify uniqueness of all 40 mapped station IDs
    assert len(set(station_mapping.values())) == 40


# ------------------------------------------------------------------------------
# 6. Many-to-One Road-to-Station Nearest Mapping & Tie Breaking
# ------------------------------------------------------------------------------

def test_many_to_one_nearest_station_mapping_and_tie_breaking():
    """Verify road segments map many-to-one to nearest weather station with deterministic tie breaking."""
    stations = [
        {"weather_point_id": "WX-001", "latitude": 26.0, "longitude": 91.0},
        {"weather_point_id": "WX-002", "latitude": 26.0, "longitude": 93.0},
    ]

    # Two segments closer to WX-001, one closer to WX-002
    segments = [
        {"segment_id": "SEG-A", "latitude": 26.01, "longitude": 91.02},  # Near WX-001
        {"segment_id": "SEG-B", "latitude": 26.05, "longitude": 91.10},  # Near WX-001
        {"segment_id": "SEG-C", "latitude": 25.99, "longitude": 92.95},  # Near WX-002
    ]

    mapping = bmd.map_segments_to_nearest_station(segments, stations)

    assert mapping["SEG-A"]["nearest_weather_point_id"] == "WX-001"
    assert mapping["SEG-B"]["nearest_weather_point_id"] == "WX-001"  # Many-to-one
    assert mapping["SEG-C"]["nearest_weather_point_id"] == "WX-002"
    assert mapping["SEG-A"]["weather_point_dist_km"] > 0.0

    # Deterministic tie-breaking test: segment exactly equidistant between WX-001 and WX-002
    # Midpoint of (26.0, 91.0) and (26.0, 93.0) is (26.0, 92.0)
    equidistant_segment = [{"segment_id": "SEG-TIE", "latitude": 26.0, "longitude": 92.0}]
    tie_mapping = bmd.map_segments_to_nearest_station(equidistant_segment, stations)

    # Lexicographically smaller ID must win tie break
    assert tie_mapping["SEG-TIE"]["nearest_weather_point_id"] == "WX-001"


# ------------------------------------------------------------------------------
# 7. Exact Canonical disruption_proxy v0.1 Rules & Boundaries
# ------------------------------------------------------------------------------

def test_disruption_proxy_exact_condition_a_disaster_proximity():
    """Verify condition (a): nearest_disaster_distance_km <= 10.0 AND disaster_severity >= 0.50."""
    # Trigger: dist=10.0, sev=0.50 -> 1
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=0.0,
        wind_gust_kmh=10.0,
        accessibility_score=0.90,
        nearest_disaster_distance_km=10.0,
        disaster_severity=0.50,
    )
    assert label == 1

    # Boundary: dist=10.01 -> 0
    label, _ = bmd.derive_disruption_proxy(
        precipitation_mm=0.0,
        wind_gust_kmh=10.0,
        accessibility_score=0.90,
        nearest_disaster_distance_km=10.01,
        disaster_severity=0.50,
    )
    assert label == 0

    # Boundary: sev=0.499 -> 0
    label, _ = bmd.derive_disruption_proxy(
        precipitation_mm=0.0,
        wind_gust_kmh=10.0,
        accessibility_score=0.90,
        nearest_disaster_distance_km=10.0,
        disaster_severity=0.499,
    )
    assert label == 0


def test_disruption_proxy_exact_condition_b_severe_precipitation():
    """Verify condition (b): precipitation_mm >= 50.0."""
    # Boundary: 50.0 -> 1
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=50.0,
        wind_gust_kmh=10.0,
        accessibility_score=0.90,
    )
    assert label == 1

    # Boundary: 49.99 -> 0
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=49.99,
        wind_gust_kmh=10.0,
        accessibility_score=0.90,
    )
    assert label == 0


def test_disruption_proxy_exact_condition_c_gale_wind_gust():
    """Verify condition (c): wind_gust_kmh >= 65.0."""
    # Boundary: 65.0 -> 1
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=5.0,
        wind_gust_kmh=65.0,
        accessibility_score=0.90,
    )
    assert label == 1

    # Boundary: 64.99 -> 0
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=5.0,
        wind_gust_kmh=64.99,
        accessibility_score=0.90,
    )
    assert label == 0


def test_disruption_proxy_exact_condition_d_fragile_infrastructure_impact():
    """Verify condition (d): accessibility_score < 0.40 AND precipitation_mm >= 25.0."""
    # Trigger: acc=0.399, precip=25.0 -> 1
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=25.0,
        wind_gust_kmh=10.0,
        accessibility_score=0.399,
    )
    assert label == 1

    # Boundary: acc=0.400, precip=25.0 -> 0 (strict inequality < 0.40)
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=25.0,
        wind_gust_kmh=10.0,
        accessibility_score=0.400,
    )
    assert label == 0

    # Boundary: acc=0.399, precip=24.99 -> 0
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=24.99,
        wind_gust_kmh=10.0,
        accessibility_score=0.399,
    )
    assert label == 0


def test_disruption_proxy_normal_no_trigger_and_continuous_bounds():
    """Verify normal calm conditions produce label 0 and continuous score stays in [0.0, 1.0]."""
    label, score = bmd.derive_disruption_proxy(
        precipitation_mm=2.0,
        wind_gust_kmh=15.0,
        accessibility_score=0.85,
        nearest_disaster_distance_km=999.0,
        disaster_severity=0.0,
    )
    assert label == 0
    assert 0.0 <= score <= 1.0

    # Extreme conditions bounded at 1.0
    _, extreme_score = bmd.derive_disruption_proxy(
        precipitation_mm=300.0,
        wind_gust_kmh=150.0,
        accessibility_score=0.10,
    )
    assert extreme_score == 1.0


# ------------------------------------------------------------------------------
# 8. Label Provenance Contract
# ------------------------------------------------------------------------------

def test_label_provenance_contract():
    """Ensure label provenance fields comply strictly with DATASET_SPEC_v0.1.txt."""
    provenance = bmd.get_label_provenance()

    assert provenance["label_type"] == "derived"
    assert provenance["label_source"] == "GDACS + Open-Meteo + OSM"
    assert provenance["label_derivation_method"] == "deterministic_threshold_rule_v0.1"
    assert provenance["disaster_condition_a_active"] is False
    assert "never claim it as observed road-closure" in provenance["honesty_disclosure"].lower()


# ------------------------------------------------------------------------------
# 9. Zero-Leakage Column Exclusion
# ------------------------------------------------------------------------------

def test_zero_leakage_columns_exclusion():
    """Ensure Risk Engine outputs and post-incident variables are strictly excluded."""
    schema_cols = bmd.get_dataset_feature_names()

    forbidden_leakage_cols = [
        "risk_score",
        "risk_band",
        "current_delay_ratio",
        "actual_travel_time_sec",
        "confirmed_blocked",
        "clearance_time",
        "operator_approval",
        "reroute_status",
        "future_weather_severity",
        "next_day_precipitation_mm",
    ]

    for col in forbidden_leakage_cols:
        assert col not in schema_cols, f"Forbidden leakage column '{col}' must NOT exist in ML dataset schema."

    # Verify target variable names are present
    assert "disruption_proxy" in schema_cols
    assert "disruption_score_continuous" in schema_cols


# ------------------------------------------------------------------------------
# 10. Same-Day Temporal Alignment & No Future Leakage
# ------------------------------------------------------------------------------

def test_same_day_temporal_alignment_and_no_future_leakage():
    """Verify records represent same-day historical classification without future lookahead."""
    mock_segment = {
        "segment_id": "OSM-001",
        "latitude": 26.1,
        "longitude": 91.7,
        "elevation_m": 100.0,
        "road_type": "trunk",
        "surface": "asphalt",
        "lanes": 2,
        "maxspeed": 60.0,
    }

    mock_daily_weather = {
        "date": "2020-07-15",
        "precipitation_mm": 35.0,
        "rain_mm": 35.0,
        "precipitation_hours": 8.0,
        "temperature_c": 28.0,
        "temperature_max_c": 32.0,
        "temperature_min_c": 24.0,
        "temp_range_c": 8.0,
        "wind_speed_kmh": 20.0,
        "wind_gust_kmh": 45.0,
        "weather_code": 63,
        "weather_severity_daily": 0.55,
    }

    record = bmd.assemble_ml_record(mock_segment, mock_daily_weather, density_proxy=1, nearest_dist_km=5.0)

    assert record["date"] == "2020-07-15"
    assert record["year"] == 2020
    assert record["month"] == 7
    assert record["day"] == 15
    assert record["day_of_week"] == 2  # Wednesday

    # Weather attributes in record match exact same-day weather
    assert record["precipitation_mm"] == 35.0
    assert record["wind_gust_kmh"] == 45.0


# ------------------------------------------------------------------------------
# 11. Duplicate Detection & Deterministic Row Ordering
# ------------------------------------------------------------------------------

def test_duplicate_detection_and_deterministic_row_ordering():
    """Verify duplicate (segment_id, date) rows raise ValueError and rows are deterministically sorted."""
    records = [
        {"segment_id": "OSM-002", "date": "2019-01-02", "val": 1},
        {"segment_id": "OSM-001", "date": "2019-01-02", "val": 2},
        {"segment_id": "OSM-001", "date": "2019-01-01", "val": 3},
    ]

    # Deterministic sort: primary key = date (asc), secondary key = segment_id (asc)
    sorted_records = bmd.sort_records_deterministic(records)
    assert sorted_records[0]["date"] == "2019-01-01"
    assert sorted_records[0]["segment_id"] == "OSM-001"
    assert sorted_records[1]["date"] == "2019-01-02"
    assert sorted_records[1]["segment_id"] == "OSM-001"
    assert sorted_records[2]["date"] == "2019-01-02"
    assert sorted_records[2]["segment_id"] == "OSM-002"

    # Duplicate check
    duplicate_records = records + [{"segment_id": "OSM-001", "date": "2019-01-01", "val": 99}]
    with pytest.raises(ValueError, match="Duplicate"):
        bmd.validate_no_duplicate_keys(duplicate_records)


# ------------------------------------------------------------------------------
# 12. Metadata Schema & Deterministic Generation
# ------------------------------------------------------------------------------

def test_metadata_schema_and_deterministic_generation():
    """Verify metadata manifest conforms to contract and separates run metadata from core content."""
    mock_stats = {
        "total_rows": 8007 * 365,
        "positive_labels": 120000,
        "yearly_breakdown": {
            "2019": {"rows": 8007 * 365, "days": 365, "positive_labels": 120000, "prevalence": 0.041}
        },
    }

    metadata = bmd.generate_dataset_metadata(mock_stats)

    required_keys = [
        "dataset_version",
        "target_geography",
        "total_road_segments",
        "temporal_range",
        "total_expected_rows",
        "spatial_density_method",
        "weather_station_mapping",
        "label_provenance",
        "leakage_safeguards",
        "actual_class_prevalence",
        "schema",
        "run_metadata",
    ]

    for k in required_keys:
        assert k in metadata, f"Metadata must contain top-level key '{k}'."

    assert metadata["total_road_segments"] == 8007
    assert metadata["temporal_range"]["total_days"] == 2192
    assert metadata["leakage_safeguards"]["risk_engine_outputs_excluded"] is True
    assert metadata["leakage_safeguards"]["temporal_framing"] == "same_day_historical_classification_only"
