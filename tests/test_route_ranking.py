"""Tests for SETU Route Candidate Ranking v0.1 (Checkpoint 14).

Covers all mandatory verification areas for deterministic candidate route ranking:
1. basic ranking of multiple candidates
2. lower ETA preferred when other factors are equal
3. lower risk preferred when other factors are equal
4. higher accessibility preferred when other factors are equal
5. shorter distance preferred when other factors are equal
6. vehicle profile compatibility proxy effect
7. deterministic normalization
8. constant metric sets
9. single-candidate input
10. deterministic tie-breaking
11. invalid candidate values rejected
12. missing required ranking context rejected:
    - missing incident_severity raises validation error (never defaulted to 0)
    - missing current_delay_ratio raises validation error (never derived from ETA)
    - missing accessibility_score raises validation error (never derived from segments)
    - missing weather_severity, road_condition_score, network_criticality raises validation error
13. no candidate mutation
14. no external API calls
15. package import through src.routing works and weights sum to exactly 1.0
16. ranking does not generate additional routes
17. ranking does not perform rerouting
18. output preserves candidate segment metadata
19. repeated invocation is deterministic (100 runs)
20. strict custom weights validation:
    - unknown keys in custom_weights raise RouteRankingValidationError
    - negative weights rejected
    - zero sum rejected
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
import pytest

from src.routing import (
    DEFAULT_RANKING_WEIGHTS,
    RouteRankingValidationError,
    rank_route_candidates,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def complete_risk_context() -> Dict[str, float]:
    """Complete, explicit risk context containing all 6 required Risk Engine fields."""
    return {
        "incident_severity": 0.15,
        "accessibility_score": 0.70,
        "weather_severity": 0.20,
        "road_condition_score": 0.80,
        "network_criticality": 0.40,
        "current_delay_ratio": 0.05,
    }


@pytest.fixture
def sample_candidates_with_precomputed_risk() -> List[Dict[str, Any]]:
    """Three physically plausible candidates with precomputed metrics."""
    return [
        {
            "route_id": "candidate_001",
            "total_distance_km": 20.0,
            "segment_count": 2,
            "segment_ids": ["SEG_1", "SEG_2"],
            "node_ids": ["N1", "N2", "N3"],
            "eta_seconds": 1800.0,  # 30 mins
            "risk_score": 25.0,
            "accessibility_score": 0.85,
            "vehicle_profile_compatibility": 0.90,
            "segments": [
                {"segment_id": "SEG_1", "road_type": "primary", "surface": "asphalt", "segment_length_km": 10.0},
                {"segment_id": "SEG_2", "road_type": "primary", "surface": "asphalt", "segment_length_km": 10.0},
            ],
        },
        {
            "route_id": "candidate_002",
            "total_distance_km": 24.0,
            "segment_count": 2,
            "segment_ids": ["SEG_3", "SEG_4"],
            "node_ids": ["N1", "N4", "N3"],
            "eta_seconds": 2400.0,  # 40 mins
            "risk_score": 45.0,
            "accessibility_score": 0.60,
            "vehicle_profile_compatibility": 0.70,
            "segments": [
                {"segment_id": "SEG_3", "road_type": "secondary", "surface": "concrete", "segment_length_km": 12.0},
                {"segment_id": "SEG_4", "road_type": "secondary", "surface": "concrete", "segment_length_km": 12.0},
            ],
        },
        {
            "route_id": "candidate_003",
            "total_distance_km": 30.0,
            "segment_count": 2,
            "segment_ids": ["SEG_5", "SEG_6"],
            "node_ids": ["N1", "N5", "N3"],
            "eta_seconds": 3600.0,  # 60 mins
            "risk_score": 60.0,
            "accessibility_score": 0.40,
            "vehicle_profile_compatibility": 0.50,
            "segments": [
                {"segment_id": "SEG_5", "road_type": "tertiary", "surface": "unpaved", "segment_length_km": 15.0},
                {"segment_id": "SEG_6", "road_type": "tertiary", "surface": "unpaved", "segment_length_km": 15.0},
            ],
        },
    ]


@pytest.fixture
def candidates_without_precomputed_risk() -> List[Dict[str, Any]]:
    """Candidates containing segments and distances, requiring explicit risk_context."""
    return [
        {
            "route_id": "route_A",
            "total_distance_km": 20.0,
            "segment_count": 2,
            "segment_ids": ["SEG_A1", "SEG_A2"],
            "node_ids": ["N1", "NA", "N2"],
            "segments": [
                {"segment_id": "SEG_A1", "road_type": "primary", "surface": "asphalt", "segment_length_km": 10.0},
                {"segment_id": "SEG_A2", "road_type": "primary", "surface": "asphalt", "segment_length_km": 10.0},
            ],
        },
        {
            "route_id": "route_B",
            "total_distance_km": 25.0,
            "segment_count": 2,
            "segment_ids": ["SEG_B1", "SEG_B2"],
            "node_ids": ["N1", "NB", "N2"],
            "segments": [
                {"segment_id": "SEG_B1", "road_type": "secondary", "surface": "unpaved", "segment_length_km": 12.5},
                {"segment_id": "SEG_B2", "road_type": "secondary", "surface": "unpaved", "segment_length_km": 12.5},
            ],
        },
    ]


# ==============================================================================
# 1. Basic Ranking of Multiple Candidates
# ==============================================================================

def test_1_basic_ranking_of_multiple_candidates(sample_candidates_with_precomputed_risk):
    """Test 1: Evaluates and ranks candidates in descending order of composite ranking score."""
    ranked = rank_route_candidates(sample_candidates_with_precomputed_risk)

    assert len(ranked) == 3
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2
    assert ranked[2]["rank"] == 3

    # Candidate 1 dominates on all dimensions (shortest, lowest ETA, lowest risk, highest acc, highest veh fit)
    assert ranked[0]["route_id"] == "candidate_001"
    assert ranked[0]["ranking_score"] == 1.0000

    # Candidate 3 is worst on all dimensions
    assert ranked[2]["route_id"] == "candidate_003"
    assert ranked[2]["ranking_score"] == 0.0000

    # Scores must be in monotonically non-increasing order
    assert ranked[0]["ranking_score"] >= ranked[1]["ranking_score"] >= ranked[2]["ranking_score"]


# ==============================================================================
# 2. Lower ETA Preferred When Other Factors Equal
# ==============================================================================

def test_2_lower_eta_preferred_when_other_factors_equal():
    """Test 2: When risk, accessibility, distance, and vehicle fit are equal, lower ETA wins."""
    c1 = {
        "route_id": "route_faster",
        "total_distance_km": 50.0,
        "eta_seconds": 3000.0,  # faster
        "risk_score": 30.0,
        "accessibility_score": 0.80,
        "vehicle_profile_compatibility": 1.0,
    }
    c2 = {
        "route_id": "route_slower",
        "total_distance_km": 50.0,
        "eta_seconds": 4500.0,  # slower
        "risk_score": 30.0,
        "accessibility_score": 0.80,
        "vehicle_profile_compatibility": 1.0,
    }

    ranked = rank_route_candidates([c1, c2])
    assert ranked[0]["route_id"] == "route_faster"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["route_id"] == "route_slower"
    assert ranked[1]["rank"] == 2
    assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]


# ==============================================================================
# 3. Lower Risk Preferred When Other Factors Equal
# ==============================================================================

def test_3_lower_risk_preferred_when_other_factors_equal():
    """Test 3: When ETA, accessibility, distance, and vehicle fit are equal, lower risk wins."""
    c1 = {
        "route_id": "route_safe",
        "total_distance_km": 50.0,
        "eta_seconds": 3600.0,
        "risk_score": 20.0,  # lower risk
        "accessibility_score": 0.80,
        "vehicle_profile_compatibility": 1.0,
    }
    c2 = {
        "route_id": "route_risky",
        "total_distance_km": 50.0,
        "eta_seconds": 3600.0,
        "risk_score": 60.0,  # higher risk
        "accessibility_score": 0.80,
        "vehicle_profile_compatibility": 1.0,
    }

    ranked = rank_route_candidates([c1, c2])
    assert ranked[0]["route_id"] == "route_safe"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["route_id"] == "route_risky"
    assert ranked[1]["rank"] == 2
    assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]


# ==============================================================================
# 4. Higher Accessibility Preferred When Other Factors Equal
# ==============================================================================

def test_4_higher_accessibility_preferred_when_other_factors_equal():
    """Test 4: When ETA, risk, distance, and vehicle fit are equal, higher accessibility wins."""
    c1 = {
        "route_id": "route_high_acc",
        "total_distance_km": 50.0,
        "eta_seconds": 3600.0,
        "risk_score": 30.0,
        "accessibility_score": 0.90,  # higher accessibility
        "vehicle_profile_compatibility": 1.0,
    }
    c2 = {
        "route_id": "route_low_acc",
        "total_distance_km": 50.0,
        "eta_seconds": 3600.0,
        "risk_score": 30.0,
        "accessibility_score": 0.40,  # lower accessibility
        "vehicle_profile_compatibility": 1.0,
    }

    ranked = rank_route_candidates([c1, c2])
    assert ranked[0]["route_id"] == "route_high_acc"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["route_id"] == "route_low_acc"
    assert ranked[1]["rank"] == 2
    assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]


# ==============================================================================
# 5. Shorter Distance Preferred When Other Factors Equal
# ==============================================================================

def test_5_shorter_distance_preferred_when_other_factors_equal():
    """Test 5: When ETA, risk, accessibility, and vehicle fit are equal, shorter distance wins."""
    c1 = {
        "route_id": "route_short",
        "total_distance_km": 30.0,  # shorter
        "eta_seconds": 3600.0,
        "risk_score": 30.0,
        "accessibility_score": 0.80,
        "vehicle_profile_compatibility": 1.0,
    }
    c2 = {
        "route_id": "route_long",
        "total_distance_km": 60.0,  # longer
        "eta_seconds": 3600.0,
        "risk_score": 30.0,
        "accessibility_score": 0.80,
        "vehicle_profile_compatibility": 1.0,
    }

    ranked = rank_route_candidates([c1, c2])
    assert ranked[0]["route_id"] == "route_short"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["route_id"] == "route_long"
    assert ranked[1]["rank"] == 2
    assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]


# ==============================================================================
# 6. Vehicle Profile Compatibility Proxy Effect
# ==============================================================================

def test_6_vehicle_profile_compatibility_proxy_effect():
    """Test 6: Heavy truck profile penalizes routes on unpaved surfaces."""
    c_paved = {
        "route_id": "route_paved",
        "total_distance_km": 20.0,
        "risk_score": 25.0,
        "segments": [
            {"segment_id": "S1", "road_type": "primary", "surface": "asphalt", "segment_length_km": 20.0}
        ],
    }
    c_unpaved = {
        "route_id": "route_unpaved",
        "total_distance_km": 20.0,
        "risk_score": 25.0,
        "segments": [
            {"segment_id": "S2", "road_type": "primary", "surface": "unpaved", "segment_length_km": 20.0}
        ],
    }

    # Evaluate with heavy_truck profile
    ranked = rank_route_candidates([c_paved, c_unpaved], vehicle_profile="heavy_truck")

    assert ranked[0]["route_id"] == "route_paved"
    assert ranked[0]["metrics"]["vehicle_profile_compatibility"] > ranked[1]["metrics"]["vehicle_profile_compatibility"]
    assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]


# ==============================================================================
# 7. Deterministic Min-Max Normalization
# ==============================================================================

def test_7_deterministic_normalization():
    """Test 7: Normalized scores are strictly in [0.0, 1.0]."""
    c1 = {"route_id": "c1", "total_distance_km": 10.0, "eta_seconds": 1000.0, "risk_score": 10.0, "accessibility_score": 0.9, "vehicle_profile_compatibility": 1.0}
    c2 = {"route_id": "c2", "total_distance_km": 20.0, "eta_seconds": 2000.0, "risk_score": 30.0, "accessibility_score": 0.6, "vehicle_profile_compatibility": 0.5}
    c3 = {"route_id": "c3", "total_distance_km": 30.0, "eta_seconds": 3000.0, "risk_score": 50.0, "accessibility_score": 0.3, "vehicle_profile_compatibility": 0.0}

    ranked = rank_route_candidates([c1, c2, c3])

    for r in ranked:
        for k, val in r["normalized_scores"].items():
            assert 0.0 <= val <= 1.0, f"Normalized score {k} out of bounds: {val}"
        assert 0.0 <= r["ranking_score"] <= 1.0


# ==============================================================================
# 8. Constant Metric Sets
# ==============================================================================

def test_8_constant_metric_sets():
    """Test 8: When all candidates share identical values for a metric, utility is 1.0 without div-by-zero."""
    c1 = {"route_id": "c1", "total_distance_km": 15.0, "eta_seconds": 1500.0, "risk_score": 30.0, "accessibility_score": 0.8, "vehicle_profile_compatibility": 1.0}
    c2 = {"route_id": "c2", "total_distance_km": 15.0, "eta_seconds": 1500.0, "risk_score": 30.0, "accessibility_score": 0.8, "vehicle_profile_compatibility": 1.0}

    ranked = rank_route_candidates([c1, c2])

    assert len(ranked) == 2
    assert ranked[0]["normalized_scores"]["eta_score"] == 1.0
    assert ranked[0]["normalized_scores"]["risk_score"] == 1.0
    assert ranked[0]["normalized_scores"]["distance_score"] == 1.0
    assert ranked[0]["ranking_score"] == 1.0
    assert ranked[1]["ranking_score"] == 1.0


# ==============================================================================
# 9. Single-Candidate Input
# ==============================================================================

def test_9_single_candidate_input():
    """Test 9: Single candidate receives Rank 1 and perfect 1.0 normalized utility."""
    c = {
        "route_id": "only_route",
        "total_distance_km": 42.0,
        "eta_seconds": 2500.0,
        "risk_score": 35.0,
        "accessibility_score": 0.75,
        "vehicle_profile_compatibility": 0.95,
    }

    ranked = rank_route_candidates([c])

    assert len(ranked) == 1
    assert ranked[0]["rank"] == 1
    assert ranked[0]["route_id"] == "only_route"
    assert ranked[0]["ranking_score"] == 1.0000
    assert ranked[0]["normalized_scores"]["eta_score"] == 1.0
    assert ranked[0]["tradeoff_summary"]["is_fastest"] is True
    assert ranked[0]["tradeoff_summary"]["is_lowest_risk"] is True


# ==============================================================================
# 10. Deterministic Tie-Breaking
# ==============================================================================

def test_10_deterministic_tie_breaking():
    """Test 10: When ranking scores are tied, shorter distance, then fewer segments, then IDs break ties."""
    c1 = {
        "route_id": "route_A",
        "total_distance_km": 20.0,
        "segment_count": 3,
        "segment_ids": ["S1", "S2", "S3"],
        "eta_seconds": 1800.0,
        "risk_score": 25.0,
        "accessibility_score": 0.8,
        "vehicle_profile_compatibility": 1.0,
    }
    c2 = {
        "route_id": "route_B",
        "total_distance_km": 18.0,  # Shorter distance breaks tie
        "segment_count": 3,
        "segment_ids": ["S4", "S5", "S6"],
        "eta_seconds": 1800.0,
        "risk_score": 25.0,
        "accessibility_score": 0.8,
        "vehicle_profile_compatibility": 1.0,
    }

    weights = {"eta": 0.4, "risk": 0.3, "accessibility": 0.3, "distance": 0.0, "vehicle_profile_compatibility": 0.0}
    ranked = rank_route_candidates([c1, c2], custom_weights=weights)

    assert ranked[0]["ranking_score"] == ranked[1]["ranking_score"]
    assert ranked[0]["route_id"] == "route_B"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["route_id"] == "route_A"
    assert ranked[1]["rank"] == 2


# ==============================================================================
# 11. Invalid Candidate Values Rejected
# ==============================================================================

def test_11_invalid_candidate_values_rejected():
    """Test 11: Negative, non-numeric, inf, or NaN values raise RouteRankingValidationError."""
    # Negative distance
    with pytest.raises(RouteRankingValidationError, match="total_distance_km"):
        rank_route_candidates([{"route_id": "c1", "total_distance_km": -10.0, "risk_score": 10.0}])

    # NaN ETA
    with pytest.raises(RouteRankingValidationError, match="eta_seconds"):
        rank_route_candidates([{"route_id": "c1", "total_distance_km": 10.0, "eta_seconds": float("nan"), "risk_score": 10.0}])

    # Inf risk
    with pytest.raises(RouteRankingValidationError, match="risk_score"):
        rank_route_candidates([{"route_id": "c1", "total_distance_km": 10.0, "risk_score": float("inf")}])

    # Missing route_id
    with pytest.raises(RouteRankingValidationError, match="non-empty 'route_id'"):
        rank_route_candidates([{"total_distance_km": 10.0, "risk_score": 10.0}])


# ==============================================================================
# 12. Strict Risk Integrity Validation (Never Fabricate, Default, or Derive)
# ==============================================================================

def test_12_no_precomputed_and_no_context_rejected(candidates_without_precomputed_risk):
    """Test 12a: If risk is not precomputed and no risk_context is provided, raise error."""
    with pytest.raises(RouteRankingValidationError, match="no precomputed 'risk_score' and no complete 'risk_context'"):
        rank_route_candidates(candidates_without_precomputed_risk, risk_context=None)


def test_12_missing_incident_severity_rejected(candidates_without_precomputed_risk, complete_risk_context):
    """Test 12b: incident_severity must NEVER be defaulted to 0; missing field must raise error."""
    bad_context = dict(complete_risk_context)
    del bad_context["incident_severity"]

    with pytest.raises(RouteRankingValidationError, match="missing required field.*incident_severity"):
        rank_route_candidates(candidates_without_precomputed_risk, risk_context=bad_context)


def test_12_missing_current_delay_ratio_rejected(candidates_without_precomputed_risk, complete_risk_context):
    """Test 12c: current_delay_ratio must NEVER be derived from ETA; missing field must raise error."""
    bad_context = dict(complete_risk_context)
    del bad_context["current_delay_ratio"]

    with pytest.raises(RouteRankingValidationError, match="missing required field.*current_delay_ratio"):
        rank_route_candidates(candidates_without_precomputed_risk, risk_context=bad_context)


def test_12_missing_accessibility_score_rejected(candidates_without_precomputed_risk, complete_risk_context):
    """Test 12d: accessibility_score must NEVER be derived from segments for risk; missing field must raise error."""
    bad_context = dict(complete_risk_context)
    del bad_context["accessibility_score"]

    with pytest.raises(RouteRankingValidationError, match="missing required field.*accessibility_score"):
        rank_route_candidates(candidates_without_precomputed_risk, risk_context=bad_context)


def test_12_missing_other_risk_fields_rejected(candidates_without_precomputed_risk, complete_risk_context):
    """Test 12e: weather_severity, road_condition_score, network_criticality must all be explicitly present."""
    for field in ("weather_severity", "road_condition_score", "network_criticality"):
        bad_context = dict(complete_risk_context)
        del bad_context[field]
        with pytest.raises(RouteRankingValidationError, match=f"missing required field.*{field}"):
            rank_route_candidates(candidates_without_precomputed_risk, risk_context=bad_context)


def test_12_complete_risk_context_evaluates_via_risk_engine(candidates_without_precomputed_risk, complete_risk_context):
    """Test 12f: When all 6 required fields are explicitly provided, evaluates risk cleanly."""
    ranked = rank_route_candidates(candidates_without_precomputed_risk, risk_context=complete_risk_context)

    assert len(ranked) == 2
    for r in ranked:
        assert "risk_score" in r["metrics"]
        assert 0.0 <= r["metrics"]["risk_score"] <= 100.0


# ==============================================================================
# 13. No Candidate Mutation
# ==============================================================================

def test_13_no_candidate_mutation(sample_candidates_with_precomputed_risk):
    """Test 13: Caller candidate input mappings are not mutated."""
    snapshot = [dict(c) for c in sample_candidates_with_precomputed_risk]

    _ = rank_route_candidates(sample_candidates_with_precomputed_risk)

    assert sample_candidates_with_precomputed_risk == snapshot


# ==============================================================================
# 14. No External API Calls (Zero Network)
# ==============================================================================

def test_14_pure_standard_library_no_external_apis(sample_candidates_with_precomputed_risk, monkeypatch):
    """Test 14: Confirms ranking uses no socket/http requests."""
    import socket
    def forbidden_connect(*args, **kwargs):
        raise RuntimeError("External network connection attempted!")
    monkeypatch.setattr(socket, "socket", forbidden_connect)

    ranked = rank_route_candidates(sample_candidates_with_precomputed_risk)
    assert len(ranked) == 3


# ==============================================================================
# 15. Package Import Through src.routing Works & Exact Weights Sum
# ==============================================================================

def test_15_package_import_and_exact_weights_sum():
    """Test 15: Public symbols importable cleanly from src.routing and weights mathematically sum to 1.0."""
    from src.routing import DEFAULT_RANKING_WEIGHTS, RouteRankingValidationError, rank_route_candidates
    assert callable(rank_route_candidates)
    assert issubclass(RouteRankingValidationError, ValueError)
    assert "eta" in DEFAULT_RANKING_WEIGHTS

    # Mathematically sums to exactly 1.0 in IEEE 754 float
    assert sum(DEFAULT_RANKING_WEIGHTS.values()) == 1.0

    # Preserves approved proportional ratios
    assert math.isclose(DEFAULT_RANKING_WEIGHTS["eta"], 30.0 / 95.0, abs_tol=1e-12)
    assert math.isclose(DEFAULT_RANKING_WEIGHTS["risk"], 20.0 / 95.0, abs_tol=1e-12)
    assert math.isclose(DEFAULT_RANKING_WEIGHTS["accessibility"], 20.0 / 95.0, abs_tol=1e-12)
    assert math.isclose(DEFAULT_RANKING_WEIGHTS["distance"], 15.0 / 95.0, abs_tol=1e-12)
    assert math.isclose(DEFAULT_RANKING_WEIGHTS["vehicle_profile_compatibility"], 10.0 / 95.0, abs_tol=1e-12)


# ==============================================================================
# 16. Ranking Does Not Generate Additional Routes
# ==============================================================================

def test_16_ranking_preserves_candidate_count(sample_candidates_with_precomputed_risk):
    """Test 16: Exact N input candidates yields exact N ranked output candidates."""
    ranked = rank_route_candidates(sample_candidates_with_precomputed_risk)
    assert len(ranked) == len(sample_candidates_with_precomputed_risk)
    assert {r["route_id"] for r in ranked} == {c["route_id"] for c in sample_candidates_with_precomputed_risk}


# ==============================================================================
# 17. Ranking Does Not Perform Rerouting
# ==============================================================================

def test_17_ranking_does_not_perform_rerouting(sample_candidates_with_precomputed_risk):
    """Test 17: Ranks existing candidates without modifying their route sequences or state."""
    ranked = rank_route_candidates(sample_candidates_with_precomputed_risk)

    for r, orig in zip(ranked, sample_candidates_with_precomputed_risk):
        matching_orig = next(c for c in sample_candidates_with_precomputed_risk if c["route_id"] == r["route_id"])
        assert r["segment_ids"] == matching_orig["segment_ids"]
        assert r["node_ids"] == matching_orig["node_ids"]


# ==============================================================================
# 18. Output Preserves Candidate Segment Metadata
# ==============================================================================

def test_18_output_preserves_segment_metadata(sample_candidates_with_precomputed_risk):
    """Test 18: Preserves nested segment metadata (road_type, surface, etc.) on ranked records."""
    ranked = rank_route_candidates(sample_candidates_with_precomputed_risk)

    for r in ranked:
        assert "segments" in r
        assert len(r["segments"]) == r["segment_count"]
        for s in r["segments"]:
            assert "road_type" in s
            assert "surface" in s


# ==============================================================================
# 19. Repeated Invocation is Deterministic Across 100 Runs
# ==============================================================================

def test_19_repeated_invocation_deterministic_100_runs(sample_candidates_with_precomputed_risk):
    """Test 19: 100 consecutive invocations yield strictly identical ranking results."""
    first_result = rank_route_candidates(sample_candidates_with_precomputed_risk)

    for _ in range(100):
        run_result = rank_route_candidates(sample_candidates_with_precomputed_risk)
        assert run_result == first_result


# ==============================================================================
# 20. Strict Custom Weights Validation
# ==============================================================================

def test_20_strict_custom_weights_validation(sample_candidates_with_precomputed_risk):
    """Test 20: Strict validation of custom weights rejects unknown keys, negative values, and zero sums."""
    # Valid custom weights
    custom_w = {"eta": 0.0, "risk": 0.0, "accessibility": 1.0, "distance": 0.0, "vehicle_profile_compatibility": 0.0}
    ranked = rank_route_candidates(sample_candidates_with_precomputed_risk, custom_weights=custom_w)
    assert ranked[0]["route_id"] == "candidate_001"
    assert ranked[0]["ranking_score"] == 1.0

    # Unknown key in custom_weights MUST be rejected
    with pytest.raises(RouteRankingValidationError, match="Unknown key.*availability"):
        rank_route_candidates(
            sample_candidates_with_precomputed_risk,
            custom_weights={"availability": 0.05, "eta": 0.30},
        )

    # Unknown arbitrary key in custom_weights MUST be rejected
    with pytest.raises(RouteRankingValidationError, match="Unknown key.*speed"):
        rank_route_candidates(
            sample_candidates_with_precomputed_risk,
            custom_weights={"speed": 0.20},
        )

    # Negative custom weight raises error
    with pytest.raises(RouteRankingValidationError, match="custom_weights"):
        rank_route_candidates(sample_candidates_with_precomputed_risk, custom_weights={"eta": -0.5})

    # Zero total weights raises error
    with pytest.raises(RouteRankingValidationError, match="strictly positive"):
        rank_route_candidates(
            sample_candidates_with_precomputed_risk,
            custom_weights={"eta": 0.0, "risk": 0.0, "accessibility": 0.0, "distance": 0.0, "vehicle_profile_compatibility": 0.0},
        )
