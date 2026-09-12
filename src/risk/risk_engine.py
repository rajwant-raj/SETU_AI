"""SETU Risk Engine v0.1.

Deterministic risk assessment engine for road segments and routes.
Converts incident severity, weather, accessibility, road condition,
network criticality, and delay into a deterministic risk score, risk band,
and explainable machine-readable reason codes and human-readable reasons.

Specification: src/risk/RISK_ENGINE_SPEC_v0.1.md
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Tuple


class RiskEngineValidationError(ValueError):
    """Raised when required inputs are missing, invalid, or non-numeric."""
    pass


# Prototype policy weights (sum exactly to 1.00)
WEIGHTS: Dict[str, float] = {
    "incident_severity": 0.30,
    "weather_severity": 0.20,
    "accessibility_risk": 0.15,
    "road_condition_risk": 0.15,
    "network_criticality": 0.10,
    "current_delay_ratio": 0.10,
}

# Six required input fields as defined in the v0.1 specification
REQUIRED_FIELDS: Tuple[str, ...] = (
    "incident_severity",
    "accessibility_score",
    "weather_severity",
    "road_condition_score",
    "network_criticality",
    "current_delay_ratio",
)

# Threshold constants for risk bands
BAND_LOW_MAX = 25.0
BAND_MEDIUM_MAX = 50.0
BAND_HIGH_MAX = 75.0
BAND_CRITICAL_MAX = 100.0

# Thresholds for explainability factor reporting
REASON_THRESHOLD_HIGH = 0.75
REASON_THRESHOLD_MODERATE = 0.50

# Deterministic reason mapping per factor risk
REASON_CONFIG: Dict[str, Dict[str, Tuple[str, str]]] = {
    "incident_severity": {
        "high": ("HIGH_INCIDENT_SEVERITY", "High incident severity"),
        "moderate": ("MODERATE_INCIDENT_SEVERITY", "Moderate incident severity"),
    },
    "weather_severity": {
        "high": ("ADVERSE_WEATHER", "Adverse weather conditions"),
        "moderate": ("MODERATE_WEATHER_RISK", "Moderate weather conditions"),
    },
    "accessibility_risk": {
        "high": ("LOW_ACCESSIBILITY", "Low route accessibility"),
        "moderate": ("REDUCED_ACCESSIBILITY", "Reduced route accessibility"),
    },
    "road_condition_risk": {
        "high": ("POOR_ROAD_CONDITION", "Poor road condition"),
        "moderate": ("DEGRADED_ROAD_CONDITION", "Degraded road condition"),
    },
    "network_criticality": {
        "high": ("HIGH_NETWORK_CRITICALITY", "High network criticality"),
        "moderate": ("MODERATE_NETWORK_CRITICALITY", "Moderate network criticality"),
    },
    "current_delay_ratio": {
        "high": ("HIGH_CURRENT_DELAY", "Significant route delay"),
        "moderate": ("MODERATE_CURRENT_DELAY", "Moderate route delay"),
    },
}


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp a floating point value to the [min_val, max_val] interval."""
    return max(min_val, min(max_val, float(value)))


def _extract_inputs(data: Mapping[str, Any] | None = None, **kwargs: Any) -> Dict[str, float]:
    """Validate and extract required input values without inventing missing data."""
    merged: Dict[str, Any] = {}
    if data is not None:
        if not isinstance(data, Mapping):
            raise RiskEngineValidationError(
                f"Expected inputs to be a mapping/dict, got {type(data).__name__}"
            )
        merged.update(data)
    merged.update(kwargs)

    missing: List[str] = [field for field in REQUIRED_FIELDS if field not in merged or merged[field] is None]
    if missing:
        raise RiskEngineValidationError(
            f"Missing required input fields: {', '.join(missing)}"
        )

    validated: Dict[str, float] = {}
    for field in REQUIRED_FIELDS:
        val = merged[field]
        # Boolean is an int subclass in Python; reject boolean explicitly
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise RiskEngineValidationError(
                f"Field '{field}' must be a numeric value, got {type(val).__name__} ({val!r})"
            )
        float_val = float(val)
        if not math.isfinite(float_val):
            raise RiskEngineValidationError(
                f"Field '{field}' must be a finite number, got {float_val}"
            )
        validated[field] = float_val

    return validated


def _classify_risk_band(score: float) -> str:
    """Classify continuous score into risk band using lower-inclusive, upper-exclusive intervals."""
    if score < BAND_LOW_MAX:
        return "LOW"
    elif score < BAND_MEDIUM_MAX:
        return "MEDIUM"
    elif score < BAND_HIGH_MAX:
        return "HIGH"
    else:
        return "CRITICAL"


def _generate_reasons(
    factor_risks: List[Tuple[str, float]]
) -> Tuple[List[str], List[str]]:
    """Deterministically generate reason codes and human-readable reasons for factors >= 0.50.
    
    Factors are reported in order of strongest contribution (factor risk descending,
    then weight descending, then field name).
    """
    qualifying_factors: List[Tuple[float, float, str, str, str]] = []

    for factor_name, risk_val in factor_risks:
        config = REASON_CONFIG.get(factor_name)
        if not config:
            continue

        if risk_val >= REASON_THRESHOLD_HIGH:
            code, text = config["high"]
            weight = WEIGHTS.get(factor_name, 0.0)
            qualifying_factors.append((risk_val, weight, factor_name, code, text))
        elif risk_val >= REASON_THRESHOLD_MODERATE:
            code, text = config["moderate"]
            weight = WEIGHTS.get(factor_name, 0.0)
            qualifying_factors.append((risk_val, weight, factor_name, code, text))

    # Sort primarily by risk_val descending, secondarily by weight descending, tertiarily by factor_name
    qualifying_factors.sort(key=lambda item: (-item[0], -item[1], item[2]))

    reason_codes = [item[3] for item in qualifying_factors]
    reasons = [item[4] for item in qualifying_factors]
    return reason_codes, reasons


def calculate_risk(
    data: Mapping[str, Any] | None = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """Calculate deterministic risk score, band, and reasons according to RISK_ENGINE_SPEC_v0.1.

    Args:
        data: Mapping containing the six required fields:
            - incident_severity: 0-1
            - accessibility_score: 0-1 (1 = fully accessible)
            - weather_severity: 0-1
            - road_condition_score: 0-1 (1 = good condition)
            - network_criticality: 0-1
            - current_delay_ratio: 0-1
        **kwargs: Alternative keyword arguments for the six fields.

    Returns:
        Structured dictionary matching specification:
        {
            "risk_score": float (0-100),
            "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
            "reason_codes": List[str],
            "reasons": List[str]
        }

    Raises:
        RiskEngineValidationError: If any required field is missing or invalid.
    """
    raw_inputs = _extract_inputs(data, **kwargs)

    # 1. Clamp inputs to [0, 1]
    incident_severity = _clamp(raw_inputs["incident_severity"], 0.0, 1.0)
    accessibility_score = _clamp(raw_inputs["accessibility_score"], 0.0, 1.0)
    weather_severity = _clamp(raw_inputs["weather_severity"], 0.0, 1.0)
    road_condition_score = _clamp(raw_inputs["road_condition_score"], 0.0, 1.0)
    network_criticality = _clamp(raw_inputs["network_criticality"], 0.0, 1.0)
    current_delay_ratio = _clamp(raw_inputs["current_delay_ratio"], 0.0, 1.0)

    # 2. Invert accessibility and road condition (higher is safer -> convert to risk)
    accessibility_risk = 1.0 - accessibility_score
    road_condition_risk = 1.0 - road_condition_score

    # 3. Weighted risk formula
    weighted_sum = (
        WEIGHTS["incident_severity"] * incident_severity
        + WEIGHTS["weather_severity"] * weather_severity
        + WEIGHTS["accessibility_risk"] * accessibility_risk
        + WEIGHTS["road_condition_risk"] * road_condition_risk
        + WEIGHTS["network_criticality"] * network_criticality
        + WEIGHTS["current_delay_ratio"] * current_delay_ratio
    )

    raw_score = 100.0 * weighted_sum
    clamped_score = _clamp(raw_score, 0.0, 100.0)
    risk_score = round(clamped_score, 2)

    # 4. Risk band classification
    risk_level = _classify_risk_band(risk_score)

    # 5. Explainability factor risk evaluation
    factor_risks: List[Tuple[str, float]] = [
        ("incident_severity", incident_severity),
        ("weather_severity", weather_severity),
        ("accessibility_risk", accessibility_risk),
        ("road_condition_risk", road_condition_risk),
        ("network_criticality", network_criticality),
        ("current_delay_ratio", current_delay_ratio),
    ]

    reason_codes, reasons = _generate_reasons(factor_risks)

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "reason_codes": reason_codes,
        "reasons": reasons,
    }


# Alias for calculate_risk
assess_risk = calculate_risk
