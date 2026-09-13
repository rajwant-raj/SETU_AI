"""SETU_AI — Checkpoint 20: Decision-Layer & Incident-to-Reroute Integration Tests.

Verifies:
1. Default CP16 behavior is preserved when include_ml_assessment=False.
2. Opt-in auxiliary ML assessment attached when include_ml_assessment=True.
3. Ranking scores, normalized utility, weights, and candidate ordering remain
   100% identical between include_ml_assessment=False and include_ml_assessment=True.
4. Potentially affected segments within incident impact radius NEVER automatically
   become confirmed blocked by ML inference.
5. Missing model artifact produces explicit machine-readable UNAVAILABLE status
   while deterministic reroute recommendation succeeds normally.
6. Recommendation lifecycle: remains PENDING_APPROVAL with approval_required=True.
7. Operational route state (DigitalTwinState) remains unchanged before explicit operator approval.
8. Explicit operator approval (approve_reroute_recommendation) and rejection
   (reject_reroute_recommendation) continue to operate authoritatively.
"""

from __future__ import annotations

import copy
from pathlib import Path
import numpy as np
import pytest

from src.digital_twin.state import DigitalTwinState

from src.ml.inference import (
    DisruptionInferenceEngine,
    FROZEN_DECISION_THRESHOLD,
)
from src.reroute import (
    approve_reroute_recommendation,
    create_reroute_recommendation,
    reject_reroute_recommendation,
)


class MockPredictProbaModel:
    """Deterministic dummy scikit-learn model for testing integration."""

    def __init__(self, prob: float = 0.45) -> None:
        self.prob = prob

    def predict_proba(self, X: Any) -> Any:
        n_rows = len(X)
        return np.array([[1.0 - self.prob, self.prob] for _ in range(n_rows)], dtype=np.float64)



@pytest.fixture
def sample_network() -> List[Dict[str, Any]]:
    """Diamond road network with 2 parallel routes between Node A and Node D:
    Route 1: A -> B -> D (seg_AB, seg_BD) (Total length: 20 km)
    Route 2: A -> C -> D (seg_AC, seg_CD) (Total length: 24 km)
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
            "surface": "asphalt",
            "lanes": 2,
            "elevation_m": 60.0,
            "connectivity_degree": 6,
            "accessibility_score": 0.85,
            "weather_point_dist_km": 3.0,
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
            "surface": "asphalt",
            "lanes": 2,
            "elevation_m": 70.0,
            "connectivity_degree": 6,
            "accessibility_score": 0.85,
            "weather_point_dist_km": 3.5,
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
            "surface": "asphalt",
            "lanes": 2,
            "elevation_m": 65.0,
            "connectivity_degree": 5,
            "accessibility_score": 0.75,
            "weather_point_dist_km": 4.0,
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
            "surface": "asphalt",
            "lanes": 2,
            "elevation_m": 75.0,
            "connectivity_degree": 5,
            "accessibility_score": 0.75,
            "weather_point_dist_km": 4.5,
            "active_incident_ids": [],
            "is_blocked": False,
        },
    ]


@pytest.fixture
def sample_incident() -> Dict[str, Any]:
    """Incident centered along seg_AB with impact radius that affects seg_AB."""
    return {
        "incident_id": "inc_landslide_001",
        "latitude": 26.125,
        "longitude": 91.725,
        "incident_type": "landslide",
        "severity": 0.85,
        "impact_radius_km": 5.0,
    }


@pytest.fixture
def sample_current_route() -> Dict[str, Any]:
    """Operational shipment route following Path 1."""
    return {
        "shipment_id": "ship_001",
        "route_id": "route_current",
        "assigned_route_segment_ids": ["seg_AB", "seg_BD"],
        "origin": {"latitude": 26.10, "longitude": 91.70},
        "destination": {"latitude": 26.20, "longitude": 91.80},
        "weather": {
            "weather_code": 61,
            "precipitation_mm": 15.0,
            "rain_mm": 15.0,
            "precipitation_hours": 4.0,
            "temperature_c": 22.0,
            "temperature_max_c": 25.0,
            "temperature_min_c": 19.0,
            "wind_speed_kmh": 20.0,
            "wind_gust_kmh": 30.0,
            "weather_severity_daily": 0.40,
        },
        "date": "2024-06-15",
    }


@pytest.fixture
def complete_risk_context() -> Dict[str, float]:
    """Complete 6-factor deterministic risk context."""
    return {
        "incident_severity": 0.85,
        "accessibility_score": 0.80,
        "weather_severity": 0.40,
        "road_condition_score": 0.70,
        "network_criticality": 0.50,
        "current_delay_ratio": 0.20,
    }


def test_default_cp16_path_unaffected(sample_incident, sample_network, sample_current_route, complete_risk_context):
    """When include_ml_assessment=False (default), recommendation matches CP16 behavior without ML keys."""
    rec = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=False,
    )

    assert "recommendation_id" in rec
    assert rec["recommendation_status"] == "PENDING_APPROVAL"
    assert rec["approval_required"] is True
    assert "ml_assessment" not in rec

    for r in rec["ranked_routes"]:
        assert "ml_assessment" not in r

    for exp in rec["explanations"]:
        assert "ml_advisory" not in exp


def test_opt_in_ml_advisory_attached(sample_incident, sample_network, sample_current_route, complete_risk_context):
    """When include_ml_assessment=True with engine, ML assessment is attached to rec and routes."""
    mock_model = MockPredictProbaModel(prob=0.42)
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    rec = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=True,
        ml_engine=engine,
    )

    assert "ml_assessment" in rec
    assert rec["ml_assessment"]["status"] == "AVAILABLE", f"ML Assessment: {rec['ml_assessment']}"
    assert "route_assessments" in rec["ml_assessment"]


    # Each ranked route carries its ML assessment
    for r in rec["ranked_routes"]:
        assert "ml_assessment" in r
        assert r["ml_assessment"]["status"] == "AVAILABLE"
        assert r["ml_assessment"]["length_weighted_mean_disruption_probability"] == 0.42
        assert r["ml_assessment"]["peak_segment_disruption_probability"] == 0.42
        # Prob 0.42 >= 0.30 -> disrupted
        assert r["ml_assessment"]["disrupted_segment_count"] == r["segment_count"]

    # Explanations surface ml_advisory
    for exp in rec["explanations"]:
        assert "ml_advisory" in exp
        assert exp["ml_advisory"]["status"] == "AVAILABLE"
        assert exp["ml_advisory"]["length_weighted_mean_disruption_probability"] == 0.42


def test_ranking_scores_and_order_identical_with_and_without_ml(
    sample_incident, sample_network, sample_current_route, complete_risk_context
):
    """Ranking scores, normalized utility, weights, and candidate ordering must be 100% identical."""
    mock_model = MockPredictProbaModel(prob=0.88)
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    rec_without_ml = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=False,
    )

    rec_with_ml = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=True,
        ml_engine=engine,
    )

    routes_no_ml = rec_without_ml["ranked_routes"]
    routes_with_ml = rec_with_ml["ranked_routes"]

    assert len(routes_no_ml) == len(routes_with_ml)
    assert rec_without_ml["recommended_route_id"] == rec_with_ml["recommended_route_id"]

    for r_base, r_ml in zip(routes_no_ml, routes_with_ml):
        assert r_base["route_id"] == r_ml["route_id"]
        assert r_base["rank"] == r_ml["rank"]
        assert r_base["ranking_score"] == r_ml["ranking_score"]
        assert r_base["normalized_scores"] == r_ml["normalized_scores"]
        assert r_base["weights_applied"] == r_ml["weights_applied"]
        assert r_base["metrics"] == r_ml["metrics"]


def test_potentially_affected_segments_never_automatically_blocked(
    sample_incident, sample_network, sample_current_route, complete_risk_context
):
    """Network Impact identifies seg_AB as impacted, but ML prediction does NOT block it."""
    mock_model = MockPredictProbaModel(prob=0.99)  # Very high disruption probability
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    rec = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        confirmed_blocked_segment_ids=[],  # Explicitly zero confirmed blockages
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=True,
        ml_engine=engine,
    )

    # seg_AB is in impacted_segment_ids
    assert "seg_AB" in rec["impacted_segment_ids"]
    # But confirmed_blocked_segment_ids is strictly empty
    assert rec["confirmed_blocked_segment_ids"] == []

    # seg_AB is NOT blocked and can still appear in alternative route candidates
    all_generated_segment_ids = set()
    for r in rec["ranked_routes"]:
        all_generated_segment_ids.update(r["segment_ids"])
    assert "seg_AB" in all_generated_segment_ids


def test_missing_model_produces_explicit_unavailable_status(
    sample_incident, sample_network, sample_current_route, complete_risk_context
):
    """When model artifact is absent on disk, reroute continues cleanly with status UNAVAILABLE."""
    fake_engine = DisruptionInferenceEngine(model_path=Path("models/non_existent_rf.joblib"))

    rec = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=True,
        ml_engine=fake_engine,
    )

    # Reroute succeeds deterministically
    assert rec["recommendation_status"] == "PENDING_APPROVAL"
    assert len(rec["ranked_routes"]) > 0

    # ML assessment reports UNAVAILABLE with reason
    assert "ml_assessment" in rec
    assert rec["ml_assessment"]["status"] == "UNAVAILABLE"

    for r in rec["ranked_routes"]:
        assert r["ml_assessment"]["status"] == "UNAVAILABLE"
        assert "not found" in r["ml_assessment"]["reason"].lower()


def test_approval_lifecycle_and_state_immutability(
    sample_incident, sample_network, sample_current_route, complete_risk_context
):
    """Approval lifecycle invariant: state unchanged before approval, updated only after approval."""
    mock_model = MockPredictProbaModel(prob=0.25)
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    state = DigitalTwinState()
    for seg in sample_network:
        state.add_segment(seg)

    # Add initial shipment
    state.add_shipment({
        "shipment_id": "ship_001",
        "status": "in_transit",
        "origin": "Node_A",
        "destination": "Node_D",
        "assigned_vehicle_id": None,
        "assigned_route_segment_ids": ["seg_AB", "seg_BD"],
        "dispatched_at": "2024-06-15T08:00:00Z",
    })


    rec = create_reroute_recommendation(
        incident=sample_incident,
        network_segments=sample_network,
        current_route=sample_current_route,
        confirmed_blocked_segment_ids=["seg_AB"],
        risk_context=complete_risk_context,
        k=2,
        include_ml_assessment=True,
        ml_engine=engine,
    )

    # 1. State must remain unchanged before approval
    assert state.shipments["ship_001"]["assigned_route_segment_ids"] == ["seg_AB", "seg_BD"]
    assert rec["recommendation_status"] == "PENDING_APPROVAL"

    # 2. Rejection must not alter state
    rec_rejected = reject_reroute_recommendation(rec, rejected_by="operator_raj", reason="Operational hold")
    assert rec_rejected["recommendation_status"] == "REJECTED"
    assert state.shipments["ship_001"]["assigned_route_segment_ids"] == ["seg_AB", "seg_BD"]

    # 3. Explicit approval updates state
    rec_approved = approve_reroute_recommendation(
        rec,
        approved_by="operator_raj",
        state=state,
        reason="Severe landslide bypass",
    )
    assert rec_approved["recommendation_status"] == "APPROVED"
    assert rec_approved["approval_required"] is False
    # Operational route updated to alternative route (seg_AC, seg_CD)
    assert state.shipments["ship_001"]["assigned_route_segment_ids"] == ["seg_AC", "seg_CD"]
