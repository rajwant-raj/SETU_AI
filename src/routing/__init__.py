"""SETU Routing Module v0.1.

Candidate generation for physically plausible alternative routes on normalized
road network graphs without calculating ranking weights, recommendation scores,
or external routing API calls.
"""

from src.routing.route_candidates import (
    RouteCandidateValidationError,
    generate_route_candidates,
)

__all__ = [
    "RouteCandidateValidationError",
    "generate_route_candidates",
]
