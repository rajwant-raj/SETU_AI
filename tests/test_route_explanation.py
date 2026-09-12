"""Tests for Checkpoint 15 — Route Explanation Layer.

Covers:
- Package imports and public API exports
- Valid ranked-route explanation structure
- Required input validation and error handling
- Deterministic output (repeated executions)
- Input immutability (no mutation of caller dictionaries)
- All five supported ranking factors present and correctly mapped
- Ranking weights taken strictly from supplied ranking output
- Missing optional risk reasons handled honestly
- Supplied risk reasons and reason codes preserved
- Vehicle compatibility terminology remains a proxy
- Availability is not fabricated
- Single-route explanation behavior
- Multiple-route comparative tradeoff explanation
- Missing/invalid ranking fields rejected
- No invented values
- Honesty disclosure present
- Deterministic ordering of factor output
- Pure Python standard library / no external APIs
"""

import copy
import pytest

from src.explanation import (
    FACTOR_DEFINITIONS,
    HONESTY_DISCLOSURE,
    RouteExplanationValidationError,
    explain_ranked_route,
    explain_ranked_routes,
)
from src.routing.route_ranking import DEFAULT_RANKING_WEIGHTS, rank_route_candidates


@pytest.fixture
def sample_candidates():
    """Realistic candidate routes from Checkpoint 13."""
    return [
        {
            "route_id": "route_A",
            "total_distance_km": 10.0,
            "eta_seconds": 1200.0,
            "accessibility_score": 0.85,
            "risk_score": 25.0,
            "vehicle_profile_compatibility": 0.90,
            "reasons": ["Moderate incident severity"],
            "reason_codes": ["MODERATE_INCIDENT_SEVERITY"],
            "segment_ids": ["seg_1", "seg_2"],
            "node_ids": ["N1", "N2", "N3"],
        },
        {
            "route_id": "route_B",
            "total_distance_km": 12.5,
            "eta_seconds": 1500.0,
            "accessibility_score": 0.95,
            "risk_score": 15.0,
            "vehicle_profile_compatibility": 0.70,
            "reasons": ["Low accessibility"],
            "reason_codes": ["LOW_ACCESSIBILITY"],
            "segment_ids": ["seg_3", "seg_4"],
            "node_ids": ["N1", "N4", "N3"],
        },
        {
            "route_id": "route_C",
            "total_distance_km": 9.0,
            "eta_seconds": 1800.0,
            "accessibility_score": 0.50,
            "risk_score": 60.0,
            "vehicle_profile_compatibility": 0.80,
            "segment_ids": ["seg_5"],
            "node_ids": ["N1", "N5", "N3"],
        },
    ]


@pytest.fixture
def ranked_candidates(sample_candidates):
    """Ranked routes using actual Checkpoint 14 ranking engine."""
    return rank_route_candidates(sample_candidates)


def test_1_package_import():
    """Verify package import and public API availability."""
    assert callable(explain_ranked_route)
    assert callable(explain_ranked_routes)
    assert issubclass(RouteExplanationValidationError, ValueError)
    assert isinstance(HONESTY_DISCLOSURE, str)
    assert len(FACTOR_DEFINITIONS) == 5


def test_2_valid_ranked_route_explanation(ranked_candidates):
    """Verify valid ranked route explanation produces all required minimum fields."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)

    assert explanation["route_id"] == top_route["route_id"]
    assert explanation["rank"] == 1
    assert explanation["ranking_score"] == top_route["ranking_score"]
    assert isinstance(explanation["summary"], str)
    assert len(explanation["summary"]) > 0
    assert isinstance(explanation["decision_factors"], list)
    assert len(explanation["decision_factors"]) == 5
    assert isinstance(explanation["tradeoffs"], dict)
    assert isinstance(explanation["risk_reasons"], list)
    assert isinstance(explanation["honesty_disclosure"], str)


def test_3_deterministic_ordering_of_factor_output(ranked_candidates):
    """Verify the 5 decision factors are strictly ordered: eta, risk, accessibility, distance, vehicle."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)

    expected_order = [
        "eta",
        "risk",
        "accessibility",
        "distance",
        "vehicle_profile_compatibility",
    ]
    actual_order = [f["factor"] for f in explanation["decision_factors"]]
    assert actual_order == expected_order


def test_4_all_five_supported_ranking_factors_and_weights(ranked_candidates):
    """Verify decision_factors derives raw values, normalized scores, and weights from ranking input."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)

    factors_by_key = {f["factor"]: f for f in explanation["decision_factors"]}

    # ETA
    assert factors_by_key["eta"]["label"] == "ETA"
    assert factors_by_key["eta"]["raw_value"] == top_route["metrics"]["eta_seconds"]
    assert factors_by_key["eta"]["normalized_score"] == top_route["normalized_scores"]["eta_score"]
    assert factors_by_key["eta"]["weight"] == top_route["weights_applied"]["eta"]
    assert factors_by_key["eta"]["direction"] == "lower_is_better"

    # Risk
    assert factors_by_key["risk"]["label"] == "Risk"
    assert factors_by_key["risk"]["raw_value"] == top_route["metrics"]["risk_score"]
    assert factors_by_key["risk"]["normalized_score"] == top_route["normalized_scores"]["risk_score"]
    assert factors_by_key["risk"]["weight"] == top_route["weights_applied"]["risk"]
    assert factors_by_key["risk"]["direction"] == "lower_is_better"

    # Accessibility
    assert factors_by_key["accessibility"]["label"] == "Accessibility"
    assert factors_by_key["accessibility"]["raw_value"] == top_route["metrics"]["accessibility_score"]
    assert factors_by_key["accessibility"]["normalized_score"] == top_route["normalized_scores"]["accessibility_score"]
    assert factors_by_key["accessibility"]["weight"] == top_route["weights_applied"]["accessibility"]
    assert factors_by_key["accessibility"]["direction"] == "higher_is_better"

    # Distance
    assert factors_by_key["distance"]["label"] == "Distance"
    assert factors_by_key["distance"]["raw_value"] == top_route["metrics"]["distance_km"]
    assert factors_by_key["distance"]["normalized_score"] == top_route["normalized_scores"]["distance_score"]
    assert factors_by_key["distance"]["weight"] == top_route["weights_applied"]["distance"]
    assert factors_by_key["distance"]["direction"] == "lower_is_better"

    # Vehicle Profile Compatibility Proxy
    assert factors_by_key["vehicle_profile_compatibility"]["label"] == "Vehicle Profile Compatibility Proxy"
    assert factors_by_key["vehicle_profile_compatibility"]["raw_value"] == top_route["metrics"]["vehicle_profile_compatibility"]
    assert factors_by_key["vehicle_profile_compatibility"]["normalized_score"] == top_route["normalized_scores"]["vehicle_profile_compatibility_score"]
    assert factors_by_key["vehicle_profile_compatibility"]["weight"] == top_route["weights_applied"]["vehicle_profile_compatibility"]
    assert factors_by_key["vehicle_profile_compatibility"]["direction"] == "higher_is_better"


def test_5_ranking_weights_taken_from_supplied_ranking_output(sample_candidates):
    """Verify explanation does NOT introduce new weights, but reflects custom weights when supplied."""
    custom_w = {
        "eta": 0.50,
        "risk": 0.20,
        "accessibility": 0.10,
        "distance": 0.10,
        "vehicle_profile_compatibility": 0.10,
    }
    ranked = rank_route_candidates(sample_candidates, custom_weights=custom_w)
    explanation = explain_ranked_route(ranked[0])

    for f in explanation["decision_factors"]:
        key = f["factor"]
        assert pytest.approx(f["weight"], abs=1e-6) == custom_w[key]


def test_6_no_independent_recalculation_of_route_score(ranked_candidates):
    """Verify explanation does not alter or recompute a divergent route score."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)
    assert explanation["ranking_score"] == top_route["ranking_score"]


def test_7_no_input_mutation(ranked_candidates):
    """Verify explaining a route does not mutate the caller's input dictionary or collections."""
    original = copy.deepcopy(ranked_candidates)
    _ = explain_ranked_route(ranked_candidates[0], all_ranked_routes=ranked_candidates)
    _ = explain_ranked_routes(ranked_candidates)

    assert ranked_candidates == original


def test_8_deterministic_output_100_runs(ranked_candidates):
    """Verify repeated execution produces byte-for-byte identical output."""
    top_route = ranked_candidates[0]
    first_run = explain_ranked_route(top_route, all_ranked_routes=ranked_candidates)

    for _ in range(100):
        next_run = explain_ranked_route(top_route, all_ranked_routes=ranked_candidates)
        assert next_run == first_run


def test_9_supplied_risk_reasons_preserved(ranked_candidates):
    """Verify risk reasons and reason codes present in candidate are preserved."""
    # Find route_A which had Moderate incident severity
    route_a = next(r for r in ranked_candidates if r["route_id"] == "route_A")
    explanation = explain_ranked_route(route_a)

    assert "Moderate incident severity" in explanation["risk_reasons"]
    assert "MODERATE_INCIDENT_SEVERITY" in explanation["risk_reason_codes"]


def test_10_missing_optional_risk_reasons_handled_honestly(ranked_candidates):
    """Verify that when risk reasons are absent, none are fabricated."""
    # Find route_C which had no reasons
    route_c = next(r for r in ranked_candidates if r["route_id"] == "route_C")
    explanation = explain_ranked_route(route_c)

    assert explanation["risk_reasons"] == []
    assert explanation["risk_reason_codes"] == []


def test_11_vehicle_compatibility_terminology_remains_proxy(ranked_candidates):
    """Verify vehicle compatibility is described as a proxy and not physical clearance."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)

    veh_factor = next(f for f in explanation["decision_factors"] if f["factor"] == "vehicle_profile_compatibility")
    assert "Proxy" in veh_factor["label"]
    assert "PROXY" in explanation["honesty_disclosure"]
    assert "axle" in explanation["honesty_disclosure"].lower() or "clearance" in explanation["honesty_disclosure"].lower()


def test_12_availability_is_not_fabricated(ranked_candidates):
    """Verify availability is never included in factors or implied in tradeoffs."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)

    factor_keys = [f["factor"] for f in explanation["decision_factors"]]
    assert "availability" not in factor_keys

    tradeoff_text = str(explanation["tradeoffs"]).lower()
    assert "availability" not in tradeoff_text

    assert "UNSUPPORTED" in explanation["honesty_disclosure"]


def test_13_single_route_behavior(ranked_candidates):
    """Verify single-route explanation produces valid output without nonexistent alternative comparisons."""
    single_route = ranked_candidates[0]
    explanation = explain_ranked_route(single_route, all_ranked_routes=None)

    assert explanation["tradeoffs"]["compared_to_route_id"] is None
    assert "Single candidate route evaluated" in explanation["tradeoffs"]["narrative"]
    assert "tradeoff_flags" in explanation["tradeoffs"]


def test_14_multiple_route_tradeoff_explanation(ranked_candidates):
    """Verify multiple-route tradeoff explanation captures advantages and disadvantages vs competitors."""
    explanations = explain_ranked_routes(ranked_candidates)
    assert len(explanations) == 3

    # Rank 1 route compared against Rank 2 runner-up
    rank1 = explanations[0]
    assert rank1["rank"] == 1
    assert rank1["tradeoffs"]["compared_to_route_id"] == explanations[1]["route_id"]
    assert "ranks #1 ahead of alternative" in rank1["tradeoffs"]["narrative"]

    # Rank 2 route compared against Rank 1
    rank2 = explanations[1]
    assert rank2["rank"] == 2
    assert rank2["tradeoffs"]["compared_to_route_id"] == rank1["route_id"]
    assert "ranks #2 behind top route" in rank2["tradeoffs"]["narrative"]


def test_15_honesty_disclosure_present(ranked_candidates):
    """Verify honesty disclosure is present and contains required transparency elements."""
    top_route = ranked_candidates[0]
    explanation = explain_ranked_route(top_route)

    disclosure = explanation["honesty_disclosure"]
    assert "Vehicle Profile Compatibility Proxy" in disclosure
    assert "Availability" in disclosure
    assert "Operational Conditions" in disclosure
    assert "Decision Support" in disclosure


def test_16_validation_rejects_none_and_invalid_types(ranked_candidates):
    """Verify input validation on target and collections."""
    with pytest.raises(RouteExplanationValidationError, match="Expected ranked_route to be a mapping"):
        explain_ranked_route(None)

    with pytest.raises(RouteExplanationValidationError, match="Expected ranked_route to be a mapping"):
        explain_ranked_route("not_a_map")

    with pytest.raises(RouteExplanationValidationError, match="Expected all_ranked_routes to be an iterable"):
        explain_ranked_route(ranked_candidates[0], all_ranked_routes="invalid_string")

    with pytest.raises(RouteExplanationValidationError, match="Expected ranked_routes to be an iterable"):
        explain_ranked_routes(None)

    with pytest.raises(RouteExplanationValidationError, match="Cannot explain an empty collection"):
        explain_ranked_routes([])


def test_17_validation_rejects_missing_or_corrupted_fields(ranked_candidates):
    """Verify input validation rejects missing route_id, rank, metrics, scores, or weights."""
    valid = ranked_candidates[0]

    # Missing route_id
    bad = copy.deepcopy(valid)
    del bad["route_id"]
    with pytest.raises(RouteExplanationValidationError, match="route_id"):
        explain_ranked_route(bad)

    # Empty route_id
    bad = copy.deepcopy(valid)
    bad["route_id"] = "   "
    with pytest.raises(RouteExplanationValidationError, match="route_id"):
        explain_ranked_route(bad)

    # Missing rank
    bad = copy.deepcopy(valid)
    del bad["rank"]
    with pytest.raises(RouteExplanationValidationError, match="missing 'rank'"):
        explain_ranked_route(bad)

    # Invalid rank (< 1)
    bad = copy.deepcopy(valid)
    bad["rank"] = 0
    with pytest.raises(RouteExplanationValidationError, match="rank' must be >= 1"):
        explain_ranked_route(bad)

    # Non-integer rank
    bad = copy.deepcopy(valid)
    bad["rank"] = "one"
    with pytest.raises(RouteExplanationValidationError, match="must be an integer"):
        explain_ranked_route(bad)

    # Missing ranking_score
    bad = copy.deepcopy(valid)
    del bad["ranking_score"]
    with pytest.raises(RouteExplanationValidationError, match="missing 'ranking_score'"):
        explain_ranked_route(bad)

    # Out of bounds ranking_score
    bad = copy.deepcopy(valid)
    bad["ranking_score"] = 1.5
    with pytest.raises(RouteExplanationValidationError, match="must be <= 1.0"):
        explain_ranked_route(bad)

    # Missing metrics
    bad = copy.deepcopy(valid)
    del bad["metrics"]
    with pytest.raises(RouteExplanationValidationError, match="missing or invalid 'metrics'"):
        explain_ranked_route(bad)

    # Missing metric field
    bad = copy.deepcopy(valid)
    del bad["metrics"]["eta_seconds"]
    with pytest.raises(RouteExplanationValidationError, match="missing required field 'eta_seconds'"):
        explain_ranked_route(bad)

    # Missing normalized_scores
    bad = copy.deepcopy(valid)
    del bad["normalized_scores"]
    with pytest.raises(RouteExplanationValidationError, match="missing or invalid 'normalized_scores'"):
        explain_ranked_route(bad)

    # Missing normalized_scores field
    bad = copy.deepcopy(valid)
    del bad["normalized_scores"]["risk_score"]
    with pytest.raises(RouteExplanationValidationError, match="missing required field 'risk_score'"):
        explain_ranked_route(bad)

    # Missing weights_applied
    bad = copy.deepcopy(valid)
    del bad["weights_applied"]
    with pytest.raises(RouteExplanationValidationError, match="missing or invalid 'weights_applied'"):
        explain_ranked_route(bad)

    # Missing weights_applied key
    bad = copy.deepcopy(valid)
    del bad["weights_applied"]["accessibility"]
    with pytest.raises(RouteExplanationValidationError, match="missing required weight 'accessibility'"):
        explain_ranked_route(bad)
