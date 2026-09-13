"""SETU_AI — Checkpoint 19: Training Orchestration Unit Test Suite.

Verifies the execution layer, partition loading, memory safety, model-specific
preprocessing, threshold tuning, champion selection, and artifact serialization
using lightweight synthetic fixtures.

Does NOT execute full training on the 17.5M-row dataset.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List
import unittest

import numpy as np

try:
    import src.ml.train_models as tm
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
except ImportError:
    tm = None
    StandardScaler = None
    LogisticRegression = None


def _create_synthetic_partition_csv(
    file_path: Path,
    year: int,
    num_rows: int = 15,
    positives: int = 3,
) -> None:
    """Create a lightweight synthetic CSV partition matching CP18 schema."""
    fieldnames = [
        "segment_id",
        "date",
        "year",
        "month",
        "day_of_week",
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
        "disruption_score_continuous",
        "disruption_proxy",
        "risk_score",
    ]

    rows = []
    for i in range(num_rows):
        is_pos = 1 if i < positives else 0
        rows.append({
            "segment_id": f"seg_{year}_{i}",
            "date": f"{year}-06-15",
            "year": str(year),
            "month": str((i % 12) + 1),
            "day_of_week": str(i % 7),
            "latitude": f"{26.0 + i * 0.01:.4f}",
            "longitude": f"{91.5 + i * 0.01:.4f}",
            "elevation_m": "250.0",
            "road_type_rank": "2",
            "surface_paved": "1",
            "lanes": "2",
            "connectivity_degree": "3",
            "accessibility_score": "0.75",
            "weather_point_dist_km": "5.2",
            "precipitation_mm": f"{12.5 + i:.1f}",
            "rain_mm": f"{10.0 + i:.1f}",
            "precipitation_hours": "4",
            "temperature_c": "28.0",
            "temperature_max_c": "32.0",
            "temperature_min_c": "24.0",
            "temp_range_c": "8.0",
            "wind_speed_kmh": "15.0",
            "wind_gust_kmh": "25.0",
            "weather_code": "65",
            "weather_severity_daily": "0.80",
            "disruption_score_continuous": f"{0.75 if is_pos else 0.10:.2f}",
            "disruption_proxy": str(is_pos),
            "risk_score": f"{0.80 if is_pos else 0.20:.2f}",
        })

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestMLTrainingOrchestration(unittest.TestCase):
    """Test suite for ML training orchestration, loading, and serialization."""

    def setUp(self) -> None:
        if tm is None or StandardScaler is None or LogisticRegression is None:
            self.skipTest("scikit-learn or src.ml not available in this environment")
        self.temp_dir = tempfile.mkdtemp(prefix="setu_test_orch_")
        self.base_dir = Path(self.temp_dir) / "datasets" / "processed" / "ml"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_synthetic_partition_loading_shape_and_dtypes(self) -> None:
        """Verify load_split_matrix produces exact 24-feature float32 matrix and int8 vector."""
        p2019 = self.base_dir / "ml_dataset_2019.csv"
        _create_synthetic_partition_csv(p2019, 2019, num_rows=20, positives=5)

        X, y, meta = tm.load_split_matrix(2019, base_dir=self.base_dir, chunk_size=5)

        self.assertEqual(X.shape, (20, 24))
        self.assertEqual(y.shape, (20,))
        self.assertEqual(X.dtype, np.float32)
        self.assertEqual(y.dtype, np.int8)

        self.assertEqual(meta["row_count"], 20)
        self.assertEqual(meta["positive_count"], 5)
        self.assertEqual(meta["negative_count"], 15)
        self.assertEqual(meta["feature_count"], 24)
        self.assertEqual(meta["feature_names"], tm.CANONICAL_FEATURES)
        self.assertEqual(meta["years"], [2019])
        self.assertAlmostEqual(meta["prevalence"], 5 / 20)

    def test_02_chronological_year_sequencing_and_order_preservation(self) -> None:
        """Verify load_split_matrix loads multi-year partitions deterministically in chronological order."""
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2020.csv", 2020, num_rows=10, positives=2)
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2019.csv", 2019, num_rows=15, positives=3)

        # Pass in reverse order [2020, 2019]
        X, y, meta = tm.load_split_matrix([2020, 2019], base_dir=self.base_dir, chunk_size=8)

        self.assertEqual(meta["years"], [2019, 2020])
        self.assertEqual(meta["row_count"], 25)
        self.assertEqual(meta["positive_count"], 5)
        self.assertEqual(X.shape, (25, 24))
        self.assertEqual(len(y), 25)

    def test_03_malformed_record_error_context(self) -> None:
        """Verify malformed row raises ValueError with explicit partition and row context."""
        bad_csv = self.base_dir / "ml_dataset_2021.csv"
        with bad_csv.open("w", encoding="utf-8", newline="") as f:
            f.write("month,day_of_week,latitude,disruption_proxy\n")
            f.write("13,2,26.1,1\n")  # Month 13 is invalid

        with self.assertRaises(ValueError) as ctx:
            tm.load_split_matrix(2021, base_dir=self.base_dir)

        err_msg = str(ctx.exception)
        self.assertIn("2021", err_msg)
        self.assertIn("Malformed feature record", err_msg)

    def test_04_train_only_scaler_usage(self) -> None:
        """Verify StandardScaler fit strictly on training partition does not re-fit on validation."""
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2019.csv", 2019, num_rows=20, positives=4)
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2023.csv", 2023, num_rows=10, positives=2)

        X_train, _, _ = tm.load_split_matrix(2019, base_dir=self.base_dir)
        X_val, _, _ = tm.load_split_matrix(2023, base_dir=self.base_dir)

        scaler = tm.fit_linear_scaler(X_train)
        frozen_mean = np.copy(scaler.mean_)

        X_val_scaled = tm.prepare_model_input(X_val, "linear", scaler=scaler)

        # Scaler parameters must remain identical after transforming validation data
        np.testing.assert_array_equal(scaler.mean_, frozen_mean)
        self.assertEqual(X_val_scaled.shape, X_val.shape)

    def test_05_model_specific_preprocessing(self) -> None:
        """Verify model-specific input preparation contract for linear, RF, and HGB."""
        X_dummy = np.ones((5, 24), dtype=np.float32)
        scaler = StandardScaler().fit(X_dummy)

        X_linear = tm.prepare_model_input(X_dummy, "linear", scaler=scaler)
        X_rf = tm.prepare_model_input(X_dummy, "random_forest")
        X_hgb = tm.prepare_model_input(X_dummy, "hist_gradient_boosting")

        # Linear is centered (all 0.0)
        np.testing.assert_array_almost_equal(X_linear, np.zeros((5, 24)))
        # RF and HGB are unscaled raw arrays
        np.testing.assert_array_equal(X_rf, X_dummy)
        np.testing.assert_array_equal(X_hgb, X_dummy)

    def test_06_rf_sampling_integration(self) -> None:
        """Verify positive-preserving sampling integration retains 100% positives."""
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2019.csv", 2019, num_rows=50, positives=8)
        X_train, y_train, _ = tm.load_split_matrix(2019, base_dir=self.base_dir)

        X_rf, y_rf, rf_meta = tm.sample_rf_training_data(
            X_train, y_train, target_total=25, random_state=42
        )

        self.assertEqual(len(X_rf), 25)
        self.assertEqual(int(np.sum(y_rf == 1)), 8)
        self.assertEqual(int(np.sum(y_rf == 0)), 17)
        self.assertEqual(rf_meta["positive_sampled_rows"], 8)
        self.assertEqual(rf_meta["negative_sampled_rows"], 17)

    def test_07_validation_threshold_and_champion_selection_flow(self) -> None:
        """Verify threshold sweep tuning and deterministic champion selection."""
        val_results = {
            "linear": {
                "pr_auc": 0.45,
                "roc_auc": 0.82,
                "precision": 0.35,
                "recall": 0.60,
                "f1": 0.44,
                "selected_threshold": 0.30,
            },
            "random_forest": {
                "pr_auc": 0.62,
                "roc_auc": 0.89,
                "precision": 0.50,
                "recall": 0.70,
                "f1": 0.58,
                "selected_threshold": 0.35,
            },
            "hist_gradient_boosting": {
                "pr_auc": 0.60,
                "roc_auc": 0.88,
                "precision": 0.48,
                "recall": 0.68,
                "f1": 0.56,
                "selected_threshold": 0.32,
            },
        }

        champ = tm.select_champion_model(val_results)
        self.assertEqual(champ["champion_name"], "random_forest")
        self.assertEqual(champ["champion_pr_auc"], 0.62)
        self.assertEqual(champ["total_candidates_evaluated"], 3)

    def test_08_no_artifact_directory_on_import(self) -> None:
        """Verify importing or accessing src.ml.train_models does NOT create models/ directory."""
        repo_models = Path("models")
        # models/ should not exist prior to training run
        self.assertFalse(repo_models.exists(), "models/ should not exist prior to training run")

    def test_09_artifact_path_and_saving_behavior(self) -> None:
        """Verify save_pipeline_artifacts creates output directory and writes all 7 approved files."""
        out_dir = Path(self.temp_dir) / "test_models"
        self.assertFalse(out_dir.exists())

        dummy_scaler = StandardScaler()
        dummy_scaler.fit(np.zeros((10, 24)))

        from sklearn.linear_model import LogisticRegression
        dummy_model = LogisticRegression().fit(np.zeros((10, 24)), np.array([0, 1] * 5))

        mock_results = {
            "scaler": dummy_scaler,
            "models": {
                "linear": dummy_model,
                "random_forest": dummy_model,
                "hist_gradient_boosting": dummy_model,
            },
            "evaluation_summary": {
                "methodology_disclosure": "SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION",
                "random_seed": 42,
            },
            "model_comparison_report": "# Test Report",
        }

        written = tm.save_pipeline_artifacts(mock_results, output_dir=out_dir)

        self.assertTrue(out_dir.exists())
        self.assertEqual(len(written), 7)
        self.assertTrue((out_dir / "scaler.joblib").exists())
        self.assertTrue((out_dir / "scaler_metadata.json").exists())
        self.assertTrue((out_dir / "linear_baseline.joblib").exists())
        self.assertTrue((out_dir / "random_forest.joblib").exists())
        self.assertTrue((out_dir / "hist_gradient_boosting.joblib").exists())
        self.assertTrue((out_dir / "evaluation_summary.json").exists())
        self.assertTrue((out_dir / "model_comparison_report.md").exists())

    def test_10_end_to_end_tiny_pipeline_orchestration(self) -> None:
        """Verify run_training_pipeline executes Steps 1–15 seamlessly on synthetic data."""
        # Create synthetic partitions for train, val, test
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2019.csv", 2019, num_rows=20, positives=4)
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2020.csv", 2020, num_rows=20, positives=4)
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2023.csv", 2023, num_rows=20, positives=5)
        _create_synthetic_partition_csv(self.base_dir / "ml_dataset_2024.csv", 2024, num_rows=20, positives=5)

        out_dir = Path(self.temp_dir) / "pipeline_models"

        results = tm.run_training_pipeline(
            train_years=(2019, 2020),
            val_years=(2023,),
            test_years=(2024,),
            base_dir=self.base_dir,
            chunk_size=10,
            rf_target_total=15,  # 8 pos + 7 neg
            save_artifacts=True,
            output_dir=out_dir,
            random_state=42,
        )

        # Verify return structure
        self.assertIn("scaler", results)
        self.assertIn("models", results)
        self.assertIn("validation_results", results)
        self.assertIn("champion_selection", results)
        self.assertIn("champion_name", results)
        self.assertIn("frozen_threshold", results)
        self.assertIn("test_metrics", results)
        self.assertIn("evaluation_summary", results)
        self.assertIn("model_comparison_report", results)
        self.assertEqual(len(results["artifacts_written"]), 7)

        # Verify methodology disclosure in summary
        summary = results["evaluation_summary"]
        self.assertEqual(
            summary["methodology_disclosure"],
            "SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION",
        )
        self.assertEqual(summary["random_seed"], 42)
        self.assertEqual(summary["dataset_splits"]["train_rows"], 40)
        self.assertEqual(summary["dataset_splits"]["val_rows"], 20)
        self.assertEqual(summary["dataset_splits"]["test_rows"], 20)

        # Verify frozen threshold was applied to test
        self.assertEqual(results["test_metrics"]["threshold_applied"], results["frozen_threshold"])

        # Verify report content
        report_md = results["model_comparison_report"]
        self.assertIn("SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION", report_md)
        self.assertIn("Generalization Limitation", report_md)


if __name__ == "__main__":
    unittest.main()
