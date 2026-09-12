"""SETU Thin Digital Twin Foundation - Event Layer.

Pure, deterministic event validation and state transition handlers.
Modifies operational state only; never triggers implicit ETA or Risk recalculation.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from src.digital_twin.state import (
    DigitalTwinState,
    DigitalTwinValidationError,
    VALID_SHIPMENT_STATUSES,
    _validate_coord,
    _validate_incident,
)
from src.impact.network_impact import assess_network_impact

SUPPORTED_EVENT_TYPES = frozenset({
    "incident_created",
    "vehicle_location_updated",
    "shipment_status_changed",
    "route_approved",
    "route_changed",
})


def _validate_event_envelope(event: Mapping[str, Any]) -> Tuple[str, str, str, Dict[str, Any]]:
    """Validate top-level event structure and required fields."""
    if not isinstance(event, Mapping):
        raise DigitalTwinValidationError(f"Expected event mapping, got {type(event).__name__}")

    event_id = event.get("event_id")
    if event_id is None or not isinstance(event_id, str) or not event_id.strip():
        raise DigitalTwinValidationError("Event must contain a non-empty string 'event_id'")

    event_type = event.get("event_type")
    if event_type is None or not isinstance(event_type, str) or not event_type.strip():
        raise DigitalTwinValidationError("Event must contain a non-empty string 'event_type'")

    clean_type = event_type.strip()
    if clean_type not in SUPPORTED_EVENT_TYPES:
        raise DigitalTwinValidationError(
            f"Unsupported event_type '{clean_type}'. Supported: {sorted(SUPPORTED_EVENT_TYPES)}"
        )

    timestamp = event.get("timestamp")
    if timestamp is None or not isinstance(timestamp, str) or not timestamp.strip():
        raise DigitalTwinValidationError("Event must contain a non-empty string 'timestamp'")

    payload = event.get("payload")
    if payload is None or not isinstance(payload, Mapping):
        raise DigitalTwinValidationError("Event must contain a mapping 'payload'")

    return event_id.strip(), clean_type, timestamp.strip(), dict(payload)


def _handle_incident_created(state: DigitalTwinState, payload: Dict[str, Any]) -> None:
    """Handle incident creation: validate, store, and record affected segments via Network Impact.

    Strict Rule: Only marks a segment is_blocked=True if is_confirmed_closure is True.
    Does NOT invent or apply a custom disruption-factor formula.
    """
    validated_inc = _validate_incident(payload)
    inc_id = validated_inc["incident_id"]

    if inc_id in state.incidents:
        raise DigitalTwinValidationError(f"Incident '{inc_id}' already exists in state")

    # Use existing Network Impact Engine to determine spatially affected segments
    impact_assessment = assess_network_impact(validated_inc, state.network.values())
    affected_segment_ids = set(impact_assessment["affected_segment_ids"])

    is_confirmed_closure = validated_inc["is_confirmed_closure"]

    # Record incident-to-segment relationship on affected segments
    for seg_id in affected_segment_ids:
        seg = state.network[seg_id]
        if inc_id not in seg["active_incident_ids"]:
            seg["active_incident_ids"].append(inc_id)

        # Only set is_blocked if confirmed closure was explicitly provided
        if is_confirmed_closure:
            seg["is_blocked"] = True

    state.incidents[inc_id] = validated_inc


def _handle_vehicle_location_updated(
    state: DigitalTwinState,
    payload: Dict[str, Any],
    timestamp: str,
) -> None:
    """Handle vehicle location update: updates coordinates and current segment while preserving profile."""
    veh_id = payload.get("vehicle_id")
    if veh_id is None or str(veh_id).strip() not in state.vehicles:
        raise DigitalTwinValidationError(f"Vehicle '{veh_id}' not found in operational state")
    veh_id_str = str(veh_id).strip()

    lat = _validate_coord("latitude", payload.get("latitude"), -90.0, 90.0)
    lon = _validate_coord("longitude", payload.get("longitude"), -180.0, 180.0)

    vehicle = state.vehicles[veh_id_str]
    vehicle["current_latitude"] = lat
    vehicle["current_longitude"] = lon
    vehicle["last_updated_timestamp"] = timestamp

    current_seg = payload.get("current_segment_id")
    if current_seg is not None:
        seg_str = str(current_seg).strip()
        if seg_str and seg_str not in state.network:
            raise DigitalTwinValidationError(
                f"Vehicle '{veh_id_str}' references non-existent road segment '{seg_str}'"
            )
        vehicle["current_segment_id"] = seg_str if seg_str else None


def _handle_shipment_status_changed(state: DigitalTwinState, payload: Dict[str, Any]) -> None:
    """Handle shipment operational lifecycle status transition."""
    ship_id = payload.get("shipment_id")
    if ship_id is None or str(ship_id).strip() not in state.shipments:
        raise DigitalTwinValidationError(f"Shipment '{ship_id}' not found in operational state")
    ship_id_str = str(ship_id).strip()

    new_status = payload.get("new_status")
    if not isinstance(new_status, str) or new_status.strip().upper() not in VALID_SHIPMENT_STATUSES:
        raise DigitalTwinValidationError(
            f"Invalid new_status '{new_status}'. Expected one of {sorted(VALID_SHIPMENT_STATUSES)}"
        )

    state.shipments[ship_id_str]["status"] = new_status.strip().upper()
    if "reason" in payload and payload["reason"] is not None:
        state.shipments[ship_id_str]["status_change_reason"] = str(payload["reason"]).strip()


def _handle_route_approved(
    state: DigitalTwinState,
    payload: Dict[str, Any],
    timestamp: str,
) -> None:
    """Handle route approval: stores approved route and operator credentials."""
    ship_id = payload.get("shipment_id")
    if ship_id is None or str(ship_id).strip() not in state.shipments:
        raise DigitalTwinValidationError(f"Shipment '{ship_id}' not found in operational state")
    ship_id_str = str(ship_id).strip()

    route_segs = payload.get("route_segment_ids")
    if not isinstance(route_segs, (list, tuple)) or not route_segs:
        raise DigitalTwinValidationError("Field 'route_segment_ids' must be a non-empty list of segment IDs")

    validated_route: list[str] = []
    for seg_id in route_segs:
        s_str = str(seg_id).strip()
        if s_str not in state.network:
            raise DigitalTwinValidationError(
                f"Approved route for shipment '{ship_id_str}' references non-existent segment '{s_str}'"
            )
        validated_route.append(s_str)

    approved_by = payload.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise DigitalTwinValidationError("Field 'approved_by' must be a non-empty operator identifier")

    shipment = state.shipments[ship_id_str]
    shipment["approved_route_segment_ids"] = validated_route
    shipment["approved_by"] = approved_by.strip()
    shipment["approved_at"] = payload.get("approval_timestamp", timestamp).strip()


def _handle_route_changed(state: DigitalTwinState, payload: Dict[str, Any]) -> None:
    """Handle route change: updates assigned route and transitions status to REROUTED if in-transit."""
    ship_id = payload.get("shipment_id")
    if ship_id is None or str(ship_id).strip() not in state.shipments:
        raise DigitalTwinValidationError(f"Shipment '{ship_id}' not found in operational state")
    ship_id_str = str(ship_id).strip()

    new_segs = payload.get("new_route_segment_ids")
    if not isinstance(new_segs, (list, tuple)) or not new_segs:
        raise DigitalTwinValidationError("Field 'new_route_segment_ids' must be a non-empty list of segment IDs")

    validated_route: list[str] = []
    for seg_id in new_segs:
        s_str = str(seg_id).strip()
        if s_str not in state.network:
            raise DigitalTwinValidationError(
                f"New route for shipment '{ship_id_str}' references non-existent segment '{s_str}'"
            )
        validated_route.append(s_str)

    shipment = state.shipments[ship_id_str]
    shipment["assigned_route_segment_ids"] = validated_route
    if "reason" in payload and payload["reason"] is not None:
        shipment["route_change_reason"] = str(payload["reason"]).strip()

    if shipment["status"] == "IN_TRANSIT":
        shipment["status"] = "REROUTED"


def apply_event(state: DigitalTwinState, event: Mapping[str, Any]) -> DigitalTwinState:
    """Apply an operational event deterministically to the Digital Twin state.

    Modifies operational state only; does NOT trigger implicit ETA or Risk calculation.

    Args:
        state: Live or scenario DigitalTwinState instance.
        event: Validated event envelope dictionary.

    Returns:
        The mutated state instance.
    """
    event_id, event_type, timestamp, payload = _validate_event_envelope(event)

    if event_type == "incident_created":
        _handle_incident_created(state, payload)
    elif event_type == "vehicle_location_updated":
        _handle_vehicle_location_updated(state, payload, timestamp)
    elif event_type == "shipment_status_changed":
        _handle_shipment_status_changed(state, payload)
    elif event_type == "route_approved":
        _handle_route_approved(state, payload, timestamp)
    elif event_type == "route_changed":
        _handle_route_changed(state, payload)

    return state
