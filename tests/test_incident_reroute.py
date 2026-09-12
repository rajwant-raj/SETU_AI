"""Tests for Checkpoint 16 — Incident-to-Reroute Orchestration Layer.

Covers all 25 required test cases:
1. package import
2. incident validation
3. Network Impact integration
4. affected segments are reported
5. affected segments are NOT automatically blocked
6. only confirmed blocked_segment_ids are excluded
7. route candidate generation integration
8. ranking integration
9. explanation integration
10. complete recommendation structure
11. PENDING_APPROVAL state
12. approval_required=True before approval
13. recommendation creation does not mutate operational state
14. explicit approval changes route
15. rejection/non-approval does not change route
16. approval cannot happen twice
17. invalid approval state rejected
18. malformed blocked IDs rejected
19. no alternative route handled honestly
20. deterministic repeated execution
21. caller input immutability
22. route_changed event contract preserved
23. no invented blockage
24. no new ranking formula
25. honesty disclosure present
"""

import copy
import pytest

from src.digital_twin.state import DigitalTwinState
from src.reroute import (
    REROUTE_HONESTY_DISCLOSURE,
    IncidentRerouteValidationError,
    approve_reroute_recommendation,
    create_reroute_recommendation,
    reject_reroute_recommendation,
)


@pytest.fixture
def sample_network():
    """Diamond road network with 2 parallel routes between Node A and Node D:
    Path 1: A -> B -> D (seg_AB, seg_BD)
    Path 2: A -> C -> D (seg_AC, seg_CD)
    """
    return [
        {
            "segment_id": "seg_AB",
            "start_latitude": 26.10,
            "start_longitude": 91.70,
            "end_latitude": 26.15,
            "end_longitude": 91.75,
            "segment_length_km": 10.0,
            "road_type": "primary",
            "surface": "paved",
            "active_incident_ids": [],
            "is_blocked": False,
        },
        {
            "segment_id": "seg_BD",
            "start_latitude": 26.15,
            "start_longitude": 91.75,
            "end_latitude": 26.20,
            "end_longitude": 91.80,
            "segment_length_km": 10.0,
            "road_type": "primary",
            "surface": "paved",
            "active_incident_ids": [],
            "is_blocked": False,
        },
        {
            "segment_id": "seg_AC",
            "start_latitude": 26.10,
            "start_longitude": 91.70,
            "end_latitude": 26.12,
            "end_longitude": 91.78,
            "segment_length_km": 12.0,
            "road_type": "secondary",
            "surface": "paved",
            "active_incident_ids": [],
            "is_blocked": False,
        },
        {
            "segment_id": "seg_CD",
            "start_latitude": 26.12,
            "start_longitude": 91.78,
            "end_latitude": 26.20,
            "end_longitude": 91.80,
            "segment_length_km": 12.0,
            "road_type": "secondary",
            "surface": "paved",
            "active_incident_ids": [],
            "is_blocked": False,
        },
    ]


@pytest.fixture
def sample_incident():
    """Incident spatially located on seg_AB."""
    return {
        "incident_id": "inc_landslide_001",
        "latitude": 26.125,
        "longitude": 26.125,  # Note: will be fixed to 91.725
        "incident_type": "landslide",
        "severity": 0.85,
        "impact_radius_km": 5.0,
    }


@pytest.fixture
def valid_incident():
    """Correctly positioned incident centered directly along seg_AB."""
    return {
        "incident_id": "inc_landslide_001",
        "latitude": 26.125,
        "longitude": 91.725,
        "incident_type": "landslide",
        "severity": 0.85,
        "impact_radius_km": 5.0,
    }


@pytest.fixture
def sample_risk_context():
    """Complete explicit risk context required by Risk Engine / Route Ranking."""
    return {
        "incident_severity": 0.85,
        "accessibility_score": 0.90,
        "weather_severity": 0.20,
        "road_condition_score": 0.80,
        "network_criticality": 0.50,
        "current_delay_ratio": 0.10,
    }


@pytest.fixture
def current_route(sample_risk_context):
    """Current active route following Path 1 (seg_AB, seg_BD)."""
    return {
        "route_id": "route_current_1",
        "shipment_id": "shipment_test_01",
        "segment_ids": ["seg_AB", "seg_BD"],
        "origin": {"latitude": 26.10, "longitude": 91.70},
        "destination": {"latitude": 26.20, "longitude": 91.80},
        "risk_context": sample_risk_context,
    }


@pytest.fixture
def digital_twin_state(sample_network):
    """Digital twin state populated with sample network, vehicle, and shipment."""
    state = DigitalTwinState()
    for seg in sample_network:
        state.network[seg["segment_id"]] = dict(seg)

    state.vehicles["veh_01"] = {
        "vehicle_id": "veh_01",
        "vehicle_profile": "standard_truck",
        "current_latitude": 26.10,
        "current_longitude": 91.70,
        "current_segment_id": "seg_AB",
    }

    state.shipments["shipment_test_01"] = {
        "shipment_id": "shipment_test_01",
        "assigned_vehicle_id": "veh_01",
        "assigned_route_segment_ids": ["seg_AB", "seg_BD"],
        "status": "IN_TRANSIT",
    }
    return state


def test_1_package_import():
    """Test 1: Public package exports are callable and properly typed."""
    assert callable(create_reroute_recommendation)
    assert callable(approve_reroute_recommendation)
    assert callable(reject_reroute_recommendation)
    assert issubclass(IncidentRerouteValidationError, ValueError)
    assert isinstance(REROUTE_HONESTY_DISCLOSURE, str)


def test_2_incident_validation(sample_network, current_route):
    """Test 2: Malformed incidents are strictly rejected."""
    # Missing required fields
    with pytest.raises(IncidentRerouteValidationError, match="Invalid incident"):
        create_reroute_recommendation(
            incident={"incident_id": "inc_bad"},
            network_segments=sample_network,
            current_route=current_route,
        )

    # Severity out of [0, 1] range
    with pytest.raises(IncidentRerouteValidationError, match="Invalid incident"):
        create_reroute_recommendation(
            incident={
                "latitude": 26.12,
                "longitude": 91.72,
                "incident_type": "landslide",
                "severity": 1.5,
                "impact_radius_km": 5.0,
            },
            network_segments=sample_network,
            current_route=current_route,
        )


def test_3_network_impact_integration(valid_incident, sample_network, current_route):
    """Test 3: Network Impact engine is executed and finds spatially proximate segments."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
    )
    assert isinstance(rec["impacted_segment_ids"], list)
    assert len(rec["impacted_segment_ids"]) > 0
    assert "seg_AB" in rec["impacted_segment_ids"]


def test_4_affected_segments_are_reported(valid_incident, sample_network, current_route):
    """Test 4: Potentially affected segment IDs are reported in the recommendation."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
    )
    assert "seg_AB" in rec["impacted_segment_ids"]


def test_5_affected_segments_are_not_automatically_blocked(valid_incident, sample_network, current_route):
    """Test 5: Critical Semantic Rule: Impacted segments are NOT automatically blocked!"""
    # Incident severity is 0.85 and seg_AB is impacted, but no confirmed blockages are passed.
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=None,
    )
    # The generator should still be free to traverse seg_AB because it was not confirmed blocked
    all_alt_segments = [seg_id for alt in rec["alternative_routes"] for seg_id in alt["segment_ids"]]
    assert "seg_AB" in all_alt_segments
    assert rec["confirmed_blocked_segment_ids"] == []


def test_6_only_confirmed_blocked_segment_ids_are_excluded(valid_incident, sample_network, current_route):
    """Test 6: Only explicitly supplied confirmed_blocked_segment_ids are excluded from routing."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )
    assert rec["confirmed_blocked_segment_ids"] == ["seg_AB"]
    # All alternatives MUST exclude seg_AB
    for alt in rec["alternative_routes"]:
        assert "seg_AB" not in alt["segment_ids"]
    # Path 2 (seg_AC, seg_CD) must be chosen
    assert rec["alternative_routes"][0]["segment_ids"] == ["seg_AC", "seg_CD"]


def test_7_route_candidate_generation_integration(valid_incident, sample_network, current_route):
    """Test 7: Route Candidate Generation generates valid alternative routes."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )
    assert len(rec["alternative_routes"]) >= 1
    assert "route_id" in rec["alternative_routes"][0]
    assert "total_distance_km" in rec["alternative_routes"][0]


def test_8_ranking_integration(valid_incident, sample_network, current_route):
    """Test 8: Route Ranking ranks candidates with normalized utility scores."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=None,
    )
    assert len(rec["ranked_routes"]) == len(rec["alternative_routes"])
    top = rec["ranked_routes"][0]
    assert top["rank"] == 1
    assert "ranking_score" in top
    assert "normalized_scores" in top
    assert rec["recommended_route_id"] == top["route_id"]


def test_9_explanation_integration(valid_incident, sample_network, current_route):
    """Test 9: Route Explanation generates structured factor breakdowns."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )
    assert len(rec["explanations"]) == len(rec["ranked_routes"])
    exp = rec["explanations"][0]
    assert exp["route_id"] == rec["recommended_route_id"]
    assert len(exp["decision_factors"]) == 5
    assert "summary" in exp
    assert "tradeoffs" in exp


def test_10_complete_recommendation_structure(valid_incident, sample_network, current_route):
    """Test 10: Recommendation contains all 12 required fields."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )
    required_fields = [
        "recommendation_id",
        "incident",
        "impacted_segment_ids",
        "confirmed_blocked_segment_ids",
        "current_route",
        "alternative_routes",
        "ranked_routes",
        "explanations",
        "recommended_route_id",
        "recommendation_status",
        "approval_required",
        "honesty_disclosure",
    ]
    for rf in required_fields:
        assert rf in rec, f"Missing required recommendation field: '{rf}'"


def test_11_pending_approval_state(valid_incident, sample_network, current_route):
    """Test 11: Initial recommendation status is strictly PENDING_APPROVAL."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
    )
    assert rec["recommendation_status"] == "PENDING_APPROVAL"


def test_12_approval_required_flag_true(valid_incident, sample_network, current_route):
    """Test 12: approval_required is True upon creation."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
    )
    assert rec["approval_required"] is True


def test_13_creation_does_not_mutate_operational_state(valid_incident, digital_twin_state, current_route):
    """Test 13: Creating a recommendation has zero side-effects on operational state."""
    initial_shipment = copy.deepcopy(digital_twin_state.shipments["shipment_test_01"])

    _ = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=digital_twin_state.network.values(),
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    assert digital_twin_state.shipments["shipment_test_01"] == initial_shipment


def test_14_explicit_approval_changes_route(valid_incident, digital_twin_state, current_route):
    """Test 14: Calling approve_reroute_recommendation changes operational route and transitions status."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=digital_twin_state.network.values(),
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    approved = approve_reroute_recommendation(
        rec,
        approved_by="dispatcher_ops_99",
        state=digital_twin_state,
        reason="Landslide blockage on seg_AB verified by traffic police",
    )

    assert approved["recommendation_status"] == "APPROVED"
    assert approved["approval_required"] is False
    assert approved["approved_by"] == "dispatcher_ops_99"

    # Operational route updated in state
    shipment = digital_twin_state.shipments["shipment_test_01"]
    assert shipment["assigned_route_segment_ids"] == ["seg_AC", "seg_CD"]
    assert shipment["status"] == "REROUTED"
    assert shipment.get("route_change_reason") == "Landslide blockage on seg_AB verified by traffic police"


def test_15_rejection_does_not_change_route(valid_incident, digital_twin_state, current_route):
    """Test 15: Rejection transitions recommendation to REJECTED without modifying state."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=digital_twin_state.network.values(),
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    initial_route = list(digital_twin_state.shipments["shipment_test_01"]["assigned_route_segment_ids"])

    rejected = reject_reroute_recommendation(
        rec,
        rejected_by="dispatcher_ops_99",
        reason="Alternate route too narrow for heavy convoy",
    )

    assert rejected["recommendation_status"] == "REJECTED"
    assert rejected["approval_required"] is False
    assert rejected["rejected_by"] == "dispatcher_ops_99"
    # State remains unmodified
    assert digital_twin_state.shipments["shipment_test_01"]["assigned_route_segment_ids"] == initial_route
    assert digital_twin_state.shipments["shipment_test_01"]["status"] == "IN_TRANSIT"


def test_16_approval_cannot_happen_twice(valid_incident, digital_twin_state, current_route):
    """Test 16: An already approved recommendation cannot be approved again."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=digital_twin_state.network.values(),
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    approved = approve_reroute_recommendation(
        rec,
        approved_by="dispatcher_ops_99",
        state=digital_twin_state,
    )

    with pytest.raises(IncidentRerouteValidationError, match="must be 'PENDING_APPROVAL'"):
        approve_reroute_recommendation(
            approved,
            approved_by="dispatcher_ops_99",
            state=digital_twin_state,
        )


def test_17_invalid_approval_state_rejected(valid_incident, sample_network, current_route):
    """Test 17: Approval requires non-empty approved_by and valid state."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
    )

    # Empty operator string
    with pytest.raises(IncidentRerouteValidationError, match="approved_by"):
        approve_reroute_recommendation(rec, approved_by="  ")

    # None operator
    with pytest.raises(IncidentRerouteValidationError, match="approved_by"):
        approve_reroute_recommendation(rec, approved_by=None)


def test_18_malformed_blocked_ids_rejected(valid_incident, sample_network, current_route):
    """Test 18: Blocked segment IDs that do not exist in the network are rejected."""
    with pytest.raises(IncidentRerouteValidationError, match="does not exist in network segments"):
        create_reroute_recommendation(
            incident=valid_incident,
            network_segments=sample_network,
            current_route=current_route,
            confirmed_blocked_segment_ids=["non_existent_seg_999"],
        )

    # Blocked IDs passed as string instead of iterable
    with pytest.raises(IncidentRerouteValidationError, match="must be an iterable"):
        create_reroute_recommendation(
            incident=valid_incident,
            network_segments=sample_network,
            current_route=current_route,
            confirmed_blocked_segment_ids="seg_AB",
        )


def test_19_no_alternative_route_handled_honestly(valid_incident, sample_risk_context):
    """Test 19: When all paths are blocked, disconnection error is raised rather than fabricating fake routes."""
    # Bridge network where origin and destination are separated by a single bridge segment
    bridge_network = [
        {
            "segment_id": "seg_orig_to_bridge",
            "start_latitude": 26.10,
            "start_longitude": 91.70,
            "end_latitude": 26.14,
            "end_longitude": 91.74,
            "segment_length_km": 5.0,
            "road_type": "primary",
            "surface": "paved",
        },
        {
            "segment_id": "seg_bridge",
            "start_latitude": 26.14,
            "start_longitude": 91.74,
            "end_latitude": 26.16,
            "end_longitude": 91.76,
            "segment_length_km": 2.0,
            "road_type": "bridge",
            "surface": "paved",
        },
        {
            "segment_id": "seg_bridge_to_dest",
            "start_latitude": 26.16,
            "start_longitude": 91.76,
            "end_latitude": 26.20,
            "end_longitude": 91.80,
            "segment_length_km": 5.0,
            "road_type": "primary",
            "surface": "paved",
        },
    ]
    route_across_bridge = {
        "route_id": "route_bridge_01",
        "segment_ids": ["seg_orig_to_bridge", "seg_bridge", "seg_bridge_to_dest"],
        "origin": {"latitude": 26.10, "longitude": 91.70},
        "destination": {"latitude": 26.20, "longitude": 91.80},
        "risk_context": sample_risk_context,
    }
    # Blocking seg_bridge completely isolates origin component from destination component
    with pytest.raises(IncidentRerouteValidationError, match="disconnected"):
        create_reroute_recommendation(
            incident=valid_incident,
            network_segments=bridge_network,
            current_route=route_across_bridge,
            confirmed_blocked_segment_ids=["seg_bridge"],
        )


def test_20_deterministic_repeated_execution(valid_incident, sample_network, current_route):
    """Test 20: Repeated invocation produces byte-for-byte identical output."""
    rec1 = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )
    rec2 = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    assert rec1 == rec2


def test_21_caller_input_immutability(valid_incident, sample_network, current_route):
    """Test 21: Inputs are not mutated by recommendation generation."""
    inc_orig = copy.deepcopy(valid_incident)
    net_orig = copy.deepcopy(sample_network)
    route_orig = copy.deepcopy(current_route)
    blocked_orig = ["seg_AB"]

    _ = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=blocked_orig,
    )

    assert valid_incident == inc_orig
    assert sample_network == net_orig
    assert current_route == route_orig
    assert blocked_orig == ["seg_AB"]


def test_22_route_changed_event_contract_preserved(valid_incident, digital_twin_state, current_route):
    """Test 22: Approval emits and applies a valid Digital Twin route_changed event."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=digital_twin_state.network.values(),
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    approved = approve_reroute_recommendation(
        rec,
        approved_by="dispatcher_01",
        state=digital_twin_state,
        event_id="custom_evt_123",
        timestamp="2026-09-13T10:00:00Z",
    )

    assert "applied_event" in approved
    evt = approved["applied_event"]
    assert evt["event_id"] == "custom_evt_123"
    assert evt["event_type"] == "route_changed"
    assert evt["timestamp"] == "2026-09-13T10:00:00Z"
    assert evt["payload"]["shipment_id"] == "shipment_test_01"
    assert evt["payload"]["new_route_segment_ids"] == ["seg_AC", "seg_CD"]


def test_23_no_invented_blockage(valid_incident, sample_network, current_route):
    """Test 23: Even with critical incident severity 1.0, blockage is never invented."""
    severe_incident = dict(valid_incident)
    severe_incident["severity"] = 1.0
    severe_incident["impact_radius_km"] = 50.0

    rec = create_reroute_recommendation(
        incident=severe_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=None,
    )

    # Empty confirmed blockage
    assert rec["confirmed_blocked_segment_ids"] == []


def test_24_no_new_ranking_formula(valid_incident, sample_network, current_route):
    """Test 24: Uses approved ranking weights from Checkpoint 14."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    for cand in rec["ranked_routes"]:
        assert "weights_applied" in cand
        w = cand["weights_applied"]
        # Verified proportional weights from Checkpoint 14 (30, 20, 20, 15, 10) / 95
        assert pytest.approx(w["eta"], abs=1e-4) == 30.0 / 95.0
        assert pytest.approx(w["risk"], abs=1e-4) == 20.0 / 95.0
        assert pytest.approx(w["accessibility"], abs=1e-4) == 20.0 / 95.0
        assert pytest.approx(w["distance"], abs=1e-4) == 15.0 / 95.0


def test_25_honesty_disclosure_present(valid_incident, sample_network, current_route):
    """Test 25: Honesty disclosure is present with all required transparency points."""
    rec = create_reroute_recommendation(
        incident=valid_incident,
        network_segments=sample_network,
        current_route=current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
    )

    disclosure = rec["honesty_disclosure"]
    assert "POTENTIALLY AFFECTED" in disclosure
    assert "confirmed_blocked_segment_ids" in disclosure
    assert "Decision Support" in disclosure
    assert "Vehicle Profile Compatibility Proxy" in disclosure
    assert "Operator Authority" in disclosure
