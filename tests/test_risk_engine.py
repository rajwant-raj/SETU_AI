"""Tests for SETU Risk Engine v0.1.

Verification of deterministic weighted risk scoring, clamping, inversions,
risk band boundaries, explainability reasons, validation errors, and determinism.
"""

import math
import pytest

from src.risk.risk_engine import (
    RiskEngineValidationError,
    calculate_risk,
    assess_risk,
    _classify_risk_band,
    WEIGHTS,
    REQUIRED_FIELDS,
)


@pytest.fixture
def baseline_safe_inputs():
    """Baseline inputs with zero risk (safe/optimal conditions)."""
    return {
        "incident_severity": 0.0,
        "accessibility_score": 1.0,  # 1.0 = fully accessible -> 0.0 risk
        "weather_severity": 0.0,
        "road_condition_score": 1.0,  # 1.0 = good condition -> 0.0 risk
        "network_criticality": 0.0,
        "current_delay_ratio": 0.0,
    }


@pytest.fixture
def baseline_worst_inputs():
    """Baseline inputs with maximum risk across all factors."""
    return {
        "incident_severity": 1.0,
        "accessibility_score": 0.0,  # 0.0 = inaccessible -> 1.0 risk
        "weather_severity": 1.0,
        "road_condition_score": 0.0,  # 0.0 = poor condition -> 1.0 risk
        "network_criticality": 1.0,
        "current_delay_ratio": 1.0,
    }


# ==============================================================================
# Requirement 10: Weights sum to exactly 1.00
# ==============================================================================
def test_weights_sum_to_one():
    """Verify that prototype policy weights sum to exactly 1.00."""
    total_weight = sum(WEIGHTS.values())
    assert math.isclose(total_weight, 1.00, rel_tol=1e-9)
    assert total_weight == 1.00

    assert WEIGHTS["incident_severity"] == 0.30
    assert WEIGHTS["weather_severity"] == 0.20
    assert WEIGHTS["accessibility_risk"] == 0.15
    assert WEIGHTS["road_condition_risk"] == 0.15
    assert WEIGHTS["network_criticality"] == 0.10
    assert WEIGHTS["current_delay_ratio"] == 0.10


# ==============================================================================
# Requirement 1: All-zero inputs
# ==============================================================================
def test_all_zero_inputs():
    """Test when all six raw input values are explicitly 0.0.
    
    Because accessibility_score (0.0) and road_condition_score (0.0) invert to 1.0 risk,
    the score is 100 * (0.15 + 0.15) = 30.0 (MEDIUM band).
    """
    inputs = {field: 0.0 for field in REQUIRED_FIELDS}
    result = calculate_risk(inputs)

    assert result["risk_score"] == 30.0
    assert result["risk_level"] == "MEDIUM"
    assert "LOW_ACCESSIBILITY" in result["reason_codes"]
    assert "POOR_ROAD_CONDITION" in result["reason_codes"]


def test_zero_risk_baseline(baseline_safe_inputs):
    """Test zero-risk conditions (incident=0, weather=0, accessible=1, good road=1).
    
    Risk score must be 0.0 in the LOW band with no reasons.
    """
    result = calculate_risk(baseline_safe_inputs)

    assert result["risk_score"] == 0.0
    assert result["risk_level"] == "LOW"
    assert result["reason_codes"] == []
    assert result["reasons"] == []


# ==============================================================================
# Requirement 2: All-one inputs
# ==============================================================================
def test_all_one_inputs():
    """Test when all six raw input values are explicitly 1.0.
    
    Because accessibility_score (1.0) and road_condition_score (1.0) invert to 0.0 risk,
    the score is 100 * (0.30 + 0.20 + 0.10 + 0.10) = 70.0 (HIGH band).
    """
    inputs = {field: 1.0 for field in REQUIRED_FIELDS}
    result = calculate_risk(inputs)

    assert result["risk_score"] == 70.0
    assert result["risk_level"] == "HIGH"
    assert "HIGH_INCIDENT_SEVERITY" in result["reason_codes"]
    assert "ADVERSE_WEATHER" in result["reason_codes"]
    assert "HIGH_NETWORK_CRITICALITY" in result["reason_codes"]
    assert "HIGH_CURRENT_DELAY" in result["reason_codes"]
    assert "LOW_ACCESSIBILITY" not in result["reason_codes"]
    assert "POOR_ROAD_CONDITION" not in result["reason_codes"]


def test_all_one_risk_inputs(baseline_worst_inputs):
    """Test maximum risk conditions across all 6 factors.
    
    Risk score must be 100.0 in the CRITICAL band.
    """
    result = calculate_risk(baseline_worst_inputs)

    assert result["risk_score"] == 100.0
    assert result["risk_level"] == "CRITICAL"
    assert len(result["reason_codes"]) == 6


# ==============================================================================
# Requirement 3: Accessibility inversion
# ==============================================================================
def test_accessibility_inversion(baseline_safe_inputs):
    """Verify accessibility_score inversion: accessibility_risk = 1 - accessibility_score."""
    # When fully accessible (1.0), risk is 0
    safe_copy = dict(baseline_safe_inputs)
    safe_copy["accessibility_score"] = 1.0
    assert calculate_risk(safe_copy)["risk_score"] == 0.0

    # When inaccessible (0.0), risk contribution is 100 * 0.15 = 15.0
    inaccessible = dict(baseline_safe_inputs)
    inaccessible["accessibility_score"] = 0.0
    assert calculate_risk(inaccessible)["risk_score"] == 15.0

    # Intermediate value: accessibility_score = 0.6 -> risk = 0.4 -> 100 * 0.15 * 0.4 = 6.0
    partial = dict(baseline_safe_inputs)
    partial["accessibility_score"] = 0.6
    assert calculate_risk(partial)["risk_score"] == 6.0

    # Inversion property: higher accessibility score must yield strictly lower risk
    assert calculate_risk(safe_copy)["risk_score"] < calculate_risk(partial)["risk_score"] < calculate_risk(inaccessible)["risk_score"]


# ==============================================================================
# Requirement 4: Road-condition inversion
# ==============================================================================
def test_road_condition_inversion(baseline_safe_inputs):
    """Verify road_condition_score inversion: road_condition_risk = 1 - road_condition_score."""
    # When good condition (1.0), risk is 0
    good_road = dict(baseline_safe_inputs)
    good_road["road_condition_score"] = 1.0
    assert calculate_risk(good_road)["risk_score"] == 0.0

    # When poor condition (0.0), risk contribution is 100 * 0.15 = 15.0
    poor_road = dict(baseline_safe_inputs)
    poor_road["road_condition_score"] = 0.0
    assert calculate_risk(poor_road)["risk_score"] == 15.0

    # Intermediate value: road_condition_score = 0.2 -> risk = 0.8 -> 100 * 0.15 * 0.8 = 12.0
    rough_road = dict(baseline_safe_inputs)
    rough_road["road_condition_score"] = 0.2
    assert calculate_risk(rough_road)["risk_score"] == 12.0

    # Inversion property: higher road condition score must yield strictly lower risk
    assert calculate_risk(good_road)["risk_score"] < calculate_risk(rough_road)["risk_score"] < calculate_risk(poor_road)["risk_score"]


# ==============================================================================
# Requirement 5: Every risk-band boundary
# ==============================================================================
@pytest.mark.parametrize(
    "score,expected_band",
    [
        (0.0, "LOW"),
        (10.0, "LOW"),
        (24.99, "LOW"),
        (25.0, "MEDIUM"),
        (35.0, "MEDIUM"),
        (49.99, "MEDIUM"),
        (50.0, "HIGH"),
        (60.0, "HIGH"),
        (74.99, "HIGH"),
        (75.0, "CRITICAL"),
        (90.0, "CRITICAL"),
        (100.0, "CRITICAL"),
    ],
)
def test_risk_band_boundaries_direct(score, expected_band):
    """Verify exact classification rules at all boundaries."""
    assert _classify_risk_band(score) == expected_band


def test_risk_band_boundaries_integrated(baseline_safe_inputs):
    """Verify risk bands produced end-to-end through calculate_risk."""
    # 1. LOW: baseline safe inputs produce score 0.0
    res_0 = calculate_risk(baseline_safe_inputs)
    assert res_0["risk_score"] == 0.0
    assert res_0["risk_level"] == "LOW"

    # 2. MEDIUM boundary: incident_severity = 25.0 / 30.0 = 5/6 = 0.8333333333333334
    # 100 * 0.30 * (5/6) = 25.0
    med_inputs = dict(baseline_safe_inputs)
    med_inputs["incident_severity"] = 5.0 / 6.0
    res_25 = calculate_risk(med_inputs)
    assert res_25["risk_score"] == 25.0
    assert res_25["risk_level"] == "MEDIUM"

    # 3. Just below MEDIUM: 24.99
    below_med_inputs = dict(baseline_safe_inputs)
    below_med_inputs["incident_severity"] = 24.99 / 30.0
    res_below_med = calculate_risk(below_med_inputs)
    assert res_below_med["risk_score"] == 24.99
    assert res_below_med["risk_level"] == "LOW"

    # 4. HIGH boundary: 50.0 -> incident_severity = 1.0 (30) + weather_severity = 1.0 (20) -> 50.0
    high_inputs = dict(baseline_safe_inputs)
    high_inputs["incident_severity"] = 1.0
    high_inputs["weather_severity"] = 1.0
    res_50 = calculate_risk(high_inputs)
    assert res_50["risk_score"] == 50.0
    assert res_50["risk_level"] == "HIGH"

    # 5. Just below HIGH: 49.99
    below_high_inputs = dict(baseline_safe_inputs)
    below_high_inputs["incident_severity"] = 1.0  # 30.0
    below_high_inputs["weather_severity"] = 19.99 / 20.0  # 19.99
    res_below_high = calculate_risk(below_high_inputs)
    assert res_below_high["risk_score"] == 49.99
    assert res_below_high["risk_level"] == "MEDIUM"

    # 6. CRITICAL boundary: 75.0 -> incident (30) + weather (20) + accessibility_risk (15) + delay (10) = 75.0
    crit_inputs = dict(baseline_safe_inputs)
    crit_inputs["incident_severity"] = 1.0  # 30
    crit_inputs["weather_severity"] = 1.0   # 20
    crit_inputs["accessibility_score"] = 0.0 # risk 1.0 -> 15
    crit_inputs["current_delay_ratio"] = 1.0 # 10
    res_75 = calculate_risk(crit_inputs)
    assert res_75["risk_score"] == 75.0
    assert res_75["risk_level"] == "CRITICAL"

    # 7. Just below CRITICAL: 74.99
    below_crit_inputs = dict(crit_inputs)
    below_crit_inputs["current_delay_ratio"] = 9.99 / 10.0
    res_below_crit = calculate_risk(below_crit_inputs)
    assert res_below_crit["risk_score"] == 74.99
    assert res_below_crit["risk_level"] == "HIGH"

    # 8. CRITICAL max: 100.0
    max_inputs = {
        "incident_severity": 1.0,
        "accessibility_score": 0.0,
        "weather_severity": 1.0,
        "road_condition_score": 0.0,
        "network_criticality": 1.0,
        "current_delay_ratio": 1.0,
    }
    res_100 = calculate_risk(max_inputs)
    assert res_100["risk_score"] == 100.0
    assert res_100["risk_level"] == "CRITICAL"


# ==============================================================================
# Requirement 6: Clamping
# ==============================================================================
def test_input_clamping_above_one():
    """Inputs exceeding 1.0 must be clamped to 1.0 without raising errors."""
    overclamped = {
        "incident_severity": 2.5,
        "accessibility_score": 5.0,
        "weather_severity": 1.2,
        "road_condition_score": 10.0,
        "network_criticality": 1.5,
        "current_delay_ratio": 3.0,
    }
    normal = {
        "incident_severity": 1.0,
        "accessibility_score": 1.0,
        "weather_severity": 1.0,
        "road_condition_score": 1.0,
        "network_criticality": 1.0,
        "current_delay_ratio": 1.0,
    }
    assert calculate_risk(overclamped) == calculate_risk(normal)


def test_input_clamping_below_zero():
    """Inputs below 0.0 must be clamped to 0.0 without raising errors."""
    underclamped = {
        "incident_severity": -0.5,
        "accessibility_score": -1.0,
        "weather_severity": -10.0,
        "road_condition_score": -0.1,
        "network_criticality": -2.0,
        "current_delay_ratio": -0.01,
    }
    zeros = {field: 0.0 for field in REQUIRED_FIELDS}
    assert calculate_risk(underclamped) == calculate_risk(zeros)


# ==============================================================================
# Requirement 7: Missing fields & Validation
# ==============================================================================
@pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
def test_missing_required_field_raises_validation_error(baseline_safe_inputs, missing_field):
    """Missing any required field must raise RiskEngineValidationError."""
    incomplete = dict(baseline_safe_inputs)
    del incomplete[missing_field]

    with pytest.raises(RiskEngineValidationError) as exc_info:
        calculate_risk(incomplete)
    assert "Missing required input fields" in str(exc_info.value)
    assert missing_field in str(exc_info.value)


def test_none_value_raises_validation_error(baseline_safe_inputs):
    """Passing None for a required field must raise RiskEngineValidationError."""
    inputs_with_none = dict(baseline_safe_inputs)
    inputs_with_none["weather_severity"] = None

    with pytest.raises(RiskEngineValidationError) as exc_info:
        calculate_risk(inputs_with_none)
    assert "Missing required input fields" in str(exc_info.value)
    assert "weather_severity" in str(exc_info.value)


def test_invalid_data_type_raises_validation_error(baseline_safe_inputs):
    """Non-numeric types or invalid types must raise RiskEngineValidationError."""
    # Test non-mapping
    with pytest.raises(RiskEngineValidationError):
        calculate_risk(["not", "a", "dict"])

    # Test string value
    invalid_string = dict(baseline_safe_inputs)
    invalid_string["incident_severity"] = "high"
    with pytest.raises(RiskEngineValidationError):
        calculate_risk(invalid_string)

    # Test boolean value (rejected explicitly even though bool is subclass of int)
    invalid_bool = dict(baseline_safe_inputs)
    invalid_bool["incident_severity"] = True
    with pytest.raises(RiskEngineValidationError):
        calculate_risk(invalid_bool)

    # Test NaN and Infinity
    nan_inputs = dict(baseline_safe_inputs)
    nan_inputs["incident_severity"] = float("nan")
    with pytest.raises(RiskEngineValidationError):
        calculate_risk(nan_inputs)

    inf_inputs = dict(baseline_safe_inputs)
    inf_inputs["incident_severity"] = float("inf")
    with pytest.raises(RiskEngineValidationError):
        calculate_risk(inf_inputs)


# ==============================================================================
# Requirement 8: Deterministic repeated execution
# ==============================================================================
def test_deterministic_repeated_execution():
    """Identical inputs must consistently yield identical outputs across many runs."""
    inputs = {
        "incident_severity": 0.72,
        "accessibility_score": 0.35,
        "weather_severity": 0.88,
        "road_condition_score": 0.45,
        "network_criticality": 0.90,
        "current_delay_ratio": 0.60,
    }

    reference = calculate_risk(inputs)

    for _ in range(100):
        result = calculate_risk(inputs)
        assert result == reference
        assert result["risk_score"] == reference["risk_score"]
        assert result["risk_level"] == reference["risk_level"]
        assert result["reason_codes"] == reference["reason_codes"]
        assert result["reasons"] == reference["reasons"]


# ==============================================================================
# Requirement 9: Reason-code generation
# ==============================================================================
def test_reason_code_generation_spec_example():
    """Verify reason code generation matches Section 7 of the specification.
    
    Spec example:
    risk_score: 81.0, CRITICAL
    reason_codes: ["HIGH_INCIDENT_SEVERITY", "ADVERSE_WEATHER", "LOW_ACCESSIBILITY"]
    reasons: ["High incident severity", "Adverse weather conditions", "Low route accessibility"]
    """
    inputs = {
        "incident_severity": 1.0,     # risk 1.0 -> weight 0.30 -> 30.0 (HIGH reason)
        "accessibility_score": 0.0,   # risk 1.0 -> weight 0.15 -> 15.0 (HIGH reason)
        "weather_severity": 0.90,     # risk 0.90 -> weight 0.20 -> 18.0 (HIGH reason)
        "road_condition_score": 1.0,  # risk 0.0 -> weight 0.15 -> 0.0 (no reason)
        "network_criticality": 0.90,  # risk 0.90 -> weight 0.10 -> 9.0 (HIGH reason)
        "current_delay_ratio": 0.90,  # risk 0.90 -> weight 0.10 -> 9.0 (HIGH reason)
    }
    # Total = 30 + 15 + 18 + 0 + 9 + 9 = 81.0
    result = calculate_risk(inputs)

    assert result["risk_score"] == 81.0
    assert result["risk_level"] == "CRITICAL"
    assert "HIGH_INCIDENT_SEVERITY" in result["reason_codes"]
    assert "ADVERSE_WEATHER" in result["reason_codes"]
    assert "LOW_ACCESSIBILITY" in result["reason_codes"]
    assert "High incident severity" in result["reasons"]
    assert "Adverse weather conditions" in result["reasons"]
    assert "Low route accessibility" in result["reasons"]


def test_moderate_reasons_and_omissions():
    """Verify factors between 0.50 and 0.749 produce moderate reasons, and <0.50 are omitted."""
    inputs = {
        "incident_severity": 0.60,      # MODERATE
        "accessibility_score": 0.40,    # risk 0.60 -> MODERATE
        "weather_severity": 0.20,       # risk 0.20 -> OMITTED
        "road_condition_score": 0.85,   # risk 0.15 -> OMITTED
        "network_criticality": 0.65,    # MODERATE
        "current_delay_ratio": 0.10,    # OMITTED
    }
    result = calculate_risk(inputs)

    assert "MODERATE_INCIDENT_SEVERITY" in result["reason_codes"]
    assert "REDUCED_ACCESSIBILITY" in result["reason_codes"]
    assert "MODERATE_NETWORK_CRITICALITY" in result["reason_codes"]

    # Omitted factors
    assert "ADVERSE_WEATHER" not in result["reason_codes"]
    assert "MODERATE_WEATHER_RISK" not in result["reason_codes"]
    assert "POOR_ROAD_CONDITION" not in result["reason_codes"]
    assert "DEGRADED_ROAD_CONDITION" not in result["reason_codes"]
    assert "HIGH_CURRENT_DELAY" not in result["reason_codes"]
    assert "MODERATE_CURRENT_DELAY" not in result["reason_codes"]


# ==============================================================================
# assess_risk Alias and Calling Style Interface
# ==============================================================================
def test_assess_risk_alias_and_kwargs(baseline_safe_inputs):
    """Verify assess_risk alias and kwargs calling style work identically to calculate_risk."""
    res_func = calculate_risk(baseline_safe_inputs)
    res_alias = assess_risk(baseline_safe_inputs)
    res_kwargs = calculate_risk(**baseline_safe_inputs)
    res_alias_kwargs = assess_risk(**baseline_safe_inputs)

    assert res_func == res_alias == res_kwargs == res_alias_kwargs
