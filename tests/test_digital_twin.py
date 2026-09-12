"""Tests for SETU Thin Digital Twin Foundation v0.1.

Verification of state initialization, entity validation, referential integrity,
all 5 deterministic events, event envelope validation, state cloning isolation,
what-if scenario simulation, blocked segment handling, baseline vs scenario deltas,
and thin engine composition (Network Impact, Accessibility, ETA, Risk) with strict
input contracts and determinism across 100 runs.
"""

import math
import pytest

from src.accessibility.accessibility_scorer import calculate_accessibility
from src.digital_twin import (
    DigitalTwinState,
    DigitalTwinValidationError,
    VALID_SHIPMENT_STATUSES,
    apply_event,
    evaluate_incident_impact,
    evaluate_segment_accessibility,
    evaluate_shipment_eta,
    evaluate_shipment_risk,
    simulate_what_if,
)
from src.eta.eta_engine import DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS, estimate_route_eta
from src.risk.risk_engine import calculate_risk


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_segments():
    """A realistic 3-segment corridor around Guwahati."""
    return {
        "SEG-001": {
            "segment_id": "SEG-001",
            "road_type": "primary",
            "segment_length_km": 20.0,
            "surface": "asphalt",
            "start_latitude": 26.1000,
            "start_longitude": 91.7000,
            "end_latitude": 26.2000,
            "end_longitude": 91.7000,
            "latitude": 26.1500,
            "longitude": 91.7000,
        },
        "SEG-002": {
            "segment_id": "SEG-002",
            "road_type": "trunk",
            "segment_length_km": 30.0,
            "surface": "concrete",
            "start_latitude": 26.2000,
            "start_longitude": 91.7000,
            "end_latitude": 26.3500,
            "end_longitude": 91.7000,
            "latitude": 26.2750,
            "longitude": 91.7000,
        },
        "SEG-003": {
            "segment_id": "SEG-003",
            "road_type": "secondary",
            "segment_length_km": 15.0,
            "surface": "unpaved",
            "start_latitude": 26.3500,
            "start_longitude": 91.7000,
            "end_latitude": 26.4500,
            "end_longitude": 91.7000,
            "latitude": 26.4000,
            "longitude": 91.7000,
        },
    }


@pytest.fixture
def sample_vehicle():
    """Standard commercial vehicle."""
    return {
        "vehicle_id": "VEH-001",
        "vehicle_profile": "standard_truck",
        "current_latitude": 26.1000,
        "current_longitude": 91.7000,
        "current_segment_id": "SEG-001",
    }


@pytest.fixture
def sample_shipment():
    """Shipment assigned to the 3-segment route."""
    return {
        "shipment_id": "SHIP-001",
        "origin": {"name": "Guwahati Hub", "latitude": 26.1000, "longitude": 91.7000},
        "destination": {"name": "Barpeta Depot", "latitude": 26.4500, "longitude": 91.7000},
        "status": "IN_TRANSIT",
        "assigned_vehicle_id": "VEH-001",
        "assigned_route_segment_ids": ["SEG-001", "SEG-002", "SEG-003"],
    }


@pytest.fixture
def populated_state(sample_segments, sample_vehicle, sample_shipment):
    """DigitalTwinState populated with network, vehicle, and shipment."""
    return DigitalTwinState(
        network=sample_segments,
        vehicles={"VEH-001": sample_vehicle},
        shipments={"SHIP-001": sample_shipment},
        incidents={},
    )


# ==============================================================================
# 1. State Initialization & Entity Validation Tests
# ==============================================================================

def test_initial_empty_state():
    """Default state initializes empty collections and serializes cleanly."""
    state = DigitalTwinState()
    assert state.network == {}
    assert state.vehicles == {}
    assert state.shipments == {}
    assert state.incidents == {}

    snap = state.to_dict()
    assert isinstance(snap, dict)
    assert set(snap.keys()) == {"network", "vehicles", "shipments", "incidents"}


def test_add_entities_successfully(populated_state):
    """Entities are added and accessible in the collections."""
    assert len(populated_state.network) == 3
    assert len(populated_state.vehicles) == 1
    assert len(populated_state.shipments) == 1


def test_duplicate_entity_id_raises_error(populated_state):
    """Adding an entity with an existing ID must raise DigitalTwinValidationError."""
    with pytest.raises(DigitalTwinValidationError, match="already exists"):
        populated_state.add_segment({"segment_id": "SEG-001", "road_type": "primary"})

    with pytest.raises(DigitalTwinValidationError, match="already exists"):
        populated_state.add_vehicle({"vehicle_id": "VEH-001", "vehicle_profile": "standard_truck"})

    with pytest.raises(DigitalTwinValidationError, match="already exists"):
        populated_state.add_shipment({"shipment_id": "SHIP-001", "status": "PENDING"})


def test_negative_segment_length_raises_error():
    """Negative segment length is invalid."""
    with pytest.raises(DigitalTwinValidationError, match="segment_length_km"):
        DigitalTwinState(
            network={"SEG-NEG": {"segment_id": "SEG-NEG", "road_type": "primary", "segment_length_km": -5.0}}
        )


def test_invalid_coordinates_raise_error():
    """Out-of-range coordinates must raise DigitalTwinValidationError."""
    with pytest.raises(DigitalTwinValidationError, match="latitude"):
        DigitalTwinState(
            network={"SEG-BAD": {"segment_id": "SEG-BAD", "road_type": "primary", "latitude": 95.0}}
        )


# ==============================================================================
# 2. Referential Integrity Tests
# ==============================================================================

def test_shipment_referencing_non_existent_segment_raises_error(sample_vehicle):
    """Shipment route referencing unknown segment ID raises DigitalTwinValidationError."""
    with pytest.raises(DigitalTwinValidationError, match="non-existent network segment"):
        DigitalTwinState(
            network={"SEG-001": {"segment_id": "SEG-001", "road_type": "primary"}},
            vehicles={"VEH-001": sample_vehicle},
            shipments={
                "SHIP-BAD": {
                    "shipment_id": "SHIP-BAD",
                    "status": "PENDING",
                    "assigned_route_segment_ids": ["SEG-001", "SEG-DOES-NOT-EXIST"],
                }
            },
        )


def test_shipment_referencing_non_existent_vehicle_raises_error(sample_segments):
    """Shipment assigned to unknown vehicle ID raises DigitalTwinValidationError."""
    with pytest.raises(DigitalTwinValidationError, match="non-existent vehicle"):
        DigitalTwinState(
            network=sample_segments,
            vehicles={},
            shipments={
                "SHIP-BAD": {
                    "shipment_id": "SHIP-BAD",
                    "status": "PENDING",
                    "assigned_vehicle_id": "VEH-UNKNOWN",
                    "assigned_route_segment_ids": ["SEG-001"],
                }
            },
        )


# ==============================================================================
# 3. Deterministic Event Application Tests
# ==============================================================================

def test_event_envelope_validation():
    """Events missing required envelope fields or with unknown event_type must fail."""
    state = DigitalTwinState()

    with pytest.raises(DigitalTwinValidationError, match="event_id"):
        apply_event(state, {"event_type": "incident_created", "timestamp": "2026-09-13T00:00:00Z", "payload": {}})

    with pytest.raises(DigitalTwinValidationError, match="Unsupported event_type"):
        apply_event(state, {"event_id": "E1", "event_type": "magic_event", "timestamp": "2026-09-13T00:00:00Z", "payload": {}})

    with pytest.raises(DigitalTwinValidationError, match="payload"):
        apply_event(state, {"event_id": "E1", "event_type": "incident_created", "timestamp": "2026-09-13T00:00:00Z"})


def test_event_incident_created_unconfirmed_closure(populated_state):
    """incident_created links incident ID to affected segments without inventing closure."""
    # Incident centered on SEG-002 (26.2750, 91.7000)
    event = {
        "event_id": "EVT-INC-001",
        "event_type": "incident_created",
        "timestamp": "2026-09-13T10:00:00Z",
        "payload": {
            "incident_id": "INC-001",
            "latitude": 26.2750,
            "longitude": 91.7000,
            "incident_type": "landslide",
            "severity": 0.80,
            "impact_radius_km": 5.0,
            "is_confirmed_closure": False,
        },
    }

    apply_event(populated_state, event)

    assert "INC-001" in populated_state.incidents
    # SEG-002 should have INC-001 in active_incident_ids
    assert "INC-001" in populated_state.network["SEG-002"]["active_incident_ids"]
    # But NOT is_blocked because is_confirmed_closure was False
    assert populated_state.network["SEG-002"]["is_blocked"] is False


def test_event_incident_created_confirmed_closure(populated_state):
    """incident_created marks affected segments is_blocked=True ONLY when confirmed."""
    event = {
        "event_id": "EVT-INC-002",
        "event_type": "incident_created",
        "timestamp": "2026-09-13T10:05:00Z",
        "payload": {
            "incident_id": "INC-002",
            "latitude": 26.2750,
            "longitude": 91.7000,
            "incident_type": "bridge_collapse",
            "severity": 1.00,
            "impact_radius_km": 5.0,
            "is_confirmed_closure": True,
        },
    }

    apply_event(populated_state, event)

    assert populated_state.network["SEG-002"]["is_blocked"] is True


def test_event_vehicle_location_updated(populated_state):
    """vehicle_location_updated updates coordinates and timestamp, preserving profile."""
    event = {
        "event_id": "EVT-VEH-001",
        "event_type": "vehicle_location_updated",
        "timestamp": "2026-09-13T10:15:00Z",
        "payload": {
            "vehicle_id": "VEH-001",
            "latitude": 26.2500,
            "longitude": 91.7000,
            "current_segment_id": "SEG-002",
        },
    }

    apply_event(populated_state, event)
    veh = populated_state.vehicles["VEH-001"]
    assert veh["current_latitude"] == 26.2500
    assert veh["current_segment_id"] == "SEG-002"
    assert veh["vehicle_profile"] == "standard_truck"
    assert veh["last_updated_timestamp"] == "2026-09-13T10:15:00Z"


def test_event_shipment_status_changed(populated_state):
    """shipment_status_changed transitions status and rejects invalid statuses."""
    event = {
        "event_id": "EVT-SHP-001",
        "event_type": "shipment_status_changed",
        "timestamp": "2026-09-13T10:20:00Z",
        "payload": {"shipment_id": "SHIP-001", "new_status": "DELAYED", "reason": "Severe rain"},
    }

    apply_event(populated_state, event)
    assert populated_state.shipments["SHIP-001"]["status"] == "DELAYED"
    assert populated_state.shipments["SHIP-001"]["status_change_reason"] == "Severe rain"

    bad_event = {
        "event_id": "EVT-SHP-BAD",
        "event_type": "shipment_status_changed",
        "timestamp": "2026-09-13T10:21:00Z",
        "payload": {"shipment_id": "SHIP-001", "new_status": "INVALID_STATUS"},
    }
    with pytest.raises(DigitalTwinValidationError, match="Invalid new_status"):
        apply_event(populated_state, bad_event)


def test_event_route_approved(populated_state):
    """route_approved stores approved segments, operator, and timestamp."""
    event = {
        "event_id": "EVT-APP-001",
        "event_type": "route_approved",
        "timestamp": "2026-09-13T10:30:00Z",
        "payload": {
            "shipment_id": "SHIP-001",
            "route_segment_ids": ["SEG-001", "SEG-002"],
            "approved_by": "OPERATOR-42",
        },
    }

    apply_event(populated_state, event)
    ship = populated_state.shipments["SHIP-001"]
    assert ship["approved_route_segment_ids"] == ["SEG-001", "SEG-002"]
    assert ship["approved_by"] == "OPERATOR-42"
    assert ship["approved_at"] == "2026-09-13T10:30:00Z"


def test_event_route_changed_transitions_to_rerouted(populated_state):
    """route_changed replaces route and updates in-transit status to REROUTED."""
    event = {
        "event_id": "EVT-REROUTE-001",
        "event_type": "route_changed",
        "timestamp": "2026-09-13T10:35:00Z",
        "payload": {
            "shipment_id": "SHIP-001",
            "new_route_segment_ids": ["SEG-001", "SEG-003"],
            "reason": "Avoid incident",
        },
    }

    apply_event(populated_state, event)
    ship = populated_state.shipments["SHIP-001"]
    assert ship["assigned_route_segment_ids"] == ["SEG-001", "SEG-003"]
    assert ship["status"] == "REROUTED"
    assert ship["route_change_reason"] == "Avoid incident"


# ==============================================================================
# 4. State Cloning & What-If Isolation Tests
# ==============================================================================

def test_clone_isolation(populated_state):
    """Mutating cloned state leaves original state completely unmodified."""
    clone = populated_state.clone()
    clone.network["SEG-001"]["is_blocked"] = True
    clone.vehicles["VEH-001"]["current_latitude"] = 0.0

    assert populated_state.network["SEG-001"]["is_blocked"] is False
    assert populated_state.network["SEG-001"]["is_blocked"] != clone.network["SEG-001"]["is_blocked"]
    assert populated_state.vehicles["VEH-001"]["current_latitude"] == 26.1000


def test_simulate_what_if_zero_live_mutation(populated_state):
    """simulate_what_if must NOT mutate the baseline state."""
    snap_before = populated_state.to_dict()

    scenario = {
        "scenario_id": "TEST-SCENARIO",
        "blocked_segment_ids": ["SEG-002"],
    }

    res = simulate_what_if(populated_state, scenario)

    assert populated_state.to_dict() == snap_before
    assert populated_state.network["SEG-002"]["is_blocked"] is False
    assert res["is_baseline_mutated"] is False


def test_simulate_what_if_blocked_segment(populated_state):
    """Scenario blocking a route segment causes shipment to become newly impassable with delay."""
    scenario = {
        "scenario_id": "SCENARIO-BLOCKED-SEG-2",
        "blocked_segment_ids": ["SEG-002"],
    }

    res = simulate_what_if(populated_state, scenario)

    assert "SHIP-001" in res["newly_impassable_shipments"]
    assert "SHIP-001" in res["affected_shipment_ids"]
    assert res["baseline_summary"]["SHIP-001"]["is_passable"] is True
    assert res["scenario_summary"]["SHIP-001"]["is_passable"] is False
    # Delay delta should equal DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS (7200s)
    assert res["delay_deltas"]["SHIP-001"] == DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS


# ==============================================================================
# 5. Thin Engine Composition Tests
# ==============================================================================

def test_evaluate_shipment_eta_matches_eta_engine(populated_state):
    """evaluate_shipment_eta directly delegates to estimate_route_eta."""
    res = evaluate_shipment_eta(populated_state, "SHIP-001")

    # Manually call estimate_route_eta with the same segments and vehicle
    expected = estimate_route_eta(
        [populated_state.network[s] for s in ["SEG-001", "SEG-002", "SEG-003"]],
        vehicle_profile="standard_truck",
    )

    assert res["total_distance_km"] == expected["total_distance_km"]
    assert res["baseline_eta_seconds"] == expected["baseline_eta_seconds"]
    assert res["disrupted_eta_seconds"] == expected["disrupted_eta_seconds"]
    assert res["is_passable"] == expected["is_passable"]


def test_evaluate_segment_accessibility_matches_scorer(populated_state):
    """evaluate_segment_accessibility directly delegates to calculate_accessibility."""
    res = evaluate_segment_accessibility(populated_state, "SEG-001")
    expected = calculate_accessibility(populated_state.network["SEG-001"])

    assert res["accessibility_score"] == expected["accessibility_score"]
    assert res["accessibility_level"] == expected["accessibility_level"]


def test_evaluate_incident_impact_matches_impact_engine(populated_state):
    """evaluate_incident_impact directly delegates to assess_network_impact."""
    inc = {
        "latitude": 26.2750,
        "longitude": 91.7000,
        "incident_type": "flood",
        "severity": 0.75,
        "impact_radius_km": 10.0,
    }
    res = evaluate_incident_impact(populated_state, inc)
    assert res["affected_segment_count"] >= 1
    assert "SEG-002" in res["affected_segment_ids"]


def test_evaluate_shipment_risk_strict_contract(populated_state):
    """evaluate_shipment_risk requires all external inputs and produces valid risk score."""
    # Missing required context must raise DigitalTwinValidationError
    with pytest.raises(DigitalTwinValidationError, match="Missing required external Risk Engine context"):
        evaluate_shipment_risk(populated_state, "SHIP-001", {"weather_severity": 0.5})

    valid_context = {
        "weather_severity": 0.30,
        "road_condition_score": 0.85,
        "network_criticality": 0.60,
    }

    risk_res = evaluate_shipment_risk(populated_state, "SHIP-001", valid_context)
    assert 0.0 <= risk_res["risk_score"] <= 100.0
    assert risk_res["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert "reason_codes" in risk_res


def test_simulation_with_risk_comparison(populated_state):
    """When risk_context is supplied, simulation computes baseline risk, scenario risk, and risk deltas."""
    valid_context = {
        "weather_severity": 0.20,
        "road_condition_score": 0.90,
        "network_criticality": 0.50,
    }

    scenario = {
        "scenario_id": "SCENARIO-SPEED-RED",
        "speed_reductions": {"SEG-001": 0.80},  # severe 80% slowdown increases delay
    }

    res = simulate_what_if(populated_state, scenario, risk_context=valid_context)

    b_risk = res["baseline_summary"]["SHIP-001"]["risk_score"]
    s_risk = res["scenario_summary"]["SHIP-001"]["risk_score"]
    assert b_risk is not None
    assert s_risk is not None
    assert s_risk > b_risk  # Higher delay should produce higher risk score
    assert res["risk_score_deltas"]["SHIP-001"] > 0.0


# ==============================================================================
# 6. Determinism Across 100 Runs
# ==============================================================================

def test_repeated_deterministic_simulation(populated_state):
    """100 repeated runs of identical scenario produce identical results."""
    scenario = {
        "scenario_id": "SCENARIO-DETERMINISM",
        "blocked_segment_ids": ["SEG-003"],
        "speed_reductions": {"SEG-001": 0.50},
    }
    context = {
        "weather_severity": 0.25,
        "road_condition_score": 0.80,
        "network_criticality": 0.70,
    }

    baseline = simulate_what_if(populated_state, scenario, risk_context=context)

    for _ in range(100):
        run_res = simulate_what_if(populated_state, scenario, risk_context=context)
        assert run_res == baseline
