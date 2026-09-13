"""SETU_AI — Checkpoint 19: Supervised Baseline Model Training & Evaluation Test Suite.

Verifies the mathematical, schema, temporal, and methodological contracts for training
and evaluating baseline machine learning models on the Guwahati–Imphal road disruption
corridor dataset (2019–2024).

Enforces the 11 approved Checkpoint 19 contracts:
1. Exact 24-Feature Schema (deterministic names and order)
2. WMO Weather Code Encoding (canonical mapping from src.data.weather.weather_severity)
3. Chronological Splits (Train 2019–2022, Val 2023, Test 2024)
4. Target and Leakage Isolation (disruption_proxy target, zero leakage columns)
5. Linear Scaler Contract (StandardScaler fit ONLY on training data)
6. Model-Specific Preprocessing (StandardScaler for linear; raw features for trees)
7. Random Forest Sampling Contract (deterministic positive-preserving sample to 500k)
8. Validation Threshold Tuning (precision floor >= 0.20, F1 maximization, tie breaking)
9. Evaluation Metric Contract (PR-AUC, ROC-AUC, P, R, F1, Brier, Log-Loss, Confusion Matrix)
10. Temporal Evaluation Contract (2024 evaluated with frozen validation threshold)
11. Reproducibility (RANDOM_SEED = 42 across all components)

All unit tests use lightweight synthetic data; no 2.68GB datasets or heavy models are loaded.
Uses Python standard-library unittest to maintain zero-dependency test runner compatibility
within the Python 3.10.9 + scikit-learn 1.6.1 environment.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple
import unittest

import importlib.util
from pathlib import Path

# Load canonical WMO_CODE_SEVERITY directly from file to avoid triggering optional package init dependencies
def _load_wmo_code_severity() -> Dict[int, float]:
    ws_path = Path(__file__).resolve().parent.parent / "src" / "data" / "weather" / "weather_severity.py"
    spec = importlib.util.spec_from_file_location("weather_severity_direct", ws_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load weather_severity from {ws_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.WMO_CODE_SEVERITY

WMO_CODE_SEVERITY = _load_wmo_code_severity()

# Target training module (Checkpoint 19 implementation gate)
try:
    import src.ml.train_models as tm
except ImportError:
    tm = None


CANONICAL_24_FEATURES: List[str] = [
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

REQUIRED_METRIC_KEYS = {
    "pr_auc",
    "roc_auc",
    "precision",
    "recall",
    "f1",
    "brier_score",
    "log_loss",
    "tn",
    "fp",
    "fn",
    "tp",
}


class TestMLTrainingContracts(unittest.TestCase):
    """Test suite enforcing the 11 approved Checkpoint 19 training and evaluation contracts."""

    def _require_tm(self):
        """Enforces that src.ml.train_models is implemented."""
        if tm is None:
            self.fail("src.ml.train_models is not implemented yet (Checkpoint 19 Implementation Gate)")
        return tm

    # --------------------------------------------------------------------------
    # 1. Exact 24-Feature Schema
    # --------------------------------------------------------------------------

    def test_01_canonical_feature_count_and_order(self):
        """Verify that the module exposes exactly 24 canonical features in deterministic order."""
        mod = self._require_tm()
        self.assertTrue(hasattr(mod, "CANONICAL_FEATURES"), "Module must expose CANONICAL_FEATURES")
        self.assertEqual(
            len(mod.CANONICAL_FEATURES),
            24,
            f"Expected exactly 24 features, got {len(mod.CANONICAL_FEATURES)}",
        )
        self.assertEqual(
            mod.CANONICAL_FEATURES,
            CANONICAL_24_FEATURES,
            "CANONICAL_FEATURES does not match the approved 24-feature schema and order",
        )

    def test_02_feature_extraction_from_record(self):
        """Verify that extract_features extracts exactly the 24 values in canonical order."""
        mod = self._require_tm()
        record = {
            "segment_id": "SEG-001",
            "date": "2023-06-15",
            "month_sin": 0.5,
            "month_cos": -0.866,
            "dow_sin": 0.974,
            "dow_cos": -0.222,
            "latitude": 26.14,
            "longitude": 91.73,
            "elevation_m": 55.0,
            "road_type_rank": 2,
            "surface_paved": 1,
            "lanes": 4,
            "connectivity_degree": 6,
            "accessibility_score": 0.85,
            "weather_point_dist_km": 3.2,
            "precipitation_mm": 12.5,
            "rain_mm": 12.0,
            "precipitation_hours": 4.0,
            "temperature_c": 28.5,
            "temperature_max_c": 32.0,
            "temperature_min_c": 25.0,
            "temp_range_c": 7.0,
            "wind_speed_kmh": 15.0,
            "wind_gust_kmh": 25.0,
            "weather_code": 65.0,
            "weather_severity_daily": 0.45,
            "disruption_score_continuous": 0.78,  # leakage
            "disruption_proxy": 1,                # target
            "risk_score": 68.5,                   # leakage
        }

        vec = mod.extract_feature_vector(record)
        self.assertEqual(len(vec), 24)
        self.assertIsInstance(vec, (list, tuple))
        for i, col in enumerate(CANONICAL_24_FEATURES):
            expected_val = float(record[col])
            self.assertTrue(
                math.isclose(float(vec[i]), expected_val, rel_tol=1e-5),
                f"Feature {col} at index {i} mismatch: got {vec[i]}, expected {expected_val}",
            )

    # --------------------------------------------------------------------------
    # 2. Canonical WMO Encoding
    # --------------------------------------------------------------------------

    def test_03_canonical_wmo_code_severity_definition(self):
        """Verify repository's canonical WMO_CODE_SEVERITY exists and covers key hazard codes in [0.0, 1.0]."""
        self.assertIsInstance(WMO_CODE_SEVERITY, dict)
        self.assertGreater(len(WMO_CODE_SEVERITY), 0)

        for code, sev in WMO_CODE_SEVERITY.items():
            self.assertIsInstance(code, int, f"WMO code {code} must be an integer")
            self.assertTrue(0.0 <= sev <= 1.0, f"WMO severity {sev} for code {code} out of bounds [0.0, 1.0]")

        self.assertEqual(WMO_CODE_SEVERITY[0], 0.00)
        self.assertEqual(WMO_CODE_SEVERITY[65], 0.80)
        self.assertEqual(WMO_CODE_SEVERITY[95], 0.80)
        self.assertEqual(WMO_CODE_SEVERITY[99], 1.00)

    def test_04_wmo_encoding_function_uses_canonical_mapping(self):
        """Verify that encode_weather_code uses WMO_CODE_SEVERITY without defining a second divergent mapping."""
        mod = self._require_tm()
        self.assertTrue(hasattr(mod, "encode_weather_code"), "Module must provide encode_weather_code")

        self.assertAlmostEqual(mod.encode_weather_code(0), 0.00, places=5)
        self.assertAlmostEqual(mod.encode_weather_code(61), 0.30, places=5)
        self.assertAlmostEqual(mod.encode_weather_code(65), 0.80, places=5)
        self.assertAlmostEqual(mod.encode_weather_code(95), 0.80, places=5)
        self.assertAlmostEqual(mod.encode_weather_code(99), 1.00, places=5)

        fallback_val = mod.encode_weather_code(9999)
        self.assertTrue(0.0 <= fallback_val <= 1.0)
        self.assertEqual(fallback_val, 0.0)

    # --------------------------------------------------------------------------
    # 3. Chronological Splits
    # --------------------------------------------------------------------------

    def test_05_chronological_split_definitions(self):
        """Verify train = 2019-2022, val = 2023, test = 2024 with zero cross-year leakage."""
        mod = self._require_tm()
        self.assertTrue(hasattr(mod, "TRAIN_YEARS"), "Module must define TRAIN_YEARS")
        self.assertTrue(hasattr(mod, "VAL_YEARS"), "Module must define VAL_YEARS")
        self.assertTrue(hasattr(mod, "TEST_YEARS"), "Module must define TEST_YEARS")

        train_set = set(mod.TRAIN_YEARS)
        val_set = set(mod.VAL_YEARS)
        test_set = set(mod.TEST_YEARS)

        self.assertEqual(train_set, {2019, 2020, 2021, 2022})
        self.assertEqual(val_set, {2023})
        self.assertEqual(test_set, {2024})

        self.assertTrue(train_set.isdisjoint(val_set), "Train and Val years overlap!")
        self.assertTrue(train_set.isdisjoint(test_set), "Train and Test years overlap!")
        self.assertTrue(val_set.isdisjoint(test_set), "Val and Test years overlap!")

    def test_06_chronological_split_assignment(self):
        """Verify split categorization function assigns dates strictly by year."""
        mod = self._require_tm()
        self.assertEqual(mod.get_split_name(2019), "train")
        self.assertEqual(mod.get_split_name(2022), "train")
        self.assertEqual(mod.get_split_name(2023), "val")
        self.assertEqual(mod.get_split_name(2024), "test")

        with self.assertRaises(ValueError):
            mod.get_split_name(2018)

        with self.assertRaises(ValueError):
            mod.get_split_name(2025)

    # --------------------------------------------------------------------------
    # 4. Target & Leakage Isolation
    # --------------------------------------------------------------------------

    def test_07_target_and_leakage_isolation(self):
        """Verify disruption_proxy is the target and all forbidden columns are excluded from features."""
        mod = self._require_tm()
        self.assertTrue(hasattr(mod, "TARGET_COLUMN"), "Module must define TARGET_COLUMN")
        self.assertEqual(mod.TARGET_COLUMN, "disruption_proxy")

        feature_set = set(mod.CANONICAL_FEATURES)
        for forbidden in FORBIDDEN_LEAKAGE_COLUMNS:
            self.assertNotIn(
                forbidden,
                feature_set,
                f"CRITICAL LEAKAGE: Forbidden column '{forbidden}' found in CANONICAL_FEATURES!",
            )

    # --------------------------------------------------------------------------
    # 5. Linear Scaler Contract (Train-Only Fitting)
    # --------------------------------------------------------------------------

    def test_08_linear_scaler_train_only_contract(self):
        """Verify StandardScaler is fit ONLY on training data, never influenced by val/test."""
        mod = self._require_tm()
        import numpy as np

        rng = np.random.RandomState(42)
        X_train = rng.normal(loc=10.0, scale=2.0, size=(1000, 24))
        X_val = rng.normal(loc=100.0, scale=50.0, size=(500, 24))

        scaler = mod.fit_linear_scaler(X_train)
        self.assertIsNotNone(scaler)

        np.testing.assert_allclose(scaler.mean_, np.mean(X_train, axis=0), rtol=1e-4)
        np.testing.assert_allclose(scaler.scale_, np.std(X_train, axis=0), rtol=1e-4)

        mean_before = np.copy(scaler.mean_)
        _ = scaler.transform(X_val)
        np.testing.assert_array_equal(scaler.mean_, mean_before)

    # --------------------------------------------------------------------------
    # 6. Model-Specific Preprocessing Routing
    # --------------------------------------------------------------------------

    def test_09_model_specific_preprocessing_routing(self):
        """Verify linear model receives scaled features while tree models receive raw unscaled features."""
        mod = self._require_tm()
        import numpy as np

        rng = np.random.RandomState(42)
        X_raw = rng.uniform(low=5.0, high=100.0, size=(50, 24))

        scaler = mod.fit_linear_scaler(X_raw)

        # 1. Linear model input must be standardized
        X_linear = mod.prepare_model_input(X_raw, model_type="linear", scaler=scaler)
        self.assertFalse(np.allclose(X_linear, X_raw), "Linear model must receive standardized features!")
        np.testing.assert_allclose(np.mean(X_linear, axis=0), 0.0, atol=1e-5)

        # 2. Random Forest must receive raw unscaled features
        X_rf = mod.prepare_model_input(X_raw, model_type="random_forest", scaler=scaler)
        np.testing.assert_array_equal(X_rf, X_raw)

        # 3. HistGradientBoosting must receive raw unscaled features
        X_hgb = mod.prepare_model_input(X_raw, model_type="hist_gradient_boosting", scaler=scaler)
        np.testing.assert_array_equal(X_hgb, X_raw)

    # --------------------------------------------------------------------------
    # 7. Random Forest Sampling Contract
    # --------------------------------------------------------------------------

    def test_10_random_forest_sampler_contract(self):
        """Verify RF sampler retains 100% positive rows, fills remaining with negatives, and returns exact count."""
        mod = self._require_tm()
        import numpy as np

        num_pos = 30
        num_neg = 2000
        total_rows = num_pos + num_neg

        X = np.arange(total_rows * 24).reshape((total_rows, 24))
        y = np.zeros(total_rows, dtype=int)
        y[:num_pos] = 1

        target_sample_size = 200
        X_sampled, y_sampled, meta = mod.sample_rf_training_data(
            X, y, target_total=target_sample_size, random_state=42
        )

        self.assertEqual(len(X_sampled), target_sample_size)
        self.assertEqual(len(y_sampled), target_sample_size)

        sampled_pos_count = int(np.sum(y_sampled == 1))
        self.assertEqual(sampled_pos_count, num_pos)

        sampled_neg_count = int(np.sum(y_sampled == 0))
        self.assertEqual(sampled_neg_count, target_sample_size - num_pos)

        self.assertEqual(meta["total_sampled_rows"], target_sample_size)
        self.assertEqual(meta["positive_sampled_rows"], num_pos)
        self.assertEqual(meta["negative_sampled_rows"], target_sample_size - num_pos)
        self.assertTrue(math.isclose(meta["sampled_prevalence"], num_pos / target_sample_size, rel_tol=1e-4))
        self.assertEqual(meta["random_seed"], 42)

    def test_11_random_forest_sampler_determinism_and_seed(self):
        """Verify sampler produces identical subsets with seed=42 and changes with different seed."""
        mod = self._require_tm()
        import numpy as np

        num_pos = 20
        num_neg = 500
        total = num_pos + num_neg
        X = np.arange(total * 24).reshape((total, 24))
        y = np.zeros(total, dtype=int)
        y[:num_pos] = 1

        X1, y1, _ = mod.sample_rf_training_data(X, y, target_total=100, random_state=42)
        X2, y2, _ = mod.sample_rf_training_data(X, y, target_total=100, random_state=42)
        X3, y3, _ = mod.sample_rf_training_data(X, y, target_total=100, random_state=99)

        np.testing.assert_array_equal(X1, X2)
        np.testing.assert_array_equal(y1, y2)
        self.assertFalse(np.array_equal(X1, X3))

    # --------------------------------------------------------------------------
    # 8. Validation Threshold Tuning
    # --------------------------------------------------------------------------

    def test_12_threshold_tuning_logic_and_precision_floor(self):
        """Verify threshold sweep respects precision floor >= 0.20 and selects optimal F1."""
        mod = self._require_tm()
        import numpy as np

        y_true = np.zeros(500, dtype=int)
        y_true[:50] = 1

        rng = np.random.RandomState(42)
        y_proba = np.zeros(500, dtype=float)
        y_proba[:50] = rng.uniform(0.35, 0.95, size=50)
        y_proba[50:] = rng.uniform(0.01, 0.45, size=450)

        best_thresh, table = mod.tune_validation_threshold(
            y_true, y_proba, precision_floor=0.20, num_thresholds=100
        )

        self.assertTrue(0.01 <= best_thresh <= 0.99)
        self.assertIsInstance(table, (list, dict))

        preds = (y_proba >= best_thresh).astype(int)
        tp = np.sum((preds == 1) & (y_true == 1))
        fp = np.sum((preds == 1) & (y_true == 0))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        self.assertGreaterEqual(
            prec, 0.20, f"Selected threshold {best_thresh} violated precision floor: precision = {prec:.3f}"
        )

    def test_13_threshold_tuning_deterministic_tie_breaking(self):
        """Verify deterministic tie handling when multiple thresholds have identical F1."""
        mod = self._require_tm()
        import numpy as np

        y_true = np.array([0, 0, 0, 1, 1, 1])
        y_proba = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])

        thresh1, _ = mod.tune_validation_threshold(y_true, y_proba, precision_floor=0.20)
        thresh2, _ = mod.tune_validation_threshold(y_true, y_proba, precision_floor=0.20)

        self.assertEqual(thresh1, thresh2)
        self.assertTrue(0.3 < thresh1 <= 0.7)

    # --------------------------------------------------------------------------
    # 9. Evaluation Metric Contract
    # --------------------------------------------------------------------------

    def test_14_metric_contract_schema_and_ranges(self):
        """Verify compute_evaluation_metrics outputs all 11 required keys within valid ranges."""
        mod = self._require_tm()
        import numpy as np

        y_true = np.array([0, 0, 1, 1, 0, 1, 0, 0, 1, 0])
        y_proba = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7, 0.4, 0.15, 0.85, 0.05])
        threshold = 0.50

        metrics = mod.compute_evaluation_metrics(y_true, y_proba, threshold=threshold)

        self.assertIsInstance(metrics, dict)
        missing_keys = REQUIRED_METRIC_KEYS - set(metrics.keys())
        self.assertEqual(len(missing_keys), 0, f"Missing required metric keys: {missing_keys}")

        for key in ["pr_auc", "roc_auc", "precision", "recall", "f1", "brier_score"]:
            val = metrics[key]
            self.assertTrue(0.0 <= val <= 1.0, f"Metric {key}={val} out of bounds [0.0, 1.0]")

        self.assertGreaterEqual(metrics["log_loss"], 0.0)

        total_cm = metrics["tn"] + metrics["fp"] + metrics["fn"] + metrics["tp"]
        self.assertEqual(total_cm, len(y_true))

    # --------------------------------------------------------------------------
    # 10. Temporal Evaluation Contract (Frozen Validation Threshold)
    # --------------------------------------------------------------------------

    def test_15_temporal_evaluation_frozen_threshold_contract(self):
        """Verify 2024 test evaluation uses the exact frozen threshold from validation without re-tuning."""
        mod = self._require_tm()
        import numpy as np

        y_test = np.array([0, 0, 1, 1, 0, 1, 0, 1])
        y_test_proba = np.array([0.1, 0.25, 0.45, 0.85, 0.35, 0.65, 0.15, 0.75])

        frozen_val_threshold = 0.40

        test_metrics = mod.evaluate_temporal_test(
            y_true=y_test,
            y_proba=y_test_proba,
            frozen_threshold=frozen_val_threshold,
        )

        self.assertEqual(test_metrics["threshold_applied"], frozen_val_threshold)
        expected_tp = int(np.sum((y_test_proba >= frozen_val_threshold) & (y_test == 1)))
        self.assertEqual(test_metrics["tp"], expected_tp)

    # --------------------------------------------------------------------------
    # 11. Reproducibility Contract
    # --------------------------------------------------------------------------

    def test_16_reproducibility_contract(self):
        """Verify module defines and enforces RANDOM_SEED = 42 across training helpers."""
        mod = self._require_tm()
        self.assertTrue(hasattr(mod, "RANDOM_SEED"), "Module must export RANDOM_SEED")
        self.assertEqual(mod.RANDOM_SEED, 42)


if __name__ == "__main__":
    unittest.main()
