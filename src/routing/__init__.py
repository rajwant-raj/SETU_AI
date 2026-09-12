"""SETU Routing Module v0.1.

Candidate generation (Checkpoint 13) and deterministic candidate ranking (Checkpoint 14)
for physically plausible alternative routes on normalized road network graphs.
"""

from src.routing.route_candidates import (
    RouteCandidateValidationError,
    generate_route_candidates,
)
from src.routing.route_ranking import (
    DEFAULT_RANKING_WEIGHTS,
    RouteRankingValidationError,
    rank_route_candidates,
)

__all__ = [
    "DEFAULT_RANKING_WEIGHTS",
    "RouteCandidateValidationError",
    "RouteRankingValidationError",
    "generate_route_candidates",
    "rank_route_candidates",
]
