"""SETU Thin Digital Twin Foundation - Orchestration & Composition.

Thin composition helpers that delegate to existing deterministic engines:
- Network Impact Engine (src/impact/network_impact.py)
- Accessibility Scorer (src/accessibility/accessibility_scorer.py)
- ETA / Delay Engine (src/eta/eta_engine.py)
- Risk Engine v0.1 (src/risk/risk_engine.py)

Contains ZERO intelligence math or duplicate formulas.
Strictly adheres to the Risk Engine v0.1 input contract without fabricating missing values.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from src.accessibility.accessibility_scorer import calculate_accessibility
from src.digital_twin.state import DigitalTwinState, DigitalTwinValidationError
from src.eta.eta_engine import estimate_route_eta
from src.impact.network_impact import assess_network_impact
from src.risk.risk_engine import calculate_risk

REQUIRED_EXTERNAL_RISK_CONTEXT_FIELDS = frozenset({
    "weather_severity",
    "road_condition_score",
    "network_criticality",
})


def evaluate_shipment_eta(
    state: DigitalTwinState,
    shipment_id: str,
) -> Dict[str, Any]:
    """Evaluate baseline and disrupted ETA for a shipment by composing the ETA Engine.

    Args:
        state: Operational Digital Twin state.
        shipment_id: Target shipment identifier.

    Returns:
        Structured output dictionary directly from src.eta.eta_engine.estimate_route_eta.
    """
    if shipment_id not in state.shipments:
        raise DigitalTwinValidationError(f"Shipment '{shipment_id}' not found in state")

    shipment = state.shipments[shipment_id]
    route_ids: List[str] = shipment.get("assigned_route_segment_ids", [])
    if not route_ids:
        raise DigitalTwinValidationError(f"Shipment '{shipment_id}' has no assigned route segments to evaluate")

    # Fetch segment mappings from network state
    segments = [state.network[seg_id] for seg_id in route_ids]

    # Resolve vehicle profile from assigned vehicle if present
    vehicle_profile: Any = "standard_truck"
    assigned_veh_id = shipment.get("assigned_vehicle_id")
    if assigned_veh_id and assigned_veh_id in state.vehicles:
        vehicle_profile = state.vehicles[assigned_veh_id].get("vehicle_profile", "standard_truck")

    if isinstance(vehicle_profile, (int, float)):
        return estimate_route_eta(segments, vehicle_speed_factor=float(vehicle_profile))
    return estimate_route_eta(segments, vehicle_profile=str(vehicle_profile))


def evaluate_segment_accessibility(
    state: DigitalTwinState,
    segment_id: str,
) -> Dict[str, Any]:
    """Evaluate infrastructure accessibility for a segment by composing the Accessibility Scorer."""
    if segment_id not in state.network:
        raise DigitalTwinValidationError(f"Segment '{segment_id}' not found in network state")

    return calculate_accessibility(state.network[segment_id])


def evaluate_incident_impact(
    state: DigitalTwinState,
    incident: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate spatial impact of an incident across the network via Network Impact Engine."""
    return assess_network_impact(incident, state.network.values())


def evaluate_shipment_risk(
    state: DigitalTwinState,
    shipment_id: str,
    risk_context: Mapping[str, Any],
) -> Dict[str, Any]:
    """Evaluate comprehensive operational risk for a shipment by composing Risk, ETA, and Accessibility.

    Strict Rule: Requires all external risk context fields (weather_severity, road_condition_score,
    network_criticality). Will NOT fabricate or default missing values.

    Args:
        state: Operational Digital Twin state.
        shipment_id: Target shipment identifier.
        risk_context: Mapping providing required external inputs:
            - weather_severity: float in [0, 1]
            - road_condition_score: float in [0, 1]
            - network_criticality: float in [0, 1]

    Returns:
        Structured output dictionary directly from src.risk.risk_engine.calculate_risk.
    """
    if not isinstance(risk_context, Mapping):
        raise DigitalTwinValidationError(f"Expected risk_context mapping, got {type(risk_context).__name__}")

    missing = [f for f in REQUIRED_EXTERNAL_RISK_CONTEXT_FIELDS if f not in risk_context or risk_context[f] is None]
    if missing:
        raise DigitalTwinValidationError(
            f"Missing required external Risk Engine context fields: {sorted(missing)}. "
            "Digital Twin never fabricates missing Risk inputs."
        )

    # 1. Composed ETA signal -> normalized_delay_ratio
    eta_result = evaluate_shipment_eta(state, shipment_id)
    current_delay_ratio = float(eta_result["normalized_delay_ratio"])

    # 2. Composed Accessibility signal -> average accessibility across route segments
    shipment = state.shipments[shipment_id]
    route_ids = shipment["assigned_route_segment_ids"]

    acc_scores: List[float] = []
    active_incidents_on_route: List[str] = []

    for seg_id in route_ids:
        seg = state.network[seg_id]
        acc_eval = calculate_accessibility(seg)
        acc_scores.append(float(acc_eval["accessibility_score"]))
        for inc_id in seg.get("active_incident_ids", []):
            if inc_id not in active_incidents_on_route:
                active_incidents_on_route.append(inc_id)

    route_accessibility = sum(acc_scores) / len(acc_scores) if acc_scores else 1.0

    # 3. Composed Incident signal -> max severity of overlapping active incidents
    incident_severity = 0.0
    for inc_id in active_incidents_on_route:
        if inc_id in state.incidents:
            inc = state.incidents[inc_id]
            if inc.get("status") == "ACTIVE":
                incident_severity = max(incident_severity, float(inc.get("severity", 0.0)))

    # 4. Delegate to pure Risk Engine v0.1
    risk_inputs = {
        "incident_severity": incident_severity,
        "accessibility_score": route_accessibility,
        "weather_severity": float(risk_context["weather_severity"]),
        "road_condition_score": float(risk_context["road_condition_score"]),
        "network_criticality": float(risk_context["network_criticality"]),
        "current_delay_ratio": current_delay_ratio,
    }

    return calculate_risk(risk_inputs)
