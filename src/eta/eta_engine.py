"""SETU Deterministic ETA and Delay Engine v0.1.

Estimates baseline free-flow travel time and disruption-adjusted travel time
from OSM-derived infrastructure data and optional disruption signals.
Calculates absolute delay, uncapped delay ratio, and normalized delay ratio
compatible with SETU Risk Engine v0.1.

IMPORTANT HONESTY CONTRACT:
Baseline speeds and travel times are deterministic infrastructure proxies derived
from OpenStreetMap road classes and recorded limits, not observed real-world GPS probe
traffic or telemetry.
"""

from __future__ import annotations

import math
import re
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from src.impact.network_impact import haversine_km

# Deterministic regional design-speed proxies by road hierarchy (km/h)
DEFAULT_SPEED_LIMITS_KMH: Mapping[str, float] = MappingProxyType({
    "motorway": 80.0,
    "trunk": 60.0,
    "primary": 50.0,
    "secondary": 40.0,
    "tertiary": 30.0,
    "unclassified": 25.0,
    "residential": 25.0,
    "service": 20.0,
    "other": 25.0,
})

# Deterministic physical road surface speed multipliers
DEFAULT_SURFACE_MODIFIERS: Mapping[str, float] = MappingProxyType({
    "paved": 1.00,
    "asphalt": 1.00,
    "concrete": 1.00,
    "concrete:lanes": 1.00,
    "concrete:plates": 1.00,
    "tar": 1.00,
    "compacted": 0.90,
    "paving_stones": 0.90,
    "sett": 0.90,
    "chipseal": 0.90,
    "cobblestone": 0.90,
    "unpaved": 0.75,
    "gravel": 0.75,
    "dirt": 0.75,
    "earth": 0.75,
    "mud": 0.75,
    "ground": 0.75,
    "sand": 0.75,
    "clay": 0.75,
})

# Deterministic vehicle profile multipliers
DEFAULT_VEHICLE_PROFILES: Mapping[str, float] = MappingProxyType({
    "standard_truck": 1.00,
    "heavy_truck": 0.85,
    "light_commercial": 1.15,
    "passenger": 1.25,
})

# Safety speed floor to avoid division by zero or infinite travel time
MIN_SPEED_KMH = 5.0

# Canonical blocked segment penalty in seconds (2 hours)
DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS = 7200.0

# Explicit disclosure requirement
HONESTY_DISCLOSURE = (
    "Baseline speeds and travel times are deterministic infrastructure proxies derived "
    "from OpenStreetMap road classes and recorded limits, not observed real-world GPS probe traffic or telemetry."
)


class ETAEngineValidationError(ValueError):
    """Raised when segment attributes, coordinates, vehicle, or disruptions are invalid."""
    pass


def _validate_coord(field: str, val: Any, min_val: float, max_val: float) -> float:
    """Validate that a coordinate is a finite numeric value within bounds."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ETAEngineValidationError(f"Field '{field}' must be numeric, got {type(val).__name__} ({val!r})")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ETAEngineValidationError(f"Field '{field}' must be a finite number, got {f_val}")
    if not (min_val <= f_val <= max_val):
        raise ETAEngineValidationError(f"Field '{field}' must be between {min_val} and {max_val}, got {f_val}")
    return f_val


def _parse_maxspeed(maxspeed: Any) -> float | None:
    """Parse recorded maxspeed in km/h if present, or return None if unrecorded."""
    if maxspeed is None:
        return None
    if isinstance(maxspeed, bool):
        raise ETAEngineValidationError("Field 'maxspeed' cannot be a boolean")

    if isinstance(maxspeed, str):
        clean_speed = maxspeed.strip().lower()
        if not clean_speed:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", clean_speed)
        if not match:
            raise ETAEngineValidationError(f"Invalid maxspeed format: {maxspeed!r}")
        raw_val = float(match.group(1))
        speed_kmh = raw_val * 1.60934 if "mph" in clean_speed else raw_val
    elif isinstance(maxspeed, (int, float)):
        if not math.isfinite(maxspeed):
            raise ETAEngineValidationError(f"Field 'maxspeed' must be a finite number, got {maxspeed}")
        speed_kmh = float(maxspeed)
    else:
        raise ETAEngineValidationError(
            f"Field 'maxspeed' must be an integer, float, or parseable string, got {type(maxspeed).__name__}"
        )

    if speed_kmh <= 0.0:
        raise ETAEngineValidationError(f"Field 'maxspeed' must be positive, got {speed_kmh}")

    return speed_kmh


def _get_surface_modifier(surface: Any) -> Tuple[float, bool]:
    """Return surface speed modifier in (0.0, 1.0] and boolean indicating unpaved status."""
    if surface is None:
        return 1.00, False
    if not isinstance(surface, str):
        raise ETAEngineValidationError(f"Field 'surface' must be a string if provided, got {type(surface).__name__}")
    clean_surface = surface.strip().lower()
    if not clean_surface:
        return 1.00, False

    if clean_surface in DEFAULT_SURFACE_MODIFIERS:
        mod = DEFAULT_SURFACE_MODIFIERS[clean_surface]
        is_unpaved = (mod <= 0.75)
        return mod, is_unpaved
    return 1.00, False


def _resolve_vehicle_speed_factor(
    profile: str | None = None,
    custom_factor: float | int | None = None,
) -> Tuple[str, float]:
    """Resolve vehicle profile name and speed factor deterministically."""
    if profile is not None and not isinstance(profile, str):
        raise ETAEngineValidationError(f"Vehicle profile must be a string, got {type(profile).__name__}")

    if custom_factor is not None:
        if isinstance(custom_factor, bool) or not isinstance(custom_factor, (int, float)):
            raise ETAEngineValidationError(f"Vehicle speed factor must be a number, got {type(custom_factor).__name__}")
        f_val = float(custom_factor)
        if not math.isfinite(f_val) or f_val <= 0.0:
            raise ETAEngineValidationError(f"Vehicle speed factor must be positive and finite, got {custom_factor}")

        if profile is not None:
            norm_profile = profile.strip().lower()
            if norm_profile in DEFAULT_VEHICLE_PROFILES:
                expected_factor = DEFAULT_VEHICLE_PROFILES[norm_profile]
                if not math.isclose(f_val, expected_factor, rel_tol=1e-5):
                    raise ETAEngineValidationError(
                        f"Conflicting vehicle profile '{profile}' (factor {expected_factor}) "
                        f"and custom speed factor {f_val}"
                    )
                return norm_profile, f_val
            return norm_profile, f_val
        return "custom", f_val

    if profile is None:
        return "standard_truck", DEFAULT_VEHICLE_PROFILES["standard_truck"]

    norm_profile = profile.strip().lower()
    if norm_profile not in DEFAULT_VEHICLE_PROFILES:
        raise ETAEngineValidationError(
            f"Unknown vehicle profile '{profile}'. Supported: {sorted(DEFAULT_VEHICLE_PROFILES.keys())}"
        )
    return norm_profile, DEFAULT_VEHICLE_PROFILES[norm_profile]


def _resolve_segment_distance(segment: Mapping[str, Any]) -> float:
    """Resolve and validate segment distance in km."""
    segment_id = segment.get("segment_id", "<unknown>")
    has_explicit_len = "segment_length_km" in segment and segment["segment_length_km"] is not None

    if has_explicit_len:
        val = segment["segment_length_km"]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ETAEngineValidationError(
                f"Field 'segment_length_km' on segment '{segment_id}' must be numeric, got {type(val).__name__}"
            )
        f_val = float(val)
        if not math.isfinite(f_val):
            raise ETAEngineValidationError(
                f"Field 'segment_length_km' on segment '{segment_id}' must be a finite number, got {f_val}"
            )
        if f_val < 0.0:
            raise ETAEngineValidationError(
                f"Field 'segment_length_km' on segment '{segment_id}' must be non-negative (>= 0.0), got {f_val}"
            )
        return f_val

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

    if has_endpoints:
        s_lat = _validate_coord("start_latitude", segment["start_latitude"], -90.0, 90.0)
        s_lon = _validate_coord("start_longitude", segment["start_longitude"], -180.0, 180.0)
        e_lat = _validate_coord("end_latitude", segment["end_latitude"], -90.0, 90.0)
        e_lon = _validate_coord("end_longitude", segment["end_longitude"], -180.0, 180.0)
        return haversine_km(s_lat, s_lon, e_lat, e_lon)

    raise ETAEngineValidationError(
        f"Segment '{segment_id}' must provide either 'segment_length_km' (>= 0.0) "
        "or valid endpoint coordinates (start_latitude, start_longitude, end_latitude, end_longitude)"
    )


def _resolve_base_speed(
    road_type: Any,
    maxspeed: Any,
    surface: Any,
    vehicle_factor: float,
) -> Tuple[float, float, str, str, bool]:
    """Resolve baseline and surface-adjusted speed in km/h.

    Returns:
        (raw_base_kmh, effective_base_kmh, speed_source, surface_desc, is_unpaved)
    """
    if not isinstance(road_type, str) or not road_type.strip():
        raise ETAEngineValidationError(f"Field 'road_type' must be a non-empty string, got {road_type!r}")
    clean_type = road_type.strip().lower()

    # 1. Valid recorded maxspeed proxy
    parsed_maxspeed = _parse_maxspeed(maxspeed)
    if parsed_maxspeed is not None:
        raw_base = parsed_maxspeed
        source = "recorded_maxspeed_proxy"
    else:
        # 2. Road type proxy
        raw_base = DEFAULT_SPEED_LIMITS_KMH.get(clean_type, DEFAULT_SPEED_LIMITS_KMH["other"])
        source = f"road_type_proxy_{clean_type}"

    # 3. Surface modifier
    surface_mod, is_unpaved = _get_surface_modifier(surface)
    surface_desc = surface.strip() if isinstance(surface, str) and surface.strip() else "unspecified"
    speed_after_surface = raw_base * surface_mod

    # 4. Vehicle factor and safety floor
    effective_base = max(MIN_SPEED_KMH, speed_after_surface * vehicle_factor)

    return raw_base, effective_base, source, surface_desc, is_unpaved


def _resolve_segment_disruption(
    segment: Mapping[str, Any],
) -> Tuple[str, float | None, bool]:
    """Validate disruption fields on segment ensuring no conflicting representations.

    Returns:
        (disruption_type, disruption_value, is_blocked)
        where disruption_type in ("none", "disruption_factor", "speed_reduction_ratio", "delay_seconds", "blocked")
    """
    disruption_fields = ["disruption_factor", "speed_reduction_ratio", "delay_seconds"]
    present = [f for f in disruption_fields if segment.get(f) is not None]

    if len(present) > 1:
        raise ETAEngineValidationError(
            f"Conflicting disruption representations on segment '{segment.get('segment_id', '<unknown>')}': "
            f"{present}. Exactly one disruption representation must be supplied."
        )

    is_blocked_flag = segment.get("is_blocked")
    if is_blocked_flag is not None:
        if not isinstance(is_blocked_flag, bool):
            raise ETAEngineValidationError(
                f"Field 'is_blocked' must be a boolean, got {type(is_blocked_flag).__name__}"
            )

    if present:
        field = present[0]
        val = segment[field]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ETAEngineValidationError(f"Field '{field}' must be numeric, got {type(val).__name__}")
        f_val = float(val)
        if not math.isfinite(f_val):
            raise ETAEngineValidationError(f"Field '{field}' must be a finite number, got {f_val}")

        if field in ("disruption_factor", "speed_reduction_ratio"):
            if not (0.0 <= f_val <= 1.0):
                raise ETAEngineValidationError(f"Field '{field}' must be between 0.0 and 1.0, got {f_val}")

            # Check for conflict with is_blocked flag
            if is_blocked_flag is False and f_val == 1.0:
                raise ETAEngineValidationError(
                    "Segment has is_blocked=False but disruption value is 1.0 (total blockage)"
                )
            if is_blocked_flag is True and f_val != 1.0:
                raise ETAEngineValidationError(
                    f"Segment has is_blocked=True but {field}={f_val} is not 1.0"
                )

            is_blocked = (f_val == 1.0 or is_blocked_flag is True)
            disr_type = "blocked" if is_blocked else field
            return disr_type, f_val, is_blocked

        elif field == "delay_seconds":
            if f_val < 0.0:
                raise ETAEngineValidationError(f"Field 'delay_seconds' must be non-negative (>= 0.0), got {f_val}")
            if is_blocked_flag is True:
                raise ETAEngineValidationError(
                    "Segment cannot specify both explicit delay_seconds and is_blocked=True"
                )
            return "delay_seconds", f_val, False

    if is_blocked_flag is True:
        return "blocked", 1.0, True

    return "none", None, False


def estimate_segment_eta(
    segment: Mapping[str, Any],
    vehicle_profile: str | None = None,
    vehicle_speed_factor: float | None = None,
) -> Dict[str, Any]:
    """Estimate deterministic baseline travel time and disrupted delay for a single road segment.

    Args:
        segment: Mapping containing segment attributes:
            - segment_id: str | int (required)
            - road_type: str (required)
            - segment_length_km: float >= 0.0 (optional if start/end coords given)
            - maxspeed: float | int | str | None (optional)
            - surface: str | None (optional)
            - start_latitude, start_longitude, end_latitude, end_longitude (optional)
            - disruption_factor: float [0, 1] | None (optional)
            - speed_reduction_ratio: float [0, 1] | None (optional)
            - delay_seconds: float >= 0.0 | None (optional)
            - is_blocked: bool | None (optional)
        vehicle_profile: Predefined vehicle profile name.
        vehicle_speed_factor: Custom positive numeric speed multiplier.

    Returns:
        Structured segment assessment dictionary.
    """
    if not isinstance(segment, Mapping):
        raise ETAEngineValidationError(f"Expected segment to be a mapping/dict, got {type(segment).__name__}")

    segment_id = segment.get("segment_id")
    if segment_id is None or str(segment_id).strip() == "":
        raise ETAEngineValidationError("Segment must contain a non-empty 'segment_id'")
    seg_id_str = str(segment_id).strip()

    veh_profile_name, veh_factor = _resolve_vehicle_speed_factor(vehicle_profile, vehicle_speed_factor)
    distance_km = _resolve_segment_distance(segment)

    raw_base_speed, effective_base_speed, speed_source, surface_desc, is_unpaved = _resolve_base_speed(
        segment.get("road_type"),
        segment.get("maxspeed"),
        segment.get("surface"),
        veh_factor,
    )

    disr_type, disr_val, is_blocked = _resolve_segment_disruption(segment)

    # 1. Baseline ETA (seconds)
    if math.isclose(distance_km, 0.0, abs_tol=1e-12):
        t_base = 0.0
    else:
        t_base = (distance_km / effective_base_speed) * 3600.0

    # 2. Disrupted ETA (seconds) and effective disrupted speed
    reason_codes: List[str] = []
    reasons: List[str] = []

    if is_unpaved:
        reason_codes.append("UNPAVED_SURFACE_PENALTY")
        reasons.append(f"Unpaved surface ({surface_desc}) reduces baseline design speed")

    if is_blocked:
        is_passable = False
        t_disrupted = t_base + DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS
        delay_seconds = DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS
        disrupted_speed = 0.0
        reason_codes.append("SEGMENT_BLOCKED")
        reasons.append(
            f"Segment is completely blocked; clearance penalty {DEFAULT_BLOCKED_SEGMENT_PENALTY_SECONDS:.0f}s applied"
        )
    elif disr_type == "disruption_factor":
        is_passable = True
        delta = disr_val if disr_val is not None else 0.0
        disrupted_speed = max(MIN_SPEED_KMH, effective_base_speed * (1.0 - delta * 0.85))
        if math.isclose(distance_km, 0.0, abs_tol=1e-12):
            t_disrupted = 0.0
            delay_seconds = 0.0
        else:
            t_disrupted = (distance_km / disrupted_speed) * 3600.0
            delay_seconds = max(0.0, t_disrupted - t_base)
        if delta > 0.0:
            reason_codes.append("DISRUPTION_FACTOR_SLOWDOWN")
            reasons.append(f"Disruption factor {delta:.2f} reduced operating speed to {disrupted_speed:.1f} km/h")
    elif disr_type == "speed_reduction_ratio":
        is_passable = True
        ratio = disr_val if disr_val is not None else 0.0
        disrupted_speed = max(MIN_SPEED_KMH, effective_base_speed * (1.0 - ratio))
        if math.isclose(distance_km, 0.0, abs_tol=1e-12):
            t_disrupted = 0.0
            delay_seconds = 0.0
        else:
            t_disrupted = (distance_km / disrupted_speed) * 3600.0
            delay_seconds = max(0.0, t_disrupted - t_base)
        if ratio > 0.0:
            reason_codes.append("SPEED_REDUCTION_SLOWDOWN")
            reasons.append(f"Speed reduction ratio {ratio:.2f} reduced operating speed to {disrupted_speed:.1f} km/h")
    elif disr_type == "delay_seconds":
        is_passable = True
        delay_seconds = disr_val if disr_val is not None else 0.0
        t_disrupted = t_base + delay_seconds
        if t_disrupted > 0.0 and distance_km > 0.0:
            disrupted_speed = (distance_km / t_disrupted) * 3600.0
        else:
            disrupted_speed = effective_base_speed
        if delay_seconds > 0.0:
            reason_codes.append("EXPLICIT_DELAY_ADDED")
            reasons.append(f"Explicit delay of {delay_seconds:.1f}s applied to segment")
    else:  # none
        is_passable = True
        t_disrupted = t_base
        delay_seconds = 0.0
        disrupted_speed = effective_base_speed

    delay_ratio = (delay_seconds / t_base) if t_base > 0.0 else 0.0

    return {
        "segment_id": seg_id_str,
        "distance_km": round(distance_km, 6),
        "raw_base_speed_kmh": round(raw_base_speed, 2),
        "effective_base_speed_kmh": round(effective_base_speed, 2),
        "disrupted_speed_kmh": round(disrupted_speed, 2),
        "baseline_eta_seconds": round(t_base, 3),
        "disrupted_eta_seconds": round(t_disrupted, 3),
        "delay_seconds": round(delay_seconds, 3),
        "delay_ratio": round(delay_ratio, 6),
        "is_passable": is_passable,
        "disruption_type": disr_type,
        "disruption_value": disr_val,
        "speed_source": speed_source,
        "surface": surface_desc,
        "vehicle_profile": veh_profile_name,
        "vehicle_speed_factor": veh_factor,
        "reason_codes": reason_codes,
        "reasons": reasons,
    }


def estimate_route_eta(
    segments: Iterable[Mapping[str, Any]],
    vehicle_profile: str | None = None,
    vehicle_speed_factor: float | None = None,
) -> Dict[str, Any]:
    """Estimate deterministic baseline travel time, disrupted ETA, and delay metrics for a route.

    Args:
        segments: Iterable of segment dictionaries.
        vehicle_profile: Optional predefined vehicle profile name.
        vehicle_speed_factor: Optional custom positive numeric speed multiplier.

    Returns:
        Structured deterministic dictionary:
        {
            "total_distance_km": float,
            "baseline_eta_seconds": float,
            "disrupted_eta_seconds": float,
            "delay_seconds": float,
            "delay_ratio": float,
            "normalized_delay_ratio": float, # clamped [0, 1] for Risk Engine
            "is_passable": bool,
            "segment_count": int,
            "disrupted_segment_count": int,
            "vehicle_profile": str,
            "vehicle_speed_factor": float,
            "reason_codes": List[str],
            "reasons": List[str],
            "segments": List[Dict[str, Any]],
            "honesty_disclosure": str,
        }
    """
    if segments is None:
        raise ETAEngineValidationError("Expected segments to be an iterable, got None")

    try:
        segment_iter = iter(segments)
    except TypeError as exc:
        raise ETAEngineValidationError(
            f"Expected segments to be an iterable, got {type(segments).__name__}"
        ) from exc

    veh_profile_name, veh_factor = _resolve_vehicle_speed_factor(vehicle_profile, vehicle_speed_factor)

    segment_evals: List[Dict[str, Any]] = []
    total_dist_km = 0.0
    total_base_seconds = 0.0
    total_disrupted_seconds = 0.0
    total_delay_seconds = 0.0
    all_passable = True
    disrupted_count = 0

    route_reason_codes: List[str] = []
    route_reasons: List[str] = []

    for seg in segment_iter:
        seg_res = estimate_segment_eta(
            seg,
            vehicle_profile=vehicle_profile,
            vehicle_speed_factor=vehicle_speed_factor,
        )
        segment_evals.append(seg_res)
        total_dist_km += seg_res["distance_km"]
        total_base_seconds += seg_res["baseline_eta_seconds"]
        total_disrupted_seconds += seg_res["disrupted_eta_seconds"]
        total_delay_seconds += seg_res["delay_seconds"]

        if not seg_res["is_passable"]:
            all_passable = False
        if seg_res["delay_seconds"] > 0.0:
            disrupted_count += 1

    total_segments = len(segment_evals)

    delay_ratio = (total_delay_seconds / total_base_seconds) if total_base_seconds > 0.0 else 0.0
    normalized_delay_ratio = min(1.0, max(0.0, delay_ratio))

    if not all_passable:
        route_reason_codes.append("ROUTE_IMPASSABLE")
        route_reasons.append("Route contains one or more impassable/blocked segments")
    elif normalized_delay_ratio >= 0.50:
        route_reason_codes.append("SIGNIFICANT_ROUTE_DELAY")
        route_reasons.append("Route experiences significant delay relative to baseline travel time")
    elif normalized_delay_ratio > 0.15:
        route_reason_codes.append("MODERATE_ROUTE_DELAY")
        route_reasons.append("Route experiences moderate delay relative to baseline travel time")
    elif total_segments > 0 and disrupted_count == 0:
        route_reason_codes.append("FREE_FLOW_BASELINE")
        route_reasons.append("Route operates at unimpeded baseline conditions")

    if any("UNPAVED_SURFACE_PENALTY" in s["reason_codes"] for s in segment_evals):
        route_reason_codes.append("ROUTE_SURFACE_DEGRADATION")
        route_reasons.append("One or more segments have unpaved surface reducing transit speed")

    return {
        "total_distance_km": round(total_dist_km, 6),
        "baseline_eta_seconds": round(total_base_seconds, 3),
        "disrupted_eta_seconds": round(total_disrupted_seconds, 3),
        "delay_seconds": round(total_delay_seconds, 3),
        "delay_ratio": round(delay_ratio, 6),
        "normalized_delay_ratio": round(normalized_delay_ratio, 6),
        "is_passable": all_passable,
        "segment_count": total_segments,
        "disrupted_segment_count": disrupted_count,
        "vehicle_profile": veh_profile_name,
        "vehicle_speed_factor": veh_factor,
        "reason_codes": route_reason_codes,
        "reasons": route_reasons,
        "segments": segment_evals,
        "honesty_disclosure": HONESTY_DISCLOSURE,
    }
