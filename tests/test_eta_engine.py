"""Tests for SETU Deterministic ETA and Delay Engine v0.1.

Verification of deterministic baseline travel time, disruption adjustment,
absolute delay, uncapped delay ratio, normalized delay ratio (clamped for Risk Engine),
degenerate 0.0 km segments, conflicting disruption validation, vehicle profiles,
surface degradation modifiers, blocked segment penalties, route additivity,
explainability reasons, and immutability.
"""

import math
from types import MappingProxyType
import pytest

from src.eta.eta_engine import (
    DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS,
    DEFAULT_SPEED_LIMITS_KMH,
    DEFAULT_SURFACE_MODIFIERS,
    DEFAULT_VEHICLE_PROFILES,
    HONESTY_DISCLOSURE,
    MIN_SPEED_KMH,
    ETAEngineValidationError,
    estimate_route_eta,
    estimate_segment_eta,
)
from src.risk.risk_engine import calculate_risk


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def standard_segment():
    """Standard 50 km primary road segment in Assam."""
    return {
        "segment_id": "SEG-TEST-001",
        "road_type": "primary",
        "segment_length_km": 50.0,
        "name": "Guwahati Intercity Corridor",
    }


@pytest.fixture
def multi_segment_route():
    """A realistic 3-segment route: motorway -> primary -> secondary."""
    return [
        {
            "segment_id": "SEG-001",
            "road_type": "motorway",
            "segment_length_km": 40.0,
            "surface": "asphalt",
        },
        {
            "segment_id": "SEG-002",
            "road_type": "primary",
            "segment_length_km": 25.0,
            "surface": "paved",
        },
        {
            "segment_id": "SEG-003",
            "road_type": "secondary",
            "segment_length_km": 20.0,
            "surface": "unpaved",
        },
    ]


# ==============================================================================
# 1. Baseline ETA & Speed Hierarchy Tests
# ==============================================================================

@pytest.mark.parametrize(
    "road_type,length_km,expected_speed,expected_seconds",
    [
        ("motorway", 80.0, 80.0, 3600.0),
        ("trunk", 60.0, 60.0, 3600.0),
        ("primary", 50.0, 50.0, 3600.0),
        ("secondary", 40.0, 40.0, 3600.0),
        ("tertiary", 30.0, 30.0, 3600.0),
        ("unclassified", 25.0, 25.0, 3600.0),
        ("residential", 25.0, 25.0, 3600.0),
        ("other", 25.0, 25.0, 3600.0),
        ("custom_road_type", 25.0, 25.0, 3600.0),  # Falls back to other proxy
    ],
)
def test_road_type_baseline_speed_and_eta(road_type, length_km, expected_speed, expected_seconds):
    """Test road class design speed proxy matches the defined speed hierarchy."""
    seg = {
        "segment_id": f"SEG-{road_type}",
        "road_type": road_type,
        "segment_length_km": length_km,
    }
    res = estimate_segment_eta(seg)
    assert math.isclose(res["effective_base_speed_kmh"], expected_speed, rel_tol=1e-5)
    assert math.isclose(res["baseline_eta_seconds"], expected_seconds, rel_tol=1e-5)
    assert res["delay_seconds"] == 0.0
    assert res["delay_ratio"] == 0.0
    assert res["is_passable"] is True


def test_recorded_maxspeed_overrides_road_type():
    """Explicit recorded maxspeed must take precedence over the road class default."""
    seg = {
        "segment_id": "SEG-SPEED-LIMIT",
        "road_type": "primary",  # default would be 50 km/h
        "segment_length_km": 100.0,
        "maxspeed": 100.0,  # explicitly 100 km/h
    }
    res = estimate_segment_eta(seg)
    assert res["raw_base_speed_kmh"] == 100.0
    assert res["effective_base_speed_kmh"] == 100.0
    # 100 km at 100 km/h = 1 hour = 3600s
    assert math.isclose(res["baseline_eta_seconds"], 3600.0, rel_tol=1e-5)
    assert res["speed_source"] == "recorded_maxspeed_proxy"


@pytest.mark.parametrize(
    "maxspeed_input,expected_kmh",
    [
        ("60", 60.0),
        ("80 km/h", 80.0),
        ("40 KM/H", 40.0),
        ("50 mph", 50.0 * 1.60934),
        (75, 75.0),
        (75.5, 75.5),
    ],
)
def test_maxspeed_formats_parsing(maxspeed_input, expected_kmh):
    """Various string and numeric maxspeed formats must parse accurately."""
    seg = {
        "segment_id": "SEG-FORMATS",
        "road_type": "primary",
        "segment_length_km": 10.0,
        "maxspeed": maxspeed_input,
    }
    res = estimate_segment_eta(seg)
    assert math.isclose(res["raw_base_speed_kmh"], expected_kmh, rel_tol=1e-4)


# ==============================================================================
# 2. Surface Degradation Modifier Tests
# ==============================================================================

def test_unpaved_surface_penalty():
    """Unpaved surface applies 0.75 speed modifier and increases baseline ETA."""
    seg_paved = {
        "segment_id": "SEG-PAVED",
        "road_type": "primary",  # 50 km/h
        "segment_length_km": 50.0,
        "surface": "asphalt",
    }
    seg_unpaved = {
        "segment_id": "SEG-UNPAVED",
        "road_type": "primary",  # 50 * 0.75 = 37.5 km/h
        "segment_length_km": 50.0,
        "surface": "unpaved",
    }
    res_paved = estimate_segment_eta(seg_paved)
    res_unpaved = estimate_segment_eta(seg_unpaved)

    assert res_paved["effective_base_speed_kmh"] == 50.0
    assert res_unpaved["effective_base_speed_kmh"] == 37.5
    assert res_paved["baseline_eta_seconds"] == 3600.0
    # 50 km / 37.5 km/h = 1.3333 h = 4800s
    assert math.isclose(res_unpaved["baseline_eta_seconds"], 4800.0, rel_tol=1e-5)
    assert "UNPAVED_SURFACE_PENALTY" in res_unpaved["reason_codes"]


def test_intermediate_surface_penalty():
    """Compacted or cobblestone surface applies 0.90 speed modifier."""
    seg = {
        "segment_id": "SEG-COMPACTED",
        "road_type": "secondary",  # 40 * 0.90 = 36 km/h
        "segment_length_km": 36.0,
        "surface": "compacted",
    }
    res = estimate_segment_eta(seg)
    assert res["effective_base_speed_kmh"] == 36.0
    assert math.isclose(res["baseline_eta_seconds"], 3600.0, rel_tol=1e-5)


# ==============================================================================
# 3. Vehicle Profile Tests
# ==============================================================================

@pytest.mark.parametrize(
    "profile,expected_factor",
    [
        ("standard_truck", 1.00),
        ("heavy_truck", 0.85),
        ("light_commercial", 1.15),
        ("passenger", 1.25),
    ],
)
def test_vehicle_profile_speed_adjustment(standard_segment, profile, expected_factor):
    """Predefined vehicle profiles deterministically scale speed."""
    res = estimate_segment_eta(standard_segment, vehicle_profile=profile)
    expected_speed = 50.0 * expected_factor
    assert math.isclose(res["effective_base_speed_kmh"], expected_speed, rel_tol=1e-5)
    assert res["vehicle_profile"] == profile
    assert res["vehicle_speed_factor"] == expected_factor


def test_custom_vehicle_factor(standard_segment):
    """Custom positive speed factor can be provided."""
    res = estimate_segment_eta(standard_segment, vehicle_speed_factor=0.60)
    assert res["vehicle_profile"] == "custom"
    assert res["vehicle_speed_factor"] == 0.60
    # 50 * 0.60 = 30 km/h -> 50 km / 30 km/h = 1.6667h = 6000s
    assert math.isclose(res["baseline_eta_seconds"], 6000.0, rel_tol=1e-5)


def test_conflicting_vehicle_profile_and_custom_factor(standard_segment):
    """Conflicting vehicle profile and custom speed factor must raise error."""
    with pytest.raises(ETAEngineValidationError, match="Conflicting vehicle profile"):
        estimate_segment_eta(
            standard_segment,
            vehicle_profile="standard_truck",  # factor 1.0
            vehicle_speed_factor=0.50,         # conflicting
        )


# ==============================================================================
# 4. Degenerate 0.0 km Length & Endpoint Fallback Tests
# ==============================================================================

def test_degenerate_zero_length_segment():
    """0.0 km segment is valid and produces 0.0 baseline ETA and 0.0 delay."""
    seg = {
        "segment_id": "SEG-ZERO-KM",
        "road_type": "primary",
        "segment_length_km": 0.0,
    }
    res = estimate_segment_eta(seg)
    assert res["distance_km"] == 0.0
    assert res["baseline_eta_seconds"] == 0.0
    assert res["disrupted_eta_seconds"] == 0.0
    assert res["delay_seconds"] == 0.0
    assert res["delay_ratio"] == 0.0
    assert res["is_passable"] is True


def test_distance_derived_from_endpoints():
    """Distance is derived accurately using haversine from endpoint coordinates when length is omitted."""
    seg = {
        "segment_id": "SEG-COORDS",
        "road_type": "primary",
        "start_latitude": 26.0000,
        "start_longitude": 91.0000,
        "end_latitude": 26.0000,
        "end_longitude": 91.5000,  # ~50 km east along parallel
    }
    res = estimate_segment_eta(seg)
    assert res["distance_km"] > 40.0
    assert res["baseline_eta_seconds"] > 0.0


def test_zero_distance_from_identical_endpoints():
    """Identical start and end coordinates derive 0.0 distance and 0.0 ETA."""
    seg = {
        "segment_id": "SEG-SAME-COORDS",
        "road_type": "primary",
        "start_latitude": 26.1500,
        "start_longitude": 91.7500,
        "end_latitude": 26.1500,
        "end_longitude": 91.7500,
    }
    res = estimate_segment_eta(seg)
    assert res["distance_km"] == 0.0
    assert res["baseline_eta_seconds"] == 0.0
    assert res["delay_seconds"] == 0.0


# ==============================================================================
# 5. Disruption Representations & Math
# ==============================================================================

def test_disruption_factor_slowdown(standard_segment):
    """Disruption factor delta reduces speed by (1.0 - delta * 0.85)."""
    seg = dict(standard_segment)
    seg["disruption_factor"] = 0.50  # delta = 0.50 -> 1 - 0.425 = 0.575 factor
    res = estimate_segment_eta(seg)

    expected_speed = 50.0 * 0.575  # 28.75 km/h
    assert math.isclose(res["disrupted_speed_kmh"], expected_speed, rel_tol=1e-5)

    expected_disrupted_seconds = (50.0 / expected_speed) * 3600.0  # 6260.87s
    expected_delay = expected_disrupted_seconds - 3600.0            # 2660.87s
    assert math.isclose(res["disrupted_eta_seconds"], expected_disrupted_seconds, rel_tol=1e-4)
    assert math.isclose(res["delay_seconds"], expected_delay, rel_tol=1e-4)
    assert math.isclose(res["delay_ratio"], expected_delay / 3600.0, rel_tol=1e-4)
    assert res["is_passable"] is True
    assert "DISRUPTION_FACTOR_SLOWDOWN" in res["reason_codes"]


def test_speed_reduction_ratio_slowdown(standard_segment):
    """Speed reduction ratio reduces speed by (1.0 - ratio)."""
    seg = dict(standard_segment)
    seg["speed_reduction_ratio"] = 0.40  # 40% reduction -> speed is 50 * 0.60 = 30 km/h
    res = estimate_segment_eta(seg)

    assert math.isclose(res["disrupted_speed_kmh"], 30.0, rel_tol=1e-5)
    # 50 km / 30 km/h = 1.6667h = 6000s -> delay = 2400s
    assert math.isclose(res["disrupted_eta_seconds"], 6000.0, rel_tol=1e-4)
    assert math.isclose(res["delay_seconds"], 2400.0, rel_tol=1e-4)
    assert math.isclose(res["delay_ratio"], 2400.0 / 3600.0, rel_tol=1e-4)
    assert "SPEED_REDUCTION_SLOWDOWN" in res["reason_codes"]


def test_explicit_delay_seconds(standard_segment):
    """Explicit delay_seconds adds exact seconds to baseline ETA."""
    seg = dict(standard_segment)
    seg["delay_seconds"] = 1800.0  # 30 min extra delay
    res = estimate_segment_eta(seg)

    assert res["baseline_eta_seconds"] == 3600.0
    assert res["delay_seconds"] == 1800.0
    assert res["disrupted_eta_seconds"] == 5400.0
    assert math.isclose(res["delay_ratio"], 0.50, rel_tol=1e-5)
    assert "EXPLICIT_DELAY_ADDED" in res["reason_codes"]


def test_blocked_segment_penalty_constant(standard_segment):
    """Blocked segment applies DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS (7200s)."""
    seg = dict(standard_segment)
    seg["is_blocked"] = True
    res = estimate_segment_eta(seg)

    assert res["is_passable"] is False
    assert res["delay_seconds"] == DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS
    assert res["disrupted_eta_seconds"] == 3600.0 + DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS
    assert res["disrupted_speed_kmh"] == 0.0
    assert "SEGMENT_BLOCKED" in res["reason_codes"]


def test_disruption_factor_1_0_represents_blocked(standard_segment):
    """disruption_factor = 1.0 represents total blockage."""
    seg = dict(standard_segment)
    seg["disruption_factor"] = 1.0
    res = estimate_segment_eta(seg)

    assert res["is_passable"] is False
    assert res["delay_seconds"] == DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS
    assert "SEGMENT_BLOCKED" in res["reason_codes"]


# ==============================================================================
# 6. Conflicting Disruption Validation Tests
# ==============================================================================

@pytest.mark.parametrize(
    "conflicting_fields",
    [
        {"disruption_factor": 0.5, "speed_reduction_ratio": 0.3},
        {"disruption_factor": 0.5, "delay_seconds": 600.0},
        {"speed_reduction_ratio": 0.3, "delay_seconds": 600.0},
        {"disruption_factor": 0.5, "speed_reduction_ratio": 0.3, "delay_seconds": 600.0},
        {"is_blocked": True, "delay_seconds": 600.0},
        {"is_blocked": True, "disruption_factor": 0.5},
        {"is_blocked": False, "disruption_factor": 1.0},
    ],
)
def test_conflicting_disruption_representations_raise_error(standard_segment, conflicting_fields):
    """Supplying more than one disruption representation must raise ETAEngineValidationError."""
    seg = dict(standard_segment)
    seg.update(conflicting_fields)
    with pytest.raises(ETAEngineValidationError):
        estimate_segment_eta(seg)


# ==============================================================================
# 7. Route Aggregation & Risk Engine Integration Tests
# ==============================================================================

def test_route_eta_additivity(multi_segment_route):
    """Route totals must equal the exact sum of evaluated segment values."""
    # Give segment 2 some disruption
    multi_segment_route[1]["delay_seconds"] = 900.0

    route_res = estimate_route_eta(multi_segment_route)

    sum_dist = sum(s["distance_km"] for s in route_res["segments"])
    sum_base = sum(s["baseline_eta_seconds"] for s in route_res["segments"])
    sum_disrupted = sum(s["disrupted_eta_seconds"] for s in route_res["segments"])
    sum_delay = sum(s["delay_seconds"] for s in route_res["segments"])

    assert math.isclose(route_res["total_distance_km"], sum_dist, rel_tol=1e-5)
    assert math.isclose(route_res["baseline_eta_seconds"], sum_base, rel_tol=1e-5)
    assert math.isclose(route_res["disrupted_eta_seconds"], sum_disrupted, rel_tol=1e-5)
    assert math.isclose(route_res["delay_seconds"], sum_delay, rel_tol=1e-5)
    assert route_res["segment_count"] == 3
    assert route_res["disrupted_segment_count"] == 1
    assert route_res["is_passable"] is True


def test_delay_ratio_uncapped_vs_normalized(standard_segment):
    """delay_ratio can exceed 1.0, but normalized_delay_ratio is clamped to [0.0, 1.0]."""
    seg = dict(standard_segment)  # baseline = 3600s
    seg["delay_seconds"] = 7200.0  # delay is 2x baseline
    res = estimate_route_eta([seg])

    assert math.isclose(res["delay_ratio"], 2.0, rel_tol=1e-5)
    assert res["normalized_delay_ratio"] == 1.0


def test_normalized_delay_ratio_interoperability_with_risk_engine(multi_segment_route):
    """The normalized_delay_ratio output plugs directly into the SETU Risk Engine without error."""
    multi_segment_route[0]["delay_seconds"] = 1200.0
    eta_res = estimate_route_eta(multi_segment_route)

    # Pass the calculated normalized delay ratio directly to the Risk Engine
    risk_res = calculate_risk({
        "incident_severity": 0.50,
        "accessibility_score": 0.80,
        "weather_severity": 0.20,
        "road_condition_score": 0.90,
        "network_criticality": 0.40,
        "current_delay_ratio": eta_res["normalized_delay_ratio"],
    })

    assert 0.0 <= risk_res["risk_score"] <= 100.0
    assert risk_res["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_blocked_route_sets_impassable(multi_segment_route):
    """A route with one blocked segment is flagged is_passable = False."""
    multi_segment_route[2]["is_blocked"] = True
    res = estimate_route_eta(multi_segment_route)

    assert res["is_passable"] is False
    assert "ROUTE_IMPASSABLE" in res["reason_codes"]


def test_empty_route_evaluation():
    """Evaluating an empty route produces 0 distance, 0 ETA, 0 delay."""
    res = estimate_route_eta([])
    assert res["total_distance_km"] == 0.0
    assert res["baseline_eta_seconds"] == 0.0
    assert res["disrupted_eta_seconds"] == 0.0
    assert res["delay_seconds"] == 0.0
    assert res["delay_ratio"] == 0.0
    assert res["normalized_delay_ratio"] == 0.0
    assert res["segment_count"] == 0
    assert res["disrupted_segment_count"] == 0
    assert res["is_passable"] is True


# ==============================================================================
# 8. Validation Errors & Bad Inputs
# ==============================================================================

def test_missing_segment_id():
    """Missing or empty segment_id must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="segment_id"):
        estimate_segment_eta({"road_type": "primary", "segment_length_km": 10.0})


def test_missing_road_type():
    """Missing or empty road_type must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="road_type"):
        estimate_segment_eta({"segment_id": "S1", "segment_length_km": 10.0})


def test_negative_segment_length():
    """Negative segment length must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="non-negative"):
        estimate_segment_eta({"segment_id": "S1", "road_type": "primary", "segment_length_km": -5.0})


def test_missing_length_and_endpoints():
    """Segment with neither length nor valid coordinates must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="endpoint coordinates"):
        estimate_segment_eta({"segment_id": "S1", "road_type": "primary"})


def test_invalid_coordinates_range():
    """Invalid coordinate values must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="start_latitude"):
        estimate_segment_eta({
            "segment_id": "S1",
            "road_type": "primary",
            "start_latitude": 95.0,
            "start_longitude": 91.0,
            "end_latitude": 26.0,
            "end_longitude": 91.0,
        })


@pytest.mark.parametrize(
    "bad_disruption",
    [
        {"disruption_factor": -0.1},
        {"disruption_factor": 1.5},
        {"speed_reduction_ratio": -0.5},
        {"speed_reduction_ratio": 1.2},
        {"delay_seconds": -10.0},
    ],
)
def test_out_of_range_disruptions_raise_error(standard_segment, bad_disruption):
    """Out-of-range disruption values must raise ETAEngineValidationError."""
    seg = dict(standard_segment)
    seg.update(bad_disruption)
    with pytest.raises(ETAEngineValidationError):
        estimate_segment_eta(seg)


def test_non_mapping_segment():
    """Non-mapping segment input must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="mapping/dict"):
        estimate_segment_eta("not-a-dict")


def test_non_iterable_route_input():
    """Passing a non-iterable object as route segments must raise ETAEngineValidationError."""
    with pytest.raises(ETAEngineValidationError, match="Expected segments to be an iterable"):
        estimate_route_eta(12345)


def test_type_error_inside_route_iteration_is_not_masked():
    """TypeError occurring inside a generator must not be swallowed into ETAEngineValidationError."""
    def faulty_generator():
        yield {"segment_id": "S1", "road_type": "primary", "segment_length_km": 10.0}
        raise TypeError("Custom engine generator error")

    with pytest.raises(TypeError, match="Custom engine generator error"):
        estimate_route_eta(faulty_generator())


# ==============================================================================
# 9. Immutability, Policy Constants & Honesty Disclosure
# ==============================================================================

def test_immutable_mappings_and_constants():
    """Policy configurations must be immutable MappingProxyType instances."""
    assert isinstance(DEFAULT_SPEED_LIMITS_KMH, MappingProxyType)
    assert isinstance(DEFAULT_SURFACE_MODIFIERS, MappingProxyType)
    assert isinstance(DEFAULT_VEHICLE_PROFILES, MappingProxyType)

    with pytest.raises(TypeError):
        DEFAULT_SPEED_LIMITS_KMH["primary"] = 99.0  # type: ignore

    with pytest.raises(TypeError):
        DEFAULT_SURFACE_MODIFIERS["unpaved"] = 0.50  # type: ignore

    with pytest.raises(TypeError):
        DEFAULT_VEHICLE_PROFILES["heavy_truck"] = 0.50  # type: ignore

    assert DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS == 7200.0
    assert MIN_SPEED_KMH == 5.0


def test_honesty_disclosure_included_in_output(standard_segment):
    """Output contract must explicitly include the honesty disclosure string."""
    res = estimate_route_eta([standard_segment])
    assert res["honesty_disclosure"] == HONESTY_DISCLOSURE
    assert "OpenStreetMap" in res["honesty_disclosure"]
    assert "not observed real-world GPS probe traffic" in res["honesty_disclosure"]


# ==============================================================================
# 10. Determinism
# ==============================================================================

def test_deterministic_repeated_execution(multi_segment_route):
    """Repeated execution must produce identical results across 100 runs."""
    baseline = estimate_route_eta(multi_segment_route)
    for _ in range(100):
        run_res = estimate_route_eta(multi_segment_route)
        assert run_res == baseline
