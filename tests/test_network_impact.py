"""Tests for SETU Network Impact Engine v0.1.

Verification of deterministic spatial impact assessment, haversine calculation,
point-to-segment distance, radius boundary inclusion, zero-radius queries,
deterministic sorting, validation errors, and metadata preservation.
"""

import math
import pytest

from src.impact.network_impact import (
    NetworkImpactValidationError,
    assess_network_impact,
    find_affected_segments,
    haversine_km,
    point_to_segment_distance_km,
    EARTH_RADIUS_KM,
)


@pytest.fixture
def base_incident():
    """Standard valid field incident in Guwahati-Imphal corridor."""
    return {
        "latitude": 26.1500,
        "longitude": 91.7500,
        "incident_type": "landslide",
        "severity": 0.85,
        "impact_radius_km": 5.0,
    }


@pytest.fixture
def synthetic_segments():
    """Synthetic in-memory road segments with various distances and geometries."""
    return [
        # Segment 1: Directly through the incident point (start: (26.1400, 91.7500), end: (26.1600, 91.7500))
        {
            "segment_id": "SEG-EXACT-001",
            "osm_id": 1001,
            "start_latitude": 26.1400,
            "start_longitude": 91.7500,
            "end_latitude": 26.1600,
            "end_longitude": 91.7500,
            "latitude": 26.1500,
            "longitude": 91.7500,
            "road_type": "primary",
            "name": "Guwahati Expressway",
            "segment_length_km": 2.22,
        },
        # Segment 2: Close nearby, approx 1.5 km east
        {
            "segment_id": "SEG-CLOSE-002",
            "osm_id": 1002,
            "start_latitude": 26.1450,
            "start_longitude": 91.7650,
            "end_latitude": 26.1550,
            "end_longitude": 91.7650,
            "latitude": 26.1500,
            "longitude": 91.7650,
            "road_type": "secondary",
            "name": "East Link Road",
            "segment_length_km": 1.11,
        },
        # Segment 3: Further out, approx 3.5 km south
        {
            "segment_id": "SEG-MID-003",
            "osm_id": 1003,
            "start_latitude": 26.1180,
            "start_longitude": 91.7500,
            "end_latitude": 26.1200,
            "end_longitude": 91.7500,
            "latitude": 26.1190,
            "longitude": 91.7500,
            "road_type": "trunk",
            "name": "Southern Bypass",
            "segment_length_km": 0.22,
        },
        # Segment 4: Far away, approx 25 km north (definitely outside 5 km radius)
        {
            "segment_id": "SEG-FAR-004",
            "osm_id": 1004,
            "start_latitude": 26.3800,
            "start_longitude": 91.7500,
            "end_latitude": 26.4000,
            "end_longitude": 91.7500,
            "latitude": 26.3900,
            "longitude": 91.7500,
            "road_type": "motorway",
            "name": "North Trunk Highway",
            "segment_length_km": 2.22,
        },
    ]


# ==============================================================================
# Haversine and Point-to-Segment Calculation Tests
# ==============================================================================
def test_haversine_identical_points():
    """Distance between identical coordinates must be exactly 0.0."""
    dist = haversine_km(26.1500, 91.7500, 26.1500, 91.7500)
    assert dist == 0.0


def test_haversine_known_distance():
    """Verify haversine distance for known coordinates (1 degree latitude is approx 111.19 km)."""
    dist = haversine_km(0.0, 0.0, 1.0, 0.0)
    expected_km = (math.pi / 180.0) * EARTH_RADIUS_KM
    assert math.isclose(dist, expected_km, rel_tol=1e-5)


def test_point_to_segment_distance_on_segment():
    """A point exactly on the segment line must return distance 0.0."""
    dist = point_to_segment_distance_km(
        p_lat=26.1500,
        p_lon=91.7500,
        start_lat=26.1400,
        start_lon=91.7500,
        end_lat=26.1600,
        end_lon=91.7500,
    )
    assert math.isclose(dist, 0.0, abs_tol=1e-6)


def test_point_to_segment_distance_closest_to_start_or_end():
    """Points beyond segment endpoints must project to the respective endpoint."""
    # Point is further south than start point
    dist_start = point_to_segment_distance_km(
        p_lat=26.1300,
        p_lon=91.7500,
        start_lat=26.1400,
        start_lon=91.7500,
        end_lat=26.1600,
        end_lon=91.7500,
    )
    expected = haversine_km(26.1300, 91.7500, 26.1400, 91.7500)
    assert math.isclose(dist_start, expected, rel_tol=1e-4)

    # Point is further north than end point
    dist_end = point_to_segment_distance_km(
        p_lat=26.1700,
        p_lon=91.7500,
        start_lat=26.1400,
        start_lon=91.7500,
        end_lat=26.1600,
        end_lon=91.7500,
    )
    expected_end = haversine_km(26.1700, 91.7500, 26.1600, 91.7500)
    assert math.isclose(dist_end, expected_end, rel_tol=1e-4)


def test_point_to_segment_perpendicular():
    """Perpendicular distance to segment is shorter than distance to endpoints or midpoint."""
    # Segment runs East-West along lat 26.1500 from lon 91.7000 to 91.8000
    # Incident is at (26.1550, 91.7500) (directly north of middle of segment)
    p_lat, p_lon = 26.1550, 91.7500
    s_lat, s_lon = 26.1500, 91.7000
    e_lat, e_lon = 26.1500, 91.8000

    segment_dist = point_to_segment_distance_km(p_lat, p_lon, s_lat, s_lon, e_lat, e_lon)
    dist_to_start = haversine_km(p_lat, p_lon, s_lat, s_lon)
    dist_to_end = haversine_km(p_lat, p_lon, e_lat, e_lon)

    assert segment_dist < dist_to_start
    assert segment_dist < dist_to_end
    # The closest point on the segment is (26.1500, 91.7500)
    expected = haversine_km(p_lat, p_lon, 26.1500, 91.7500)
    assert math.isclose(segment_dist, expected, rel_tol=1e-4)


# ==============================================================================
# Basic Execution and Output Structure
# ==============================================================================
def test_valid_network_impact_assessment(base_incident, synthetic_segments):
    """Assess impact with valid inputs and verify standard return structure."""
    result = assess_network_impact(base_incident, synthetic_segments)

    assert isinstance(result, dict)
    assert "incident" in result
    assert "impact_radius_km" in result
    assert "affected_segment_count" in result
    assert "affected_segment_ids" in result
    assert "affected_segments" in result

    assert result["impact_radius_km"] == 5.0
    # Segments 1, 2, 3 should be within 5km, Segment 4 (25km away) excluded
    assert result["affected_segment_count"] == 3
    assert result["affected_segment_ids"] == ["SEG-EXACT-001", "SEG-CLOSE-002", "SEG-MID-003"]
    assert "SEG-FAR-004" not in result["affected_segment_ids"]


def test_alias_find_affected_segments(base_incident, synthetic_segments):
    """Verify that find_affected_segments alias behaves identically to assess_network_impact."""
    res1 = assess_network_impact(base_incident, synthetic_segments)
    res2 = find_affected_segments(base_incident, synthetic_segments)
    assert res1 == res2


# ==============================================================================
# Zero-Radius Query & Exact Match
# ==============================================================================
def test_zero_radius_query_exact_match(base_incident, synthetic_segments):
    """A zero-radius query is valid and must include only segments with distance_km == 0.0."""
    zero_incident = dict(base_incident)
    zero_incident["impact_radius_km"] = 0.0

    result = assess_network_impact(zero_incident, synthetic_segments)

    assert result["impact_radius_km"] == 0.0
    assert result["affected_segment_count"] == 1
    assert result["affected_segment_ids"] == ["SEG-EXACT-001"]
    assert result["affected_segments"][0]["distance_km"] == 0.0


def test_zero_radius_query_no_match(base_incident, synthetic_segments):
    """A zero-radius query returns 0 segments if no segment intersects the incident point."""
    zero_incident = dict(base_incident)
    zero_incident["latitude"] = 26.9999
    zero_incident["longitude"] = 91.9999
    zero_incident["impact_radius_km"] = 0.0

    result = assess_network_impact(zero_incident, synthetic_segments)

    assert result["affected_segment_count"] == 0
    assert result["affected_segment_ids"] == []
    assert result["affected_segments"] == []


# ==============================================================================
# Radius Boundary Inclusion & Exclusion
# ==============================================================================
def test_radius_boundary_inclusion_and_exclusion():
    """Verify segment exactly on radius is included, and segment just outside is excluded."""
    inc_lat, inc_lon = 26.0000, 91.0000
    # Create segment 1 at distance D
    # 0.045 degrees lat is approximately 5.003 km
    # Let's compute exact coordinate for 5.0 km
    deg_per_km = 1.0 / ((math.pi / 180.0) * EARTH_RADIUS_KM)
    delta_lat_5km = 5.0 * deg_per_km

    # Boundary segment exactly at 5.0 km
    boundary_segment = {
        "segment_id": "SEG-ON-BOUNDARY",
        "latitude": inc_lat + delta_lat_5km,
        "longitude": inc_lon,
    }
    # Slightly outside segment (5.001 km)
    outside_segment = {
        "segment_id": "SEG-OUTSIDE",
        "latitude": inc_lat + delta_lat_5km + (0.01 * deg_per_km),
        "longitude": inc_lon,
    }
    # Slightly inside segment (4.999 km)
    inside_segment = {
        "segment_id": "SEG-INSIDE",
        "latitude": inc_lat + delta_lat_5km - (0.01 * deg_per_km),
        "longitude": inc_lon,
    }

    incident = {
        "latitude": inc_lat,
        "longitude": inc_lon,
        "incident_type": "flooding",
        "severity": 0.5,
        "impact_radius_km": 5.0,
    }

    result = assess_network_impact(incident, [outside_segment, inside_segment, boundary_segment])
    ids = result["affected_segment_ids"]

    assert "SEG-INSIDE" in ids
    assert "SEG-ON-BOUNDARY" in ids
    assert "SEG-OUTSIDE" not in ids


# ==============================================================================
# Deterministic Ordering
# ==============================================================================
def test_deterministic_sorting():
    """Verify sorting by distance ascending, then segment_id ascending for ties."""
    incident = {
        "latitude": 26.0000,
        "longitude": 91.0000,
        "incident_type": "blockade",
        "severity": 0.9,
        "impact_radius_km": 10.0,
    }

    # Three segments: two at the identical distance (tie), one closer
    deg_per_km = 1.0 / ((math.pi / 180.0) * EARTH_RADIUS_KM)
    segments = [
        # Tied at distance 3.0 km, but with ID "SEG-Z"
        {
            "segment_id": "SEG-Z",
            "latitude": 26.0 + 3.0 * deg_per_km,
            "longitude": 91.0,
        },
        # Closest at distance 1.0 km
        {
            "segment_id": "SEG-CLOSE",
            "latitude": 26.0 + 1.0 * deg_per_km,
            "longitude": 91.0,
        },
        # Tied at distance 3.0 km, but with ID "SEG-A"
        {
            "segment_id": "SEG-A",
            "latitude": 26.0 - 3.0 * deg_per_km,
            "longitude": 91.0,
        },
    ]

    result = assess_network_impact(incident, segments)
    assert result["affected_segment_ids"] == ["SEG-CLOSE", "SEG-A", "SEG-Z"]


# ==============================================================================
# Metadata Preservation
# ==============================================================================
def test_metadata_preservation(base_incident, synthetic_segments):
    """Verify that road metadata (name, surface, length, road_type, etc.) is preserved."""
    result = assess_network_impact(base_incident, synthetic_segments)
    exact_seg = next(s for s in result["affected_segments"] if s["segment_id"] == "SEG-EXACT-001")

    assert exact_seg["name"] == "Guwahati Expressway"
    assert exact_seg["road_type"] == "primary"
    assert exact_seg["osm_id"] == 1001
    assert exact_seg["segment_length_km"] == 2.22
    assert "distance_km" in exact_seg


# ==============================================================================
# Empty Result
# ==============================================================================
def test_empty_result_when_no_segments_in_radius(base_incident):
    """Empty segment list or far away segments produce 0 count and empty arrays."""
    res_empty = assess_network_impact(base_incident, [])
    assert res_empty["affected_segment_count"] == 0
    assert res_empty["affected_segment_ids"] == []
    assert res_empty["affected_segments"] == []

    far_segments = [
        {
            "segment_id": "FAR-1",
            "latitude": 50.0,
            "longitude": 10.0,
        }
    ]
    res_far = assess_network_impact(base_incident, far_segments)
    assert res_far["affected_segment_count"] == 0
    assert res_far["affected_segment_ids"] == []
    assert res_far["affected_segments"] == []


# ==============================================================================
# Input Validation & Missing Fields
# ==============================================================================
@pytest.mark.parametrize("missing_field", ["latitude", "longitude", "incident_type", "severity", "impact_radius_km"])
def test_missing_incident_field_raises_error(base_incident, synthetic_segments, missing_field):
    """Missing any required incident field must raise NetworkImpactValidationError."""
    incomplete = dict(base_incident)
    del incomplete[missing_field]

    with pytest.raises(NetworkImpactValidationError) as exc_info:
        assess_network_impact(incomplete, synthetic_segments)
    assert "Missing required incident fields" in str(exc_info.value)
    assert missing_field in str(exc_info.value)


def test_none_incident_field_raises_error(base_incident, synthetic_segments):
    """Passing None for a required field must raise NetworkImpactValidationError."""
    inc = dict(base_incident)
    inc["severity"] = None

    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(inc, synthetic_segments)


@pytest.mark.parametrize(
    "invalid_radius",
    [-1.0, -0.001, float("nan"), float("inf"), "five", True]
)
def test_invalid_radius_raises_error(base_incident, synthetic_segments, invalid_radius):
    """Negative, non-numeric, or non-finite radii must raise NetworkImpactValidationError."""
    inc = dict(base_incident)
    inc["impact_radius_km"] = invalid_radius

    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(inc, synthetic_segments)


@pytest.mark.parametrize(
    "invalid_coord,field",
    [(-91.0, "latitude"), (91.0, "latitude"), (-181.0, "longitude"), (181.0, "longitude")]
)
def test_invalid_coordinates_raises_error(base_incident, synthetic_segments, invalid_coord, field):
    """Coordinates outside valid geographic range must raise NetworkImpactValidationError."""
    inc = dict(base_incident)
    inc[field] = invalid_coord

    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(inc, synthetic_segments)


@pytest.mark.parametrize("invalid_severity", [-0.1, 1.1, float("nan"), "high", True])
def test_invalid_severity_raises_error(base_incident, synthetic_segments, invalid_severity):
    """Severity outside [0.0, 1.0] or non-numeric must raise NetworkImpactValidationError."""
    inc = dict(base_incident)
    inc["severity"] = invalid_severity

    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(inc, synthetic_segments)


def test_invalid_incident_type_raises_error(base_incident, synthetic_segments):
    """Empty string or non-string incident type must raise NetworkImpactValidationError."""
    inc_empty = dict(base_incident)
    inc_empty["incident_type"] = "   "
    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(inc_empty, synthetic_segments)

    inc_num = dict(base_incident)
    inc_num["incident_type"] = 123
    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(inc_num, synthetic_segments)


def test_invalid_segment_record_raises_error(base_incident):
    """Segments missing segment_id or coordinate geometry must raise NetworkImpactValidationError."""
    # Missing segment_id
    with pytest.raises(NetworkImpactValidationError) as exc:
        assess_network_impact(base_incident, [{"latitude": 26.0, "longitude": 91.0}])
    assert "segment_id" in str(exc.value)

    # Missing coordinates
    with pytest.raises(NetworkImpactValidationError) as exc:
        assess_network_impact(base_incident, [{"segment_id": "SEG-BAD"}])
    assert "must provide either endpoint coordinates" in str(exc.value)

    # Non-mapping segment
    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(base_incident, ["not_a_dict"])


@pytest.mark.parametrize(
    "invalid_segment",
    [
        {"segment_id": "S1", "latitude": 95.0, "longitude": 91.0},
        {"segment_id": "S2", "latitude": -95.0, "longitude": 91.0},
        {"segment_id": "S3", "latitude": 26.0, "longitude": 185.0},
        {"segment_id": "S4", "latitude": 26.0, "longitude": -185.0},
        {"segment_id": "S5", "start_latitude": 92.0, "start_longitude": 91.0, "end_latitude": 26.0, "end_longitude": 91.0},
        {"segment_id": "S6", "start_latitude": 26.0, "start_longitude": 190.0, "end_latitude": 26.0, "end_longitude": 91.0},
        {"segment_id": "S7", "start_latitude": 26.0, "start_longitude": 91.0, "end_latitude": -92.0, "end_longitude": 91.0},
        {"segment_id": "S8", "start_latitude": 26.0, "start_longitude": 91.0, "end_latitude": 26.0, "end_longitude": -190.0},
    ]
)
def test_invalid_segment_coordinates_range_raises_error(base_incident, invalid_segment):
    """Segment coordinates outside valid geographic range must raise NetworkImpactValidationError."""
    with pytest.raises(NetworkImpactValidationError):
        assess_network_impact(base_incident, [invalid_segment])


def test_segment_without_midpoint_derives_midpoint_accurately(base_incident):
    """Endpoints-only segments derive accurate midpoints without falling back to 0.0."""
    seg = {
        "segment_id": "SEG-NO-MIDPOINT",
        "start_latitude": 26.1400,
        "start_longitude": 91.7400,
        "end_latitude": 26.1600,
        "end_longitude": 91.7600,
    }
    result = assess_network_impact(base_incident, [seg])
    assert result["affected_segment_count"] == 1
    affected = result["affected_segments"][0]
    assert math.isclose(affected["latitude"], 26.1500, abs_tol=1e-6)
    assert math.isclose(affected["longitude"], 91.7500, abs_tol=1e-6)
    assert affected["latitude"] != 0.0
    assert affected["longitude"] != 0.0



# ==============================================================================
# Determinism & Repeated Execution
# ==============================================================================
def test_deterministic_repeated_execution(base_incident, synthetic_segments):
    """Repeated execution must produce identical results across 100 runs."""
    baseline = assess_network_impact(base_incident, synthetic_segments)

    for _ in range(100):
        res = assess_network_impact(base_incident, synthetic_segments)
        assert res == baseline
        assert res["affected_segment_ids"] == baseline["affected_segment_ids"]
