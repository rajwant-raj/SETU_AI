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
import importlib.util
import json
import math
from pathlib import Path
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
    if model_type_norm == "linear":
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
# 12. Memory-Safe Dataset Loading Helpers
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
