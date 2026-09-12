"""SETU Incident-to-Reroute Orchestration Layer (Checkpoint 16).

Deterministic orchestration loop:
Incident → Network Impact → Explicit Confirmed Blockage → Route Candidate Generation
→ Route Ranking → Route Explanation → Human Approval → Operational Route Change.

Architectural Boundaries & Separation of Concerns:
- AI Recommends: Produces decision support with structured ranking and explanations.
- Backend/Orchestration Coordinates: Integrates Network Impact, Routing, Ranking, and Explanation.
- Operator Approves: Recommendation remains PENDING_APPROVAL until explicitly approved.
- Operational Change: ONLY explicit approval updates the operational route.

Critical Semantic Rule:
- Potentially Affected != Blocked.
- A detected incident identifies potentially affected segments via Network Impact.
- Segments are NEVER automatically blocked based on incident severity, radius, weather,
  risk score, accessibility, ETA, or any heuristic.
- ONLY explicitly supplied confirmed_blocked_segment_ids are excluded from alternative
  route generation.

Zero-Dependency Rule:
- Pure Python standard library only.
- No external routing APIs (no Mapbox, OSRM, Google Maps).
- No live weather, traffic APIs, ML, LLMs, RAG, databases, Kafka, Redis, or services.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from src.digital_twin.events import apply_event
from src.digital_twin.state import DigitalTwinState
from src.explanation.route_explanation import (
    RouteExplanationValidationError,
    explain_ranked_routes,
)
from src.impact.network_impact import (
    NetworkImpactValidationError,
    assess_network_impact,
)
from src.routing.route_candidates import (
    RouteCandidateValidationError,
    generate_route_candidates,
)
from src.routing.route_ranking import (
    RouteRankingValidationError,
    rank_route_candidates,
)


class IncidentRerouteValidationError(ValueError):
    """Raised when incident parameters, route context, blockage specifications, or approval states are invalid."""
    pass


REROUTE_HONESTY_DISCLOSURE: str = (
    "1. Incident Impact vs Closure: Spatial impact assessment identifies road segments "
    "that are POTENTIALLY AFFECTED within the incident radius. Potentially affected does NOT "
    "equal confirmed closure. Segments are never automatically blocked based on incident severity, "
    "radius, weather, or heuristics. "
    "2. Confirmed Blockages: Only segments explicitly supplied in confirmed_blocked_segment_ids "
    "are excluded from alternative route generation. "
    "3. Decision Support: Route ranking and explanations provide deterministic decision-support suggestions; "
    "they do not make autonomous routing decisions. "
    "4. Vehicle Profile Compatibility Proxy: Evaluation uses OSM road hierarchy and surface data from ETA Engine v0.1; "
    "it is a compatibility PROXY only, NOT a guarantee of physical vehicle clearance or weight compliance. "
    "5. Operational Verification: Live road conditions, weather, and physical passability are not independently verified. "
    "6. Operator Authority: Explicit operator approval is mandatory before any operational route change is executed."
)


def _resolve_route_endpoints(
    current_route: Mapping[str, Any],
    network_by_id: Mapping[str, Mapping[str, Any]],
    explicit_origin: Optional[Mapping[str, Any]] = None,
    explicit_destination: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Resolve origin and destination coordinate mappings for alternative routing."""
    # 1. Check explicit arguments
    orig_dict: Optional[Dict[str, float]] = None
    dest_dict: Optional[Dict[str, float]] = None

    if explicit_origin is not None:
        if not isinstance(explicit_origin, Mapping) or "latitude" not in explicit_origin or "longitude" not in explicit_origin:
            raise IncidentRerouteValidationError("Explicit origin must be a mapping with 'latitude' and 'longitude'")
        orig_dict = {"latitude": float(explicit_origin["latitude"]), "longitude": float(explicit_origin["longitude"])}

    if explicit_destination is not None:
        if not isinstance(explicit_destination, Mapping) or "latitude" not in explicit_destination or "longitude" not in explicit_destination:
            raise IncidentRerouteValidationError("Explicit destination must be a mapping with 'latitude' and 'longitude'")
        dest_dict = {"latitude": float(explicit_destination["latitude"]), "longitude": float(explicit_destination["longitude"])}

    # 2. Check current_route attributes
    if orig_dict is None and "origin" in current_route and isinstance(current_route["origin"], Mapping):
        o_map = current_route["origin"]
        if "latitude" in o_map and "longitude" in o_map:
            orig_dict = {"latitude": float(o_map["latitude"]), "longitude": float(o_map["longitude"])}

    if dest_dict is None and "destination" in current_route and isinstance(current_route["destination"], Mapping):
        d_map = current_route["destination"]
        if "latitude" in d_map and "longitude" in d_map:
            dest_dict = {"latitude": float(d_map["latitude"]), "longitude": float(d_map["longitude"])}

    if orig_dict is None and "origin_latitude" in current_route and "origin_longitude" in current_route:
        orig_dict = {
            "latitude": float(current_route["origin_latitude"]),
            "longitude": float(current_route["origin_longitude"]),
        }

    if dest_dict is None and "destination_latitude" in current_route and "destination_longitude" in current_route:
        dest_dict = {
            "latitude": float(current_route["destination_latitude"]),
            "longitude": float(current_route["destination_longitude"]),
        }

    # 3. Infer from segments in current_route if available
    route_seg_ids: List[str] = []
    if "segment_ids" in current_route and isinstance(current_route["segment_ids"], list):
        route_seg_ids = [str(sid) for sid in current_route["segment_ids"]]
    elif "assigned_route_segment_ids" in current_route and isinstance(current_route["assigned_route_segment_ids"], list):
        route_seg_ids = [str(sid) for sid in current_route["assigned_route_segment_ids"]]
    elif "route_segment_ids" in current_route and isinstance(current_route["route_segment_ids"], list):
        route_seg_ids = [str(sid) for sid in current_route["route_segment_ids"]]

    if route_seg_ids:
        first_seg_id = route_seg_ids[0]
        last_seg_id = route_seg_ids[-1]

        if orig_dict is None and first_seg_id in network_by_id:
            s_first = network_by_id[first_seg_id]
            if "start_latitude" in s_first and "start_longitude" in s_first:
                orig_dict = {
                    "latitude": float(s_first["start_latitude"]),
                    "longitude": float(s_first["start_longitude"]),
                }
            elif "latitude" in s_first and "longitude" in s_first:
                orig_dict = {
                    "latitude": float(s_first["latitude"]),
                    "longitude": float(s_first["longitude"]),
                }

        if dest_dict is None and last_seg_id in network_by_id:
            s_last = network_by_id[last_seg_id]
            if "end_latitude" in s_last and "end_longitude" in s_last:
                dest_dict = {
                    "latitude": float(s_last["end_latitude"]),
                    "longitude": float(s_last["end_longitude"]),
                }
            elif "latitude" in s_last and "longitude" in s_last:
                dest_dict = {
                    "latitude": float(s_last["latitude"]),
                    "longitude": float(s_last["longitude"]),
                }

    if orig_dict is None:
        raise IncidentRerouteValidationError(
            "Current route context does not provide valid origin coordinates (latitude/longitude)"
        )
    if dest_dict is None:
        raise IncidentRerouteValidationError(
            "Current route context does not provide valid destination coordinates (latitude/longitude)"
        )

    return orig_dict, dest_dict


def create_reroute_recommendation(
    incident: Mapping[str, Any],
    network_segments: Iterable[Mapping[str, Any]],
    current_route: Mapping[str, Any],
    confirmed_blocked_segment_ids: Optional[Iterable[str]] = None,
    *,
    origin: Optional[Mapping[str, Any]] = None,
    destination: Optional[Mapping[str, Any]] = None,
    k: int = 3,
    risk_context: Optional[Mapping[str, Any]] = None,
    vehicle_profile: Optional[str] = None,
    vehicle_speed_factor: Optional[float] = None,
    custom_ranking_weights: Optional[Mapping[str, float]] = None,
    recommendation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a structured, deterministic reroute recommendation for human operator approval.

    Workflow:
    1. Validates the incident and evaluates potentially affected segments using Network Impact.
    2. Validates confirmed_blocked_segment_ids (never assumes affected segments are blocked).
    3. Generates alternative route candidates excluding ONLY explicitly confirmed blocked segments.
    4. Ranks candidate routes using the approved normalized utility model.
    5. Explains ranked routes with comparative tradeoffs and honesty disclosures.
    6. Produces a structured recommendation in 'PENDING_APPROVAL' state.
    7. Does NOT alter operational shipment or route state.

    Args:
        incident: Incident dictionary with latitude, longitude, incident_type, severity, impact_radius_km.
        network_segments: Iterable of network road segment dictionaries.
        current_route: Mapping with current route details or shipment operational record.
        confirmed_blocked_segment_ids: Explicit collection of confirmed closed/blocked segment IDs.
        origin: Optional explicit origin mapping {'latitude': ..., 'longitude': ...}.
        destination: Optional explicit destination mapping {'latitude': ..., 'longitude': ...}.
        k: Number of alternative route candidates to generate (>= 1).
        risk_context: Complete explicit risk context if candidates lack precomputed risk_score.
        vehicle_profile: Vehicle profile identifier (e.g. 'standard_truck').
        vehicle_speed_factor: Custom vehicle speed factor multiplier.
        custom_ranking_weights: Optional custom ranking weights.
        recommendation_id: Optional custom recommendation identifier.

    Returns:
        Structured recommendation dictionary ready for operator review.
    """
    # 1. Validate inputs and preserve caller immutability
    if incident is None:
        raise IncidentRerouteValidationError("Expected incident to be a mapping, got None")
    if not isinstance(incident, Mapping):
        raise IncidentRerouteValidationError(f"Expected incident to be a mapping, got {type(incident).__name__}")

    if current_route is None:
        raise IncidentRerouteValidationError("Expected current_route to be a mapping, got None")
    if not isinstance(current_route, Mapping):
        raise IncidentRerouteValidationError(f"Expected current_route to be a mapping, got {type(current_route).__name__}")

    if network_segments is None:
        raise IncidentRerouteValidationError("Expected network_segments to be an iterable, got None")
    if isinstance(network_segments, (str, bytes, Mapping)):
        raise IncidentRerouteValidationError(
            f"Expected network_segments to be an iterable of segment mappings, got {type(network_segments).__name__}"
        )

    try:
        raw_seg_list = list(network_segments)
    except TypeError as exc:
        raise IncidentRerouteValidationError(f"network_segments must be iterable: {exc}") from exc

    if not raw_seg_list:
        raise IncidentRerouteValidationError("Network segments collection is empty; cannot evaluate routes")

    # Index network segments by ID and validate segment dictionaries
    network_by_id: Dict[str, Dict[str, Any]] = {}
    for idx, s in enumerate(raw_seg_list):
        if not isinstance(s, Mapping):
            raise IncidentRerouteValidationError(f"Segment at index {idx} must be a mapping, got {type(s).__name__}")
        sid = s.get("segment_id")
        if sid is None or not str(sid).strip():
            raise IncidentRerouteValidationError(f"Segment at index {idx} missing 'segment_id'")
        sid_str = str(sid).strip()
        network_by_id[sid_str] = dict(s)

    # 2. Assess Network Impact (potentially affected infrastructure)
    try:
        impact_result = assess_network_impact(incident, list(network_by_id.values()))
    except NetworkImpactValidationError as exc:
        raise IncidentRerouteValidationError(f"Invalid incident: {exc}") from exc

    impacted_segment_ids = sorted(impact_result["affected_segment_ids"])

    # 3. Validate confirmed blocked segment IDs
    # CRITICAL SEMANTIC RULE: Do NOT automatically block impacted segments!
    confirmed_blocked_list: List[str] = []
    if confirmed_blocked_segment_ids is not None:
        if isinstance(confirmed_blocked_segment_ids, (str, bytes)):
            raise IncidentRerouteValidationError(
                "confirmed_blocked_segment_ids must be an iterable of string segment IDs, not a string"
            )
        try:
            raw_blocked = list(confirmed_blocked_segment_ids)
        except TypeError as exc:
            raise IncidentRerouteValidationError(
                f"confirmed_blocked_segment_ids must be iterable: {exc}"
            ) from exc

        for b_id in raw_blocked:
            if b_id is None or not str(b_id).strip():
                raise IncidentRerouteValidationError("Confirmed blocked segment IDs must be non-empty strings")
            b_str = str(b_id).strip()
            # Strictly reject blocked IDs that are not valid network segment IDs
            if b_str not in network_by_id:
                raise IncidentRerouteValidationError(
                    f"Confirmed blocked segment '{b_str}' does not exist in network segments"
                )
            confirmed_blocked_list.append(b_str)

    confirmed_blocked_set = set(confirmed_blocked_list)

    # 4. Resolve origin and destination
    orig_coords, dest_coords = _resolve_route_endpoints(
        current_route,
        network_by_id,
        explicit_origin=origin,
        explicit_destination=destination,
    )

    # 5. Generate Route Candidates (Excluding ONLY explicitly confirmed blocked segments)
    try:
        raw_candidates = generate_route_candidates(
            network_segments=list(network_by_id.values()),
            origin=orig_coords,
            destination=dest_coords,
            k=k,
            blocked_segment_ids=confirmed_blocked_set,
        )
    except RouteCandidateValidationError as exc:
        raise IncidentRerouteValidationError(f"Cannot generate route candidates: {exc}") from exc

    if not raw_candidates:
        raise IncidentRerouteValidationError("Route candidate generator produced zero candidates")

    # 6. Rank Route Candidates
    resolved_risk_context = risk_context
    if resolved_risk_context is None and isinstance(current_route, Mapping):
        if "risk_context" in current_route and isinstance(current_route["risk_context"], Mapping):
            resolved_risk_context = current_route["risk_context"]

    try:
        ranked_candidates = rank_route_candidates(
            raw_candidates,
            risk_context=resolved_risk_context,
            vehicle_profile=vehicle_profile,
            vehicle_speed_factor=vehicle_speed_factor,
            custom_weights=custom_ranking_weights,
        )
    except RouteRankingValidationError as exc:
        raise IncidentRerouteValidationError(f"Route ranking failed: {exc}") from exc

    # 7. Explain Ranked Routes
    try:
        explanations = explain_ranked_routes(ranked_candidates)
    except RouteExplanationValidationError as exc:
        raise IncidentRerouteValidationError(f"Route explanation failed: {exc}") from exc

    # 8. Deterministic Recommendation ID
    if recommendation_id is not None and str(recommendation_id).strip():
        rec_id = str(recommendation_id).strip()
    else:
        hash_payload = (
            str(impact_result["incident"].get("incident_id", "inc")),
            round(orig_coords["latitude"], 6),
            round(orig_coords["longitude"], 6),
            round(dest_coords["latitude"], 6),
            round(dest_coords["longitude"], 6),
            tuple(sorted(confirmed_blocked_set)),
            k,
        )
        h_str = hashlib.sha256(str(hash_payload).encode("utf-8")).hexdigest()[:8]
        rec_id = f"rec_{h_str}"

    recommended_route_id = ranked_candidates[0]["route_id"]

    return {
        "recommendation_id": rec_id,
        "incident": dict(impact_result["incident"]),
        "impacted_segment_ids": impacted_segment_ids,
        "confirmed_blocked_segment_ids": sorted(confirmed_blocked_set),
        "current_route": dict(current_route),
        "alternative_routes": raw_candidates,
        "ranked_routes": ranked_candidates,
        "explanations": explanations,
        "recommended_route_id": recommended_route_id,
        "recommendation_status": "PENDING_APPROVAL",
        "approval_required": True,
        "honesty_disclosure": REROUTE_HONESTY_DISCLOSURE,
    }


def approve_reroute_recommendation(
    recommendation: Mapping[str, Any],
    approved_by: str,
    state: Optional[DigitalTwinState] = None,
    *,
    selected_route_id: Optional[str] = None,
    event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Approve a pending reroute recommendation and apply the operational route change.

    Workflow:
    1. Validates recommendation is in 'PENDING_APPROVAL' state.
    2. Validates explicit non-empty approved_by operator identifier.
    3. Selects the target route (recommended_route_id or chosen selected_route_id).
    4. If a DigitalTwinState is provided, applies the route_changed event to update operational state.
    5. Returns an approved recommendation dictionary with status 'APPROVED' and approval_required=False.

    Args:
        recommendation: A valid reroute recommendation dictionary.
        approved_by: Non-empty string identifying the human operator.
        state: Optional DigitalTwinState instance to execute the operational state update.
        selected_route_id: Optional route_id to approve (defaults to recommended_route_id).
        event_id: Optional custom Digital Twin event ID.
        timestamp: Optional ISO timestamp.
        reason: Optional route change reason string.

    Returns:
        Approved recommendation dictionary with status 'APPROVED'.
    """
    if recommendation is None:
        raise IncidentRerouteValidationError("Expected recommendation to be a mapping, got None")
    if not isinstance(recommendation, Mapping):
        raise IncidentRerouteValidationError(
            f"Expected recommendation to be a mapping, got {type(recommendation).__name__}"
        )

    rec_status = recommendation.get("recommendation_status")
    if rec_status != "PENDING_APPROVAL":
        raise IncidentRerouteValidationError(
            f"Cannot approve recommendation with status '{rec_status}'; status must be 'PENDING_APPROVAL'"
        )

    if not approved_by or not isinstance(approved_by, str) or not approved_by.strip():
        raise IncidentRerouteValidationError(
            "Approval requires an explicit, non-empty 'approved_by' operator identifier"
        )

    target_route_id = selected_route_id or recommendation.get("recommended_route_id")
    if not target_route_id:
        raise IncidentRerouteValidationError("Recommendation has no recommended_route_id or selected_route_id")

    ranked_routes = recommendation.get("ranked_routes", [])
    matched_candidate = next((r for r in ranked_routes if r.get("route_id") == target_route_id), None)
    if matched_candidate is None:
        raise IncidentRerouteValidationError(
            f"Selected route '{target_route_id}' not found in recommendation's ranked_routes"
        )

    new_segment_ids = list(matched_candidate.get("segment_ids", []))
    approval_time = timestamp.strip() if (timestamp and str(timestamp).strip()) else "2026-09-13T00:00:00Z"
    rec_id = recommendation.get("recommendation_id", "rec_unknown")

    # If operational state is supplied, apply route_changed event
    applied_event: Optional[Dict[str, Any]] = None
    if state is not None:
        if not isinstance(state, DigitalTwinState):
            raise IncidentRerouteValidationError(
                f"Expected state to be a DigitalTwinState instance, got {type(state).__name__}"
            )

        current_route = recommendation.get("current_route", {})
        shipment_id = current_route.get("shipment_id")

        if shipment_id is not None and str(shipment_id).strip():
            ship_id_str = str(shipment_id).strip()
            if ship_id_str not in state.shipments:
                raise IncidentRerouteValidationError(
                    f"Shipment '{ship_id_str}' referenced in current_route not found in Digital Twin state"
                )

            route_evt_id = event_id or f"evt_rc_{rec_id}_{approval_time.replace(':', '').replace('-', '')}"
            event_envelope = {
                "event_id": route_evt_id,
                "event_type": "route_changed",
                "timestamp": approval_time,
                "payload": {
                    "shipment_id": ship_id_str,
                    "new_route_segment_ids": new_segment_ids,
                    "reason": reason or f"Approved reroute recommendation {rec_id} by {approved_by.strip()}",
                },
            }
            apply_event(state, event_envelope)
            applied_event = event_envelope

    approved_record = copy.deepcopy(dict(recommendation))
    approved_record["recommendation_status"] = "APPROVED"
    approved_record["approval_required"] = False
    approved_record["approved_by"] = approved_by.strip()
    approved_record["approved_at"] = approval_time
    approved_record["applied_route_id"] = target_route_id
    approved_record["applied_route_segment_ids"] = new_segment_ids
    if applied_event is not None:
        approved_record["applied_event"] = applied_event

    return approved_record


def reject_reroute_recommendation(
    recommendation: Mapping[str, Any],
    rejected_by: str,
    *,
    reason: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Explicitly reject a pending reroute recommendation without altering operational state.

    Args:
        recommendation: A valid reroute recommendation dictionary.
        rejected_by: Non-empty string identifying the human operator.
        reason: Optional rejection reason string.
        timestamp: Optional ISO timestamp.

    Returns:
        Rejected recommendation dictionary with status 'REJECTED' and approval_required=False.
    """
    if recommendation is None:
        raise IncidentRerouteValidationError("Expected recommendation to be a mapping, got None")
    if not isinstance(recommendation, Mapping):
        raise IncidentRerouteValidationError(
            f"Expected recommendation to be a mapping, got {type(recommendation).__name__}"
        )

    rec_status = recommendation.get("recommendation_status")
    if rec_status != "PENDING_APPROVAL":
        raise IncidentRerouteValidationError(
            f"Cannot reject recommendation with status '{rec_status}'; status must be 'PENDING_APPROVAL'"
        )

    if not rejected_by or not isinstance(rejected_by, str) or not rejected_by.strip():
        raise IncidentRerouteValidationError(
            "Rejection requires an explicit, non-empty 'rejected_by' operator identifier"
        )

    rejection_time = timestamp.strip() if (timestamp and str(timestamp).strip()) else "2026-09-13T00:00:00Z"

    rejected_record = copy.deepcopy(dict(recommendation))
    rejected_record["recommendation_status"] = "REJECTED"
    rejected_record["approval_required"] = False
    rejected_record["rejected_by"] = rejected_by.strip()
    rejected_record["rejected_at"] = rejection_time
    rejected_record["rejection_reason"] = reason or "Rejected by human operator"

    return rejected_record
