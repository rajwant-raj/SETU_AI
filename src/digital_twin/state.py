"""SETU Thin Digital Twin Foundation - State Model.

Deterministic, in-memory state representation of the operational logistics network,
including road segments, vehicles, shipments, and incidents.

Separation of Concerns:
The Digital Twin owns operational state, entity validation, and deep-copy cloning.
It contains zero intelligence formulas; calculations are delegated to dedicated engines.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

VALID_SHIPMENT_STATUSES = frozenset({
    "PENDING",
    "IN_TRANSIT",
    "DELAYED",
    "REROUTED",
    "DELIVERED",
    "CANCELLED",
})


class DigitalTwinValidationError(ValueError):
    """Raised when digital twin entities, coordinates, references, or events are invalid."""
    pass


def _validate_numeric(field_name: str, val: Any, min_val: float | None = None, max_val: float | None = None) -> float:
    """Validate that a value is a finite number within optional bounds."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise DigitalTwinValidationError(
            f"Field '{field_name}' must be numeric, got {type(val).__name__} ({val!r})"
        )
    f_val = float(val)
    if not math.isfinite(f_val):
        raise DigitalTwinValidationError(f"Field '{field_name}' must be finite, got {f_val}")
    if min_val is not None and f_val < min_val:
        raise DigitalTwinValidationError(f"Field '{field_name}' must be >= {min_val}, got {f_val}")
    if max_val is not None and f_val > max_val:
        raise DigitalTwinValidationError(f"Field '{field_name}' must be <= {max_val}, got {f_val}")
    return f_val


def _validate_coord(field_name: str, val: Any, min_val: float, max_val: float) -> float:
    """Validate geographic coordinates."""
    return _validate_numeric(field_name, val, min_val, max_val)


def _validate_segment(segment: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate road segment data dictionary."""
    if not isinstance(segment, Mapping):
        raise DigitalTwinValidationError(f"Expected segment mapping, got {type(segment).__name__}")

    segment_id = segment.get("segment_id")
    if segment_id is None or str(segment_id).strip() == "":
        raise DigitalTwinValidationError("Segment must contain a non-empty 'segment_id'")
    seg_id_str = str(segment_id).strip()

    road_type = segment.get("road_type")
    if not isinstance(road_type, str) or not road_type.strip():
        raise DigitalTwinValidationError(f"Segment '{seg_id_str}' must contain a non-empty 'road_type'")

    seg_dict = dict(segment)
    seg_dict["segment_id"] = seg_id_str
    seg_dict["road_type"] = road_type.strip().lower()

    # Validate distance if present
    if "segment_length_km" in segment and segment["segment_length_km"] is not None:
        seg_dict["segment_length_km"] = _validate_numeric(
            "segment_length_km", segment["segment_length_km"], min_val=0.0
        )

    # Validate coordinate bounds if provided
    for coord_key, min_b, max_b in [
        ("latitude", -90.0, 90.0),
        ("longitude", -180.0, 180.0),
        ("start_latitude", -90.0, 90.0),
        ("start_longitude", -180.0, 180.0),
        ("end_latitude", -90.0, 90.0),
        ("end_longitude", -180.0, 180.0),
    ]:
        if coord_key in segment and segment[coord_key] is not None:
            seg_dict[coord_key] = _validate_coord(coord_key, segment[coord_key], min_b, max_b)

    # Status flags
    seg_dict["is_blocked"] = bool(segment.get("is_blocked", False))
    active_incidents = segment.get("active_incident_ids", [])
    if not isinstance(active_incidents, (list, tuple, set)):
        raise DigitalTwinValidationError(f"Segment '{seg_id_str}' active_incident_ids must be a sequence")
    seg_dict["active_incident_ids"] = [str(inc).strip() for inc in active_incidents if str(inc).strip()]

    return seg_dict


def _validate_vehicle(vehicle: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate vehicle data dictionary."""
    if not isinstance(vehicle, Mapping):
        raise DigitalTwinValidationError(f"Expected vehicle mapping, got {type(vehicle).__name__}")

    vehicle_id = vehicle.get("vehicle_id")
    if vehicle_id is None or str(vehicle_id).strip() == "":
        raise DigitalTwinValidationError("Vehicle must contain a non-empty 'vehicle_id'")
    veh_id_str = str(vehicle_id).strip()

    veh_dict = dict(vehicle)
    veh_dict["vehicle_id"] = veh_id_str

    profile = vehicle.get("vehicle_profile", "standard_truck")
    if not isinstance(profile, (str, int, float)):
        raise DigitalTwinValidationError(f"Vehicle '{veh_id_str}' vehicle_profile must be string or numeric factor")
    veh_dict["vehicle_profile"] = profile.strip() if isinstance(profile, str) else float(profile)

    if "current_latitude" in vehicle and vehicle["current_latitude"] is not None:
        veh_dict["current_latitude"] = _validate_coord("current_latitude", vehicle["current_latitude"], -90.0, 90.0)
    if "current_longitude" in vehicle and vehicle["current_longitude"] is not None:
        veh_dict["current_longitude"] = _validate_coord("current_longitude", vehicle["current_longitude"], -180.0, 180.0)

    if "current_segment_id" in vehicle and vehicle["current_segment_id"] is not None:
        veh_dict["current_segment_id"] = str(vehicle["current_segment_id"]).strip()

    if "assigned_shipment_id" in vehicle and vehicle["assigned_shipment_id"] is not None:
        veh_dict["assigned_shipment_id"] = str(vehicle["assigned_shipment_id"]).strip()

    return veh_dict


def _validate_shipment(
    shipment: Mapping[str, Any],
    network: Mapping[str, Any],
    vehicles: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate shipment data dictionary and referential integrity against network and vehicles."""
    if not isinstance(shipment, Mapping):
        raise DigitalTwinValidationError(f"Expected shipment mapping, got {type(shipment).__name__}")

    shipment_id = shipment.get("shipment_id")
    if shipment_id is None or str(shipment_id).strip() == "":
        raise DigitalTwinValidationError("Shipment must contain a non-empty 'shipment_id'")
    ship_id_str = str(shipment_id).strip()

    status = shipment.get("status", "PENDING")
    if not isinstance(status, str) or status.strip().upper() not in VALID_SHIPMENT_STATUSES:
        raise DigitalTwinValidationError(
            f"Shipment '{ship_id_str}' status must be one of {sorted(VALID_SHIPMENT_STATUSES)}, got {status!r}"
        )
    status_str = status.strip().upper()

    ship_dict = dict(shipment)
    ship_dict["shipment_id"] = ship_id_str
    ship_dict["status"] = status_str

    # Referential check: assigned_vehicle_id
    assigned_veh = shipment.get("assigned_vehicle_id")
    if assigned_veh is not None:
        veh_str = str(assigned_veh).strip()
        if veh_str and veh_str not in vehicles:
            raise DigitalTwinValidationError(
                f"Shipment '{ship_id_str}' references non-existent vehicle '{veh_str}'"
            )
        ship_dict["assigned_vehicle_id"] = veh_str if veh_str else None
    else:
        ship_dict["assigned_vehicle_id"] = None

    # Referential check: assigned_route_segment_ids
    route_segs = shipment.get("assigned_route_segment_ids", [])
    if not isinstance(route_segs, (list, tuple)):
        raise DigitalTwinValidationError(f"Shipment '{ship_id_str}' assigned_route_segment_ids must be a list")

    validated_route: List[str] = []
    for seg_id in route_segs:
        s_id_str = str(seg_id).strip()
        if s_id_str not in network:
            raise DigitalTwinValidationError(
                f"Shipment '{ship_id_str}' route references non-existent network segment '{s_id_str}'"
            )
        validated_route.append(s_id_str)
    ship_dict["assigned_route_segment_ids"] = validated_route

    # Approved route
    appr_segs = shipment.get("approved_route_segment_ids")
    if appr_segs is not None:
        if not isinstance(appr_segs, (list, tuple)):
            raise DigitalTwinValidationError(f"Shipment '{ship_id_str}' approved_route_segment_ids must be a list")
        validated_appr: List[str] = []
        for seg_id in appr_segs:
            s_id_str = str(seg_id).strip()
            if s_id_str not in network:
                raise DigitalTwinValidationError(
                    f"Shipment '{ship_id_str}' approved route references non-existent network segment '{s_id_str}'"
                )
            validated_appr.append(s_id_str)
        ship_dict["approved_route_segment_ids"] = validated_appr
    else:
        ship_dict["approved_route_segment_ids"] = None

    return ship_dict


def _validate_incident(incident: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate incident data dictionary."""
    if not isinstance(incident, Mapping):
        raise DigitalTwinValidationError(f"Expected incident mapping, got {type(incident).__name__}")

    incident_id = incident.get("incident_id")
    if incident_id is None or str(incident_id).strip() == "":
        raise DigitalTwinValidationError("Incident must contain a non-empty 'incident_id'")
    inc_id_str = str(incident_id).strip()

    inc_type = incident.get("incident_type")
    if not isinstance(inc_type, str) or not inc_type.strip():
        raise DigitalTwinValidationError(f"Incident '{inc_id_str}' must contain a non-empty 'incident_type'")

    lat = _validate_coord("latitude", incident.get("latitude"), -90.0, 90.0)
    lon = _validate_coord("longitude", incident.get("longitude"), -180.0, 180.0)
    severity = _validate_numeric("severity", incident.get("severity"), min_val=0.0, max_val=1.0)
    radius = _validate_numeric("impact_radius_km", incident.get("impact_radius_km"), min_val=0.0)

    is_confirmed_closure = bool(incident.get("is_confirmed_closure", False))
    status = incident.get("status", "ACTIVE")
    if not isinstance(status, str) or status.strip().upper() not in ("ACTIVE", "RESOLVED"):
        raise DigitalTwinValidationError(f"Incident '{inc_id_str}' status must be ACTIVE or RESOLVED")

    inc_dict = dict(incident)
    inc_dict["incident_id"] = inc_id_str
    inc_dict["incident_type"] = inc_type.strip()
    inc_dict["latitude"] = lat
    inc_dict["longitude"] = lon
    inc_dict["severity"] = severity
    inc_dict["impact_radius_km"] = radius
    inc_dict["is_confirmed_closure"] = is_confirmed_closure
    inc_dict["status"] = status.strip().upper()

    return inc_dict


@dataclass
class DigitalTwinState:
    """In-memory operational state container for SETU."""

    network: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    vehicles: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    shipments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    incidents: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate initial collections and enforce referential integrity."""
        validated_network: Dict[str, Dict[str, Any]] = {}
        for seg_id, seg in self.network.items():
            s_dict = _validate_segment(seg)
            if s_dict["segment_id"] != str(seg_id):
                raise DigitalTwinValidationError(
                    f"Segment key '{seg_id}' does not match segment_id '{s_dict['segment_id']}'"
                )
            validated_network[s_dict["segment_id"]] = s_dict
        self.network = validated_network

        validated_vehicles: Dict[str, Dict[str, Any]] = {}
        for veh_id, veh in self.vehicles.items():
            v_dict = _validate_vehicle(veh)
            if v_dict["vehicle_id"] != str(veh_id):
                raise DigitalTwinValidationError(
                    f"Vehicle key '{veh_id}' does not match vehicle_id '{v_dict['vehicle_id']}'"
                )
            validated_vehicles[v_dict["vehicle_id"]] = v_dict
        self.vehicles = validated_vehicles

        validated_shipments: Dict[str, Dict[str, Any]] = {}
        for ship_id, ship in self.shipments.items():
            sh_dict = _validate_shipment(ship, self.network, self.vehicles)
            if sh_dict["shipment_id"] != str(ship_id):
                raise DigitalTwinValidationError(
                    f"Shipment key '{ship_id}' does not match shipment_id '{sh_dict['shipment_id']}'"
                )
            validated_shipments[sh_dict["shipment_id"]] = sh_dict
        self.shipments = validated_shipments

        validated_incidents: Dict[str, Dict[str, Any]] = {}
        for inc_id, inc in self.incidents.items():
            i_dict = _validate_incident(inc)
            if i_dict["incident_id"] != str(inc_id):
                raise DigitalTwinValidationError(
                    f"Incident key '{inc_id}' does not match incident_id '{i_dict['incident_id']}'"
                )
            validated_incidents[i_dict["incident_id"]] = i_dict
        self.incidents = validated_incidents

    def clone(self) -> "DigitalTwinState":
        """Produce an isolated deep-copy of the state for scenario evaluation."""
        return copy.deepcopy(self)

    def to_dict(self) -> Dict[str, Any]:
        """Return a clean serializable snapshot of the operational state."""
        return {
            "network": {k: dict(v) for k, v in self.network.items()},
            "vehicles": {k: dict(v) for k, v in self.vehicles.items()},
            "shipments": {k: dict(v) for k, v in self.shipments.items()},
            "incidents": {k: dict(v) for k, v in self.incidents.items()},
        }

    def add_segment(self, segment: Mapping[str, Any]) -> None:
        """Add a single road segment to the network state."""
        seg_dict = _validate_segment(segment)
        seg_id = seg_dict["segment_id"]
        if seg_id in self.network:
            raise DigitalTwinValidationError(f"Segment '{seg_id}' already exists in network")
        self.network[seg_id] = seg_dict

    def add_vehicle(self, vehicle: Mapping[str, Any]) -> None:
        """Add a vehicle to the operational state."""
        veh_dict = _validate_vehicle(vehicle)
        veh_id = veh_dict["vehicle_id"]
        if veh_id in self.vehicles:
            raise DigitalTwinValidationError(f"Vehicle '{veh_id}' already exists")
        self.vehicles[veh_id] = veh_dict

    def add_shipment(self, shipment: Mapping[str, Any]) -> None:
        """Add a shipment to the operational state, validating route segments against network."""
        ship_dict = _validate_shipment(shipment, self.network, self.vehicles)
        ship_id = ship_dict["shipment_id"]
        if ship_id in self.shipments:
            raise DigitalTwinValidationError(f"Shipment '{ship_id}' already exists")
        self.shipments[ship_id] = ship_dict

    def add_incident(self, incident: Mapping[str, Any]) -> None:
        """Add an incident directly to the incident collection."""
        inc_dict = _validate_incident(incident)
        inc_id = inc_dict["incident_id"]
        if inc_id in self.incidents:
            raise DigitalTwinValidationError(f"Incident '{inc_id}' already exists")
        self.incidents[inc_id] = inc_dict
