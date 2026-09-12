"""SETU Network Impact Intelligence Module."""

from .network_impact import (
    NetworkImpactValidationError,
    assess_network_impact,
    find_affected_segments,
    haversine_km,
    point_to_segment_distance_km,
    EARTH_RADIUS_KM,
    REQUIRED_INCIDENT_FIELDS,
)

__all__ = [
    "NetworkImpactValidationError",
    "assess_network_impact",
    "find_affected_segments",
    "haversine_km",
    "point_to_segment_distance_km",
    "EARTH_RADIUS_KM",
    "REQUIRED_INCIDENT_FIELDS",
]
