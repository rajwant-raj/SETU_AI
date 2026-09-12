"""SETU Explanation Package (Checkpoint 15).

Deterministic explanation layer for candidate route ranking decisions.
"""

from src.explanation.route_explanation import (
    FACTOR_DEFINITIONS,
    HONESTY_DISCLOSURE,
    RouteExplanationValidationError,
    explain_ranked_route,
    explain_ranked_routes,
)

__all__ = [
    "explain_ranked_route",
    "explain_ranked_routes",
    "RouteExplanationValidationError",
    "HONESTY_DISCLOSURE",
    "FACTOR_DEFINITIONS",
]
