"""SETU_AI — Checkpoint 20: ML Inference Component & Local Service Boundary.

Provides frozen Random Forest champion inference for disruption probability estimation
across road network segments and routes.

Core Invariants:
1. Random Forest predict_proba outputs are auxiliary decision signals, NOT proven
   real-world road closure forecasting.
2. AI recommends -> Backend orchestrates -> Operator approves.
3. Deterministic Risk, Network Impact, Accessibility, ETA, Route Candidates, Route Ranking,
   and Human Approval remain authoritative.
4. Potentially affected segments within an incident radius never automatically become
   confirmed blocked.
5. Tree models consume raw unscaled features (StandardScaler is bypassed).
6. Exact 24 CP19 canonical features are constructed in strict deterministic order without
   fabrication, heuristic defaulting, or silent substitution.
"""

from __future__ import annotations

import copy
import datetime
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import joblib
import numpy as np

from src.accessibility.accessibility_scorer import calculate_accessibility
from src.data.weather.weather_severity import (
    InvalidWeatherInputError,
    WMO_CODE_SEVERITY,
    calculate_weather_severity,
)
from src.ml.train_models import (
    CANONICAL_FEATURES,
    RANDOM_FOREST_ARTIFACT_PATH,
    derive_cyclical_temporal_features,
)


# ------------------------------------------------------------------------------
# 1. Error Hierarchy
# ------------------------------------------------------------------------------

class ModelArtifactNotFoundError(FileNotFoundError):
    """Raised when the requested trained model artifact cannot be found on disk."""
    pass


class MLInferenceValidationError(ValueError):
    """Raised when operational segment, weather, date, or feature inputs are invalid or missing."""
    pass


class MLInferenceRuntimeError(RuntimeError):
    """Raised when underlying model inference encounters an unrecoverable runtime failure."""
    pass


# ------------------------------------------------------------------------------
# 2. Canonical Constants & Disclosures
# ------------------------------------------------------------------------------

FROZEN_DECISION_THRESHOLD: float = 0.30

ROAD_TYPE_RANKS: Dict[str, int] = {
    "motorway": 4,
    "trunk": 3,
    "primary": 2,
    "secondary": 1,
}

PAVED_SURFACES: set[str] = {
    "asphalt",
    "paved",
    "concrete",
    "bitumen",
    "chipseal",
    "tar",
    "concrete:lanes",
    "concrete:plates",
}

DISCLOSURE_TEXT: str = (
    "These probabilities are model outputs for the engineered-label classification "
    "task and are not calibrated or validated probabilities of real-world road closure."
)

METHODOLOGY_TEXT: str = "SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION"


def get_default_provenance(model_name: str = "random_forest", threshold: float = FROZEN_DECISION_THRESHOLD) -> Dict[str, Any]:
    """Return immutable provenance metadata dictionary for ML inference outputs."""
    return {
        "model_champion": model_name,
        "frozen_threshold": float(threshold),
        "methodology": METHODOLOGY_TEXT,
        "probability_type": "Random Forest predict_proba disruption probabilities",
        "disclosure": DISCLOSURE_TEXT,
        "is_unseen_road_tested": False,
    }


# ------------------------------------------------------------------------------
# 3. Input Validation & Strict Feature Construction
# ------------------------------------------------------------------------------

def _validate_numeric_scalar(field_name: str, val: Any) -> float:
    """Validate that val is a finite numeric scalar (not bool)."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise MLInferenceValidationError(
            f"Field '{field_name}' must be a numeric value, got {type(val).__name__} ({val!r})"
        )
    f_val = float(val)
    if not math.isfinite(f_val):
        raise MLInferenceValidationError(
            f"Field '{field_name}' must be a finite number, got {f_val}"
        )
    return f_val


def _validate_weather_code_strict(code_val: Any) -> float:
    """Strictly validate WMO weather code and return its canonical severity score.

    Unlike CP19 training fallback, the operational inference boundary MUST NOT
    silently convert invalid or missing weather codes to 0.0.
    """
    if code_val is None:
        raise InvalidWeatherInputError("weather_code is required and cannot be None")
    if isinstance(code_val, bool):
        raise InvalidWeatherInputError(f"weather_code cannot be a boolean: {code_val!r}")

    if isinstance(code_val, float):
        if not math.isfinite(code_val):
            raise InvalidWeatherInputError(f"weather_code must be finite, got: {code_val!r}")
        if not code_val.is_integer():
            raise InvalidWeatherInputError(f"weather_code must be an integer, got non-integer float: {code_val!r}")
        c = int(code_val)
    elif isinstance(code_val, int):
        c = code_val
    elif isinstance(code_val, str):
        try:
            c = int(code_val)
        except ValueError:
            raise InvalidWeatherInputError(f"weather_code must be an integer, got: {code_val!r}")
    else:
        raise InvalidWeatherInputError(
            f"weather_code must be an integer, got type {type(code_val).__name__}: {code_val!r}"
        )

    if c not in WMO_CODE_SEVERITY:
        raise InvalidWeatherInputError(
            f"Unsupported or unknown WMO weather_code: {c}. "
            f"Supported codes: {sorted(WMO_CODE_SEVERITY.keys())}"
        )

    return float(WMO_CODE_SEVERITY[c])


def _resolve_date_components(date_val: Any) -> Tuple[int, int]:
    """Resolve (month, day_of_week) from an ISO date string or datetime.date object.

    day_of_week: 0=Monday, 6=Sunday.
    """
    if date_val is None:
        raise MLInferenceValidationError("Missing observation date for temporal feature construction")

    if isinstance(date_val, datetime.date):
        return date_val.month, date_val.weekday()
    elif isinstance(date_val, str):
        clean_date = date_val.strip()
        if not clean_date:
            raise MLInferenceValidationError("Date string cannot be empty")
        try:
            # Supports 'YYYY-MM-DD' or full ISO timestamps
            dt = datetime.datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
            return dt.month, dt.weekday()
        except ValueError as err:
            raise MLInferenceValidationError(f"Invalid ISO date string {date_val!r}: {err}") from err
    else:
        raise MLInferenceValidationError(
            f"Date must be a datetime.date or ISO date string, got {type(date_val).__name__}"
        )


def construct_feature_vector_from_context(
    segment_context: Mapping[str, Any],
    date: Optional[Any] = None,
) -> List[float]:
    """Construct the exact 24 CP19 canonical features in deterministic order.

    Supports two strict contracts:
    - Contract A: Pre-formed feature mapping containing the 24 canonical feature keys
      (or 'month' and 'day_of_week' plus the other 20 features).
    - Contract B: Structured operational context combining segment attributes, weather observations,
      and observation date from which all 24 features can be deterministically resolved.

    Zero fabrication, heuristic guessing, or silent substitution allowed.
    """
    if not isinstance(segment_context, Mapping):
        raise MLInferenceValidationError(
            f"Expected segment_context to be a mapping, got {type(segment_context).__name__}"
        )

    # 1. Resolve Cyclical Temporal Features
    temporal_vals: Dict[str, float] = {}
    precomputed_temporal_keys = ("month_sin", "month_cos", "dow_sin", "dow_cos")
    if all(k in segment_context for k in precomputed_temporal_keys):
        for k in precomputed_temporal_keys:
            temporal_vals[k] = _validate_numeric_scalar(k, segment_context[k])
    elif "month" in segment_context and "day_of_week" in segment_context:
        m_sin, m_cos, d_sin, d_cos = derive_cyclical_temporal_features(
            segment_context["month"], segment_context["day_of_week"]
        )
        temporal_vals["month_sin"] = m_sin
        temporal_vals["month_cos"] = m_cos
        temporal_vals["dow_sin"] = d_sin
        temporal_vals["dow_cos"] = d_cos
    elif date is not None:
        month_int, dow_int = _resolve_date_components(date)
        m_sin, m_cos, d_sin, d_cos = derive_cyclical_temporal_features(month_int, dow_int)
        temporal_vals["month_sin"] = m_sin
        temporal_vals["month_cos"] = m_cos
        temporal_vals["dow_sin"] = d_sin
        temporal_vals["dow_cos"] = d_cos
    elif "date" in segment_context:
        month_int, dow_int = _resolve_date_components(segment_context["date"])
        m_sin, m_cos, d_sin, d_cos = derive_cyclical_temporal_features(month_int, dow_int)
        temporal_vals["month_sin"] = m_sin
        temporal_vals["month_cos"] = m_cos
        temporal_vals["dow_sin"] = d_sin
        temporal_vals["dow_cos"] = d_cos
    else:
        raise MLInferenceValidationError(
            "Missing temporal inputs for feature construction. Expected either precomputed cyclical keys "
            "('month_sin', 'month_cos', 'dow_sin', 'dow_cos'), raw calendar keys ('month', 'day_of_week'), "
            "or an explicit 'date' input."
        )

    # 2. Extract Weather Sub-Mapping or Flattened Weather Keys
    weather_data: Mapping[str, Any]
    if "weather" in segment_context and isinstance(segment_context["weather"], Mapping):
        weather_data = segment_context["weather"]
    else:
        weather_data = segment_context

    # 3. Construct 24 Features in Exact Canonical Order
    vec: List[float] = []

    # 3.1 month_sin, month_cos, dow_sin, dow_cos
    vec.append(temporal_vals["month_sin"])
    vec.append(temporal_vals["month_cos"])
    vec.append(temporal_vals["dow_sin"])
    vec.append(temporal_vals["dow_cos"])

    # 3.2 Spatial coordinates (latitude, longitude)
    lat_val: Optional[float] = None
    lon_val: Optional[float] = None
    if "latitude" in segment_context and "longitude" in segment_context:
        lat_val = _validate_numeric_scalar("latitude", segment_context["latitude"])
        lon_val = _validate_numeric_scalar("longitude", segment_context["longitude"])
    elif (
        "start_latitude" in segment_context
        and "start_longitude" in segment_context
        and "end_latitude" in segment_context
        and "end_longitude" in segment_context
    ):
        s_lat = _validate_numeric_scalar("start_latitude", segment_context["start_latitude"])
        s_lon = _validate_numeric_scalar("start_longitude", segment_context["start_longitude"])
        e_lat = _validate_numeric_scalar("end_latitude", segment_context["end_latitude"])
        e_lon = _validate_numeric_scalar("end_longitude", segment_context["end_longitude"])
        lat_val = (s_lat + e_lat) / 2.0
        lon_val = (s_lon + e_lon) / 2.0
    else:
        raise MLInferenceValidationError(
            "Missing required spatial coordinate fields: expected 'latitude' and 'longitude', "
            "or start/end endpoints."
        )

    if not (-90.0 <= lat_val <= 90.0):
        raise MLInferenceValidationError(f"Invalid latitude {lat_val}: must be between -90 and 90")
    if not (-180.0 <= lon_val <= 180.0):
        raise MLInferenceValidationError(f"Invalid longitude {lon_val}: must be between -180 and 180")

    vec.append(lat_val)
    vec.append(lon_val)

    # 3.3 elevation_m
    if "elevation_m" not in segment_context:
        raise MLInferenceValidationError("Missing required segment attribute: 'elevation_m'")
    vec.append(_validate_numeric_scalar("elevation_m", segment_context["elevation_m"]))

    # 3.4 road_type_rank
    if "road_type_rank" in segment_context:
        vec.append(_validate_numeric_scalar("road_type_rank", segment_context["road_type_rank"]))
    elif "road_type" in segment_context:
        rt_str = str(segment_context["road_type"]).strip().lower()
        if rt_str not in ROAD_TYPE_RANKS:
            raise MLInferenceValidationError(
                f"Unsupported or unknown road_type '{rt_str}'. Expected one of {sorted(ROAD_TYPE_RANKS.keys())}"
            )
        vec.append(float(ROAD_TYPE_RANKS[rt_str]))
    else:
        raise MLInferenceValidationError("Missing required road hierarchy attribute: 'road_type_rank' or 'road_type'")

    # 3.5 surface_paved
    if "surface_paved" in segment_context:
        sp_val = _validate_numeric_scalar("surface_paved", segment_context["surface_paved"])
        if sp_val not in (0.0, 1.0):
            raise MLInferenceValidationError(f"surface_paved must be 0 or 1, got {sp_val}")
        vec.append(sp_val)
    elif "surface" in segment_context:
        s_str = str(segment_context["surface"]).strip().lower()
        vec.append(1.0 if s_str in PAVED_SURFACES else 0.0)
    else:
        raise MLInferenceValidationError("Missing required surface attribute: 'surface_paved' or 'surface'")

    # 3.6 lanes
    if "lanes" not in segment_context:
        raise MLInferenceValidationError("Missing required attribute: 'lanes'")
    lanes_val = _validate_numeric_scalar("lanes", segment_context["lanes"])
    if lanes_val < 1.0:
        raise MLInferenceValidationError(f"lanes must be >= 1, got {lanes_val}")
    vec.append(lanes_val)

    # 3.7 connectivity_degree (spatial midpoint density proxy)
    if "connectivity_degree" not in segment_context:
        raise MLInferenceValidationError(
            "Missing required attribute: 'connectivity_degree' (spatial midpoint density proxy)"
        )
    vec.append(_validate_numeric_scalar("connectivity_degree", segment_context["connectivity_degree"]))

    # 3.8 accessibility_score
    if "accessibility_score" in segment_context:
        acc_val = _validate_numeric_scalar("accessibility_score", segment_context["accessibility_score"])
        if not (0.0 <= acc_val <= 1.0):
            raise MLInferenceValidationError(f"accessibility_score must be between 0.0 and 1.0, got {acc_val}")
        vec.append(acc_val)
    else:
        # Resolve deterministically using existing accessibility engine
        acc_res = calculate_accessibility(segment_context)
        vec.append(float(acc_res["accessibility_score"]))

    # 3.9 weather_point_dist_km
    if "weather_point_dist_km" not in segment_context:
        raise MLInferenceValidationError("Missing required attribute: 'weather_point_dist_km'")
    dist_val = _validate_numeric_scalar("weather_point_dist_km", segment_context["weather_point_dist_km"])
    if dist_val < 0.0:
        raise MLInferenceValidationError(f"weather_point_dist_km cannot be negative, got {dist_val}")
    vec.append(dist_val)

    # 3.10 precipitation_mm
    if "precipitation_mm" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'precipitation_mm'")
    p_mm = _validate_numeric_scalar("precipitation_mm", weather_data["precipitation_mm"])
    if p_mm < 0.0:
        raise MLInferenceValidationError(f"precipitation_mm cannot be negative, got {p_mm}")
    vec.append(p_mm)

    # 3.11 rain_mm
    if "rain_mm" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'rain_mm'")
    r_mm = _validate_numeric_scalar("rain_mm", weather_data["rain_mm"])
    if r_mm < 0.0:
        raise MLInferenceValidationError(f"rain_mm cannot be negative, got {r_mm}")
    vec.append(r_mm)

    # 3.12 precipitation_hours
    if "precipitation_hours" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'precipitation_hours'")
    p_hrs = _validate_numeric_scalar("precipitation_hours", weather_data["precipitation_hours"])
    if p_hrs < 0.0:
        raise MLInferenceValidationError(f"precipitation_hours cannot be negative, got {p_hrs}")
    vec.append(p_hrs)

    # 3.13 temperature_c
    if "temperature_c" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'temperature_c'")
    vec.append(_validate_numeric_scalar("temperature_c", weather_data["temperature_c"]))

    # 3.14 temperature_max_c
    if "temperature_max_c" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'temperature_max_c'")
    t_max = _validate_numeric_scalar("temperature_max_c", weather_data["temperature_max_c"])
    vec.append(t_max)

    # 3.15 temperature_min_c
    if "temperature_min_c" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'temperature_min_c'")
    t_min = _validate_numeric_scalar("temperature_min_c", weather_data["temperature_min_c"])
    vec.append(t_min)

    # 3.16 temp_range_c
    if "temp_range_c" in weather_data:
        vec.append(_validate_numeric_scalar("temp_range_c", weather_data["temp_range_c"]))
    else:
        vec.append(round(t_max - t_min, 4))

    # 3.17 wind_speed_kmh
    if "wind_speed_kmh" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'wind_speed_kmh'")
    ws_val = _validate_numeric_scalar("wind_speed_kmh", weather_data["wind_speed_kmh"])
    if ws_val < 0.0:
        raise MLInferenceValidationError(f"wind_speed_kmh cannot be negative, got {ws_val}")
    vec.append(ws_val)

    # 3.18 wind_gust_kmh
    if "wind_gust_kmh" not in weather_data:
        raise MLInferenceValidationError("Missing required weather observation: 'wind_gust_kmh'")
    wg_val = _validate_numeric_scalar("wind_gust_kmh", weather_data["wind_gust_kmh"])
    if wg_val < 0.0:
        raise MLInferenceValidationError(f"wind_gust_kmh cannot be negative, got {wg_val}")
    vec.append(wg_val)

    # 3.19 weather_code (canonical mapping from WMO_CODE_SEVERITY)
    if "weather_code" not in weather_data:
        raise InvalidWeatherInputError("Missing required weather observation: 'weather_code'")
    w_code_severity = _validate_weather_code_strict(weather_data["weather_code"])
    vec.append(w_code_severity)

    # 3.20 weather_severity_daily
    if "weather_severity_daily" in weather_data:
        ws_daily = _validate_numeric_scalar("weather_severity_daily", weather_data["weather_severity_daily"])
        if not (0.0 <= ws_daily <= 1.0):
            raise MLInferenceValidationError(f"weather_severity_daily must be in [0.0, 1.0], got {ws_daily}")
        vec.append(ws_daily)
    else:
        sev = calculate_weather_severity({
            "weather_code": weather_data["weather_code"],
            "precipitation": p_mm,
            "wind_speed_10m": ws_val,
            "wind_gusts_10m": wg_val,
        })
        vec.append(float(sev))

    if len(vec) != len(CANONICAL_FEATURES):
        raise MLInferenceRuntimeError(
            f"Feature extraction failed: expected {len(CANONICAL_FEATURES)} features, produced {len(vec)}"
        )

    return vec


# ------------------------------------------------------------------------------
# 4. DisruptionInferenceEngine Component
# ------------------------------------------------------------------------------

class DisruptionInferenceEngine:
    """Encapsulated local Python service boundary for Random Forest disruption inference.

    Caches the loaded champion model artifact in memory. Never reloads the artifact
    on individual inference calls. Operates directly on unscaled features (scaler bypassed).
    """

    def __init__(
        self,
        model_path: Union[str, Path] = RANDOM_FOREST_ARTIFACT_PATH,
        threshold: float = FROZEN_DECISION_THRESHOLD,
        model_instance: Optional[Any] = None,
    ) -> None:
        """Initialize the inference engine with a model artifact path or pre-instantiated model.

        Args:
            model_path: Filesystem path to the serialized scikit-learn model artifact.
            threshold: Frozen decision threshold for binary disruption classification.
            model_instance: Optional pre-loaded or dummy model instance (useful for unit tests).
        """
        self._model_path = Path(model_path)
        self._threshold = float(threshold)
        self._model = model_instance

    def _ensure_model_loaded(self) -> Any:
        """Load and cache the model artifact in memory once. Thread-safe read reuse."""
        if self._model is not None:
            return self._model

        if not self._model_path.exists():
            raise ModelArtifactNotFoundError(
                f"Trained model artifact not found at: {self._model_path.resolve()}"
            )

        try:
            loaded_obj = joblib.load(self._model_path)
            self._model = loaded_obj
            return self._model
        except Exception as err:
            raise MLInferenceRuntimeError(
                f"Failed to load model artifact from {self._model_path}: {err}"
            ) from err

    @property
    def threshold(self) -> float:
        """Return the frozen decision threshold."""
        return self._threshold

    def predict_segment_disruption(
        self,
        segment_context: Mapping[str, Any],
        date: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Perform disruption inference for a single road segment.

        Enforces thresholding on raw probability and rounding only on output:
            raw_probability = model.predict_proba(...)
            disruption_predicted = raw_probability >= 0.30
            returned_probability = round(raw_probability, 4)
        """
        model = self._ensure_model_loaded()
        vec = construct_feature_vector_from_context(segment_context, date=date)

        X = np.array([vec], dtype=np.float32)

        try:
            if hasattr(model, "predict_proba"):
                proba = np.asarray(model.predict_proba(X))
                if hasattr(proba, "ndim") and proba.ndim == 2 and proba.shape[1] >= 2:
                    raw_prob = float(proba[0, 1])
                elif hasattr(proba, "ndim") and proba.ndim == 1:
                    raw_prob = float(proba[0])
                else:
                    raw_prob = float(proba[0, 0])
            elif hasattr(model, "decision_function"):
                scores = float(model.decision_function(X)[0])
                raw_prob = float(1.0 / (1.0 + math.exp(-scores)))
            else:
                raise MLInferenceRuntimeError(f"Model {type(model).__name__} lacks predict_proba/decision_function")
        except Exception as err:
            if isinstance(err, MLInferenceRuntimeError):
                raise
            raise MLInferenceRuntimeError(f"Runtime error during model inference: {err}") from err

        raw_prob_clamped = max(0.0, min(1.0, raw_prob))
        disruption_predicted = bool(raw_prob_clamped >= self._threshold)
        returned_prob = round(raw_prob_clamped, 4)

        segment_id = str(segment_context.get("segment_id", "unknown_segment"))

        return {
            "segment_id": segment_id,
            "disruption_probability": returned_prob,
            "disruption_predicted": disruption_predicted,
            "threshold": self._threshold,
            "model_name": "random_forest",
            "provenance": get_default_provenance("random_forest", self._threshold),
        }

    def predict_segments_disruption(
        self,
        segment_contexts: Iterable[Mapping[str, Any]],
        date: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Perform batch disruption inference across an iterable of segment contexts.

        Guarantees equivalence with individual single-segment inferences.
        """
        model = self._ensure_model_loaded()
        contexts_list = list(segment_contexts)
        if not contexts_list:
            return []

        vectors: List[List[float]] = []
        seg_ids: List[str] = []
        for s in contexts_list:
            v = construct_feature_vector_from_context(s, date=date)
            vectors.append(v)
            seg_ids.append(str(s.get("segment_id", "unknown_segment")))

        X = np.array(vectors, dtype=np.float32)

        try:
            if hasattr(model, "predict_proba"):
                proba = np.asarray(model.predict_proba(X))
                if hasattr(proba, "ndim") and proba.ndim == 2 and proba.shape[1] >= 2:
                    raw_probs = np.asarray(proba[:, 1], dtype=np.float64)
                elif hasattr(proba, "ndim") and proba.ndim == 1:
                    raw_probs = np.asarray(proba, dtype=np.float64)
                else:
                    raw_probs = np.asarray(proba[:, 0], dtype=np.float64)

            elif hasattr(model, "decision_function"):
                scores = np.asarray(model.decision_function(X), dtype=np.float64)
                raw_probs = 1.0 / (1.0 + np.exp(-scores))
            else:
                raise MLInferenceRuntimeError(f"Model {type(model).__name__} lacks predict_proba/decision_function")
        except Exception as err:
            if isinstance(err, MLInferenceRuntimeError):
                raise
            raise MLInferenceRuntimeError(f"Runtime error during batch model inference: {err}") from err

        results: List[Dict[str, Any]] = []
        for sid, p in zip(seg_ids, raw_probs):
            p_clamped = max(0.0, min(1.0, float(p)))
            predicted = bool(p_clamped >= self._threshold)
            ret_p = round(p_clamped, 4)
            results.append({
                "segment_id": sid,
                "disruption_probability": ret_p,
                "disruption_predicted": predicted,
                "threshold": self._threshold,
                "model_name": "random_forest",
                "provenance": get_default_provenance("random_forest", self._threshold),
            })

        return results

    def predict_route_disruption(
        self,
        route: Mapping[str, Any],
        segment_contexts: Mapping[str, Mapping[str, Any]],
        date: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Perform route-level disruption inference using physical length-weighted aggregation.

        Formula:
            length_weighted_mean = SUM(probability_i * segment_length_km_i) / SUM(segment_length_km_i)

        Strict Requirements:
        - Evaluated strictly using actual physical segment_length_km.
        - Segment count is NEVER substituted for physical length.
        - peak_segment_disruption_probability is strictly the maximum individual segment probability.
        - Each segment is evaluated with exact same CP19 24-feature construction.
        """
        if not isinstance(route, Mapping):
            raise MLInferenceValidationError(f"Expected route to be a mapping, got {type(route).__name__}")
        if not isinstance(segment_contexts, Mapping):
            raise MLInferenceValidationError(f"Expected segment_contexts to be a mapping, got {type(segment_contexts).__name__}")

        route_id = str(route.get("route_id", "route_unknown"))

        # Resolve segment sequence from route
        seg_records: List[Mapping[str, Any]] = []
        if "segments" in route and isinstance(route["segments"], list) and route["segments"]:
            seg_records = route["segments"]
        elif "segment_ids" in route and isinstance(route["segment_ids"], list) and route["segment_ids"]:
            for sid in route["segment_ids"]:
                sid_str = str(sid)
                if sid_str not in segment_contexts:
                    raise MLInferenceValidationError(
                        f"Route '{route_id}' references segment '{sid_str}' missing from segment_contexts"
                    )
                seg_records.append(segment_contexts[sid_str])
        else:
            raise MLInferenceValidationError(
                f"Route '{route_id}' contains no valid 'segments' or 'segment_ids' collection"
            )

        if not seg_records:
            raise MLInferenceValidationError(f"Route '{route_id}' contains zero segments")

        # Gather complete context and physical length for each segment
        contexts_to_predict: List[Mapping[str, Any]] = []
        lengths_km: List[float] = []

        for idx, seg in enumerate(seg_records):
            sid = str(seg.get("segment_id", "")).strip()
            if not sid:
                raise MLInferenceValidationError(f"Segment at index {idx} in route '{route_id}' missing 'segment_id'")

            # Resolve full context from segment_contexts mapping or segment itself
            if sid in segment_contexts:
                ctx = segment_contexts[sid]
            else:
                ctx = seg

            contexts_to_predict.append(ctx)

            # Resolve physical segment length strictly
            len_val: Optional[float] = None
            if "segment_length_km" in ctx and ctx["segment_length_km"] is not None:
                len_val = _validate_numeric_scalar(f"segment_length_km[{sid}]", ctx["segment_length_km"])
            elif "segment_length_km" in seg and seg["segment_length_km"] is not None:
                len_val = _validate_numeric_scalar(f"segment_length_km[{sid}]", seg["segment_length_km"])
            elif "length_km" in ctx and ctx["length_km"] is not None:
                len_val = _validate_numeric_scalar(f"length_km[{sid}]", ctx["length_km"])
            elif "length_km" in seg and seg["length_km"] is not None:
                len_val = _validate_numeric_scalar(f"length_km[{sid}]", seg["length_km"])
            else:
                raise MLInferenceValidationError(
                    f"Segment '{sid}' in route '{route_id}' is missing physical 'segment_length_km'. "
                    "Segment count is never allowed as a substitute for physical road length."
                )

            if len_val <= 0.0:
                raise MLInferenceValidationError(
                    f"Segment '{sid}' in route '{route_id}' has non-positive length {len_val} km"
                )

            lengths_km.append(len_val)

        # Execute predictions across all segments
        seg_predictions = self.predict_segments_disruption(contexts_to_predict, date=date)

        total_length_km = sum(lengths_km)
        weighted_sum = sum(p["disruption_probability"] * l_km for p, l_km in zip(seg_predictions, lengths_km))
        length_weighted_mean = weighted_sum / total_length_km

        raw_probs = [p["disruption_probability"] for p in seg_predictions]
        peak_prob = max(raw_probs) if raw_probs else 0.0

        disrupted_ids = [p["segment_id"] for p in seg_predictions if p["disruption_predicted"]]

        return {
            "route_id": route_id,
            "segment_count": len(seg_predictions),
            "total_distance_km": round(total_length_km, 6),
            "length_weighted_mean_disruption_probability": round(length_weighted_mean, 4),
            "peak_segment_disruption_probability": round(peak_prob, 4),
            "disrupted_segment_count": len(disrupted_ids),
            "disrupted_segment_ids": disrupted_ids,
            "segment_predictions": seg_predictions,
            "provenance": get_default_provenance("random_forest", self._threshold),
        }


# ------------------------------------------------------------------------------
# 5. Public Convenience Functions
# ------------------------------------------------------------------------------

_DEFAULT_ENGINE: Optional[DisruptionInferenceEngine] = None


def get_default_inference_engine(
    model_path: Union[str, Path] = RANDOM_FOREST_ARTIFACT_PATH,
    threshold: float = FROZEN_DECISION_THRESHOLD,
) -> DisruptionInferenceEngine:
    """Return a singleton DisruptionInferenceEngine instance to ensure model is loaded once."""
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = DisruptionInferenceEngine(model_path=model_path, threshold=threshold)
    return _DEFAULT_ENGINE


def predict_segment_disruption(
    segment_context: Mapping[str, Any],
    date: Optional[Any] = None,
    engine: Optional[DisruptionInferenceEngine] = None,
) -> Dict[str, Any]:
    """Public convenience function for single segment disruption inference."""
    eng = engine or get_default_inference_engine()
    return eng.predict_segment_disruption(segment_context, date=date)


def predict_segments_disruption(
    segment_contexts: Iterable[Mapping[str, Any]],
    date: Optional[Any] = None,
    engine: Optional[DisruptionInferenceEngine] = None,
) -> List[Dict[str, Any]]:
    """Public convenience function for batch segment disruption inference."""
    eng = engine or get_default_inference_engine()
    return eng.predict_segments_disruption(segment_contexts, date=date)


def predict_route_disruption(
    route: Mapping[str, Any],
    segment_contexts: Mapping[str, Mapping[str, Any]],
    date: Optional[Any] = None,
    engine: Optional[DisruptionInferenceEngine] = None,
) -> Dict[str, Any]:
    """Public convenience function for route-level physical-length weighted disruption inference."""
    eng = engine or get_default_inference_engine()
    return eng.predict_route_disruption(route, segment_contexts, date=date)
