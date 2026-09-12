"""Tests for SETU Road Accessibility Scorer v0.1.

Verification of deterministic infrastructure accessibility proxy scoring,
dynamic evidence normalization, missing-data transparency, boundary classifications,
monotonic factor behaviors, and input validation.
"""

import math
import pytest

from src.accessibility.accessibility_scorer import (
    AccessibilityValidationError,
    calculate_accessibility,
    score_segments,
    ACCESSIBILITY_WEIGHTS,
    LEVEL_HIGH_THRESHOLD,
    LEVEL_MEDIUM_THRESHOLD,
    LEVEL_LOW_THRESHOLD,
)


@pytest.fixture
def ideal_segment():
    """Ideal highway segment with optimal infrastructure attributes."""
    return {
        "segment_id": "SEG-IDEAL-001",
        "road_type": "motorway",
        "surface": "asphalt",
        "lanes": 4,
        "maxspeed": 100,
    }


@pytest.fixture
def minimal_segment():
    """Segment with only mandatory road_type, missing all optional attributes."""
    return {
        "segment_id": "SEG-MINIMAL-002",
        "road_type": "primary",
    }


# ==============================================================================
# Weight Configuration & Immutability
# ==============================================================================
def test_weights_sum_to_one():
    """Verify accessibility weights sum to 1.00."""
    total = sum(ACCESSIBILITY_WEIGHTS.values())
    assert math.isclose(total, 1.00, rel_tol=1e-9)
    assert ACCESSIBILITY_WEIGHTS["road_type"] == 0.50
    assert ACCESSIBILITY_WEIGHTS["surface"] == 0.25
    assert ACCESSIBILITY_WEIGHTS["lanes"] == 0.15
    assert ACCESSIBILITY_WEIGHTS["maxspeed"] == 0.10


def test_weights_are_immutable():
    """Verify that ACCESSIBILITY_WEIGHTS is a read-only mapping proxy."""
    with pytest.raises(TypeError):
        ACCESSIBILITY_WEIGHTS["road_type"] = 0.99  # type: ignore

    with pytest.raises(TypeError):
        ACCESSIBILITY_WEIGHTS["new_factor"] = 0.10  # type: ignore

    with pytest.raises(TypeError):
        del ACCESSIBILITY_WEIGHTS["road_type"]  # type: ignore


# ==============================================================================
# Ideal & Poor Accessibility Cases (Accurate Math)
# ==============================================================================
def test_ideal_high_accessibility(ideal_segment):
    """Motorway + asphalt + 4 lanes + 100 km/h must yield 1.0000 (HIGH)."""
    result = calculate_accessibility(ideal_segment)

    assert result["segment_id"] == "SEG-IDEAL-001"
    assert result["accessibility_score"] == 1.0000
    assert result["accessibility_level"] == "HIGH"
    assert set(result["evaluated_factors"]) == {"road_type", "surface", "lanes", "maxspeed"}
    assert result["missing_factors"] == []
    assert "HIGH_GRADE_HIGHWAY" in result["reason_codes"]
    assert "PAVED_SURFACE" in result["reason_codes"]
    assert "MULTI_LANE_CAPACITY" in result["reason_codes"]
    assert "HIGH_SPEED_DESIGN" in result["reason_codes"]


def test_tertiary_unpaved_single_lane_math():
    """Verify exact math for tertiary + unpaved + 1 lane + 30 km/h:
    
    0.40 * 0.50 + 0.20 * 0.25 + 0.35 * 0.15 + 0.35 * 0.10
    = 0.20 + 0.05 + 0.0525 + 0.035 = 0.3375 -> LOW (not CRITICAL).
    """
    segment = {
        "segment_id": "SEG-TERTIARY-POOR",
        "road_type": "tertiary",
        "surface": "unpaved",
        "lanes": 1,
        "maxspeed": 30,
    }
    result = calculate_accessibility(segment)

    assert math.isclose(result["accessibility_score"], 0.3375, abs_tol=1e-4)
    assert result["accessibility_score"] == 0.3375
    assert result["accessibility_level"] == "LOW"
    assert "TERTIARY_ROAD" in result["reason_codes"]
    assert "UNPAVED_SURFACE" in result["reason_codes"]
    assert "SINGLE_LANE_BOTTLENECK" in result["reason_codes"]
    assert "LOW_SPEED_CORRIDOR" in result["reason_codes"]


def test_worst_proxy_case_math():
    """Verify exact math for worst-case proxy: other/unclassified + unpaved + 1 lane + 30 km/h:
    
    0.25 * 0.50 + 0.20 * 0.25 + 0.35 * 0.15 + 0.35 * 0.10
    = 0.125 + 0.05 + 0.0525 + 0.035 = 0.2625 -> LOW (not CRITICAL).
    """
    segment = {
        "segment_id": "SEG-WORST-PROXY",
        "road_type": "unclassified",
        "surface": "dirt",
        "lanes": 1,
        "maxspeed": 20,
    }
    result = calculate_accessibility(segment)

    assert math.isclose(result["accessibility_score"], 0.2625, abs_tol=1e-4)
    assert result["accessibility_score"] == 0.2625
    assert result["accessibility_level"] == "LOW"
    assert "LOWER_TIER_ROAD" in result["reason_codes"]


# ==============================================================================
# Dynamic Evidence Normalization & Missing Data Transparency
# ==============================================================================
def test_missing_optional_attributes_normalized_over_available_evidence(minimal_segment):
    """When optional attributes are unrecorded, normalize strictly over observed weights.
    
    Primary road only:
    score = (0.50 * 0.75) / 0.50 = 0.7500.
    Missing attributes must be listed and not fabricated.
    """
    result = calculate_accessibility(minimal_segment)

    assert result["accessibility_score"] == 0.7500
    assert result["accessibility_level"] == "HIGH"
    assert result["evaluated_factors"] == ["road_type"]
    assert set(result["missing_factors"]) == {"surface", "lanes", "maxspeed"}
    assert "MISSING_SURFACE_DATA" in result["reason_codes"]
    assert "MISSING_LANES_DATA" in result["reason_codes"]
    assert "MISSING_MAXSPEED_DATA" in result["reason_codes"]


def test_partial_evidence_normalization():
    """Test segment with road_type and surface only (active weight 0.50 + 0.25 = 0.75).
    
    Secondary (0.60) + paved (1.00):
    raw_score = (0.50 * 0.60 + 0.25 * 1.00) / 0.75 = 0.55 / 0.75 = 0.7333.
    """
    segment = {
        "segment_id": "SEG-PARTIAL",
        "road_type": "secondary",
        "surface": "paved",
    }
    result = calculate_accessibility(segment)

    assert math.isclose(result["accessibility_score"], 0.7333, abs_tol=1e-4)
    assert result["accessibility_level"] == "MEDIUM"
    assert set(result["evaluated_factors"]) == {"road_type", "surface"}
    assert set(result["missing_factors"]) == {"lanes", "maxspeed"}


# ==============================================================================
# Monotonic Factor Progression
# ==============================================================================
def test_road_type_progression():
    """Higher highway hierarchy must strictly yield higher accessibility score."""
    hierarchy = ["motorway", "trunk", "primary", "secondary", "tertiary", "unclassified"]
    scores = [
        calculate_accessibility({"segment_id": f"SEG-{rt}", "road_type": rt})["accessibility_score"]
        for rt in hierarchy
    ]
    # Verify strictly decreasing
    for i in range(len(scores) - 1):
        assert scores[i] > scores[i + 1]


def test_surface_progression():
    """Paved > intermediate > unpaved surface."""
    base = {"segment_id": "SEG", "road_type": "secondary"}
    paved_score = calculate_accessibility({**base, "surface": "asphalt"})["accessibility_score"]
    inter_score = calculate_accessibility({**base, "surface": "compacted"})["accessibility_score"]
    unpaved_score = calculate_accessibility({**base, "surface": "gravel"})["accessibility_score"]

    assert paved_score > inter_score > unpaved_score


def test_lanes_progression():
    """More lanes must yield higher accessibility score."""
    base = {"segment_id": "SEG", "road_type": "primary"}
    l4 = calculate_accessibility({**base, "lanes": 4})["accessibility_score"]
    l3 = calculate_accessibility({**base, "lanes": 3})["accessibility_score"]
    l2 = calculate_accessibility({**base, "lanes": 2})["accessibility_score"]
    l1 = calculate_accessibility({**base, "lanes": 1})["accessibility_score"]

    assert l4 > l3 > l2 > l1


def test_maxspeed_progression():
    """Higher design speed must yield higher accessibility score."""
    base = {"segment_id": "SEG", "road_type": "trunk"}
    s100 = calculate_accessibility({**base, "maxspeed": 100})["accessibility_score"]
    s70 = calculate_accessibility({**base, "maxspeed": 70})["accessibility_score"]
    s50 = calculate_accessibility({**base, "maxspeed": 50})["accessibility_score"]
    s30 = calculate_accessibility({**base, "maxspeed": 30})["accessibility_score"]

    assert s100 > s70 > s50 > s30


# ==============================================================================
# Boundary Classification
# ==============================================================================
@pytest.mark.parametrize(
    "score,expected_level",
    [
        (1.0000, "HIGH"),
        (0.7500, "HIGH"),
        (0.7499, "MEDIUM"),
        (0.5000, "MEDIUM"),
        (0.4999, "LOW"),
        (0.2500, "LOW"),
        (0.2499, "CRITICAL"),
        (0.1000, "CRITICAL"),
        (0.0000, "CRITICAL"),
    ],
)
def test_accessibility_level_boundaries(score, expected_level):
    """Verify boundary thresholds for HIGH, MEDIUM, LOW, and CRITICAL levels."""
    from src.accessibility.accessibility_scorer import _classify_accessibility_level
    assert _classify_accessibility_level(score) == expected_level


# ==============================================================================
# Bounds [0, 1] Verification
# ==============================================================================
def test_score_strictly_bounded_between_zero_and_one():
    """All combinations of road attributes must produce scores in [0.0, 1.0]."""
    road_types = ["motorway", "trunk", "primary", "secondary", "tertiary", "track"]
    surfaces = ["asphalt", "compacted", "dirt", None, ""]
    lanes_list = [1, 2, 4, 8, None, ""]
    speeds = [20, 50, 80, 120, None, ""]

    for rt in road_types:
        for surf in surfaces:
            for ln in lanes_list:
                for sp in speeds:
                    res = calculate_accessibility({
                        "segment_id": "TEST",
                        "road_type": rt,
                        "surface": surf,
                        "lanes": ln,
                        "maxspeed": sp,
                    })
                    assert 0.0 <= res["accessibility_score"] <= 1.0


# ==============================================================================
# Input Validation & Errors
# ==============================================================================
def test_missing_segment_id_raises_error():
    """Missing or empty segment_id must raise AccessibilityValidationError."""
    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility({"road_type": "primary"})

    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility({"segment_id": "   ", "road_type": "primary"})


def test_missing_road_type_raises_error():
    """Missing or empty road_type must raise AccessibilityValidationError."""
    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility({"segment_id": "S1"})

    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility({"segment_id": "S1", "road_type": "   "})


def test_non_mapping_segment_raises_error():
    """Non-dict / non-mapping input must raise AccessibilityValidationError."""
    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility(["not", "a", "dict"])


@pytest.mark.parametrize(
    "invalid_lanes",
    [0, -1, 1.5, 2.8, "1.5", "2.8", "invalid", True, float("nan"), float("inf")]
)
def test_invalid_lanes_raises_error(invalid_lanes):
    """Negative, zero, fractional, or unparseable lanes values must raise AccessibilityValidationError."""
    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility({"segment_id": "S1", "road_type": "primary", "lanes": invalid_lanes})


def test_integer_float_lanes_accepted():
    """Numeric floats or strings representing exact integers (e.g. 2.0, '2.0') must be accepted."""
    res_float = calculate_accessibility({"segment_id": "S1", "road_type": "primary", "lanes": 2.0})
    res_str_float = calculate_accessibility({"segment_id": "S1", "road_type": "primary", "lanes": "2.0"})
    res_int = calculate_accessibility({"segment_id": "S1", "road_type": "primary", "lanes": 2})

    assert res_float["accessibility_score"] == res_int["accessibility_score"]
    assert res_str_float["accessibility_score"] == res_int["accessibility_score"]


def test_maxspeed_reason_text_wording():
    """Verify maxspeed reason text describes recorded speed-limit proxy without claiming observed curvature or geometry."""
    res_80 = calculate_accessibility({"segment_id": "S1", "road_type": "primary", "maxspeed": 80})
    res_60 = calculate_accessibility({"segment_id": "S2", "road_type": "primary", "maxspeed": 65})
    res_40 = calculate_accessibility({"segment_id": "S3", "road_type": "primary", "maxspeed": 45})
    res_30 = calculate_accessibility({"segment_id": "S4", "road_type": "primary", "maxspeed": 30})

    assert "Recorded speed limit (80+ km/h) supports high-speed corridor accessibility" in res_80["reasons"]
    assert "Recorded speed limit (60-79 km/h) indicates standard regional highway speed capacity" in res_60["reasons"]
    assert "Recorded speed limit (40-59 km/h) reflects moderate speed restrictions on this segment" in res_40["reasons"]
    assert "Low recorded speed limit (<40 km/h) limits corridor flow rate and throughput" in res_30["reasons"]

    # Verify no unobserved geometry/curvature claims are made
    for res in [res_80, res_60, res_40, res_30]:
        combined_reasons = " ".join(res["reasons"]).lower()
        assert "curvature" not in combined_reasons
        assert "alignment" not in combined_reasons


@pytest.mark.parametrize("invalid_speed", [0, -10, "bad_speed", True, float("nan"), float("inf")])
def test_invalid_maxspeed_raises_error(invalid_speed):
    """Negative, zero, or unparseable maxspeed values must raise AccessibilityValidationError."""
    with pytest.raises(AccessibilityValidationError):
        calculate_accessibility({"segment_id": "S1", "road_type": "primary", "maxspeed": invalid_speed})


# ==============================================================================
# Determinism & Batch Scoring Helper
# ==============================================================================
def test_deterministic_repeated_execution(ideal_segment):
    """100 identical executions must yield identical results."""
    baseline = calculate_accessibility(ideal_segment)
    for _ in range(100):
        assert calculate_accessibility(ideal_segment) == baseline


def test_score_segments_batch_helper(ideal_segment, minimal_segment):
    """score_segments batch helper scores all segments in iterable."""
    batch = [ideal_segment, minimal_segment]
    results = score_segments(batch)
    assert len(results) == 2
    assert results[0]["segment_id"] == "SEG-IDEAL-001"
    assert results[1]["segment_id"] == "SEG-MINIMAL-002"

    with pytest.raises(AccessibilityValidationError):
        score_segments(None)
