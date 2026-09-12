"""SETU Route Explanation v0.1 (Checkpoint 15).

Translates deterministic Route Ranking outputs into structured, operator-readable
decision explanations without recalculating scores, modifying ranks, or fabricating
unobserved operational facts.

Separation of Concerns:
- Candidate Generation (Checkpoint 13): "What physically plausible routes exist?"
- Route Ranking (Checkpoint 14): "Which candidate is preferable?"
- Explanation (Checkpoint 15): "Why was this candidate ranked best?"
- Human Operator: Retains authority to review, approve, or reject reroute suggestions.

Strict Boundaries:
- Does NOT recalculate, modify, or re-weight route ranking scores.
- Does NOT introduce new ranking weights or alternative evaluation formulas.
- Does NOT generate routes, alter geometry, or invoke external routing/traffic APIs.
- Does NOT fabricate road closures, weather events, vehicle clearances, or traffic conditions.
- Does NOT fabricate availability (unsupported in Checkpoint 14/15).
- Does NOT present the vehicle profile compatibility proxy as guaranteed physical vehicle passability.
- Strictly pure Python standard library; no external services or ML/LLM dependencies.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


class RouteExplanationValidationError(ValueError):
    """Raised when ranked route records, decision metrics, or weights are invalid or missing."""
    pass


# Deterministic factor schema and ordering
FACTOR_DEFINITIONS: Tuple[Dict[str, str], ...] = (
    {
        "key": "eta",
        "metric_field": "eta_seconds",
        "score_field": "eta_score",
        "label": "ETA",
        "direction": "lower_is_better",
        "unit": "seconds",
    },
    {
        "key": "risk",
        "metric_field": "risk_score",
        "score_field": "risk_score",
        "label": "Risk",
        "direction": "lower_is_better",
        "unit": "score (0-100)",
    },
    {
        "key": "accessibility",
        "metric_field": "accessibility_score",
        "score_field": "accessibility_score",
        "label": "Accessibility",
        "direction": "higher_is_better",
        "unit": "score (0-1)",
    },
    {
        "key": "distance",
        "metric_field": "distance_km",
        "score_field": "distance_score",
        "label": "Distance",
        "direction": "lower_is_better",
        "unit": "km",
    },
    {
        "key": "vehicle_profile_compatibility",
        "metric_field": "vehicle_profile_compatibility",
        "score_field": "vehicle_profile_compatibility_score",
        "label": "Vehicle Profile Compatibility Proxy",
        "direction": "higher_is_better",
        "unit": "score (0-1)",
    },
)

HONESTY_DISCLOSURE: str = (
    "1. Vehicle Profile Compatibility Proxy: Evaluated from OSM road hierarchy and surface data recognized "
    "by SETU ETA Engine v0.1. This is a compatibility PROXY only, NOT a guarantee of physical vehicle clearance, "
    "axle load limits, or bridge capacity. "
    "2. Availability: Infrastructure availability is explicitly UNSUPPORTED in v0.1 and has not been evaluated. "
    "3. Operational Conditions: Real-world road closures, live weather severity, and traffic delays are not verified "
    "unless explicitly supplied by upstream operational data. "
    "4. Decision Support: Rankings and explanations are deterministic decision-support suggestions; "
    "the human operator retains final authority to review, approve, or reject route recommendations."
)


def _validate_numeric(field: str, val: Any, min_val: float | None = None, max_val: float | None = None) -> float:
    """Validate that a value is a finite number within optional bounds."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise RouteExplanationValidationError(
            f"Field '{field}' must be numeric, got {type(val).__name__} ({val!r})"
        )
    f_val = float(val)
    if not math.isfinite(f_val):
        raise RouteExplanationValidationError(f"Field '{field}' must be finite, got {f_val}")
    if min_val is not None and f_val < min_val:
        raise RouteExplanationValidationError(f"Field '{field}' must be >= {min_val}, got {f_val}")
    if max_val is not None and f_val > max_val:
        raise RouteExplanationValidationError(f"Field '{field}' must be <= {max_val}, got {f_val}")
    return f_val


def _validate_ranked_route_structure(route: Any, context_name: str = "ranked_route") -> Dict[str, Any]:
    """Strictly validate the required structure of a ranked route record without mutating it."""
    if route is None:
        raise RouteExplanationValidationError(f"Expected {context_name} to be a mapping, got None")
    if not isinstance(route, Mapping):
        raise RouteExplanationValidationError(f"Expected {context_name} to be a mapping, got {type(route).__name__}")

    route_id = route.get("route_id")
    if route_id is None or not str(route_id).strip():
        raise RouteExplanationValidationError(f"{context_name} must contain a non-empty 'route_id'")
    route_id_str = str(route_id).strip()

    # Validate rank
    if "rank" not in route or route["rank"] is None:
        raise RouteExplanationValidationError(f"{context_name} '{route_id_str}' missing 'rank'")
    rank_val = route["rank"]
    if isinstance(rank_val, bool) or not isinstance(rank_val, int):
        raise RouteExplanationValidationError(f"{context_name} '{route_id_str}' field 'rank' must be an integer >= 1")
    if rank_val < 1:
        raise RouteExplanationValidationError(f"{context_name} '{route_id_str}' field 'rank' must be >= 1, got {rank_val}")

    # Validate ranking_score
    if "ranking_score" not in route or route["ranking_score"] is None:
        raise RouteExplanationValidationError(f"{context_name} '{route_id_str}' missing 'ranking_score'")
    ranking_score = _validate_numeric(f"{route_id_str}.ranking_score", route["ranking_score"], 0.0, 1.0)

    # Validate metrics
    metrics = route.get("metrics")
    if metrics is None or not isinstance(metrics, Mapping):
        raise RouteExplanationValidationError(f"{context_name} '{route_id_str}' missing or invalid 'metrics' mapping")

    # Validate normalized_scores
    normalized_scores = route.get("normalized_scores")
    if normalized_scores is None or not isinstance(normalized_scores, Mapping):
        raise RouteExplanationValidationError(
            f"{context_name} '{route_id_str}' missing or invalid 'normalized_scores' mapping"
        )

    # Validate weights_applied
    weights_applied = route.get("weights_applied")
    if weights_applied is None or not isinstance(weights_applied, Mapping):
        raise RouteExplanationValidationError(
            f"{context_name} '{route_id_str}' missing or invalid 'weights_applied' mapping"
        )

    # Check all 5 factors exist across metrics, normalized_scores, and weights_applied
    for factor_def in FACTOR_DEFINITIONS:
        key = factor_def["key"]
        m_field = factor_def["metric_field"]
        s_field = factor_def["score_field"]

        if m_field not in metrics or metrics[m_field] is None:
            raise RouteExplanationValidationError(
                f"{context_name} '{route_id_str}' metrics missing required field '{m_field}'"
            )
        _validate_numeric(f"{route_id_str}.metrics.{m_field}", metrics[m_field], min_val=0.0)

        if s_field not in normalized_scores or normalized_scores[s_field] is None:
            raise RouteExplanationValidationError(
                f"{context_name} '{route_id_str}' normalized_scores missing required field '{s_field}'"
            )
        _validate_numeric(f"{route_id_str}.normalized_scores.{s_field}", normalized_scores[s_field], 0.0, 1.0)

        if key not in weights_applied or weights_applied[key] is None:
            raise RouteExplanationValidationError(
                f"{context_name} '{route_id_str}' weights_applied missing required weight '{key}'"
            )
        _validate_numeric(f"{route_id_str}.weights_applied.{key}", weights_applied[key], min_val=0.0)

    # Return clean shallow copy of validated reference
    clean_copy = dict(route)
    clean_copy["route_id"] = route_id_str
    clean_copy["rank"] = rank_val
    clean_copy["ranking_score"] = ranking_score
    clean_copy["metrics"] = dict(metrics)
    clean_copy["normalized_scores"] = dict(normalized_scores)
    clean_copy["weights_applied"] = dict(weights_applied)
    return clean_copy


def _format_factor_narrative(
    factor_def: Dict[str, str],
    raw_val: float,
    norm_val: float,
    weight_val: float,
) -> str:
    """Deterministic, factual description of a decision factor."""
    label = factor_def["label"]
    direction = "lower is better" if factor_def["direction"] == "lower_is_better" else "higher is better"
    unit = factor_def["unit"]

    if factor_def["key"] == "eta":
        val_str = f"{raw_val:.1f} s"
    elif factor_def["key"] == "risk":
        val_str = f"{raw_val:.2f}/100"
    elif factor_def["key"] == "distance":
        val_str = f"{raw_val:.3f} km"
    else:
        val_str = f"{raw_val:.4f}"

    return (
        f"{label}: {val_str} ({direction}; normalized utility: {norm_val:.4f}, weight: {weight_val:.4f})"
    )


def _build_tradeoffs(
    target: Dict[str, Any],
    alternatives: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Construct deterministic comparative trade-offs without fabricating facts."""
    route_id = target["route_id"]
    rank = target["rank"]
    target_norm = target["normalized_scores"]
    flags = dict(target.get("tradeoff_summary", {}))

    if not alternatives:
        # Single-route behavior: Explain inherent performance without comparing against nonexistent alternatives
        strengths: List[str] = []
        limitations: List[str] = []

        for fdef in FACTOR_DEFINITIONS:
            score = float(target_norm[fdef["score_field"]])
            label = fdef["label"]
            if score >= 0.75:
                strengths.append(f"{label} ({score:.4f})")
            elif score <= 0.25:
                limitations.append(f"{label} ({score:.4f})")

        narrative = "Single candidate route evaluated; no alternative routes available for comparative trade-off analysis."
        return {
            "narrative": narrative,
            "compared_to_route_id": None,
            "advantages": strengths,
            "disadvantages": limitations,
            "tradeoff_flags": flags,
        }

    # Find the primary competitor route for comparative trade-off analysis:
    # - If target is rank 1, compare against rank 2 (the runner-up).
    # - If target is rank > 1, compare against rank 1 (the top-ranked candidate).
    competitor: Optional[Dict[str, Any]] = None
    if rank == 1:
        # Closest runner-up (lowest rank > 1)
        sorted_alts = sorted(alternatives, key=lambda a: a["rank"])
        competitor = sorted_alts[0] if sorted_alts else None
    else:
        # Top-ranked route
        rank1_candidates = [a for a in alternatives if a["rank"] == 1]
        competitor = rank1_candidates[0] if rank1_candidates else alternatives[0]

    if competitor is None:
        return {
            "narrative": "Single candidate route evaluated; no alternative routes available for comparative trade-off analysis.",
            "compared_to_route_id": None,
            "advantages": [],
            "disadvantages": [],
            "tradeoff_flags": flags,
        }

    competitor_id = competitor["route_id"]
    competitor_norm = competitor["normalized_scores"]

    advantages: List[str] = []
    disadvantages: List[str] = []
    neutral: List[str] = []

    for fdef in FACTOR_DEFINITIONS:
        s_field = fdef["score_field"]
        label = fdef["label"]
        t_val = float(target_norm[s_field])
        c_val = float(competitor_norm[s_field])
        diff = t_val - c_val

        if diff > 1e-4:
            advantages.append(label)
        elif diff < -1e-4:
            disadvantages.append(label)
        else:
            neutral.append(label)

    # Deterministic narrative construction
    if rank == 1:
        if advantages and disadvantages:
            adv_str = ", ".join(advantages)
            disadv_str = ", ".join(disadvantages)
            narrative = (
                f"Route '{route_id}' ranks #1 ahead of alternative '{competitor_id}' because its advantages in "
                f"{adv_str} outweigh its compromises in {disadv_str}."
            )
        elif advantages and not disadvantages:
            adv_str = ", ".join(advantages)
            narrative = (
                f"Route '{route_id}' ranks #1 ahead of alternative '{competitor_id}' by dominating across all "
                f"differing decision factors: {adv_str}."
            )
        elif not advantages and not disadvantages:
            narrative = (
                f"Route '{route_id}' ranks #1 ahead of alternative '{competitor_id}' via deterministic tie-breaking "
                "with equivalent utility scores across all factors."
            )
        else:
            # Fallback if tied on normalized utility but differing slightly in rounding
            disadv_str = ", ".join(disadvantages)
            narrative = (
                f"Route '{route_id}' ranks #1 ahead of alternative '{competitor_id}' via composite ranking score."
            )
    else:
        if advantages and disadvantages:
            adv_str = ", ".join(advantages)
            disadv_str = ", ".join(disadvantages)
            narrative = (
                f"Route '{route_id}' ranks #{rank} behind top route '{competitor_id}' because compromises in "
                f"{disadv_str} outweigh its advantages in {adv_str}."
            )
        elif disadvantages and not advantages:
            disadv_str = ", ".join(disadvantages)
            narrative = (
                f"Route '{route_id}' ranks #{rank} behind top route '{competitor_id}' due to lower utility across "
                f"{disadv_str}."
            )
        elif not advantages and not disadvantages:
            narrative = (
                f"Route '{route_id}' ranks #{rank} behind top route '{competitor_id}' via deterministic tie-breaking "
                "despite equivalent utility scores."
            )
        else:
            adv_str = ", ".join(advantages)
            narrative = (
                f"Route '{route_id}' ranks #{rank} behind top route '{competitor_id}'."
            )

    return {
        "narrative": narrative,
        "compared_to_route_id": competitor_id,
        "advantages": advantages,
        "disadvantages": disadvantages,
        "tradeoff_flags": flags,
    }


def explain_ranked_route(
    ranked_route: Mapping[str, Any],
    all_ranked_routes: Optional[Iterable[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Translate an existing Route Ranking result into an operator-readable structured explanation.

    This function is strictly explanatory:
    - It does NOT recalculate or re-order rankings.
    - It does NOT introduce new weights.
    - It preserves existing Risk Engine reason codes when present.
    - It does NOT fabricate weather, closures, physical vehicle clearance, or availability.

    Args:
        ranked_route: A single ranked candidate route dictionary from Checkpoint 14.
        all_ranked_routes: Optional collection of all ranked routes from the same ranking pass,
            used to provide comparative trade-off context against alternative candidates.

    Returns:
        Deterministic dictionary containing:
        - route_id: Identifier string
        - rank: Integer rank (1-based)
        - ranking_score: Composite score from ranking [0.0, 1.0]
        - summary: Human-readable executive summary
        - decision_factors: Ordered list of all 5 evaluated decision factors with weights and utilities
        - tradeoffs: Comparative trade-off analysis vs alternatives (or single-route breakdown)
        - risk_reasons: Extracted Risk Engine reasons (or empty list if absent)
        - risk_reason_codes: Extracted Risk Engine reason codes (or empty list if absent)
        - honesty_disclosure: Required transparency disclosure
    """
    validated_target = _validate_ranked_route_structure(ranked_route, context_name="ranked_route")

    # Validate alternatives if provided
    validated_alts: List[Dict[str, Any]] = []
    if all_ranked_routes is not None:
        if isinstance(all_ranked_routes, (str, bytes, Mapping)):
            raise RouteExplanationValidationError(
                f"Expected all_ranked_routes to be an iterable of mappings, got {type(all_ranked_routes).__name__}"
            )
        try:
            raw_alts = list(all_ranked_routes)
        except TypeError as exc:
            raise RouteExplanationValidationError(
                f"Expected all_ranked_routes to be iterable, got {type(all_ranked_routes).__name__}"
            ) from exc

        for idx, alt in enumerate(raw_alts):
            val_alt = _validate_ranked_route_structure(alt, context_name=f"all_ranked_routes[{idx}]")
            if val_alt["route_id"] != validated_target["route_id"]:
                validated_alts.append(val_alt)

    route_id = validated_target["route_id"]
    rank = validated_target["rank"]
    ranking_score = validated_target["ranking_score"]
    metrics = validated_target["metrics"]
    normalized_scores = validated_target["normalized_scores"]
    weights_applied = validated_target["weights_applied"]

    # 1. Decision Factors (deterministic order across all 5 supported signals)
    decision_factors: List[Dict[str, Any]] = []
    for fdef in FACTOR_DEFINITIONS:
        key = fdef["key"]
        m_field = fdef["metric_field"]
        s_field = fdef["score_field"]

        raw_val = float(metrics[m_field])
        norm_val = float(normalized_scores[s_field])
        weight_val = float(weights_applied[key])
        contribution = round(norm_val * weight_val, 4)

        description = _format_factor_narrative(fdef, raw_val, norm_val, weight_val)

        decision_factors.append({
            "factor": key,
            "label": fdef["label"],
            "direction": fdef["direction"],
            "raw_value": raw_val,
            "normalized_score": norm_val,
            "weight": weight_val,
            "weighted_contribution": contribution,
            "description": description,
        })

    # 2. Risk Reasons (preserve existing without inventing facts)
    risk_reasons: List[str] = []
    risk_reason_codes: List[str] = []

    # Check candidate and metrics for risk reasons/codes
    source_records = [validated_target, metrics]
    for src in source_records:
        if not risk_reasons:
            if "risk_reasons" in src and isinstance(src["risk_reasons"], list):
                risk_reasons = [str(r) for r in src["risk_reasons"]]
            elif "reasons" in src and isinstance(src["reasons"], list):
                risk_reasons = [str(r) for r in src["reasons"]]

        if not risk_reason_codes:
            if "risk_reason_codes" in src and isinstance(src["risk_reason_codes"], list):
                risk_reason_codes = [str(rc) for rc in src["risk_reason_codes"]]
            elif "reason_codes" in src and isinstance(src["reason_codes"], list):
                risk_reason_codes = [str(rc) for rc in src["reason_codes"]]

    # 3. Tradeoffs
    tradeoffs = _build_tradeoffs(validated_target, validated_alts)

    # 4. Summary
    if rank == 1:
        summary = (
            f"Route '{route_id}' is ranked #1 (highest overall utility) with a composite score of {ranking_score:.4f}. "
            f"{tradeoffs['narrative']}"
        )
    else:
        summary = (
            f"Route '{route_id}' is ranked #{rank} with a composite score of {ranking_score:.4f}. "
            f"{tradeoffs['narrative']}"
        )

    return {
        "route_id": route_id,
        "rank": rank,
        "ranking_score": ranking_score,
        "summary": summary,
        "decision_factors": decision_factors,
        "tradeoffs": tradeoffs,
        "risk_reasons": risk_reasons,
        "risk_reason_codes": risk_reason_codes,
        "honesty_disclosure": HONESTY_DISCLOSURE,
    }


def explain_ranked_routes(
    ranked_routes: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate structured explanations for all routes in a ranked candidate collection.

    Every route is explained with full comparative trade-off context relative to the set.

    Args:
        ranked_routes: Iterable of ranked candidate route dictionaries from Checkpoint 14.

    Returns:
        List of structured explanation dictionaries, one per ranked candidate, in the original order.
    """
    if ranked_routes is None:
        raise RouteExplanationValidationError("Expected ranked_routes to be an iterable collection, got None")
    if isinstance(ranked_routes, (str, bytes, Mapping)):
        raise RouteExplanationValidationError(
            f"Expected ranked_routes to be an iterable collection of mappings, got {type(ranked_routes).__name__}"
        )
    try:
        routes_list = list(ranked_routes)
    except TypeError as exc:
        raise RouteExplanationValidationError(
            f"Expected ranked_routes to be iterable, got {type(ranked_routes).__name__}"
        ) from exc

    if not routes_list:
        raise RouteExplanationValidationError("Cannot explain an empty collection of ranked routes")

    # Validate and copy all routes first
    validated_list = [
        _validate_ranked_route_structure(r, context_name=f"ranked_routes[{idx}]")
        for idx, r in enumerate(routes_list)
    ]

    return [
        explain_ranked_route(r, all_ranked_routes=validated_list)
        for r in validated_list
    ]
