"""SETU Accessibility Scorer v0.1.

Deterministic road/segment infrastructure accessibility proxy scoring engine.
Evaluates physical and operational road usability based on local OSM attributes
(road_type, surface, lanes, maxspeed) using dynamic evidence normalization.

IMPORTANT HONESTY CONTRACT:
The calculated accessibility_score is an OSM-derived infrastructure accessibility
proxy representing structural road favorability and capacity. It must NEVER be
presented as observed real-world road passability or confirmed closure ground truth.
"""

from __future__ import annotations

import math
import re
from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, Tuple

# Prototype policy weights summing to 1.00 when all factors are observed.
# Exposed as an immutable mapping proxy.
ACCESSIBILITY_WEIGHTS: Mapping[str, float] = MappingProxyType({
    "road_type": 0.50,
    "surface": 0.25,
    "lanes": 0.15,
    "maxspeed": 0.10,
})

# Thresholds for accessibility level classification
LEVEL_HIGH_THRESHOLD = 0.75
LEVEL_MEDIUM_THRESHOLD = 0.50
LEVEL_LOW_THRESHOLD = 0.25


class AccessibilityValidationError(ValueError):
    """Raised when segment attributes are missing, non-mapping, or invalid."""
    pass


def _score_road_type(road_type: str) -> Tuple[float, str, str]:
    """Score road_type hierarchy strictly and deterministically."""
    clean_type = road_type.lower().strip()
    if clean_type == "motorway":
        return 1.00, "HIGH_GRADE_HIGHWAY", "Motorway corridor provides highest infrastructure standard"
    elif clean_type == "trunk":
        return 0.90, "HIGH_GRADE_HIGHWAY", "Trunk highway provides high-capacity arterial passage"
    elif clean_type == "primary":
        return 0.75, "PRIMARY_ROAD", "Primary road provides standard intercity connectivity"
    elif clean_type == "secondary":
        return 0.60, "SECONDARY_ROAD", "Secondary road provides regional connectivity with moderate capacity"
    elif clean_type == "tertiary":
        return 0.40, "TERTIARY_ROAD", "Tertiary feeder road with lower design standard"
    else:
        return 0.25, "LOWER_TIER_ROAD", "Lower-tier or unclassified road with restricted infrastructure standard"


def _score_surface(surface: Any) -> Tuple[float, str, str] | None:
    """Score road surface if present, or return None if unrecorded."""
    if surface is None:
        return None
    if not isinstance(surface, str):
        raise AccessibilityValidationError(
            f"Field 'surface' must be a string if provided, got {type(surface).__name__} ({surface!r})"
        )
    clean_surface = surface.lower().strip()
    if not clean_surface:
        return None

    paved_set = {
        "asphalt",
        "concrete",
        "paved",
        "concrete:lanes",
        "concrete:plates",
        "tar",
    }
    intermediate_set = {
        "compacted",
        "paving_stones",
        "sett",
        "chipseal",
        "cobblestone",
    }
    unpaved_set = {
        "unpaved",
        "gravel",
        "dirt",
        "earth",
        "mud",
        "ground",
        "sand",
        "clay",
    }

    if clean_surface in paved_set:
        return 1.00, "PAVED_SURFACE", "Paved road surface provides reliable traction and year-round usability"
    elif clean_surface in intermediate_set:
        return 0.60, "INTERMEDIATE_SURFACE", "Intermediate road surface with moderate wear and seasonal sensitivity"
    elif clean_surface in unpaved_set:
        return 0.20, "UNPAVED_SURFACE", "Unpaved surface restricts heavy vehicle movement and increases disruption risk"
    else:
        # Unrecognized custom string: treat as unrecorded/missing rather than fabricating
        return None


def _score_lanes(lanes: Any) -> Tuple[float, str, str] | None:
    """Score number of lanes if present, or return None if unrecorded."""
    if lanes is None:
        return None
    if isinstance(lanes, bool):
        raise AccessibilityValidationError("Field 'lanes' cannot be a boolean")

    lane_count: int
    if isinstance(lanes, str):
        clean_lanes = lanes.strip()
        if not clean_lanes:
            return None
        # Reject fractional string inputs such as "1.5" or "2.8"
        if "." in clean_lanes:
            try:
                f_val = float(clean_lanes)
                if not f_val.is_integer():
                    raise AccessibilityValidationError(
                        f"Field 'lanes' must be an integer count, got fractional value {clean_lanes!r}"
                    )
                lane_count = int(f_val)
            except ValueError:
                raise AccessibilityValidationError(f"Invalid lanes format: {lanes!r}")
        elif ";" in clean_lanes:
            # Semicolon-separated format (e.g. '1;2')
            parts = clean_lanes.split(";")
            try:
                lane_count = sum(int(p.strip()) for p in parts if p.strip())
            except ValueError:
                raise AccessibilityValidationError(f"Invalid lanes format: {lanes!r}")
        else:
            try:
                lane_count = int(clean_lanes)
            except ValueError:
                raise AccessibilityValidationError(f"Invalid lanes format: {lanes!r}")
    elif isinstance(lanes, (int, float)):
        if not math.isfinite(lanes):
            raise AccessibilityValidationError(f"Field 'lanes' must be a finite number, got {lanes}")
        if not float(lanes).is_integer():
            raise AccessibilityValidationError(
                f"Field 'lanes' must be an integer count, got fractional value {lanes}"
            )
        lane_count = int(lanes)
    else:
        raise AccessibilityValidationError(
            f"Field 'lanes' must be an integer, float, or parseable string, got {type(lanes).__name__}"
        )

    if lane_count <= 0:
        raise AccessibilityValidationError(f"Field 'lanes' must be positive, got {lane_count}")

    if lane_count >= 4:
        return 1.00, "MULTI_LANE_CAPACITY", "Multi-lane roadway (4+ lanes) provides high throughput and passing capacity"
    elif lane_count == 3:
        return 0.85, "MULTI_LANE_CAPACITY", "Three-lane roadway provides good passing capacity"
    elif lane_count == 2:
        return 0.70, "DUAL_LANE_STANDARD", "Standard two-lane roadway provides bidirectional passage"
    else:  # lane_count == 1
        return 0.35, "SINGLE_LANE_BOTTLENECK", "Single-lane road limits vehicle passing and creates potential bottlenecks"


def _score_maxspeed(maxspeed: Any) -> Tuple[float, str, str] | None:
    """Score design speed limit in km/h if present, or return None if unrecorded."""
    if maxspeed is None:
        return None
    if isinstance(maxspeed, bool):
        raise AccessibilityValidationError("Field 'maxspeed' cannot be a boolean")

    speed_kmh: float
    if isinstance(maxspeed, str):
        clean_speed = maxspeed.strip().lower()
        if not clean_speed:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", clean_speed)
        if not match:
            raise AccessibilityValidationError(f"Invalid maxspeed format: {maxspeed!r}")
        raw_val = float(match.group(1))
        if "mph" in clean_speed:
            speed_kmh = raw_val * 1.60934
        else:
            speed_kmh = raw_val
    elif isinstance(maxspeed, (int, float)):
        if not math.isfinite(maxspeed):
            raise AccessibilityValidationError(f"Field 'maxspeed' must be a finite number, got {maxspeed}")
        speed_kmh = float(maxspeed)
    else:
        raise AccessibilityValidationError(
            f"Field 'maxspeed' must be an integer, float, or parseable string, got {type(maxspeed).__name__}"
        )

    if speed_kmh <= 0.0:
        raise AccessibilityValidationError(f"Field 'maxspeed' must be positive, got {speed_kmh}")

    if speed_kmh >= 80.0:
        return 1.00, "HIGH_SPEED_DESIGN", "Recorded speed limit (80+ km/h) supports high-speed corridor accessibility"
    elif speed_kmh >= 60.0:
        return 0.80, "MODERATE_SPEED_DESIGN", "Recorded speed limit (60-79 km/h) indicates standard regional highway speed capacity"
    elif speed_kmh >= 40.0:
        return 0.60, "REDUCED_SPEED_DESIGN", "Recorded speed limit (40-59 km/h) reflects moderate speed restrictions on this segment"
    else:
        return 0.35, "LOW_SPEED_CORRIDOR", "Low recorded speed limit (<40 km/h) limits corridor flow rate and throughput"


def _classify_accessibility_level(score: float) -> str:
    """Classify accessibility score into deterministic level."""
    if score >= LEVEL_HIGH_THRESHOLD:
        return "HIGH"
    elif score >= LEVEL_MEDIUM_THRESHOLD:
        return "MEDIUM"
    elif score >= LEVEL_LOW_THRESHOLD:
        return "LOW"
    else:
        return "CRITICAL"


def calculate_accessibility(
    segment: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Calculate deterministic accessibility proxy score for a road segment.

    Uses dynamic evidence normalization over observed attributes without fabricating
    unrecorded optional fields.

    Args:
        segment: Mapping containing road segment attributes:
            - segment_id: str | int (required)
            - road_type: str (required)
            - surface: str | None (optional)
            - lanes: int | float | str | None (optional)
            - maxspeed: int | float | str | None (optional)
        **kwargs: Alternative keyword arguments for segment attributes.

    Returns:
        Structured dictionary:
        {
            "segment_id": str,
            "accessibility_score": float (0.0 to 1.0),
            "accessibility_level": "HIGH" | "MEDIUM" | "LOW" | "CRITICAL",
            "evaluated_factors": List[str],
            "missing_factors": List[str],
            "reason_codes": List[str],
            "reasons": List[str],
        }

    Raises:
        AccessibilityValidationError: If required fields are missing or attributes are invalid.
    """
    merged: Dict[str, Any] = {}
    if segment is not None:
        if not isinstance(segment, Mapping):
            raise AccessibilityValidationError(
                f"Expected segment to be a mapping/dict, got {type(segment).__name__}"
            )
        merged.update(segment)
    merged.update(kwargs)

    raw_id = merged.get("segment_id")
    if raw_id is None or str(raw_id).strip() == "":
        raise AccessibilityValidationError("Segment must contain a non-empty 'segment_id'")
    segment_id = str(raw_id).strip()

    raw_road_type = merged.get("road_type")
    if raw_road_type is None or not isinstance(raw_road_type, str) or not raw_road_type.strip():
        raise AccessibilityValidationError(
            f"Segment '{segment_id}' must contain a non-empty string 'road_type', got {raw_road_type!r}"
        )

    evaluated_factors: List[str] = []
    missing_factors: List[str] = []
    factor_scores: Dict[str, float] = {}
    observed_reasons: List[Tuple[str, str, str]] = []

    # 1. road_type (mandatory primary signal)
    rt_score, rt_code, rt_text = _score_road_type(raw_road_type)
    evaluated_factors.append("road_type")
    factor_scores["road_type"] = rt_score
    observed_reasons.append(("road_type", rt_code, rt_text))

    # 2. surface (optional)
    surface_eval = _score_surface(merged.get("surface"))
    if surface_eval is not None:
        s_score, s_code, s_text = surface_eval
        evaluated_factors.append("surface")
        factor_scores["surface"] = s_score
        observed_reasons.append(("surface", s_code, s_text))
    else:
        missing_factors.append("surface")

    # 3. lanes (optional)
    lanes_eval = _score_lanes(merged.get("lanes"))
    if lanes_eval is not None:
        l_score, l_code, l_text = lanes_eval
        evaluated_factors.append("lanes")
        factor_scores["lanes"] = l_score
        observed_reasons.append(("lanes", l_code, l_text))
    else:
        missing_factors.append("lanes")

    # 4. maxspeed (optional)
    maxspeed_eval = _score_maxspeed(merged.get("maxspeed"))
    if maxspeed_eval is not None:
        m_score, m_code, m_text = maxspeed_eval
        evaluated_factors.append("maxspeed")
        factor_scores["maxspeed"] = m_score
        observed_reasons.append(("maxspeed", m_code, m_text))
    else:
        missing_factors.append("maxspeed")

    # Dynamic evidence normalization: normalize strictly by sum of observed weights
    total_observed_weight = sum(ACCESSIBILITY_WEIGHTS[f] for f in evaluated_factors)
    weighted_sum = sum(ACCESSIBILITY_WEIGHTS[f] * factor_scores[f] for f in evaluated_factors)

    raw_score = weighted_sum / total_observed_weight
    bounded_score = max(0.0, min(1.0, raw_score))
    accessibility_score = round(bounded_score, 4)

    accessibility_level = _classify_accessibility_level(accessibility_score)

    # Deterministic explainability assembly
    reason_codes: List[str] = [item[1] for item in observed_reasons]
    reasons: List[str] = [item[2] for item in observed_reasons]

    missing_notice_map = {
        "surface": ("MISSING_SURFACE_DATA", "Road surface type not recorded in local data"),
        "lanes": ("MISSING_LANES_DATA", "Lane count not recorded in local data"),
        "maxspeed": ("MISSING_MAXSPEED_DATA", "Speed limit not recorded in local data"),
    }
    for mf in missing_factors:
        if mf in missing_notice_map:
            m_code, m_text = missing_notice_map[mf]
            reason_codes.append(m_code)
            reasons.append(m_text)

    return {
        "segment_id": segment_id,
        "accessibility_score": accessibility_score,
        "accessibility_level": accessibility_level,
        "evaluated_factors": evaluated_factors,
        "missing_factors": missing_factors,
        "reason_codes": reason_codes,
        "reasons": reasons,
    }


def score_segments(segments: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Batch-score an iterable of road segments with accessibility assessments."""
    if segments is None:
        raise AccessibilityValidationError("Expected segments to be an iterable, got None")
    return [calculate_accessibility(seg) for seg in segments]
