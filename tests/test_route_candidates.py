"""Tests for SETU Route Candidate Generation v0.1 (Checkpoint 13).

Covers all 14 mandatory test areas from the Checkpoint 13 specification:
1. synthetic network with 3 distinct valid routes
2. K=1
3. K=3
4. deterministic repeated calls
5. blocked segment removes affected candidate
6. disconnected network
7. origin == destination
8. invalid coordinates
9. malformed segment data
10. invalid k
11. caller input is not mutated
12. route geometry is deterministic
13. segment metadata is preserved
14. bidirectional behavior is explicit/documented

Plus validation of empty networks, malformed blocked_segment_ids, and real OSM schema.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
import pytest

from src.routing import (
    RouteCandidateValidationError,
    generate_route_candidates,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def synthetic_3route_network() -> List[Dict[str, Any]]:
    """Synthetic diamond network guaranteed to offer at least 3 distinct simple routes.

    Topology:
        Origin: (26.000000, 91.000000) [Node N_26.000000_91.000000]
        Destination: (26.000000, 92.000000) [Node N_26.000000_92.000000]

    Paths:
        1. Center path (via (26.0, 91.5)):
           - SEG_C1 (10.0 km) + SEG_C2 (10.0 km) = 20.0 km
        2. Upper path (via (26.1, 91.5)):
           - SEG_U1 (12.0 km) + SEG_U2 (12.0 km) = 24.0 km
        3. Lower path (via (25.9, 91.5)):
           - SEG_L1 (15.0 km) + SEG_L2 (15.0 km) = 30.0 km
    """
    return [
        # Center path
        {
            "segment_id": "SEG_C1",
            "start_latitude": 26.000000,
            "start_longitude": 91.000000,
            "end_latitude": 26.000000,
            "end_longitude": 91.500000,
            "segment_length_km": 10.0,
            "road_type": "primary",
            "surface": "asphalt",
            "maxspeed": "60",
            "lanes": "2",
        },
        {
            "segment_id": "SEG_C2",
            "start_latitude": 26.000000,
            "start_longitude": 91.500000,
            "end_latitude": 26.000000,
            "end_longitude": 92.000000,
            "segment_length_km": 10.0,
            "road_type": "primary",
            "surface": "asphalt",
            "maxspeed": "60",
            "lanes": "2",
        },
        # Upper path
        {
            "segment_id": "SEG_U1",
            "start_latitude": 26.000000,
            "start_longitude": 91.000000,
            "end_latitude": 26.100000,
            "end_longitude": 91.500000,
            "segment_length_km": 12.0,
            "road_type": "secondary",
            "surface": "asphalt",
            "maxspeed": "50",
            "lanes": "2",
        },
        {
            "segment_id": "SEG_U2",
            "start_latitude": 26.100000,
            "start_longitude": 91.500000,
            "end_latitude": 26.000000,
            "end_longitude": 92.000000,
            "segment_length_km": 12.0,
            "road_type": "secondary",
            "surface": "asphalt",
            "maxspeed": "50",
            "lanes": "2",
        },
        # Lower path
        {
            "segment_id": "SEG_L1",
            "start_latitude": 26.000000,
            "start_longitude": 91.000000,
            "end_latitude": 25.900000,
            "end_longitude": 91.500000,
            "segment_length_km": 15.0,
            "road_type": "tertiary",
            "surface": "paved",
            "maxspeed": "40",
            "lanes": "1",
        },
        {
            "segment_id": "SEG_L2",
            "start_latitude": 25.900000,
            "start_longitude": 91.500000,
            "end_latitude": 26.000000,
            "end_longitude": 92.000000,
            "segment_length_km": 15.0,
            "road_type": "tertiary",
            "surface": "paved",
            "maxspeed": "40",
            "lanes": "1",
        },
    ]


@pytest.fixture
def real_osm_shaped_segments() -> List[Dict[str, Any]]:
    """Segments matching the exact repository normalized OSM schema."""
    return [
        {
            "segment_id": "OSM-22826704-0001",
            "osm_id": 22826704,
            "latitude": 24.577670,
            "longitude": 92.351206,
            "start_latitude": 24.575000,
            "start_longitude": 92.350000,
            "end_latitude": 24.580000,
            "end_longitude": 92.352000,
            "segment_length_km": 0.582,
            "road_type": "tertiary",
            "name": "ONGC Road",
            "surface": "asphalt",
            "maxspeed": "40",
            "lanes": "2",
        },
        {
            "segment_id": "OSM-22826704-0002",
            "osm_id": 22826704,
            "latitude": 24.582500,
            "longitude": 92.353000,
            "start_latitude": 24.580000,
            "start_longitude": 92.352000,
            "end_latitude": 24.585000,
            "end_longitude": 92.354000,
            "segment_length_km": 0.585,
            "road_type": "tertiary",
            "name": "ONGC Road",
            "surface": "asphalt",
            "maxspeed": "40",
            "lanes": "2",
        },
        {
            "segment_id": "OSM-22826705-0001",
            "osm_id": 22826705,
            "latitude": 24.580000,
            "longitude": 92.356000,
            "start_latitude": 24.575000,
            "start_longitude": 92.350000,
            "end_latitude": 24.585000,
            "end_longitude": 92.354000,
            "segment_length_km": 1.180,
            "road_type": "secondary",
            "name": "Bypass Link",
            "surface": "concrete",
            "maxspeed": "50",
            "lanes": "2",
        },
    ]


# ==============================================================================
# 1. Synthetic Network with 3 Distinct Valid Routes & 3. K=3
# ==============================================================================

def test_1_synthetic_network_with_3_distinct_valid_routes(synthetic_3route_network):
    """Test 1 & 3: Network generates exactly 3 distinct valid simple routes ordered by distance."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 92.000000}

    candidates = generate_route_candidates(synthetic_3route_network, origin, destination, k=3)

    assert len(candidates) == 3

    # Candidate 1: Center path (20.0 km)
    assert candidates[0]["route_id"] == "candidate_001"
    assert candidates[0]["total_distance_km"] == 20.0
    assert candidates[0]["segment_ids"] == ["SEG_C1", "SEG_C2"]
    assert candidates[0]["segment_count"] == 2

    # Candidate 2: Upper path (24.0 km)
    assert candidates[1]["route_id"] == "candidate_002"
    assert candidates[1]["total_distance_km"] == 24.0
    assert candidates[1]["segment_ids"] == ["SEG_U1", "SEG_U2"]
    assert candidates[1]["segment_count"] == 2

    # Candidate 3: Lower path (30.0 km)
    assert candidates[2]["route_id"] == "candidate_003"
    assert candidates[2]["total_distance_km"] == 30.0
    assert candidates[2]["segment_ids"] == ["SEG_L1", "SEG_L2"]
    assert candidates[2]["segment_count"] == 2

    # Ensure all 3 paths have completely distinct segment sequences
    seg_sequences = [tuple(c["segment_ids"]) for c in candidates]
    assert len(seg_sequences) == len(set(seg_sequences))


# ==============================================================================
# 2. K = 1
# ==============================================================================

def test_2_k_equals_1(synthetic_3route_network):
    """Test 2: When k=1, exactly one candidate (the shortest simple path) is returned."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 92.000000}

    candidates = generate_route_candidates(synthetic_3route_network, origin, destination, k=1)

    assert len(candidates) == 1
    assert candidates[0]["route_id"] == "candidate_001"
    assert candidates[0]["total_distance_km"] == 20.0
    assert candidates[0]["segment_ids"] == ["SEG_C1", "SEG_C2"]


# ==============================================================================
# 4. Deterministic Repeated Calls
# ==============================================================================

def test_4_deterministic_repeated_calls(synthetic_3route_network):
    """Test 4: Candidate generation across 100 runs produces identical outputs."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 92.000000}

    baseline = generate_route_candidates(synthetic_3route_network, origin, destination, k=3)

    for _ in range(100):
        result = generate_route_candidates(synthetic_3route_network, origin, destination, k=3)
        assert result == baseline


# ==============================================================================
# 5. Blocked Segment Removes Affected Candidate
# ==============================================================================

def test_5_blocked_segment_removes_affected_candidate(synthetic_3route_network):
    """Test 5: Explicitly blocking a segment removes that candidate and promotes the next shortest."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 92.000000}

    # Block SEG_C1 (from Center path)
    candidates = generate_route_candidates(
        synthetic_3route_network,
        origin,
        destination,
        k=3,
        blocked_segment_ids=["SEG_C1"],
    )

    assert len(candidates) == 2

    # Candidate 1 is now Upper path (24.0 km)
    assert candidates[0]["route_id"] == "candidate_001"
    assert candidates[0]["total_distance_km"] == 24.0
    assert candidates[0]["segment_ids"] == ["SEG_U1", "SEG_U2"]

    # Candidate 2 is Lower path (30.0 km)
    assert candidates[1]["route_id"] == "candidate_002"
    assert candidates[1]["total_distance_km"] == 30.0
    assert candidates[1]["segment_ids"] == ["SEG_L1", "SEG_L2"]

    # Blocked segment must never appear anywhere in the output
    for c in candidates:
        assert "SEG_C1" not in c["segment_ids"]


# ==============================================================================
# 6. Disconnected Network
# ==============================================================================

def test_6_disconnected_network_raises_validation_error():
    """Test 6: Disconnected origin and destination raise explicit RouteCandidateValidationError."""
    island_network = [
        {
            "segment_id": "SEG_A",
            "start_latitude": 26.0,
            "start_longitude": 91.0,
            "end_latitude": 26.1,
            "end_longitude": 91.1,
            "segment_length_km": 15.0,
        },
        {
            "segment_id": "SEG_B",
            "start_latitude": 28.0,
            "start_longitude": 94.0,
            "end_latitude": 28.1,
            "end_longitude": 94.1,
            "segment_length_km": 15.0,
        },
    ]
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 28.0, "longitude": 94.0}

    with pytest.raises(RouteCandidateValidationError, match="disconnected"):
        generate_route_candidates(island_network, origin, destination, k=3)


def test_6_blocked_bottleneck_disconnects_origin_destination():
    """Test 6b: Blocking the only connecting bridge leaves origin and destination disconnected."""
    bridge_corridor = [
        {
            "segment_id": "SEG_WEST",
            "start_latitude": 26.0,
            "start_longitude": 91.0,
            "end_latitude": 26.0,
            "end_longitude": 91.2,
            "segment_length_km": 10.0,
        },
        {
            "segment_id": "SEG_BRIDGE",
            "start_latitude": 26.0,
            "start_longitude": 91.2,
            "end_latitude": 26.0,
            "end_longitude": 91.8,
            "segment_length_km": 20.0,
        },
        {
            "segment_id": "SEG_EAST",
            "start_latitude": 26.0,
            "start_longitude": 91.8,
            "end_latitude": 26.0,
            "end_longitude": 92.0,
            "segment_length_km": 10.0,
        },
    ]
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 26.0, "longitude": 92.0}

    # Blocking SEG_BRIDGE cuts west and east components
    with pytest.raises(RouteCandidateValidationError, match="disconnected"):
        generate_route_candidates(
            bridge_corridor,
            origin,
            destination,
            k=3,
            blocked_segment_ids=["SEG_BRIDGE"],
        )


def test_6_all_segments_blocked_raises_validation_error(synthetic_3route_network):
    """Test 6c: Blocking all segments leaves no traversable network."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 92.000000}

    all_ids = {s["segment_id"] for s in synthetic_3route_network}
    with pytest.raises(RouteCandidateValidationError, match="No traversable segments remain"):
        generate_route_candidates(
            synthetic_3route_network,
            origin,
            destination,
            k=3,
            blocked_segment_ids=all_ids,
        )


# ==============================================================================
# 7. Origin == Destination
# ==============================================================================

def test_7_origin_equal_destination(synthetic_3route_network):
    """Test 7: Origin == Destination returns single 0-distance candidate."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 91.000000}

    candidates = generate_route_candidates(synthetic_3route_network, origin, destination, k=3)

    assert len(candidates) == 1
    c = candidates[0]
    assert c["route_id"] == "candidate_001"
    assert c["total_distance_km"] == 0.0
    assert c["segment_count"] == 0
    assert c["segment_ids"] == []
    assert c["origin_node"] == c["destination_node"]
    assert len(c["geometry"]) == 1
    assert len(c["node_ids"]) == 1


# ==============================================================================
# 8. Invalid Coordinates
# ==============================================================================

def test_8_invalid_coordinates(synthetic_3route_network):
    """Test 8: Latitude or longitude out-of-bounds or malformed raises validation error."""
    # Latitude > 90
    with pytest.raises(RouteCandidateValidationError, match="origin.latitude"):
        generate_route_candidates(synthetic_3route_network, {"latitude": 91.0, "longitude": 91.0}, {"latitude": 26.0, "longitude": 92.0})

    # Longitude < -180
    with pytest.raises(RouteCandidateValidationError, match="destination.longitude"):
        generate_route_candidates(synthetic_3route_network, {"latitude": 26.0, "longitude": 91.0}, {"latitude": 26.0, "longitude": -185.0})

    # Non-numeric coordinate
    with pytest.raises(RouteCandidateValidationError, match="numeric"):
        generate_route_candidates(synthetic_3route_network, {"latitude": "invalid", "longitude": 91.0}, {"latitude": 26.0, "longitude": 92.0})

    # Destination not a mapping
    with pytest.raises(RouteCandidateValidationError, match="mapping"):
        generate_route_candidates(synthetic_3route_network, {"latitude": 26.0, "longitude": 91.0}, [26.0, 92.0])  # type: ignore


# ==============================================================================
# 9. Malformed Segment Data
# ==============================================================================

def test_9_malformed_segment_data():
    """Test 9: Missing required fields, negative lengths, non-mappings raise validation error."""
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 26.0, "longitude": 92.0}

    # Missing segment_id
    with pytest.raises(RouteCandidateValidationError, match="segment_id"):
        generate_route_candidates(
            [{"start_latitude": 26.0, "start_longitude": 91.0, "end_latitude": 26.0, "end_longitude": 92.0, "segment_length_km": 10.0}],
            origin,
            destination,
        )

    # Missing endpoint coordinate
    with pytest.raises(RouteCandidateValidationError, match="missing required field 'end_latitude'"):
        generate_route_candidates(
            [{"segment_id": "S1", "start_latitude": 26.0, "start_longitude": 91.0, "end_longitude": 92.0, "segment_length_km": 10.0}],
            origin,
            destination,
        )

    # Negative length
    with pytest.raises(RouteCandidateValidationError, match="must be >= 0.0"):
        generate_route_candidates(
            [{"segment_id": "S1", "start_latitude": 26.0, "start_longitude": 91.0, "end_latitude": 26.0, "end_longitude": 92.0, "segment_length_km": -5.0}],
            origin,
            destination,
        )

    # Not a mapping
    with pytest.raises(RouteCandidateValidationError, match="Expected segment mapping"):
        generate_route_candidates(["not_a_mapping"], origin, destination)


# ==============================================================================
# 10. Invalid K
# ==============================================================================

def test_10_invalid_k(synthetic_3route_network):
    """Test 10: k must be a positive integer."""
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 26.0, "longitude": 92.0}

    with pytest.raises(RouteCandidateValidationError, match="Parameter 'k' must be a positive integer"):
        generate_route_candidates(synthetic_3route_network, origin, destination, k=0)

    with pytest.raises(RouteCandidateValidationError, match="Parameter 'k' must be a positive integer"):
        generate_route_candidates(synthetic_3route_network, origin, destination, k=-1)

    with pytest.raises(RouteCandidateValidationError, match="Parameter 'k' must be a positive integer"):
        generate_route_candidates(synthetic_3route_network, origin, destination, k="3")  # type: ignore

    with pytest.raises(RouteCandidateValidationError, match="Parameter 'k' must be a positive integer"):
        generate_route_candidates(synthetic_3route_network, origin, destination, k=True)  # type: ignore


# ==============================================================================
# 11. Caller Input is Not Mutated
# ==============================================================================

def test_11_caller_input_not_mutated(synthetic_3route_network):
    """Test 11: Candidate generation must never mutate caller's segment dictionaries."""
    snapshot = [dict(s) for s in synthetic_3route_network]
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 26.0, "longitude": 92.0}

    _ = generate_route_candidates(synthetic_3route_network, origin, destination, k=3)

    assert synthetic_3route_network == snapshot


# ==============================================================================
# 12. Route Geometry is Deterministic
# ==============================================================================

def test_12_route_geometry_is_deterministic(synthetic_3route_network):
    """Test 12: Route geometry reconstructed from node sequence is deterministic and continuous."""
    origin = {"latitude": 26.000000, "longitude": 91.000000}
    destination = {"latitude": 26.000000, "longitude": 92.000000}

    candidates = generate_route_candidates(synthetic_3route_network, origin, destination, k=3)

    for cand in candidates:
        geom = cand["geometry"]
        assert len(geom) == len(cand["node_ids"])
        # First coord is origin node
        assert geom[0] == [26.0, 91.0]
        # Last coord is destination node
        assert geom[-1] == [26.0, 92.0]
        # Distance equals sum of segment lengths
        computed = round(sum(s["segment_length_km"] for s in cand["segments"]), 6)
        assert math.isclose(cand["total_distance_km"], computed, abs_tol=1e-5)


# ==============================================================================
# 13. Segment Metadata is Preserved
# ==============================================================================

def test_13_segment_metadata_is_preserved(real_osm_shaped_segments):
    """Test 13: Segment metadata (name, surface, road_type, maxspeed, lanes) is preserved in candidate segments."""
    origin = {"latitude": 24.575000, "longitude": 92.350000}
    destination = {"latitude": 24.585000, "longitude": 92.354000}

    candidates = generate_route_candidates(real_osm_shaped_segments, origin, destination, k=2)

    assert len(candidates) == 2

    # Verify preserved metadata on segments
    cand_0_segs = candidates[0]["segments"]
    assert cand_0_segs[0]["name"] == "ONGC Road"
    assert cand_0_segs[0]["surface"] == "asphalt"
    assert cand_0_segs[0]["maxspeed"] == "40"
    assert cand_0_segs[0]["lanes"] == "2"
    assert cand_0_segs[0]["road_type"] == "tertiary"

    # Candidate 2
    cand_1_segs = candidates[1]["segments"]
    assert cand_1_segs[0]["name"] == "Bypass Link"
    assert cand_1_segs[0]["surface"] == "concrete"
    assert cand_1_segs[0]["road_type"] == "secondary"

    # Ensure prohibited fields are absent
    for cand in candidates:
        for forbidden in ["risk_score", "accessibility_score", "eta", "route_score", "recommendation", "confidence"]:
            assert forbidden not in cand


# ==============================================================================
# 14. Bidirectional Behavior is Explicit / Documented
# ==============================================================================

def test_14_bidirectional_behavior_and_reverse_traversal(synthetic_3route_network):
    """Test 14: Reversing origin and destination successfully routes in reverse direction."""
    forward_origin = {"latitude": 26.000000, "longitude": 91.000000}
    forward_dest = {"latitude": 26.000000, "longitude": 92.000000}

    forward_candidates = generate_route_candidates(synthetic_3route_network, forward_origin, forward_dest, k=3)
    reverse_candidates = generate_route_candidates(synthetic_3route_network, forward_dest, forward_origin, k=3)

    assert len(forward_candidates) == len(reverse_candidates) == 3

    # Total distance is identical in reverse
    for fwd, rev in zip(forward_candidates, reverse_candidates):
        assert math.isclose(fwd["total_distance_km"], rev["total_distance_km"], abs_tol=1e-5)
        # Reversed segment sequence
        assert fwd["segment_ids"] == rev["segment_ids"][::-1]
        # Reversed node sequence
        assert fwd["node_ids"] == rev["node_ids"][::-1]


# ==============================================================================
# Additional Validation Tests
# ==============================================================================

def test_empty_network_raises_validation_error():
    """Empty segment collection raises RouteCandidateValidationError."""
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 26.0, "longitude": 92.0}
    with pytest.raises(RouteCandidateValidationError, match="empty"):
        generate_route_candidates([], origin, destination, k=3)


def test_malformed_blocked_segment_ids_string(synthetic_3route_network):
    """Passing a string instead of iterable collection of IDs raises validation error."""
    origin = {"latitude": 26.0, "longitude": 91.0}
    destination = {"latitude": 26.0, "longitude": 92.0}
    with pytest.raises(RouteCandidateValidationError, match="blocked_segment_ids must be an iterable"):
        generate_route_candidates(synthetic_3route_network, origin, destination, k=3, blocked_segment_ids="SEG_C1")
