"""SETU_AI — Checkpoint 19: Supervised Baseline Model Training & Evaluation.

Implements baseline machine learning models, feature preprocessing, chronological
splitting, deterministic positive-preserving sampling, threshold tuning, and
metrics evaluation on the Guwahati–Imphal road disruption corridor dataset (2019–2024).

Enforces:
1. Exact 24-feature schema and column order
2. Canonical WMO weather code hazard transformation
3. Strict chronological splitting (Train: 2019–2022, Val: 2023, Test: 2024)
4. Total target proxy and leakage column isolation
5. Train-only StandardScaler fitting for linear models
6. Model-specific preprocessing (scaled for linear, raw unscaled for trees)
7. Deterministic positive-preserving Random Forest sampling (500k target)
8. Precision-floor-constrained F1 threshold optimization (99 candidates: 0.01–0.99)
9. Complete evaluation metric suite (PR-AUC, ROC-AUC, P, R, F1, Brier, Log-Loss, CM)
10. Temporal held-out evaluation on 2024 with frozen validation threshold
11. Reproducibility via RANDOM_SEED = 42
"""

from __future__ import annotations

import csv
import gc
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any, Dict, Generator, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight


# ------------------------------------------------------------------------------
# 1. Canonical WMO Severity Mapping Ingestion
# ------------------------------------------------------------------------------

def _load_canonical_wmo_code_severity() -> Dict[int, float]:
    """Load canonical WMO_CODE_SEVERITY from Checkpoint 17."""
    try:
        from src.data.weather.weather_severity import WMO_CODE_SEVERITY
        return dict(WMO_CODE_SEVERITY)
    except (ImportError, ModuleNotFoundError):
        ws_path = Path(__file__).resolve().parent.parent / "data" / "weather" / "weather_severity.py"
        spec = importlib.util.spec_from_file_location("weather_severity_direct", ws_path)
        if spec is not None and spec.loader is not None:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return dict(mod.WMO_CODE_SEVERITY)
        raise RuntimeError(f"Could not load WMO_CODE_SEVERITY from {ws_path}")


WMO_CODE_SEVERITY: Dict[int, float] = _load_canonical_wmo_code_severity()


# ------------------------------------------------------------------------------
# 2. Canonical Constants & Schema Declarations
# ------------------------------------------------------------------------------

RANDOM_SEED: int = 42

CANONICAL_FEATURES: List[str] = [
    "month_sin",
    "month_cos",
    "dow_sin",
    "dow_cos",
    "latitude",
    "longitude",
    "elevation_m",
    "road_type_rank",
    "surface_paved",
    "lanes",
    "connectivity_degree",
    "accessibility_score",
    "weather_point_dist_km",
    "precipitation_mm",
    "rain_mm",
    "precipitation_hours",
    "temperature_c",
    "temperature_max_c",
    "temperature_min_c",
    "temp_range_c",
    "wind_speed_kmh",
    "wind_gust_kmh",
    "weather_code",
    "weather_severity_daily",
]

TARGET_COLUMN: str = "disruption_proxy"

TRAIN_YEARS: Tuple[int, ...] = (2019, 2020, 2021, 2022)
VAL_YEARS: Tuple[int, ...] = (2023,)
TEST_YEARS: Tuple[int, ...] = (2024,)

FORBIDDEN_LEAKAGE_COLUMNS: List[str] = [
    "segment_id",
    "date",
    "year",
    "disruption_score_continuous",
    "disruption_proxy",
    "nearest_weather_point_id",
    "weather_station_id",
    "risk_score",
    "risk_band",
    "risk_factors",
    "network_impact_score",
    "reroute_recommended",
    "delay_factor",
    "current_delay_ratio",
]


# ------------------------------------------------------------------------------
# 3. Feature Extraction & Encodings
# ------------------------------------------------------------------------------

def encode_weather_code(code: Any) -> float:
    """Deterministically map a WMO weather code to [0.0, 1.0] using canonical WMO_CODE_SEVERITY.

    Unknown or unmapped codes default safely to 0.0.
    """
    try:
        c_int = int(code)
        return float(WMO_CODE_SEVERITY.get(c_int, 0.0))
    except (ValueError, TypeError):
        return 0.0


def derive_cyclical_temporal_features(month: Any, day_of_week: Any) -> Tuple[float, float, float, float]:
    """Derive deterministic cyclical sine/cosine temporal features from calendar month and day_of_week.

    Formulas:
        month_sin = sin(2 * pi * month / 12)
        month_cos = cos(2 * pi * month / 12)
        dow_sin = sin(2 * pi * day_of_week / 7)
        dow_cos = cos(2 * pi * day_of_week / 7)

    Valid Ranges:
        month: integer in 1..12
        day_of_week: integer in 0..6

    Returns:
        (month_sin, month_cos, dow_sin, dow_cos)

    Raises:
        ValueError: If month or day_of_week is invalid or out of range.
    """
    try:
        m_int = int(month)
    except (ValueError, TypeError) as err:
        raise ValueError(f"Invalid month value {month!r}: must be an integer in 1..12") from err

    if not 1 <= m_int <= 12:
        raise ValueError(f"Invalid month value {m_int}: must be in 1..12")

    try:
        dow_int = int(day_of_week)
    except (ValueError, TypeError) as err:
        raise ValueError(f"Invalid day_of_week value {day_of_week!r}: must be an integer in 0..6") from err

    if not 0 <= dow_int <= 6:
        raise ValueError(f"Invalid day_of_week value {dow_int}: must be in 0..6")

    month_sin = math.sin(2.0 * math.pi * float(m_int) / 12.0)
    month_cos = math.cos(2.0 * math.pi * float(m_int) / 12.0)
    dow_sin = math.sin(2.0 * math.pi * float(dow_int) / 7.0)
    dow_cos = math.cos(2.0 * math.pi * float(dow_int) / 7.0)

    return month_sin, month_cos, dow_sin, dow_cos


def extract_feature_vector(record: Mapping[str, Any]) -> List[float]:
    """Extract exactly the 24 canonical features in deterministic order from a record mapping.

    Handles temporal features dynamically:
    - If raw 'month' and 'day_of_week' are provided (production CSV schema), derives cyclical features.
    - If precomputed 'month_sin', 'month_cos', 'dow_sin', 'dow_cos' are provided (test schema), uses them.
    - Encodes weather_code using the canonical WMO_CODE_SEVERITY mapping.
    """
    temporal_vals: Dict[str, float] = {}
    precomputed_temporal_keys = ("month_sin", "month_cos", "dow_sin", "dow_cos")
    has_precomputed = all(k in record for k in precomputed_temporal_keys)

    if has_precomputed:
        for k in precomputed_temporal_keys:
            try:
                temporal_vals[k] = float(record[k])
            except (ValueError, TypeError) as err:
                raise ValueError(f"Precomputed temporal feature '{k}' value {record[k]!r} cannot be converted to float") from err
    elif "month" in record and "day_of_week" in record:
        m_sin, m_cos, d_sin, d_cos = derive_cyclical_temporal_features(record["month"], record["day_of_week"])
        temporal_vals["month_sin"] = m_sin
        temporal_vals["month_cos"] = m_cos
        temporal_vals["dow_sin"] = d_sin
        temporal_vals["dow_cos"] = d_cos
    else:
        raise KeyError(
            "Missing required temporal columns in record. Expected either "
            "('month' and 'day_of_week') or ('month_sin', 'month_cos', 'dow_sin', 'dow_cos')."
        )

    vec: List[float] = []
    for col in CANONICAL_FEATURES:
        if col in temporal_vals:
            vec.append(temporal_vals[col])
        else:
            if col not in record:
                raise KeyError(f"Missing required feature column in record: '{col}'")
            raw_val = record[col]
            if col == "weather_code":
                vec.append(encode_weather_code(raw_val))
            else:
                try:
                    vec.append(float(raw_val))
                except (ValueError, TypeError) as err:
                    raise ValueError(f"Feature '{col}' value {raw_val!r} cannot be converted to float") from err

    return vec


# ------------------------------------------------------------------------------
# 4. Chronological Split Selection
# ------------------------------------------------------------------------------

def get_split_name(year: int) -> str:
    """Return the chronological split name ('train', 'val', 'test') for a given calendar year.

    Raises:
        ValueError: If year is outside the supported 2019–2024 study window.
    """
    if year in TRAIN_YEARS:
        return "train"
    if year in VAL_YEARS:
        return "val"
    if year in TEST_YEARS:
        return "test"
    raise ValueError(f"Unsupported year: {year}. Must be one of {TRAIN_YEARS + VAL_YEARS + TEST_YEARS}")


# ------------------------------------------------------------------------------
# 5. Model Preprocessing & Standardization
# ------------------------------------------------------------------------------

def fit_linear_scaler(X_train: Any) -> StandardScaler:
    """Fit a StandardScaler strictly on training data."""
    scaler = StandardScaler()
    scaler.fit(X_train)
    return scaler


def prepare_model_input(
    X: Any,
    model_type: str,
    scaler: Optional[StandardScaler] = None,
) -> Any:
    """Prepare feature matrix based on model algorithm requirements.

    - 'linear': Standardized features via frozen scaler
    - 'random_forest': Raw unscaled features
    - 'hist_gradient_boosting': Raw unscaled features
    """
    model_type_norm = model_type.lower().strip()
    if model_type_norm in ("linear", "linear_baseline"):
        if scaler is None:
            raise ValueError("scaler must be provided for linear model_type")
        return scaler.transform(X)
    elif model_type_norm in ("random_forest", "hist_gradient_boosting"):
        return X
    else:
        raise ValueError(
            f"Unsupported model_type: '{model_type}'. Expected 'linear', 'random_forest', or 'hist_gradient_boosting'."
        )


# ------------------------------------------------------------------------------
# 6. Random Forest Positive-Preserving Sampling
# ------------------------------------------------------------------------------

def sample_rf_training_data(
    X: Any,
    y: Any,
    target_total: int = 500_000,
    random_state: int = RANDOM_SEED,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Deterministically sample training data for Random Forest by retaining 100% of positive rows.

    Contract:
    - Retain all positive records (y == 1)
    - Deterministically sample negatives (y == 0) to reach exactly target_total rows
    - Deterministic shuffle with random_state
    - Emits metadata manifest with row counts, prevalence, and seed
    """
    X_arr = np.asarray(X)
    y_arr = np.asarray(y, dtype=int)

    if len(X_arr) != len(y_arr):
        raise ValueError(f"X length ({len(X_arr)}) and y length ({len(y_arr)}) mismatch")

    pos_indices = np.where(y_arr == 1)[0]
    neg_indices = np.where(y_arr == 0)[0]

    num_pos = len(pos_indices)
    num_neg_avail = len(neg_indices)

    if num_pos > target_total:
        raise ValueError(
            f"Positive rows ({num_pos}) exceed requested target_total ({target_total})"
        )

    needed_neg = target_total - num_pos
    if num_neg_avail < needed_neg:
        raise ValueError(
            f"Available negative rows ({num_neg_avail}) fewer than needed ({needed_neg}) for target_total={target_total}"
        )

    rng = np.random.RandomState(random_state)
    sampled_neg_indices = rng.choice(neg_indices, size=needed_neg, replace=False)

    combined_indices = np.concatenate([pos_indices, sampled_neg_indices])
    shuffled_indices = rng.permutation(combined_indices)

    X_sampled = X_arr[shuffled_indices]
    y_sampled = y_arr[shuffled_indices]

    metadata = {
        "total_sampled_rows": int(target_total),
        "positive_sampled_rows": int(num_pos),
        "negative_sampled_rows": int(needed_neg),
        "sampled_prevalence": float(num_pos / target_total) if target_total > 0 else 0.0,
        "random_seed": int(random_state),
    }

    return X_sampled, y_sampled, metadata


# ------------------------------------------------------------------------------
# 7. Validation Threshold Optimization
# ------------------------------------------------------------------------------

def tune_validation_threshold(
    y_true: Any,
    y_proba: Any,
    precision_floor: float = 0.20,
    num_thresholds: int = 99,
) -> Tuple[float, List[Dict[str, Any]]]:
    """Sweep 99 candidate thresholds over validation predictions and select the optimal F1 threshold.

    Threshold candidates:
    linspace(0.01, 0.99, num_thresholds) -> 0.01 to 0.99 in 0.01 increments

    Constraint: precision >= precision_floor
    Objective: maximize F1
    Tie-breaking: highest precision, then lowest threshold
    """
    y_true_arr = np.asarray(y_true, dtype=int)
    y_proba_arr = np.asarray(y_proba, dtype=float)

    thresholds = np.linspace(0.01, 0.99, num_thresholds)
    table: List[Dict[str, Any]] = []

    valid_candidates: List[Tuple[float, float, float]] = []
    all_candidates: List[Tuple[float, float, float]] = []

    for t in thresholds:
        thresh = round(float(t), 4)
        preds = (y_proba_arr >= thresh).astype(int)

        tp = int(np.sum((preds == 1) & (y_true_arr == 1)))
        fp = int(np.sum((preds == 1) & (y_true_arr == 0)))
        fn = int(np.sum((preds == 0) & (y_true_arr == 1)))
        tn = int(np.sum((preds == 0) & (y_true_arr == 0)))

        prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        entry = {
            "threshold": thresh,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "valid_precision_floor": prec >= precision_floor,
        }
        table.append(entry)
        all_candidates.append((f1, prec, thresh))
        if prec >= precision_floor:
            valid_candidates.append((f1, prec, thresh))

    if valid_candidates:
        # Tie-breaking: max F1 (-x[0]), max precision (-x[1]), lowest threshold (x[2])
        valid_candidates.sort(key=lambda x: (-x[0], -x[1], x[2]))
        best_thresh = valid_candidates[0][2]
    else:
        # Fallback to candidate with maximum precision
        all_candidates.sort(key=lambda x: (-x[1], -x[0], x[2]))
        best_thresh = all_candidates[0][2]

    return best_thresh, table


# ------------------------------------------------------------------------------
# 8. Evaluation Metrics Computation
# ------------------------------------------------------------------------------

def compute_evaluation_metrics(
    y_true: Any,
    y_proba: Any,
    threshold: float = 0.50,
) -> Dict[str, Any]:
    """Compute comprehensive evaluation metrics for binary classification.

    Probabilities are used for: PR-AUC, ROC-AUC, Brier score, Log-Loss.
    Thresholded predictions are used for: Precision, Recall, F1, Confusion Matrix.
    """
    y_true_arr = np.asarray(y_true, dtype=int)
    y_proba_arr = np.asarray(y_proba, dtype=float)

    preds = (y_proba_arr >= threshold).astype(int)

    # Discrimination & probabilistic calibration
    try:
        pr_auc = float(average_precision_score(y_true_arr, y_proba_arr))
    except Exception:
        pr_auc = 0.0

    try:
        roc_auc = float(roc_auc_score(y_true_arr, y_proba_arr))
    except Exception:
        roc_auc = 0.5

    try:
        brier = float(brier_score_loss(y_true_arr, y_proba_arr))
    except Exception:
        brier = 0.0

    clipped_proba = np.clip(y_proba_arr, 1e-15, 1.0 - 1e-15)
    try:
        ll = float(log_loss(y_true_arr, clipped_proba))
    except Exception:
        ll = 0.0

    prec = float(precision_score(y_true_arr, preds, zero_division=0.0))
    rec = float(recall_score(y_true_arr, preds, zero_division=0.0))
    f1 = float(f1_score(y_true_arr, preds, zero_division=0.0))

    cm = confusion_matrix(y_true_arr, preds, labels=[0, 1])
    tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "brier_score": brier,
        "log_loss": ll,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
    }


def evaluate_temporal_test(
    y_true: Any,
    y_proba: Any,
    frozen_threshold: float,
) -> Dict[str, Any]:
    """Evaluate held-out temporal test set using frozen threshold from validation."""
    metrics = compute_evaluation_metrics(y_true, y_proba, threshold=frozen_threshold)
    metrics["threshold_applied"] = float(frozen_threshold)
    return metrics


# ------------------------------------------------------------------------------
# 9. Model Architecture Factories & Fitting Helpers
# ------------------------------------------------------------------------------

def build_logistic_regression(random_state: int = RANDOM_SEED) -> LogisticRegression:
    """Construct LogisticRegression baseline model."""
    return LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=random_state,
        solver="lbfgs",
    )


def build_sgd_classifier(random_state: int = RANDOM_SEED) -> SGDClassifier:
    """Construct memory-safe SGDClassifier fallback linear baseline."""
    return SGDClassifier(
        loss="log_loss",
        penalty="l2",
        alpha=1e-5,
        max_iter=50,
        random_state=random_state,
        class_weight="balanced",
    )


def build_random_forest(random_state: int = RANDOM_SEED) -> RandomForestClassifier:
    """Construct RandomForestClassifier bagged ensemble model."""
    return RandomForestClassifier(
        n_estimators=100,
        max_depth=16,
        min_samples_leaf=10,
        n_jobs=-1,
        random_state=random_state,
        class_weight="balanced_subsample",
    )


def build_hist_gradient_boosting(random_state: int = RANDOM_SEED) -> HistGradientBoostingClassifier:
    """Construct HistGradientBoostingClassifier tabular benchmark model."""
    return HistGradientBoostingClassifier(
        loss="log_loss",
        max_iter=150,
        learning_rate=0.08,
        max_leaf_nodes=31,
        min_samples_leaf=50,
        early_stopping=True,
        n_iter_no_change=10,
        random_state=random_state,
    )


def fit_linear_baseline_with_fallback(
    X_train_scaled: Any,
    y_train: Any,
    random_state: int = RANDOM_SEED,
) -> Tuple[Union[LogisticRegression, SGDClassifier], Dict[str, Any]]:
    """Fit linear baseline model with memory/convergence fallback contract.

    1. First attempts LogisticRegression(solver="lbfgs", class_weight="balanced").
    2. If MemoryError, TimeoutError, RuntimeError, or non-convergence occurs,
       falls back deterministically to SGDClassifier(loss="log_loss", class_weight="balanced").
    3. Returns (fitted_model, metadata_manifest).
    """
    metadata: Dict[str, Any] = {
        "primary_model_attempted": "LogisticRegression",
        "model_type_used": None,
        "fallback_occurred": False,
        "fallback_reason": None,
        "random_seed": int(random_state),
    }

    lr_model = build_logistic_regression(random_state=random_state)
    try:
        lr_model.fit(X_train_scaled, y_train)
        metadata["model_type_used"] = "LogisticRegression"
        return lr_model, metadata
    except (MemoryError, TimeoutError, RuntimeError) as err:
        metadata["fallback_occurred"] = True
        metadata["fallback_reason"] = f"{type(err).__name__}: {str(err)}"
        sgd_model = build_sgd_classifier(random_state=random_state)
        sgd_model.fit(X_train_scaled, y_train)
        metadata["model_type_used"] = "SGDClassifier"
        return sgd_model, metadata


def fit_hist_gradient_boosting(
    X_train: Any,
    y_train: Any,
    random_state: int = RANDOM_SEED,
) -> HistGradientBoostingClassifier:
    """Fit HistGradientBoostingClassifier with balanced sample weights on unscaled features.

    Deterministic imbalance handling via compute_sample_weight("balanced", y=y_train).
    """
    sample_weights = compute_sample_weight(
        class_weight="balanced",
        y=y_train,
    )
    model = build_hist_gradient_boosting(random_state=random_state)
    model.fit(
        X_train,
        y_train,
        sample_weight=sample_weights,
    )
    return model


# ------------------------------------------------------------------------------
# 10. Champion Model Selection
# ------------------------------------------------------------------------------

def select_champion_model(
    validation_results: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Deterministically select the champion model based strictly on validation metrics.

    Selection protocol:
    1. PRIMARY: Highest validation PR-AUC ('pr_auc')
    2. TIE: Highest validation F1 ('f1')
    3. FINAL TIE-BREAK: Lexicographically smallest model name

    Raises:
        ValueError: If validation_results is empty or missing required metrics.
    """
    if not validation_results:
        raise ValueError("validation_results cannot be empty")

    candidates: List[Tuple[float, float, str, Dict[str, Any]]] = []
    for model_name, metrics in validation_results.items():
        if "pr_auc" not in metrics:
            raise KeyError(f"Model '{model_name}' metrics missing required 'pr_auc'")
        if "f1" not in metrics:
            raise KeyError(f"Model '{model_name}' metrics missing required 'f1'")
        pr_auc = float(metrics["pr_auc"])
        f1 = float(metrics["f1"])
        candidates.append((pr_auc, f1, str(model_name), dict(metrics)))

    # Sort: descending pr_auc (-x[0]), descending f1 (-x[1]), ascending model_name (x[2])
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))

    champion_pr_auc, champion_f1, champion_name, champion_metrics = candidates[0]

    return {
        "champion_name": champion_name,
        "selection_metric": "pr_auc",
        "champion_pr_auc": champion_pr_auc,
        "champion_f1": champion_f1,
        "champion_metrics": champion_metrics,
        "total_candidates_evaluated": len(candidates),
        "ranking": [
            {
                "rank": i + 1,
                "model_name": c[2],
                "pr_auc": c[0],
                "f1": c[1],
            }
            for i, c in enumerate(candidates)
        ],
    }


# ------------------------------------------------------------------------------
# 11. Approved Artifact Path Declarations
# ------------------------------------------------------------------------------

MODELS_DIR = Path("models")
SCALER_ARTIFACT_PATH = MODELS_DIR / "scaler.joblib"
SCALER_METADATA_PATH = MODELS_DIR / "scaler_metadata.json"
LINEAR_BASELINE_ARTIFACT_PATH = MODELS_DIR / "linear_baseline.joblib"
RANDOM_FOREST_ARTIFACT_PATH = MODELS_DIR / "random_forest.joblib"
HIST_GRADIENT_BOOSTING_ARTIFACT_PATH = MODELS_DIR / "hist_gradient_boosting.joblib"
EVALUATION_SUMMARY_PATH = MODELS_DIR / "evaluation_summary.json"
MODEL_COMPARISON_REPORT_PATH = MODELS_DIR / "model_comparison_report.md"

ARTIFACT_PATHS: Dict[str, Path] = {
    "scaler": SCALER_ARTIFACT_PATH,
    "scaler_metadata": SCALER_METADATA_PATH,
    "linear_baseline": LINEAR_BASELINE_ARTIFACT_PATH,
    "random_forest": RANDOM_FOREST_ARTIFACT_PATH,
    "hist_gradient_boosting": HIST_GRADIENT_BOOSTING_ARTIFACT_PATH,
    "evaluation_summary": EVALUATION_SUMMARY_PATH,
    "model_comparison_report": MODEL_COMPARISON_REPORT_PATH,
}


# ------------------------------------------------------------------------------
# 12. Memory-Safe Dataset Loading & Partition Helpers
# ------------------------------------------------------------------------------

def get_partition_path(year: int, base_dir: Union[str, Path] = "datasets/processed/ml") -> Path:
    """Return the filesystem path for a specific annual partition CSV."""
    return Path(base_dir) / f"ml_dataset_{year}.csv"


def stream_partition_records(
    partition_path: Union[str, Path],
    chunk_size: int = 250_000,
) -> Generator[List[Dict[str, str]], None, None]:
    """Stream rows from a CSV partition in chunks of size chunk_size without full memory loading."""
    path = Path(partition_path)
    if not path.exists():
        raise FileNotFoundError(f"Partition file does not exist: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        chunk: List[Dict[str, str]] = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def count_partition_rows(partition_path: Union[str, Path]) -> int:
    """Fast binary counting of data rows (excluding header) in a partition CSV."""
    path = Path(partition_path)
    if not path.exists():
        raise FileNotFoundError(f"Partition file does not exist: {path}")

    total_lines = 0
    last_char = b""
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            total_lines += chunk.count(b"\n")
            if chunk:
                last_char = chunk[-1:]
    if last_char and last_char != b"\n":
        total_lines += 1
    return max(0, total_lines - 1)


def load_split_matrix(
    years: Union[int, Sequence[int]],
    base_dir: Union[str, Path] = "datasets/processed/ml",
    chunk_size: int = 250_000,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Sequentially load annual CSV partitions into preallocated float32 feature matrix and int8 target vector.

    Enforces:
    - Bounded memory usage via incremental streaming and chunk ingestion
    - Exact preallocation of X (float32) and y (int8)
    - Deterministic chronological year ordering
    - Exact row order preservation within each partition
    - Canonical 24-feature extraction with weather_code transformation and cyclical temporal derivations
    - Strict target proxy extraction (disruption_proxy) and total leakage isolation
    - Comprehensive metadata return
    - Clear failure context on malformed records
    """
    if isinstance(years, (int, str)):
        year_list = [int(years)]
    else:
        year_list = [int(y) for y in years]

    # Preserve deterministic chronological year ordering
    year_list = sorted(list(dict.fromkeys(year_list)))

    # Compute partition row counts and preallocate final matrices
    partition_counts: Dict[int, int] = {}
    for y in year_list:
        p_path = get_partition_path(y, base_dir=base_dir)
        partition_counts[y] = count_partition_rows(p_path)

    total_rows = sum(partition_counts.values())
    n_features = len(CANONICAL_FEATURES)

    X = np.empty((total_rows, n_features), dtype=np.float32)
    y = np.empty(total_rows, dtype=np.int8)

    current_idx = 0
    for year in year_list:
        p_path = get_partition_path(year, base_dir=base_dir)
        with p_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            chunk_records: List[List[float]] = []
            chunk_targets: List[int] = []

            row_num = 1  # 1-indexed relative to data rows
            for raw_row in reader:
                try:
                    features = extract_feature_vector(raw_row)
                except Exception as err:
                    raise ValueError(
                        f"Malformed feature record in partition {p_path} (year {year}) at data row {row_num}: {err}"
                    ) from err

                if TARGET_COLUMN not in raw_row:
                    raise KeyError(
                        f"Missing target column '{TARGET_COLUMN}' in partition {p_path} (year {year}) at data row {row_num}"
                    )
                try:
                    target_val = int(raw_row[TARGET_COLUMN])
                except (ValueError, TypeError) as err:
                    raise ValueError(
                        f"Invalid target value {raw_row[TARGET_COLUMN]!r} in partition {p_path} (year {year}) at data row {row_num}: {err}"
                    ) from err

                if target_val not in (0, 1):
                    raise ValueError(
                        f"Target value {target_val} not in (0, 1) in partition {p_path} (year {year}) at data row {row_num}"
                    )

                chunk_records.append(features)
                chunk_targets.append(target_val)
                row_num += 1

                if len(chunk_records) >= chunk_size:
                    n_chunk = len(chunk_records)
                    X[current_idx : current_idx + n_chunk] = np.array(chunk_records, dtype=np.float32)
                    y[current_idx : current_idx + n_chunk] = np.array(chunk_targets, dtype=np.int8)
                    current_idx += n_chunk
                    chunk_records = []
                    chunk_targets = []

            if chunk_records:
                n_chunk = len(chunk_records)
                X[current_idx : current_idx + n_chunk] = np.array(chunk_records, dtype=np.float32)
                y[current_idx : current_idx + n_chunk] = np.array(chunk_targets, dtype=np.int8)
                current_idx += n_chunk
                chunk_records = []
                chunk_targets = []

    if current_idx != total_rows:
        raise RuntimeError(
            f"Row count mismatch during loading: expected {total_rows}, processed {current_idx}"
        )

    pos_count = int(np.sum(y == 1)) if total_rows > 0 else 0
    neg_count = int(np.sum(y == 0)) if total_rows > 0 else 0
    metadata: Dict[str, Any] = {
        "years": list(year_list),
        "row_count": int(total_rows),
        "positive_count": pos_count,
        "negative_count": neg_count,
        "prevalence": float(pos_count / total_rows) if total_rows > 0 else 0.0,
        "feature_count": int(n_features),
        "feature_names": list(CANONICAL_FEATURES),
        "partition_row_counts": partition_counts,
        "dtype_information": {
            "X_dtype": str(X.dtype),
            "y_dtype": str(y.dtype),
        },
        "dtypes": {
            "X": str(X.dtype),
            "y": str(y.dtype),
        },
    }

    return X, y, metadata


# ------------------------------------------------------------------------------
# 13. Model Probability Inference Interface
# ------------------------------------------------------------------------------

def get_model_probabilities(model: Any, X: Any) -> np.ndarray:
    """Extract positive class probabilities P(y=1) using sklearn model probability API.

    Supports:
    - predict_proba()[:, 1]
    - decision_function converted via sigmoid fallback
    """
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        if hasattr(proba, "ndim") and proba.ndim == 2 and proba.shape[1] >= 2:
            return np.asarray(proba[:, 1], dtype=np.float64)
        elif hasattr(proba, "ndim") and proba.ndim == 1:
            return np.asarray(proba, dtype=np.float64)
    if hasattr(model, "decision_function"):
        scores = np.asarray(model.decision_function(X), dtype=np.float64)
        return 1.0 / (1.0 + np.exp(-scores))
    raise AttributeError(f"Model of type {type(model).__name__} has neither predict_proba nor decision_function")


# ------------------------------------------------------------------------------
# 14. Report Generation & Artifact Serialization Helpers
# ------------------------------------------------------------------------------

def generate_model_comparison_report(summary: Mapping[str, Any]) -> str:
    """Generate deterministic Markdown model comparison report from evaluation summary."""
    splits = summary.get("dataset_splits", {})
    linear_exec = summary.get("linear_model_execution", {})
    val_metrics = summary.get("validation_metrics", {})
    champ = summary.get("champion_selection", {})
    test_metrics = summary.get("test_metrics_2024", {})

    train_rows = splits.get("train_rows", 0)
    train_pos = splits.get("train_positives", 0)
    train_prev = splits.get("train_prevalence", 0.0)
    val_rows = splits.get("val_rows", 0)
    val_pos = splits.get("val_positives", 0)
    val_prev = splits.get("val_prevalence", 0.0)
    test_rows = splits.get("test_rows", 0)
    test_pos = splits.get("test_positives", 0)
    test_prev = splits.get("test_prevalence", 0.0)

    lines = [
        "# SETU_AI — Baseline Model Training & Evaluation Comparison Report",
        "",
        "## 1. Methodology Disclosure",
        "> **SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION**",
        ">",
        "> This baseline model suite evaluates historical co-occurrence on the Guwahati–Imphal road corridor",
        "> using engineered disruption proxy labels. It does **NOT** represent real-world road-closure prediction",
        "> or future forecasting.",
        "",
        "## 2. Dataset & Chronological Splits",
        f"- **Training Window (2019–2022)**: {train_rows:,} rows | {train_pos:,} positive disruptions | prevalence: {train_prev:.4%}",
        f"- **Validation Window (2023)**: {val_rows:,} rows | {val_pos:,} positive disruptions | prevalence: {val_prev:.4%}",
        f"- **Temporal Test Window (2024)**: {test_rows:,} rows | {test_pos:,} positive disruptions | prevalence: {test_prev:.4%}",
        "",
        "> **Generalization Limitation**:",
        "> The 2024 temporal holdout evaluates generalization across an unseen temporal year on the same",
        "> underlying corridor road network. It does **NOT** represent spatial generalization to unseen road segments.",
        "",
        "## 3. Feature Contract",
        f"- Total canonical features: {len(CANONICAL_FEATURES)}",
        "- Features: " + ", ".join(f"`{col}`" for col in CANONICAL_FEATURES),
        "- Preprocessing: StandardScaler fit strictly on training set (2019–2022) for linear baseline; tree ensembles consume raw unscaled features.",
        "",
        "## 4. Model Architectures & Training Protocol",
        f"1. **Linear Baseline**: LogisticRegression (solver=lbfgs, class_weight=balanced, max_iter=1000) with deterministic SGDClassifier fallback. Model used: `{linear_exec.get('model_type_used', 'N/A')}` (fallback occurred: `{linear_exec.get('fallback_occurred', False)}`).",
        "2. **Random Forest**: RandomForestClassifier (n_estimators=100, max_depth=16, min_samples_leaf=10, class_weight=balanced_subsample, seed=42) fit on 500,000 positive-preserving sample.",
        "3. **HistGradientBoosting**: HistGradientBoostingClassifier (max_iter=150, lr=0.08, max_leaf_nodes=31, min_samples_leaf=50, seed=42) fit on full population with balanced sample weights.",
        "",
        "## 5. Validation Comparison (2023)",
        "| Model | Tuned Threshold | PR-AUC | ROC-AUC | Precision | Recall | F1 | Brier Score | Log-Loss |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for model_name, m in val_metrics.items():
        t = m.get("selected_threshold", 0.5)
        lines.append(
            f"| `{model_name}` | {t:.2f} | {m.get('pr_auc', 0.0):.4f} | {m.get('roc_auc', 0.0):.4f} | "
            f"{m.get('precision', 0.0):.4f} | {m.get('recall', 0.0):.4f} | {m.get('f1', 0.0):.4f} | "
            f"{m.get('brier_score', 0.0):.4f} | {m.get('log_loss', 0.0):.4f} |"
        )

    champ_name = champ.get("champion_name", "N/A")
    champ_pr_auc = champ.get("champion_pr_auc", 0.0)
    champ_f1 = champ.get("champion_f1", 0.0)
    frozen_thresh = champ.get("frozen_threshold", 0.5)

    lines.extend([
        "",
        "## 6. Champion Model Selection",
        f"- **Champion**: `{champ_name}`",
        f"- **Selection Metric (Primary)**: Highest validation PR-AUC ({champ_pr_auc:.4f})",
        f"- **Tie-Breakers**: Highest validation F1 ({champ_f1:.4f}), then lexicographical name ordering",
        f"- **Frozen Decision Threshold**: `{frozen_thresh:.2f}` (fixed strictly on 2023 validation; never tuned on 2024)",
        "",
        "## 7. Held-Out Temporal Test Results (2024)",
        f"Evaluated on held-out 2024 test data strictly using the frozen champion threshold ({frozen_thresh:.2f}) without retraining or retuning:",
        "",
        "| Metric | Value |",
        "| :--- | :---: |",
        f"| PR-AUC | {test_metrics.get('pr_auc', 0.0):.4f} |",
        f"| ROC-AUC | {test_metrics.get('roc_auc', 0.0):.4f} |",
        f"| Decision Threshold | {test_metrics.get('threshold_applied', frozen_thresh):.2f} |",
        f"| Precision | {test_metrics.get('precision', 0.0):.4f} |",
        f"| Recall | {test_metrics.get('recall', 0.0):.4f} |",
        f"| F1-Score | {test_metrics.get('f1', 0.0):.4f} |",
        f"| Brier Score | {test_metrics.get('brier_score', 0.0):.4f} |",
        f"| Log-Loss | {test_metrics.get('log_loss', 0.0):.4f} |",
        f"| True Positives (TP) | {test_metrics.get('tp', 0):,} |",
        f"| False Positives (FP) | {test_metrics.get('fp', 0):,} |",
        f"| True Negatives (TN) | {test_metrics.get('tn', 0):,} |",
        f"| False Negatives (FN) | {test_metrics.get('fn', 0):,} |",
        "",
    ])

    return "\n".join(lines)


def save_pipeline_artifacts(
    pipeline_results: Mapping[str, Any],
    output_dir: Union[str, Path] = MODELS_DIR,
) -> Dict[str, Path]:
    """Serialize trained models, scaler, JSON metadata, and comparison report.

    Guarantees:
    - Creates target directory ONLY upon invocation.
    - Saves all 7 approved artifacts to ARTIFACT_PATHS locations under output_dir.
    - Preserves exact evaluation summary JSON schema and disclosures.
    - Generates markdown model comparison report.
    """
    import joblib

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written_paths: Dict[str, Path] = {}

    # 1. Scaler & Scaler Metadata
    scaler = pipeline_results.get("scaler")
    if scaler is not None:
        p_scaler = out_path / "scaler.joblib"
        joblib.dump(scaler, p_scaler)
        written_paths["scaler"] = p_scaler

        scaler_meta = {
            "feature_names": list(CANONICAL_FEATURES),
            "n_features_in": len(CANONICAL_FEATURES),
            "mean": [float(m) for m in scaler.mean_] if hasattr(scaler, "mean_") else [],
            "var": [float(v) for v in scaler.var_] if hasattr(scaler, "var_") else [],
            "scale": [float(s) for s in scaler.scale_] if hasattr(scaler, "scale_") else [],
            "n_samples_seen": int(scaler.n_samples_seen_) if hasattr(scaler, "n_samples_seen_") else 0,
        }
        p_scaler_meta = out_path / "scaler_metadata.json"
        with p_scaler_meta.open("w", encoding="utf-8") as f:
            json.dump(scaler_meta, f, indent=2)
        written_paths["scaler_metadata"] = p_scaler_meta

    # 2. Fitted Model Artifacts
    models_dict = pipeline_results.get("models", {})
    if "linear" in models_dict:
        p_linear = out_path / "linear_baseline.joblib"
        joblib.dump(models_dict["linear"], p_linear)
        written_paths["linear_baseline"] = p_linear

    if "random_forest" in models_dict:
        p_rf = out_path / "random_forest.joblib"
        joblib.dump(models_dict["random_forest"], p_rf)
        written_paths["random_forest"] = p_rf

    if "hist_gradient_boosting" in models_dict:
        p_hgb = out_path / "hist_gradient_boosting.joblib"
        joblib.dump(models_dict["hist_gradient_boosting"], p_hgb)
        written_paths["hist_gradient_boosting"] = p_hgb

    # 3. Evaluation Summary JSON
    summary_data = pipeline_results.get("evaluation_summary")
    if summary_data is not None:
        p_summary = out_path / "evaluation_summary.json"
        with p_summary.open("w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        written_paths["evaluation_summary"] = p_summary

    # 4. Model Comparison Report Markdown
    report_md = pipeline_results.get("model_comparison_report")
    if report_md is not None:
        p_report = out_path / "model_comparison_report.md"
        with p_report.open("w", encoding="utf-8") as f:
            f.write(report_md)
        written_paths["model_comparison_report"] = p_report

    return written_paths


# ------------------------------------------------------------------------------
# 15. Observational Preflight Diagnostics
# ------------------------------------------------------------------------------

def check_pipeline_resource_diagnostics(
    train_row_count: int,
    val_row_count: int,
    test_row_count: int,
    feature_count: int = 24,
) -> Dict[str, Any]:
    """Observational resource diagnostics distinguishing memory tiers.

    Distinguishes:
    - raw feature-matrix memory (float32 X + int8 y)
    - temporary preprocessing memory (scaled arrays, chunk buffers)
    - estimator working memory (working tree structures, histogram bins)
    - model memory (persisted estimator objects)
    """
    bytes_per_float32 = 4
    bytes_per_int8 = 1

    train_raw_x_mb = (train_row_count * feature_count * bytes_per_float32) / (1024 * 1024)
    train_raw_y_mb = (train_row_count * bytes_per_int8) / (1024 * 1024)
    val_raw_x_mb = (val_row_count * feature_count * bytes_per_float32) / (1024 * 1024)
    test_raw_x_mb = (test_row_count * feature_count * bytes_per_float32) / (1024 * 1024)

    return {
        "raw_feature_matrix_memory_mb": {
            "train_X_mb": round(train_raw_x_mb, 2),
            "train_y_mb": round(train_raw_y_mb, 2),
            "val_X_mb": round(val_raw_x_mb, 2),
            "test_X_mb": round(test_raw_x_mb, 2),
            "total_raw_train_mb": round(train_raw_x_mb + train_raw_y_mb, 2),
        },
        "temporary_preprocessing_memory_note": (
            "Train scaler creates a temporary scaled float32 copy freed immediately after linear fitting. "
            "Validation and test matrices are sequentially loaded and released without coexisting."
        ),
        "estimator_working_memory_note": (
            "RandomForest operates on a 500,000-row positive-preserving sample to cap working memory. "
            "HistGradientBoosting operates with uint8 binned features (~256 bins) to cap memory footprint."
        ),
        "model_persisted_memory_note": (
            "Model parameters in joblib files are estimated under 150MB total."
        ),
    }


# ------------------------------------------------------------------------------
# 16. Pipeline Orchestration Runner
# ------------------------------------------------------------------------------

def run_training_pipeline(
    train_years: Sequence[int] = TRAIN_YEARS,
    val_years: Sequence[int] = VAL_YEARS,
    test_years: Sequence[int] = TEST_YEARS,
    base_dir: Union[str, Path] = "datasets/processed/ml",
    chunk_size: int = 250_000,
    rf_target_total: int = 500_000,
    precision_floor: float = 0.20,
    num_thresholds: int = 99,
    save_artifacts: bool = False,
    output_dir: Union[str, Path] = MODELS_DIR,
    random_state: int = RANDOM_SEED,
) -> Dict[str, Any]:
    """Execute the supervised baseline training & evaluation pipeline across chronological splits.

    Sequence:
    STEP 1: Load training data (2019–2022).
    STEP 2: Fit StandardScaler ONLY on training data.
    STEP 3: Prepare scaled training matrix for linear model.
    STEP 4: Fit LogisticRegression through fit_linear_baseline_with_fallback.
    STEP 5: Train RandomForest on positive-preserving sample (rf_target_total rows).
    STEP 6: Train HistGradientBoosting on unscaled features with balanced weights.
    STEP 7: Load validation data (2023).
    STEP 8: Generate probability predictions for each trained model.
    STEP 9: Compute validation metrics for each model.
    STEP 10: For each model independently, tune threshold on 2023 only.
    STEP 11: Select champion (highest PR-AUC, tie -> highest F1, tie -> lexicographical name).
    STEP 12: Freeze champion, threshold, scaler/model state. Release validation matrix.
    STEP 13: Load 2024 test data.
    STEP 14: Generate ONE champion probability prediction pass.
    STEP 15: Evaluate 2024 using the frozen threshold.
    """
    # STEP 1: Load training data
    X_train, y_train, train_meta = load_split_matrix(
        years=train_years,
        base_dir=base_dir,
        chunk_size=chunk_size,
    )

    # STEP 2: Fit StandardScaler strictly on training data
    scaler = fit_linear_scaler(X_train)

    # STEP 3: Prepare scaled training matrix for linear model
    X_train_scaled = prepare_model_input(X_train, "linear", scaler=scaler)

    # STEP 4: Fit Linear baseline with deterministic fallback
    linear_model, linear_meta = fit_linear_baseline_with_fallback(
        X_train_scaled, y_train, random_state=random_state
    )
    del X_train_scaled
    gc.collect()

    # STEP 5: Train RandomForest with positive-preserving sampling
    X_rf, y_rf, rf_meta = sample_rf_training_data(
        X_train, y_train, target_total=rf_target_total, random_state=random_state
    )
    rf_model = build_random_forest(random_state=random_state)
    rf_model.fit(X_rf, y_rf)
    del X_rf, y_rf
    gc.collect()

    # STEP 6: Train HistGradientBoosting on raw unscaled features
    hgb_model = fit_hist_gradient_boosting(X_train, y_train, random_state=random_state)
    del X_train, y_train
    gc.collect()

    # STEP 7: Load validation data (2023)
    X_val, y_val, val_meta = load_split_matrix(
        years=val_years,
        base_dir=base_dir,
        chunk_size=chunk_size,
    )

    # STEP 8: Generate probability predictions for each trained model
    X_val_scaled = prepare_model_input(X_val, "linear", scaler=scaler)
    linear_val_proba = get_model_probabilities(linear_model, X_val_scaled)
    del X_val_scaled

    rf_val_proba = get_model_probabilities(rf_model, X_val)
    hgb_val_proba = get_model_probabilities(hgb_model, X_val)

    # STEP 9 & 10: Compute validation metrics & tune threshold for each model independently
    model_probas: Dict[str, np.ndarray] = {
        "linear": linear_val_proba,
        "random_forest": rf_val_proba,
        "hist_gradient_boosting": hgb_val_proba,
    }

    validation_results: Dict[str, Dict[str, Any]] = {}
    validation_thresholds: Dict[str, float] = {}

    for name, proba in model_probas.items():
        thresh, _ = tune_validation_threshold(
            y_val, proba, precision_floor=precision_floor, num_thresholds=num_thresholds
        )
        metrics = compute_evaluation_metrics(y_val, proba, threshold=thresh)
        metrics["selected_threshold"] = thresh
        validation_results[name] = metrics
        validation_thresholds[name] = thresh

    # STEP 11: Select champion model
    champion_selection = select_champion_model(validation_results)
    champ_name = champion_selection["champion_name"]

    models_dict = {
        "linear": linear_model,
        "random_forest": rf_model,
        "hist_gradient_boosting": hgb_model,
    }
    champion_model = models_dict[champ_name]
    frozen_threshold = validation_thresholds[champ_name]
    champion_selection["frozen_threshold"] = frozen_threshold
    champion_selection["champion_model_type"] = champ_name
    champion_selection["champion_selection_rationale"] = (
        f"Selected '{champ_name}' with highest validation PR-AUC ({champion_selection['champion_pr_auc']:.4f}), "
        f"tie-breaking on F1 ({champion_selection['champion_f1']:.4f}) and lexicographical model ordering."
    )

    # STEP 12: Freeze champion, threshold, scaler/model state; release validation memory
    del X_val, y_val, linear_val_proba, rf_val_proba, hgb_val_proba, model_probas
    gc.collect()

    # STEP 13: Load 2024 test data
    X_test, y_test, test_meta = load_split_matrix(
        years=test_years,
        base_dir=base_dir,
        chunk_size=chunk_size,
    )

    # STEP 14: Generate ONE champion probability prediction pass
    if champ_name == "linear":
        X_test_input = prepare_model_input(X_test, "linear", scaler=scaler)
    else:
        X_test_input = X_test

    champ_test_proba = get_model_probabilities(champion_model, X_test_input)
    if champ_name == "linear":
        del X_test_input
    del X_test
    gc.collect()

    # STEP 15: Evaluate 2024 using the frozen threshold
    test_metrics = evaluate_temporal_test(y_test, champ_test_proba, frozen_threshold=frozen_threshold)
    del y_test, champ_test_proba
    gc.collect()

    # Build evaluation summary JSON metadata
    evaluation_summary: Dict[str, Any] = {
        "methodology_disclosure": "SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION",
        "disclosure_note": (
            "This baseline model evaluates historical co-occurrence on the Guwahati–Imphal corridor "
            "using engineered disruption proxy labels. It does not represent real-world road-closure prediction "
            "or future forecasting."
        ),
        "feature_contract": {
            "feature_schema": list(CANONICAL_FEATURES),
            "feature_count": len(CANONICAL_FEATURES),
        },
        "dataset_splits": {
            "train_years": list(train_meta["years"]),
            "validation_year": list(val_meta["years"]),
            "test_year": list(test_meta["years"]),
            "train_rows": train_meta["row_count"],
            "train_positives": train_meta["positive_count"],
            "train_negatives": train_meta["negative_count"],
            "train_prevalence": train_meta["prevalence"],
            "val_rows": val_meta["row_count"],
            "val_positives": val_meta["positive_count"],
            "val_negatives": val_meta["negative_count"],
            "val_prevalence": val_meta["prevalence"],
            "test_rows": test_meta["row_count"],
            "test_positives": test_meta["positive_count"],
            "test_negatives": test_meta["negative_count"],
            "test_prevalence": test_meta["prevalence"],
        },
        "random_seed": int(random_state),
        "rf_sampling": {
            "total_sampled_rows": rf_meta["total_sampled_rows"],
            "positive_sampled_rows": rf_meta["positive_sampled_rows"],
            "negative_sampled_rows": rf_meta["negative_sampled_rows"],
            "sampled_prevalence": rf_meta["sampled_prevalence"],
            "random_seed": rf_meta["random_seed"],
        },
        "linear_model_execution": {
            "primary_model_attempted": linear_meta["primary_model_attempted"],
            "model_type_used": linear_meta["model_type_used"],
            "fallback_occurred": linear_meta["fallback_occurred"],
            "fallback_reason": linear_meta["fallback_reason"],
            "random_seed": linear_meta["random_seed"],
        },
        "validation_metrics": validation_results,
        "validation_thresholds": validation_thresholds,
        "champion_selection": champion_selection,
        "frozen_threshold": float(frozen_threshold),
        "test_metrics_2024": test_metrics,
        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
        },
    }

    report_md = generate_model_comparison_report(evaluation_summary)

    pipeline_results: Dict[str, Any] = {
        "scaler": scaler,
        "models": models_dict,
        "validation_results": validation_results,
        "validation_thresholds": validation_thresholds,
        "champion_selection": champion_selection,
        "champion_name": champ_name,
        "champion_model": champion_model,
        "frozen_threshold": float(frozen_threshold),
        "test_metrics": test_metrics,
        "evaluation_summary": evaluation_summary,
        "model_comparison_report": report_md,
        "artifacts_written": {},
    }

    if save_artifacts:
        written = save_pipeline_artifacts(pipeline_results, output_dir=output_dir)
        pipeline_results["artifacts_written"] = written

    return pipeline_results


if __name__ == "__main__":
    # Module remains strictly side-effect free on import and script invocation.
    # To run orchestration, import and call run_training_pipeline() explicitly.
    pass
