"""SETU Thin Digital Twin Foundation - What-If Scenario Simulation.

Enables isolated what-if scenario branching and delta comparison against baseline state.
Guarantees zero mutation of live baseline state.

Composes:
- ETA Engine for travel times and delay deltas
- Risk Engine v0.1 for risk score comparisons when explicit risk context is supplied
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from src.digital_twin.events import apply_event
from src.digital_twin.orchestration import evaluate_shipment_eta, evaluate_shipment_risk
from src.digital_twin.state import DigitalTwinState, DigitalTwinValidationError


def simulate_what_if(
    state: DigitalTwinState,
    scenario: Mapping[str, Any],
    risk_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute an isolated what-if simulation without mutating the live baseline state.

    Args:
        state: Live operational DigitalTwinState (treated as read-only baseline).
        scenario: Mapping of explicit scenario modifications:
            - scenario_id: Optional str
            - blocked_segment_ids: Optional sequence of segment IDs to mark is_blocked=True
            - speed_reductions: Optional Mapping[segment_id, ratio in [0, 1]]
            - simulated_incidents: Optional sequence of incident dicts to apply as events
        risk_context: Optional Mapping of required external Risk Engine inputs:
            weather_severity, road_condition_score, network_criticality.
            If provided, Risk is evaluated and compared for both baseline and scenario.

    Returns:
        Structured simulation comparison dictionary.
    """
    if not isinstance(scenario, Mapping):
        raise DigitalTwinValidationError(f"Expected scenario mapping, got {type(scenario).__name__}")

    scenario_id = str(scenario.get("scenario_id", "scenario_what_if")).strip()

    # 1. Deep clone baseline state for complete isolation
    scenario_state = state.clone()

    # 2. Apply explicit scenario overrides to scenario_state
    # A. Explicit blocked segments
    blocked_ids = scenario.get("blocked_segment_ids", [])
    if blocked_ids:
        if not isinstance(blocked_ids, (list, tuple, set)):
            raise DigitalTwinValidationError("Field 'blocked_segment_ids' must be a sequence of segment IDs")
        for seg_id in blocked_ids:
            s_str = str(seg_id).strip()
            if s_str not in scenario_state.network:
                raise DigitalTwinValidationError(
                    f"Scenario blocked segment '{s_str}' does not exist in network state"
                )
            scenario_state.network[s_str]["is_blocked"] = True

    # B. Explicit speed reductions
    speed_reds = scenario.get("speed_reductions", {})
    if speed_reds:
        if not isinstance(speed_reds, Mapping):
            raise DigitalTwinValidationError("Field 'speed_reductions' must be a mapping of segment_id -> ratio")
        for seg_id, ratio in speed_reds.items():
            s_str = str(seg_id).strip()
            if s_str not in scenario_state.network:
                raise DigitalTwinValidationError(
                    f"Scenario speed reduction segment '{s_str}' does not exist in network state"
                )
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not (0.0 <= float(ratio) <= 1.0):
                raise DigitalTwinValidationError(
                    f"Speed reduction ratio for segment '{s_str}' must be numeric in [0, 1], got {ratio!r}"
                )
            scenario_state.network[s_str]["speed_reduction_ratio"] = float(ratio)

    # C. Simulated incidents
    sim_incidents = scenario.get("simulated_incidents", [])
    if sim_incidents:
        if not isinstance(sim_incidents, (list, tuple)):
            raise DigitalTwinValidationError("Field 'simulated_incidents' must be a list of incident dicts")
        for idx, inc in enumerate(sim_incidents, start=1):
            if not isinstance(inc, Mapping):
                raise DigitalTwinValidationError("Each simulated incident must be a mapping")
            event = {
                "event_id": f"sim-event-{idx:04d}",
                "event_type": "incident_created",
                "timestamp": inc.get("timestamp", "2026-09-13T00:00:00Z"),
                "payload": dict(inc),
            }
            apply_event(scenario_state, event)

    # 3. Evaluate active shipments across both states
    baseline_summary: Dict[str, Dict[str, Any]] = {}
    scenario_summary: Dict[str, Dict[str, Any]] = {}

    delay_deltas: Dict[str, float] = {}
    newly_impassable_shipments: List[str] = []
    risk_score_deltas: Dict[str, float] = {}
    affected_shipment_ids: List[str] = []

    # Evaluate shipments in deterministic key order
    sorted_shipment_ids = sorted(state.shipments.keys())

    for ship_id in sorted_shipment_ids:
        shipment = state.shipments[ship_id]
        if not shipment.get("assigned_route_segment_ids"):
            continue

        # Baseline evaluation
        b_eta = evaluate_shipment_eta(state, ship_id)
        b_passable = bool(b_eta["is_passable"])
        b_delay = float(b_eta["delay_seconds"])

        b_risk_score: Optional[float] = None
        b_risk_level: Optional[str] = None
        if risk_context is not None:
            b_risk = evaluate_shipment_risk(state, ship_id, risk_context)
            b_risk_score = float(b_risk["risk_score"])
            b_risk_level = str(b_risk["risk_level"])

        baseline_summary[ship_id] = {
            "baseline_eta_seconds": b_eta["baseline_eta_seconds"],
            "disrupted_eta_seconds": b_eta["disrupted_eta_seconds"],
            "delay_seconds": b_delay,
            "delay_ratio": b_eta["delay_ratio"],
            "is_passable": b_passable,
            "risk_score": b_risk_score,
            "risk_level": b_risk_level,
        }

        # Scenario evaluation
        s_eta = evaluate_shipment_eta(scenario_state, ship_id)
        s_passable = bool(s_eta["is_passable"])
        s_delay = float(s_eta["delay_seconds"])

        s_risk_score: Optional[float] = None
        s_risk_level: Optional[str] = None
        if risk_context is not None:
            s_risk = evaluate_shipment_risk(scenario_state, ship_id, risk_context)
            s_risk_score = float(s_risk["risk_score"])
            s_risk_level = str(s_risk["risk_level"])

        scenario_summary[ship_id] = {
            "baseline_eta_seconds": s_eta["baseline_eta_seconds"],
            "disrupted_eta_seconds": s_eta["disrupted_eta_seconds"],
            "delay_seconds": s_delay,
            "delay_ratio": s_eta["delay_ratio"],
            "is_passable": s_passable,
            "risk_score": s_risk_score,
            "risk_level": s_risk_level,
        }

        # Compute Deltas
        delay_diff = round(s_delay - b_delay, 3)
        delay_deltas[ship_id] = delay_diff

        if b_passable and not s_passable:
            newly_impassable_shipments.append(ship_id)

        is_affected = False
        if delay_diff > 0.0 or (b_passable and not s_passable):
            is_affected = True

        if risk_context is not None and b_risk_score is not None and s_risk_score is not None:
            risk_diff = round(s_risk_score - b_risk_score, 2)
            risk_score_deltas[ship_id] = risk_diff
            if risk_diff > 0.0:
                is_affected = True

        if is_affected:
            affected_shipment_ids.append(ship_id)

    return {
        "scenario_id": scenario_id,
        "is_baseline_mutated": False,
        "evaluated_shipment_count": len(sorted_shipment_ids),
        "affected_shipment_count": len(affected_shipment_ids),
        "affected_shipment_ids": affected_shipment_ids,
        "newly_impassable_shipments": newly_impassable_shipments,
        "delay_deltas": delay_deltas,
        "risk_score_deltas": risk_score_deltas if risk_context is not None else None,
        "baseline_summary": baseline_summary,
        "scenario_summary": scenario_summary,
    }
