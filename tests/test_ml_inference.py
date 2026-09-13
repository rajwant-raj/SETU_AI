"""SETU_AI — Checkpoint 20: ML Inference Unit Tests.

Validates:
1. Model loading, reuse, and missing-artifact exception.
2. Strict 24-feature vector construction in canonical order.
3. Raw unscaled feature consumption (scaler bypass).
4. Canonical WMO mapping reuse from weather_severity.py.
5. Strict weather validation rejecting invalid/unsupported codes (never silently 0.0).
6. Missing or malformed feature validation.
7. Decision threshold boundary behavior (0.299 -> False, 0.300 -> True, 0.301 -> True).
8. Single vs. batch inference equivalence.
9. Route physical length-weighted aggregation and peak segment probability.
10. Deterministic execution and caller input immutability.
11. Zero network socket calls during inference.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
import socket
from typing import Any, Dict, List, Mapping

import numpy as np
import pytest

from src.data.weather.weather_severity import (
    InvalidWeatherInputError,
    WMO_CODE_SEVERITY,
)
from src.ml.inference import (
    FROZEN_DECISION_THRESHOLD,
    DisruptionInferenceEngine,
    MLInferenceRuntimeError,
    MLInferenceValidationError,
    ModelArtifactNotFoundError,
    construct_feature_vector_from_context,
    predict_route_disruption,
    predict_segment_disruption,
    predict_segments_disruption,
)
from src.ml.train_models import CANONICAL_FEATURES, RANDOM_FOREST_ARTIFACT_PATH


# ------------------------------------------------------------------------------
# Mock & Fixture Helpers
# ------------------------------------------------------------------------------

class MockPredictProbaModel:
    """Lightweight dummy scikit-learn model with predictable predict_proba outputs."""

    def __init__(self, probabilities: List[float]) -> None:
        self.probabilities = list(probabilities)
        self.call_count = 0
        self.cursor = 0
        self.last_X: Any = None

    def predict_proba(self, X: Any) -> np.ndarray:
        self.call_count += 1
        self.last_X = np.asarray(X)
        n_rows = len(self.last_X)
        probs: List[List[float]] = []
        for _ in range(n_rows):
            p = self.probabilities[self.cursor % len(self.probabilities)]
            self.cursor += 1
            probs.append([1.0 - p, p])
        return np.array(probs, dtype=np.float64)



def create_sample_segment_context(
    segment_id: str = "seg_test_001",
    lat: float = 26.1445,
    lon: float = 91.7362,
    road_type: str = "trunk",
    weather_code: int = 61,
    precip_mm: float = 12.5,
) -> Dict[str, Any]:
    """Create a fully-specified, valid operational segment context."""
    return {
        "segment_id": segment_id,
        "latitude": lat,
        "longitude": lon,
        "elevation_m": 55.0,
        "road_type": road_type,
        "surface": "asphalt",
        "lanes": 2,
        "connectivity_degree": 8,
        "accessibility_score": 0.85,
        "weather_point_dist_km": 4.2,
        "segment_length_km": 2.5,
        "weather": {
            "weather_code": weather_code,
            "precipitation_mm": precip_mm,
            "rain_mm": precip_mm,
            "precipitation_hours": 3.0,
            "temperature_c": 24.5,
            "temperature_max_c": 28.0,
            "temperature_min_c": 21.0,
            "temp_range_c": 7.0,
            "wind_speed_kmh": 15.0,
            "wind_gust_kmh": 25.0,
            "weather_severity_daily": 0.35,
        },
        "date": "2024-06-15",
    }


# ------------------------------------------------------------------------------
# Test Cases
# ------------------------------------------------------------------------------

def test_model_loading_and_reuse() -> None:
    """Engine loads model once and reuses the cached instance."""
    mock_model = MockPredictProbaModel([0.15])
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    ctx = create_sample_segment_context()
    res1 = engine.predict_segment_disruption(ctx)
    res2 = engine.predict_segment_disruption(ctx)

    assert res1["disruption_probability"] == 0.15
    assert res2["disruption_probability"] == 0.15
    assert mock_model.call_count == 2
    # Ensure model object identity is preserved
    assert engine._model is mock_model


def test_missing_model_artifact_raises() -> None:
    """Inference raises ModelArtifactNotFoundError when artifact file does not exist."""
    fake_path = Path("models/non_existent_model_artifact_xyz.joblib")
    engine = DisruptionInferenceEngine(model_path=fake_path)

    ctx = create_sample_segment_context()
    with pytest.raises(ModelArtifactNotFoundError) as exc_info:
        engine.predict_segment_disruption(ctx)

    assert "Trained model artifact not found" in str(exc_info.value)


def test_exact_24_canonical_feature_ordering() -> None:
    """Feature vector strictly contains 24 canonical features in exact order."""
    ctx = create_sample_segment_context()
    vec = construct_feature_vector_from_context(ctx)

    assert len(vec) == 24
    assert len(vec) == len(CANONICAL_FEATURES)

    # 1. month_sin, month_cos for June (month 6)
    # sin(2*pi*6/12) = sin(pi) ~ 0.0, cos(2*pi*6/12) = cos(pi) = -1.0
    assert math.isclose(vec[0], math.sin(math.pi), abs_tol=1e-5)
    assert math.isclose(vec[1], -1.0, abs_tol=1e-5)

    # 2. Coordinates
    assert vec[4] == 26.1445
    assert vec[5] == 91.7362

    # 3. Elevation
    assert vec[6] == 55.0

    # 4. road_type_rank: trunk -> 3
    assert vec[7] == 3.0

    # 5. surface_paved: asphalt -> 1.0
    assert vec[8] == 1.0

    # 6. lanes -> 2.0
    assert vec[9] == 2.0

    # 7. connectivity_degree -> 8.0
    assert vec[10] == 8.0

    # 8. accessibility_score -> 0.85
    assert vec[11] == 0.85

    # 9. weather_code severity: 61 (slight rain) -> 0.30
    assert vec[22] == 0.30


def test_raw_unscaled_features_passed_to_model() -> None:
    """Random Forest receives raw unscaled features, verifying StandardScaler bypass."""
    mock_model = MockPredictProbaModel([0.10])
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    ctx = create_sample_segment_context()
    engine.predict_segment_disruption(ctx)

    assert mock_model.last_X is not None
    assert mock_model.last_X.shape == (1, 24)

    # Verify unscaled values are passed directly (e.g. elevation 55.0, lanes 2.0)
    # If StandardScaler was applied, elevation would be normalized to z-score (near 0)
    assert mock_model.last_X[0, 6] == 55.0
    assert mock_model.last_X[0, 9] == 2.0
    assert mock_model.last_X[0, 10] == 8.0


def test_canonical_wmo_code_mapping_reuse() -> None:
    """WMO severity strictly matches canonical WMO_CODE_SEVERITY dictionary."""
    ctx = create_sample_segment_context(weather_code=95)  # slight/mod thunderstorm
    vec = construct_feature_vector_from_context(ctx)

    # Index 22 is weather_code
    expected_sev = WMO_CODE_SEVERITY[95]
    assert expected_sev == 0.80
    assert vec[22] == 0.80


def test_strict_weather_code_validation_rejects_invalid_inputs() -> None:
    """Invalid, non-numeric, or unsupported WMO codes raise InvalidWeatherInputError (never 0.0)."""
    # 1. Missing weather_code
    ctx1 = create_sample_segment_context()
    del ctx1["weather"]["weather_code"]
    with pytest.raises(InvalidWeatherInputError):
        construct_feature_vector_from_context(ctx1)

    # 2. Non-numeric weather_code
    ctx2 = create_sample_segment_context()
    ctx2["weather"]["weather_code"] = "tornado_alert"
    with pytest.raises(InvalidWeatherInputError):
        construct_feature_vector_from_context(ctx2)

    # 3. Unsupported WMO code (e.g. 999)
    ctx3 = create_sample_segment_context()
    ctx3["weather"]["weather_code"] = 999
    with pytest.raises(InvalidWeatherInputError):
        construct_feature_vector_from_context(ctx3)


def test_missing_required_features_raise_validation_error() -> None:
    """Missing required segment or weather features raise MLInferenceValidationError."""
    # Missing elevation_m
    ctx = create_sample_segment_context()
    del ctx["elevation_m"]
    with pytest.raises(MLInferenceValidationError) as exc:
        construct_feature_vector_from_context(ctx)
    assert "elevation_m" in str(exc.value)

    # Missing lanes
    ctx2 = create_sample_segment_context()
    del ctx2["lanes"]
    with pytest.raises(MLInferenceValidationError) as exc:
        construct_feature_vector_from_context(ctx2)
    assert "lanes" in str(exc.value)

    # Missing precipitation_mm
    ctx3 = create_sample_segment_context()
    del ctx3["weather"]["precipitation_mm"]
    with pytest.raises(MLInferenceValidationError) as exc:
        construct_feature_vector_from_context(ctx3)
    assert "precipitation_mm" in str(exc.value)


def test_invalid_coordinates_raise_validation_error() -> None:
    """Coordinates out of WGS84 bounds or non-numeric raise MLInferenceValidationError."""
    ctx = create_sample_segment_context(lat=95.0)  # > 90.0
    with pytest.raises(MLInferenceValidationError):
        construct_feature_vector_from_context(ctx)

    ctx2 = create_sample_segment_context(lon=-190.0)  # < -180.0
    with pytest.raises(MLInferenceValidationError):
        construct_feature_vector_from_context(ctx2)


def test_decision_threshold_boundaries() -> None:
    """Threshold evaluation operates strictly on raw probability at frozen 0.30."""
    # Test boundary values: 0.299, 0.300, 0.301
    mock_model = MockPredictProbaModel([0.299, 0.300, 0.301])
    engine = DisruptionInferenceEngine(model_instance=mock_model, threshold=0.30)

    ctx = create_sample_segment_context()

    # 1. 0.299 -> False
    res1 = engine.predict_segment_disruption(ctx)
    assert res1["disruption_probability"] == 0.299
    assert res1["disruption_predicted"] is False

    # 2. 0.300 -> True
    res2 = engine.predict_segment_disruption(ctx)
    assert res2["disruption_probability"] == 0.300
    assert res2["disruption_predicted"] is True

    # 3. 0.301 -> True
    res3 = engine.predict_segment_disruption(ctx)
    assert res3["disruption_probability"] == 0.301
    assert res3["disruption_predicted"] is True


def test_single_vs_batch_equivalence() -> None:
    """Batch prediction across segments returns identical results to single sequential predictions."""
    probs = [0.12345, 0.45678, 0.78901]
    mock_model = MockPredictProbaModel(probs)
    engine = DisruptionInferenceEngine(model_instance=mock_model, threshold=0.30)

    ctx1 = create_sample_segment_context(segment_id="s1")
    ctx2 = create_sample_segment_context(segment_id="s2")
    ctx3 = create_sample_segment_context(segment_id="s3")
    contexts = [ctx1, ctx2, ctx3]

    # Single sequential predictions
    single_res = [engine.predict_segment_disruption(c) for c in contexts]

    # Reset mock model call state for fair comparison
    mock_model_batch = MockPredictProbaModel(probs)
    engine_batch = DisruptionInferenceEngine(model_instance=mock_model_batch, threshold=0.30)
    batch_res = engine_batch.predict_segments_disruption(contexts)

    assert len(single_res) == len(batch_res)
    for s_item, b_item in zip(single_res, batch_res):
        assert s_item["segment_id"] == b_item["segment_id"]
        assert s_item["disruption_probability"] == b_item["disruption_probability"]
        assert s_item["disruption_predicted"] == b_item["disruption_predicted"]


def test_route_physical_length_weighted_aggregation() -> None:
    """Route aggregation uses strictly physical segment_length_km and computes peak probability."""
    # Segment 1: length = 10 km, prob = 0.10
    # Segment 2: length = 30 km, prob = 0.50
    # Total length = 40 km
    # Weighted mean = (0.10 * 10 + 0.50 * 30) / 40 = (1.0 + 15.0) / 40 = 16.0 / 40 = 0.40
    # Peak prob = 0.50
    mock_model = MockPredictProbaModel([0.10, 0.50])
    engine = DisruptionInferenceEngine(model_instance=mock_model, threshold=0.30)

    ctx1 = create_sample_segment_context(segment_id="s1")
    ctx1["segment_length_km"] = 10.0

    ctx2 = create_sample_segment_context(segment_id="s2")
    ctx2["segment_length_km"] = 30.0

    route = {
        "route_id": "route_test_alpha",
        "segment_ids": ["s1", "s2"],
        "total_distance_km": 40.0,
    }
    seg_contexts = {"s1": ctx1, "s2": ctx2}

    route_res = engine.predict_route_disruption(route, seg_contexts)

    assert route_res["route_id"] == "route_test_alpha"
    assert route_res["segment_count"] == 2
    assert route_res["total_distance_km"] == 40.0
    assert math.isclose(route_res["length_weighted_mean_disruption_probability"], 0.40, abs_tol=1e-4)
    assert route_res["peak_segment_disruption_probability"] == 0.50
    assert route_res["disrupted_segment_count"] == 1
    assert route_res["disrupted_segment_ids"] == ["s2"]


def test_route_missing_physical_length_raises() -> None:
    """Route aggregation strictly rejects segments missing physical segment_length_km."""
    mock_model = MockPredictProbaModel([0.20])
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    ctx = create_sample_segment_context(segment_id="s_nolen")
    del ctx["segment_length_km"]

    route = {
        "route_id": "route_err",
        "segment_ids": ["s_nolen"],
        "total_distance_km": 5.0,
    }

    with pytest.raises(MLInferenceValidationError) as exc_info:
        engine.predict_route_disruption(route, {"s_nolen": ctx})

    assert "missing physical 'segment_length_km'" in str(exc_info.value)


def test_input_immutability() -> None:
    """Caller input dictionaries are not mutated by inference."""
    mock_model = MockPredictProbaModel([0.25])
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    original_ctx = create_sample_segment_context()
    cloned_ctx = copy.deepcopy(original_ctx)

    engine.predict_segment_disruption(original_ctx)
    assert original_ctx == cloned_ctx


def test_reproducibility_under_same_inputs() -> None:
    """Identical inputs produce deterministic results under the frozen model."""
    mock_model = MockPredictProbaModel([0.2847])
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    ctx = create_sample_segment_context()
    res1 = engine.predict_segment_disruption(ctx)
    res2 = engine.predict_segment_disruption(ctx)

    assert res1 == res2


def test_zero_network_calls_during_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inference executes completely in-memory without network socket connections."""
    def guarded_connect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Network socket call attempted during pure local ML inference!")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    mock_model = MockPredictProbaModel([0.18])
    engine = DisruptionInferenceEngine(model_instance=mock_model)

    ctx = create_sample_segment_context()
    res = engine.predict_segment_disruption(ctx)
    assert res["disruption_probability"] == 0.18


def test_real_production_model_if_present_locally() -> None:
    """If models/random_forest.joblib exists locally, run inference and verify contract."""
    rf_path = Path("models/random_forest.joblib")
    if not rf_path.exists():
        pytest.skip("models/random_forest.joblib not present locally; skipping local artifact verification")

    engine = DisruptionInferenceEngine(model_path=rf_path)
    ctx = create_sample_segment_context()
    res = engine.predict_segment_disruption(ctx)

    assert isinstance(res["disruption_probability"], float)
    assert 0.0 <= res["disruption_probability"] <= 1.0
    assert isinstance(res["disruption_predicted"], bool)
    assert res["threshold"] == FROZEN_DECISION_THRESHOLD
    assert "provenance" in res
    assert res["provenance"]["model_champion"] == "random_forest"
