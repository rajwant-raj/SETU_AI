"""SETU Network Impact Engine v0.1.

Deterministic spatial engine to identify potentially affected road segments
around a geolocated field incident.

Uses local road geometry and lightweight standard-library geographic calculations
without heavy GIS or external API dependencies.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Tuple

EARTH_RADIUS_KM = 6371.0088

REQUIRED_INCIDENT_FIELDS: Tuple[str, ...] = (
    "latitude",
    "longitude",
    "incident_type",
    "severity",
    "impact_radius_km",
)


class NetworkImpactValidationError(ValueError):
    """Raised when incident inputs or segment geometries are missing, invalid, or out of range."""
    pass


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance between two WGS84 coordinates in kilometers."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2.0) ** 2
    )
    # Guard against precision float rounding exceeding 1.0
    a_clamped = max(0.0, min(1.0, a))
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a_clamped))


def point_to_segment_distance_km(
    p_lat: float,
    p_lon: float,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> float:
    """Return shortest geographic distance from point P to line segment AB in km.

    Uses equirectangular projection centered at point P for flat-Earth 2D projection,
    then evaluates great-circle distance to the closest point on segment AB.
    """
    # Degenerate segment: start and end are the same point
    if math.isclose(start_lat, end_lat, abs_tol=1e-9) and math.isclose(start_lon, end_lon, abs_tol=1e-9):
        return haversine_km(p_lat, p_lon, start_lat, start_lon)

    # Local equirectangular projection around (p_lat, p_lon)
    lat_ref_rad = math.radians(p_lat)
    cos_lat = math.cos(lat_ref_rad)
    deg_to_rad = math.pi / 180.0

    # Incident point P is at origin (0, 0)
    # A = start, B = end
    ax = (start_lon - p_lon) * deg_to_rad * EARTH_RADIUS_KM * cos_lat
    ay = (start_lat - p_lat) * deg_to_rad * EARTH_RADIUS_KM

    bx = (end_lon - p_lon) * deg_to_rad * EARTH_RADIUS_KM * cos_lat
    by = (end_lat - p_lat) * deg_to_rad * EARTH_RADIUS_KM

    # Segment vector V = B - A
    vx = bx - ax
    vy = by - ay
    v_len_sq = vx * vx + vy * vy

    if v_len_sq <= 1e-14:
        return haversine_km(p_lat, p_lon, start_lat, start_lon)

    # Vector AP = P - A = (0 - ax, 0 - ay) = (-ax, -ay)
    # Projection factor t = (AP . V) / |V|^2
    t = (-ax * vx - ay * vy) / v_len_sq

    if t <= 0.0:
        return haversine_km(p_lat, p_lon, start_lat, start_lon)
    elif t >= 1.0:
        return haversine_km(p_lat, p_lon, end_lat, end_lon)
    else:
        closest_lat = start_lat + t * (end_lat - start_lat)
        closest_lon = start_lon + t * (end_lon - start_lon)
        return haversine_km(p_lat, p_lon, closest_lat, closest_lon)


def _validate_numeric(field: str, val: Any) -> float:
    """Validate that val is a finite float or int (not bool)."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise NetworkImpactValidationError(
            f"Field '{field}' must be numeric, got {type(val).__name__} ({val!r})"
        )
    fval = float(val)
    if not math.isfinite(fval):
        raise NetworkImpactValidationError(
            f"Field '{field}' must be a finite number, got {fval}"
        )
    return fval


def _validate_latitude(field: str, val: Any) -> float:
    """Validate that latitude is numeric and within [-90.0, 90.0]."""
    lat = _validate_numeric(field, val)
    if not (-90.0 <= lat <= 90.0):
        raise NetworkImpactValidationError(
            f"Field '{field}' must be between -90 and 90, got {lat}"
        )
    return lat


def _validate_longitude(field: str, val: Any) -> float:
    """Validate that longitude is numeric and within [-180.0, 180.0]."""
    lon = _validate_numeric(field, val)
    if not (-180.0 <= lon <= 180.0):
        raise NetworkImpactValidationError(
            f"Field '{field}' must be between -180 and 180, got {lon}"
        )
    return lon


def _validate_incident(incident: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate incident input dictionary."""
    if not isinstance(incident, Mapping):
        raise NetworkImpactValidationError(
            f"Expected incident to be a mapping/dict, got {type(incident).__name__}"
        )

    missing = [f for f in REQUIRED_INCIDENT_FIELDS if f not in incident or incident[f] is None]
    if missing:
        raise NetworkImpactValidationError(
            f"Missing required incident fields: {', '.join(missing)}"
        )

    lat = _validate_latitude("latitude", incident["latitude"])
    lon = _validate_longitude("longitude", incident["longitude"])

    incident_type = incident["incident_type"]
    if not isinstance(incident_type, str) or not incident_type.strip():
        raise NetworkImpactValidationError(
            f"Incident 'incident_type' must be a non-empty string, got {incident_type!r}"
        )

    severity = _validate_numeric("severity", incident["severity"])
    if not (0.0 <= severity <= 1.0):
        raise NetworkImpactValidationError(
            f"Incident 'severity' must be between 0.0 and 1.0, got {severity}"
        )

    radius = _validate_numeric("impact_radius_km", incident["impact_radius_km"])
    if radius < 0.0:
        raise NetworkImpactValidationError(
            f"Incident 'impact_radius_km' must be non-negative (>= 0.0), got {radius}"
        )

    return {
        "latitude": lat,
        "longitude": lon,
        "incident_type": incident_type.strip(),
        "severity": severity,
        "impact_radius_km": radius,
    }


def _calculate_segment_distance(
    incident_lat: float,
    incident_lon: float,
    segment: Mapping[str, Any],
) -> Tuple[float, float, float]:
    """Calculate distance from incident point to road segment and resolve validated (lat, lon)."""
    has_endpoints = (
        "start_latitude" in segment
        and "start_longitude" in segment
        and "end_latitude" in segment
        and "end_longitude" in segment
        and segment["start_latitude"] is not None
        and segment["start_longitude"] is not None
        and segment["end_latitude"] is not None
        and segment["end_longitude"] is not None
    )

    has_midpoint = (
        "latitude" in segment
        and "longitude" in segment
        and segment["latitude"] is not None
        and segment["longitude"] is not None
    )

    if has_endpoints:
        s_lat = _validate_latitude("start_latitude", segment["start_latitude"])
        s_lon = _validate_longitude("start_longitude", segment["start_longitude"])
        e_lat = _validate_latitude("end_latitude", segment["end_latitude"])
        e_lon = _validate_longitude("end_longitude", segment["end_longitude"])
        dist_km = point_to_segment_distance_km(incident_lat, incident_lon, s_lat, s_lon, e_lat, e_lon)

        if has_midpoint:
            m_lat = _validate_latitude("latitude", segment["latitude"])
            m_lon = _validate_longitude("longitude", segment["longitude"])
        else:
            m_lat = (s_lat + e_lat) / 2.0
            m_lon = (s_lon + e_lon) / 2.0

        return dist_km, m_lat, m_lon

    if has_midpoint:
        m_lat = _validate_latitude("latitude", segment["latitude"])
        m_lon = _validate_longitude("longitude", segment["longitude"])
        dist_km = haversine_km(incident_lat, incident_lon, m_lat, m_lon)
        return dist_km, m_lat, m_lon

    segment_id = segment.get("segment_id", "<unknown>")
    raise NetworkImpactValidationError(
        f"Segment '{segment_id}' must provide either endpoint coordinates "
        "(start_latitude, start_longitude, end_latitude, end_longitude) "
        "or midpoint coordinates (latitude, longitude)"
    )


def assess_network_impact(
    incident: Mapping[str, Any],
    segments: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Assess potential network impact by finding all road segments within the incident impact radius.

    Args:
        incident: Mapping containing required incident fields:
            - latitude: float [-90.0, 90.0]
            - longitude: float [-180.0, 180.0]
            - incident_type: str (non-empty)
            - severity: float [0.0, 1.0]
            - impact_radius_km: float >= 0.0
        segments: Iterable of road segment dictionaries.

    Returns:
        Structured deterministic dictionary:
        {
            "incident": Dict[str, Any],
            "impact_radius_km": float,
            "affected_segment_count": int,
            "affected_segment_ids": List[str],
            "affected_segments": List[Dict[str, Any]],
        }

    Raises:
        NetworkImpactValidationError: If incident parameters or segment records are invalid.
    """
    validated_incident = _validate_incident(incident)
    inc_lat = validated_incident["latitude"]
    inc_lon = validated_incident["longitude"]
    radius_km = validated_incident["impact_radius_km"]

    if segments is None:
        raise NetworkImpactValidationError("Expected segments to be an iterable, got None")

    affected_segments: List[Dict[str, Any]] = []

    for seg in segments:
        if not isinstance(seg, Mapping):
            raise NetworkImpactValidationError(
                f"Expected each segment to be a mapping/dict, got {type(seg).__name__}"
            )

        segment_id = seg.get("segment_id")
        if segment_id is None or str(segment_id).strip() == "":
            raise NetworkImpactValidationError("Each segment must contain a non-empty 'segment_id'")

        dist_km, resolved_lat, resolved_lon = _calculate_segment_distance(inc_lat, inc_lon, seg)

        # Segments within radius (inclusive) are potentially affected
        if dist_km <= radius_km:
            # Preserve all original segment metadata and append computed distance
            seg_record = dict(seg)
            seg_record["distance_km"] = round(dist_km, 6)

            # Ensure baseline standard keys are explicitly populated without fabricating coordinates
            if "road_type" not in seg_record:
                seg_record["road_type"] = ""
            seg_record["latitude"] = resolved_lat
            seg_record["longitude"] = resolved_lon

            affected_segments.append(seg_record)

    # Deterministic sorting: distance ascending, then segment_id ascending
    affected_segments.sort(key=lambda s: (s["distance_km"], str(s["segment_id"])))

    affected_segment_ids = [str(s["segment_id"]) for s in affected_segments]

    return {
        "incident": validated_incident,
        "impact_radius_km": radius_km,
        "affected_segment_count": len(affected_segments),
        "affected_segment_ids": affected_segment_ids,
        "affected_segments": affected_segments,
    }


# Convenient alias
find_affected_segments = assess_network_impact
