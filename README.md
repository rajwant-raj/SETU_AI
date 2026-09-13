# SETU-AI

SETU Intelligence Engine for resilient transportation and logistics in the North Eastern Region (NER).

> **Source of truth:** `SIH26002 — MERN Prototype Blueprint, Repository Benchmark & Implementation Plan.md`
>
> SETU-AI is the intelligence and data workstream supporting the broader SETU logistics platform. The AI repository supports the operational decision loop without becoming an ungrounded research project: deterministic intelligence comes first, measured machine learning comes later, and operators always retain approval authority.

---

## Product Role

SETU is an intelligent logistics decision-support system that converts real-time network conditions, weather, road accessibility, and field incidents into explainable route-risk assessments and actionable rerouting recommendations.

The operational decision loop is strictly human-in-the-loop:

```text
Incident
   ↓
Network Impact
   ↓
Risk Assessment
   ↓
Accessibility
   ↓
Route Alternatives
   ↓
Route Comparison / Optimization
   ↓
Explanation
   ↓
Human Approval
   ↓
Reroute
   ↓
Live Tracking
```

**Core operational principle:**
- **AI recommends.**
- **Backend orchestrates.**
- **Operator approves.**

The system does not perform autonomous rerouting. Recommendations remain in a pending state until an authorized human operator reviews the explainable factors and formally approves or rejects the route change.

---

## Blueprint Alignment

The SIH26002 blueprint defines three core development milestones:

1. Build the complete Incident → Affected Shipment → Risk Recalculation → Alternative Route → Explainable Recommendation → Operator Approval → Reroute loop using MERN.
2. Add live simulated vehicle tracking and weather.
3. Replace the initial heuristic disruption component with a measured ML disruption model.

`SETU_AI` is developed as a modular intelligence engine so that the data, network, risk, routing, and machine learning components are thoroughly verified, tested, and benchmarked before exposing them through a clean API boundary to the MERN backend.

---

## Current Status

### CHECKPOINTS 1–19 COMPLETE

1. **OSM / Overpass Road Acquisition:** Automated extraction of bounding-box road network for the Guwahati–Imphal corridor.
2. **OSM Normalization:** Canonical coordinate, highway-type, geometry, and attribute cleaning.
3. **Core Road Network:** Extraction and pruning of **8,007 major-road core segments** (motorway, trunk, primary, secondary).
4. **Elevation Enrichment:** Representative spatial sampling and elevation gradient attribution cached across all 8,007 core segments.
5. **Historical Weather Exploration:** Six annual historical partitions (2019–2024) across 40 representative weather points via Open-Meteo.
6. **Live Weather Module Scaffold:** Bounded live weather query scaffold with spatial grid caching.
7. **Risk Engine Specification:** Formal mathematical formulation and weighting schema for road segment risk scoring.
8. **Risk Engine Implementation:** Deterministic weighted scoring with explicit risk bands and comprehensive factor explanation.
9. **Network Impact Engine:** Incident-to-network spatial projection mapping incidents to potentially affected road segments.
10. **Accessibility Scoring:** Infrastructure accessibility proxy derived from road class, surface, lanes, and connectivity.
11. **ETA / Delay Engine:** Baseline and disruption-aware travel-time calculation with vehicle-class profiles and blocked-road handling.
12. **Thin Digital Twin Foundation:** In-memory, event-driven state container for fleet, shipment, and network what-if simulation.
13. **Route Candidate Generation:** Deterministic k-shortest paths and diverse corridor candidate generation over the road graph.
14. **Route Ranking:** Multi-criteria Pareto and weighted evaluation across distance, ETA, risk score, and road accessibility.
15. **Explanation:** Structured, human-readable justification detailing exactly why routes are selected or flagged.
16. **Incident → Reroute / Human Approval Loop:** End-to-end event chain from disruption detection to pending approval and operational commitment.
17. **Live Weather Integration into Risk:** Dynamic weather severity injection into the deterministic risk scoring engine.
18. **ML Dataset Construction:** Engineered feature store of **17,551,344 segment-day records** spanning 2019–2024 with deterministic disruption proxy.
19. **ML Training + Evaluation:** Full supervised training pipeline across Logistic Regression, Random Forest, and HistGradientBoosting, with frozen holdout evaluation.
20. **Decision-Layer Integration & ML Inference Service:** In-process inference engine exposing the Random Forest champion model at frozen threshold 0.30 over 24 canonical features, integrated as an opt-in auxiliary advisory in the reroute orchestration pipeline.

```text
CURRENT CHECKPOINT:
Checkpoint 20 — Decision-Layer Integration / ML Inference Service COMPLETE

NEXT APPROVED CHECKPOINT:
Checkpoint 21 — Real-Time Alert & Incident Ingestion System
```

---

## Deterministic Intelligence

The core of SETU-AI is a battle-tested deterministic intelligence foundation that operates without external API dependencies at runtime:

- **Risk Engine:** Deterministic weighted formula combining incident severity, weather severity, accessibility risk, road condition, network criticality, and current delay ratio into a normalized `[0, 100]` score. Categorizes segments into explicit risk bands (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) with zero runtime external API requirements.
- **Network Impact Engine:** Maps geolocated disruptions to potentially affected road segments via spatial radii and network proximity. Enforces the strict rule: *potentially affected ≠ confirmed closed*.
- **Accessibility Engine:** OSM-derived physical infrastructure accessibility proxy accounting for surface quality, lane counts, and geometric connectivity. This is an infrastructure metric, not observed real-time passability.
- **ETA / Delay Engine:** Computes baseline travel times and disruption-induced delays based on vehicle profiles (light truck, heavy truck, multi-axle), road speed limits, and terrain gradients. Explicitly flags blocked segments.
- **Thin Digital Twin:** In-memory, state-driven, event-based foundation providing isolated what-if scenario evaluation. Composes all intelligence engines deterministically with zero database, message broker (Kafka), cache (Redis), or microservice overhead.
- **Routing Engine:** Deterministic generation of diverse alternative routes, multi-criteria route ranking, and explainable trade-off comparison between shortest, safest, and fastest paths.
- **Incident → Reroute Loop:** Handles confirmed blockages and incident alerts by proposing alternatives that remain explicitly in a `PENDING_APPROVAL` state. The active operational route is never altered before explicit human sign-off.

---

## Dataset Foundation

### Study Area

The primary focus is the strategic **Guwahati → Imphal corridor** and surrounding North Eastern Region network, providing the terrain, elevation, and weather variety required for route-risk modeling.

### Road Network

- **Source:** OpenStreetMap acquired via the Overpass API.
- **Normalization:** Standardized coordinate representation, topological connectivity, and attribute cleaning.
- **Core Network:** **8,007 major-road segments** spanning four principal highway classifications:
  - `motorway`
  - `trunk`
  - `primary`
  - `secondary`
- Tertiary roads remain normalized and available in storage for future network expansion.

### Elevation

- Elevation data is sampled across representative regional points and cached locally.
- All 8,007 core segments are enriched with base elevation, gradient, and terrain difficulty indicators.

### Weather

- **Source:** Open-Meteo API.
- **Historical Cache:** Complete historical weather partitions covering **2019–2024** across 40 representative regional weather points.
- *Data Note:* 2025 historical data retrieval was halted because the upstream provider returned repeated HTTP 429 rate-limit responses; 2019–2024 provides 6 full calendar years (2,192 consecutive days).
- **Live Weather:** Operates via a separate forecast pipeline using spatial grid interpolation, completely decoupled from the historical training cache.

All raw and processed datasets remain local and are strictly ignored by Git.

---

## ML Dataset — Checkpoint 18

The Checkpoint 18 dataset is an exhaustive feature store containing **17,551,344 segment-day observations** across the 6-year period (2019–2024).

### Partition Table

| Partition | Calendar Days | Core Segments | Total Rows | Positives (`disruption_proxy=1`) | Prevalence |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **2019** (Train) | 365 | 8,007 | 2,922,555 | 68,432 | 2.3415% |
| **2020** (Train, Leap) | 366 | 8,007 | 2,930,562 | 72,118 | 2.4609% |
| **2021** (Train) | 365 | 8,007 | 2,922,555 | 69,871 | 2.3908% |
| **2022** (Train) | 365 | 8,007 | 2,922,555 | 71,200 | 2.4362% |
| **2023** (Validation) | 365 | 8,007 | 2,922,555 | 65,784 | 2.2509% |
| **2024** (Test) | 366 | 8,007 | 2,930,562 | 92,511 | 3.1568% |
| **Train Total (2019–2022)** | 1,461 | 8,007 | **11,698,227** | **281,621** | **2.4074%** |
| **Validation (2023)** | 365 | 8,007 | **2,922,555** | **65,784** | **2.2509%** |
| **Test (2024)** | 366 | 8,007 | **2,930,562** | **92,511** | **3.1568%** |
| **Global Total (2019–2024)** | 2,192 | 8,007 | **17,551,344** | **439,916** | **~2.5065%** |

Each row represents an observation of one road segment on one specific day. The target label `disruption_proxy` is a **deterministic engineered proxy**, not observed road-closure ground truth.

---

## ML Dataset Schema

The Checkpoint 18 dataset contains 30 canonical columns:

1. `segment_id` *(string)* — Unique identifier of the road segment
2. `date` *(string, YYYY-MM-DD)* — Observation calendar date
3. `year` *(int)* — Calendar year (2019–2024)
4. `month` *(int)* — Month of year (1–12)
5. `day` *(int)* — Day of month (1–31)
6. `day_of_week` *(int)* — Day of week (0=Monday, 6=Sunday)
7. `latitude` *(float)* — Segment midpoint latitude
8. `longitude` *(float)* — Segment midpoint longitude
9. `elevation_m` *(float)* — Segment elevation in meters
10. `road_type` *(string)* — OSM road classification
11. `road_type_rank` *(int)* — Ordinal ranking of highway class
12. `surface_paved` *(int, binary)* — 1 if paved, 0 otherwise
13. `lanes` *(int)* — Number of traffic lanes
14. `connectivity_degree` *(int)* — Local midpoint spatial-density proxy (spatial neighbor count), not exact graph topological degree
15. `accessibility_score` *(float, 0–1)* — OSM-derived infrastructure accessibility score
16. `nearest_weather_point_id` *(int)* — Identifier of nearest weather sampling point
17. `weather_point_dist_km` *(float)* — Distance to nearest weather station in km
18. `precipitation_mm` *(float)* — Total daily precipitation in mm
19. `rain_mm` *(float)* — Total daily liquid rainfall in mm
20. `precipitation_hours` *(float)* — Duration of precipitation in hours
21. `temperature_c` *(float)* — Mean daily temperature in °C
22. `temperature_max_c` *(float)* — Maximum daily temperature in °C
23. `temperature_min_c` *(float)* — Minimum daily temperature in °C
24. `temp_range_c` *(float)* — Daily temperature diurnal range in °C
25. `wind_speed_kmh` *(float)* — Maximum daily wind speed in km/h
26. `wind_gust_kmh` *(float)* — Maximum daily wind gust in km/h
27. `weather_code` *(int)* — WMO weather interpretation code
28. `weather_severity_daily` *(float, 0–1)* — Normalized daily weather severity score
29. `disruption_proxy` *(int, binary)* — Engineered target label (0 or 1)
30. `disruption_score_continuous` *(float, 0–1)* — Continuous multi-factor severity index

---

## Disruption Proxy

### Binary Disruption Rule

The binary target `disruption_proxy` is assigned `1` if **ANY** of the following conditions are satisfied:

- **Condition A (Disaster proximity):**
  $\text{nearest disaster distance} \le 10\text{ km} \quad \text{AND} \quad \text{disaster severity} \ge 0.50$
- **Condition B (Extreme precipitation):**
  $\text{precipitation\_mm} \ge 50.0\text{ mm}$
- **Condition C (Extreme wind gust):**
  $\text{wind\_gust\_kmh} \ge 65.0\text{ km/h}$
- **Condition D (Compounded vulnerability):**
  $\text{accessibility\_score} < 0.40 \quad \text{AND} \quad \text{precipitation\_mm} \ge 25.0\text{ mm}$

Otherwise:
$$\text{disruption\_proxy} = 0$$

### Continuous Disruption Score

$$\text{disruption\_score\_continuous} = \min\left(1.0, \; 0.40 \times \frac{\min(\text{precipitation\_mm}, 100)}{100} + 0.30 \times \frac{\min(\text{wind\_gust\_kmh}, 100)}{100} + 0.30 \times (1 - \text{accessibility\_score})\right)$$

### Provenance & Honesty Disclosure

- **Label provenance:** Derived
- **Sources:** OpenStreetMap + Open-Meteo + GDACS
- **Method:** `deterministic_threshold_rule_v0.1`
- **Critical notice:** The dataset does **not** contain observed real-world road closure ground truth. It is an engineered synthetic proxy representing heightened disruption vulnerability.

---

## Leakage Policy

To guarantee mathematical integrity, strict feature exclusion boundaries are enforced. The following fields are **strictly forbidden** from entering the ML feature vector:

- Identifiers and non-cyclical calendar markers: `segment_id`, `date`, `year`
- Target labels and proxies: `disruption_proxy`, `disruption_score_continuous`
- Disaster outcome fields: `nearest_disaster_dist_km`, `nearest_disaster_severity`
- Downstream operational and risk intelligence outcomes:
  - `risk_score`
  - `risk_band`
  - `risk_factors`
  - `network_impact_score`
  - `reroute_recommended`
  - `delay_factor`
  - `current_delay_ratio`
  - Operator approval and execution states

Future-day weather variables are never exposed to same-day features. Predictive models must never consume downstream operational decisions as predictive inputs.

---

## Checkpoint 19 — ML Training & Evaluation

> ### Methodology Disclosure
> **SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION**
>
> Checkpoint 19 evaluates whether supervised statistical models can accurately reproduce the deterministic disruption proxy rule from historical same-day environmental and infrastructural features.
>
> This pipeline is **NOT**:
> - Real-world road-closure prediction
> - True future-day forecasting
> - Physical road passability estimation
> - Unseen-road spatial generalization

---

## Feature Vector

The model feature matrix comprises exactly 24 features in canonical order:

```python
FEATURE_COLUMNS = [
    "month_sin",              # Cyclical month encoding: sin(2 * pi * month / 12)
    "month_cos",              # Cyclical month encoding: cos(2 * pi * month / 12)
    "dow_sin",                # Cyclical day-of-week encoding: sin(2 * pi * dow / 7)
    "dow_cos",                # Cyclical day-of-week encoding: cos(2 * pi * dow / 7)
    "latitude",               # Spatial coordinates
    "longitude",
    "elevation_m",            # Terrain elevation
    "road_type_rank",         # Ordinal highway classification rank
    "surface_paved",          # Binary paved indicator
    "lanes",                  # Lane count
    "connectivity_degree",    # Local spatial midpoint density proxy
    "accessibility_score",    # Infrastructure accessibility metric
    "weather_point_dist_km",  # Distance to weather observation point
    "precipitation_mm",       # Daily total precipitation
    "rain_mm",                # Daily liquid rain
    "precipitation_hours",    # Hours of rain
    "temperature_c",          # Mean temperature
    "temperature_max_c",      # Max temperature
    "temperature_min_c",      # Min temperature
    "temp_range_c",           # Diurnal temperature range
    "wind_speed_kmh",         # Max sustained wind speed
    "wind_gust_kmh",          # Max wind gust speed
    "weather_code",           # Canonical WMO code severity mapping
    "weather_severity_daily", # Daily weather severity score
]
```

---

## Temporal Split

Data is partitioned strictly across calendar years to prevent temporal data leakage. No random cross-year splitting is permitted:

- **Training:** 2019–2022 (11,698,227 rows, 4 full calendar years)
- **Validation:** 2023 (2,922,555 rows, 1 full calendar year)
- **Test Holdout:** 2024 (2,930,562 rows, 1 full leap year)

The 2024 test partition was kept completely untouched during model training, hyperparameter selection, and threshold tuning. The 2024 evaluation is a **temporal holdout on the same underlying road network**, not an unseen-road spatial generalization holdout.

---

## Model Configurations

Three supervised learning architectures were trained and evaluated:

### 1. Logistic Regression (Linear Baseline)

- **Hyperparameters:** `solver="lbfgs"`, `class_weight="balanced"`, `max_iter=1000`, `random_state=42`
- **Result:** Converged cleanly without requiring fallback to stochastic gradient descent (SGD).

### 2. Random Forest (Non-Linear Ensemble)

- **Hyperparameters:** `n_estimators=100`, `max_depth=16`, `min_samples_leaf=10`, `class_weight="balanced_subsample"`, `n_jobs=-1`, `random_state=42`
- **Positive-Preserving Training Sampler:** To maintain bounded memory lifetimes during tree construction, a fixed 500,000-row sample was drawn from the 11.7M training set:
  - All **281,621 positive rows** (100%) were preserved.
  - **218,379 negative rows** were randomly sampled without replacement (`random_state=42`).
  - Training sample prevalence = **56.32%** (intentionally rebalanced relative to the raw 2.41% population).

### 3. HistGradientBoosting (Gradient Boosted Trees)

- **Hyperparameters:** `loss="log_loss"`, `max_iter=150`, `learning_rate=0.08`, `max_leaf_nodes=31`, `min_samples_leaf=50`, `early_stopping=True`, `n_iter_no_change=10`, `random_state=42`
- **Training Population:** Trained on the **full 11,698,227-row training set** using sample weights computed from the global training class distribution.

---

## Preprocessing & Randomness

- **Linear Baseline:** Scaled with `StandardScaler` fitted **strictly** on the 2019–2022 training features. The fitted scaler artifact is serialized for inference.
- **Tree Ensembles:** Random Forest and HistGradientBoosting operate directly on raw unscaled features.
- **Determinism:** All random number generators and sampling seeds are locked to `random_state=42`.

---

## Validation Results (2023)

Optimal decision thresholds were swept across candidate values `[0.01, 0.99]` on the 2023 validation set under the constraint `precision >= 0.20`, maximizing F1 with deterministic tie-breaking:

| Model | Threshold | PR-AUC | ROC-AUC | Precision | Recall | F1 Score | Brier Score | Log-Loss |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Logistic Regression** | 0.94 | 0.9678 | 0.9992 | 0.9251 | 0.8574 | 0.8899 | 0.0075 | 0.0265 |
| **Random Forest** | 0.30 | **1.0000** | **1.0000** | **1.0000** | **1.0000** | **1.0000** | **0.0001** | **0.0022** |
| **HistGradientBoosting** | 0.96 | 0.9991 | 1.0000 | 0.9902 | 0.9797 | 0.9849 | 0.0008 | 0.0057 |

---

## Champion Selection

- **Champion Model:** **Random Forest** (`random_forest.joblib`)
- **Selection Criterion:** Highest validation PR-AUC (**1.0000**) and F1 score (**1.0000**).
- **Frozen Decision Threshold:** **0.30**

The champion model and its decision threshold were strictly frozen before evaluating the 2024 holdout dataset.

---

## 2024 Held-Out Test Results

The frozen Random Forest champion was evaluated exactly once against the 2,930,562 segment-day observations of 2024. No retraining, hyperparameter tuning, or threshold re-optimization took place:

| Metric | 2024 Held-Out Result |
| :--- | :---: |
| **PR-AUC** | **1.0000** |
| **ROC-AUC** | **1.0000** |
| **Operating Threshold** | **0.30** (frozen) |
| **Precision** | **0.9999** |
| **Recall** | **1.0000** |
| **F1 Score** | **0.99995** |
| **Brier Score** | **0.0002** |
| **Log-Loss** | **0.0028** |
| **True Positives (TP)** | 92,511 |
| **False Positives (FP)** | 9 |
| **True Negatives (TN)** | 2,838,042 |
| **False Negatives (FN)** | 0 |

---

## Important Metric Interpretation

> ### Crucial Scientific & Engineering Limitation
> The near-perfect PR-AUC (1.0000), ROC-AUC (1.0000), and F1 (0.99995) metrics achieved by Random Forest and HistGradientBoosting must **NOT** be interpreted as evidence of real-world road-closure forecasting capability.
>
> **Why the metrics are near-perfect:**
> The Checkpoint 18 target label `disruption_proxy` is an engineered deterministic rule governed by thresholds on precipitation, wind gusts, and road accessibility. The ML feature matrix contains those exact same underlying variables (`precipitation_mm`, `wind_gust_kmh`, `accessibility_score`).
>
> The non-linear tree models have effectively discovered and memorized the mathematical decision boundary of the synthetic rule.
>
> **What this proves:**
> The supervised models successfully achieved high-fidelity mathematical replication of the engineered disruption-proxy heuristic under a strict temporal split.
>
> **What this DOES NOT prove:**
> - Accuracy in predicting actual physical road closures or landslides
> - Operational reliability under unforeseen emergency conditions
> - Spatial transferability to unmapped or unseen road networks
> - Causal understanding of regional logistics disruptions
> - Future predictive forecasting capability

---

## Generated Artifacts

The training and evaluation run generated 7 local artifacts in the `models/` directory:

```text
models/
├── scaler.joblib                     # Fitted StandardScaler for linear model
├── scaler_metadata.json             # Feature names and scaling statistics
├── linear_baseline.joblib           # Trained Logistic Regression model
├── random_forest.joblib             # Trained Random Forest champion model
├── hist_gradient_boosting.joblib    # Trained HistGradientBoosting model
├── evaluation_summary.json          # Machine-readable validation & test metrics
└── model_comparison_report.md       # Markdown comparison and audit report
```

All 7 artifacts are local generated files and remain **strictly ignored by Git**. Model binaries are never committed to version control.

---

## Reproducibility & Testing

The entire intelligence suite and training pipeline are validated via automated tests:

- **Checkpoint 19 Contract Tests:** `16/16 passed` (`tests/test_ml_training.py`)
- **Checkpoint 19 Orchestration Tests:** `10/10 passed` (`tests/test_ml_training_orchestration.py`)
- **Checkpoints 1–18 Regression Suite:** `333/333 passed`
- **Bytecode Compilation:** `compileall src tests` clean with zero errors

### Approved Execution Environment

- **Python:** `3.10.9`
- **scikit-learn:** `1.6.1`
- **NumPy:** `2.2.6`
- **SciPy:** `1.15.3`
- **Dataset:** `17,551,344` rows across 6 CSV partitions

---

## Repository Structure

```text
SETU_AI/
├── src/
│   ├── risk/                  # Deterministic risk engine & factors
│   ├── impact/                # Incident network impact & affected segments
│   ├── eta/                   # Baseline and disruption-aware travel time
│   ├── routing/               # Candidate generation & multi-criteria ranking
│   ├── optimization/          # Algorithmic optimization experiments
│   ├── explanation/           # Human-readable decision justification
│   ├── common/                # Shared schemas, utilities, and configuration
│   ├── api/                   # Integration boundary to MERN platform
│   ├── ml/                    # Machine learning pipeline (CP18 & CP19)
│   │   ├── feature_pipeline.py    # 24-feature extraction & cyclical encoders
│   │   ├── dataset_loader.py      # Chronological streaming & partition loading
│   │   ├── train_models.py        # Scaler, model factories, training orchestration
│   │   ├── model_evaluation.py    # Threshold sweeps, classification metrics
│   │   └── champion_selector.py   # PR-AUC champion selection & holdout test
│   └── data/
│       ├── osm/               # Overpass API acquisition & normalization
│       ├── processing/        # Network pruning & elevation enrichment
│       └── weather/           # Open-Meteo cache & live forecast scaffolding
│
├── datasets/
│   ├── raw/                   # Raw API responses (local only, ignored by Git)
│   ├── processed/             # Processed datasets (17.5M CSVs local only, ignored by Git)
│   └── sample/                # Committed mini test fixtures
│
├── models/                    # Serialized models & metrics (local only, ignored by Git)
├── evaluation/                # Performance reports and benchmarking logs
├── tests/                     # Automated test suites (359 total tests)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Architecture after Checkpoint 19

The intelligence architecture seamlessly integrates the trained ML model while maintaining the operator-approved decision loop:

```text
MERN Backend
│
├── Incident Context
├── Shipment Details
├── Vehicle Profiles
└── Route Network
│
▼
Deterministic Intelligence Layer
│
├── Network Impact (Geolocated projection)
├── Accessibility Scoring (OSM proxy)
├── Deterministic Risk Assessment
├── ETA / Delay Estimation
└── Route Candidate Generation
│
▼
ML Disruption Model (Champion: Random Forest)
│
▼
Disruption Probability [0.0, 1.0]
│
▼
Integrated Risk / Decision Layer
│
▼
Explainable Recommendation
│
▼
Human Operator Approval (Review / Accept / Override)
│
▼
Operational Reroute Execution
│
▼
Live Tracking
```

*Architectural Principle:* Machine learning is a measured component designed to refine and inform disruption probability. It does **not** replace the deterministic risk, impact, and human-in-the-loop decision layer.

---

## Checkpoint 20 — Decision-Layer Integration & ML Inference Service

The trained disruption prediction champion (Random Forest) is integrated into the decision and rerouting pipeline via a dedicated in-process inference boundary (`src/ml/inference.py`):

- **In-Process Inference Engine:** Implemented via `DisruptionInferenceEngine` in `src/ml/inference.py` (exported through `src/ml/__init__.py`). Runs synchronously without external HTTP servers, microservices, daemons, or runtime network calls.
- **Champion Artifact & Raw Evaluation:** Consumes the frozen Checkpoint 19 Random Forest champion artifact (`models/random_forest.joblib`). Evaluates raw, unscaled features directly into `predict_proba` without applying `StandardScaler` (matching the tree-based training protocol).
- **Exact Canonical Feature Contract:** Strictly validates and constructs the exact 24 CP19 canonical feature inputs in immutable order. Uses canonical `WMO_CODE_SEVERITY` mapping for weather inputs without synthetic fallback fabrication.
- **Frozen Classification Threshold:** Applies the frozen 0.30 decision threshold selected in Checkpoint 19 on raw probabilities before rounding for display.
- **Physical Length-Weighted Route Aggregation:** Aggregates segment predictions across route alternatives using physical segment lengths (`length_weighted_mean_disruption_probability`), alongside `peak_segment_disruption_probability`.
- **Opt-In Auxiliary Integration:** Exposed in `create_reroute_recommendation(..., include_ml_assessment=False)`. By default (`include_ml_assessment=False`), Checkpoint 16 deterministic reroute behavior is 100% preserved.
- **Strict Protection of Deterministic Core:** ML output is strictly advisory and attached as auxiliary metadata. It never modifies deterministic risk scores, candidate generation, route ranking metrics, candidate ordering, blockage confirmation, or the human approval requirement (`PENDING_APPROVAL`).
- **Methodology Disclosure:** *Random Forest predict_proba disruption probabilities: These probabilities are model outputs for the engineered-label classification task and are not calibrated or validated probabilities of real-world road closure.*

---

## Next — Checkpoint 21

```text
NEXT APPROVED CHECKPOINT:
Checkpoint 21 — Real-Time Alert & Incident Ingestion System
```

### Objective & Scope

Integrate real-time incident and alert ingestion into the SETU-AI event loop:
- Ingest real-time hazard, incident, and road closure alerts.
- Map external alert payloads to digital twin network segments.
- Trigger the incident reroute loop with pending human approval.
- Maintain human-in-the-loop governance across all operational commitments.

---

## Scope Guardrails

The following anti-patterns are explicitly prohibited from the SETU-AI architecture:

- **No Blockchain:** Unnecessary overhead for logistics tracking.
- **No Kafka / RabbitMQ:** In-memory queueing and synchronous endpoints suffice for the prototype.
- **No Kubernetes:** Premature deployment complexity.
- **No Premature Microservices:** Intelligence modules run within a unified, cleanly separated codebase.
- **No Redis:** In-memory Python caches provide necessary performance without external daemon dependencies.
- **No Nationwide Simulation:** Focus strictly on the North Eastern Region (Guwahati–Imphal corridor).
- **No Hardware GPS Tracking:** Simulated coordinate telemetry provides complete testing coverage.
- **No Mobile App in SETU-AI:** Offline mobile clients belong in the client application layer, not the intelligence engine.
- **No Unjustified Deep Learning:** Tabular models (Random Forest, Gradient Boosting) are superior and interpretable for this feature space.
- **No LLM in Decision Control:** LLMs must never execute or alter deterministic routing, risk, or operational approval decisions.

---

## Git & Data Policy

- **Ignored by Git:**
  - Raw and processed datasets (`datasets/raw/`, `datasets/processed/`)
  - The 17.5M-row CSV partitions (2.68 GB total)
  - Serialized model binaries and scalers (`models/*.joblib`)
- **Committed to Git:**
  - Source code (`src/`)
  - Test suites (`tests/`)
  - Documentation and specifications (`README.md`, `TASK_TRACKER.md`)
  - Schema definitions and manifests
  - Small sample test fixtures (`datasets/sample/`)

Never force-add generated dataset partitions or model binary files to Git.
