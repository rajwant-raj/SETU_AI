# SETU_AI — Task Tracker & Deviation Guard

> **Purpose:** This file is the execution guardrail for `SETU_AI`.
> Update it at every checkpoint so implementation stays aligned with the SIH26002 blueprint and does not grow into an unrelated AI research project.

## 1. Source of Truth

1. Official SIH26002 problem statement
2. `SIH26002 — MERN Prototype Blueprint, Repository Benchmark & Implementation Plan.md`
3. `README.md` in this repository
4. This tracker records the **actual implementation state** and must not claim work that is not completed.

The product's central loop is:

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

The governing architecture is:

```text
AI recommends
      ↓
Backend orchestrates
      ↓
Operator approves
```

---

## 2. Deviation Guard — MUST CHECK BEFORE EACH NEW FEATURE

Before adding a library, API, dataset, model, service, architecture component, or major script, answer:

- Does the blueprint require it?
- Does it help the **current phase**?
- Is it needed for the SETU core loop?
- Does it fit the current free-tier/API limits and project deadline?
- Does it introduce scope creep that belongs to a later phase?

If the answer is **no**, do not add it.

### Explicitly out of scope unless later justified

- Blockchain
- Complex conversational chatbot
- Kafka
- Kubernetes
- Premature microservices
- Redis before an actual scaling requirement
- Nationwide logistics simulation
- Hardware GPS integration for the prototype
- Large native mobile application
- Advanced deep-learning models without sufficient data justification
- Repeated external API calls during training/inference

---

## 3. Checkpoint Protocol

Every meaningful task follows this exact sequence:

```text
1. PLAN CHECK
      ↓
2. BUILD ONE THING
      ↓
3. VALIDATE IT
      ↓
4. ROLLBACK / DEVIATION CHECK
      ↓
5. UPDATE THIS TRACKER
      ↓
6. GIT COMMIT + PUSH
      ↓
7. CLEAN WORKING TREE CHECK
```

**Important:** The tracker is updated **before declaring a checkpoint complete**.

Generated raw/processed datasets remain local unless the blueprint explicitly requires a committed sample.

---

## 4. Current Project State — 2026-09-13

### DATA FOUNDATION

| Item | Status | Checkpoint | Notes |
|---|---|---:|---|
| OSM/Overpass road acquisition | ✅ COMPLETE | 1 | Guwahati–Imphal study area; cached locally |
| OSM normalization | ✅ COMPLETE | 2 | 16,272 normalized segments before geometry refinement |
| Core road network | ✅ COMPLETE | 3 | 8,007 major-road segments before geometry refinement |
| Elevation enrichment | ✅ COMPLETE | 4 | 8,007/8,007 core segments enriched |
| Historical weather exploration | ✅ COMPLETE | 5 | Cached 2019–2024 at 40 representative points |
| Live weather module scaffold | ✅ COMPLETE | 6 | Open-Meteo Forecast API client created and syntax-checked |
| Weather data expansion | ⛔ STOPPED | — | Do not expand historical coverage now; live weather + deterministic intelligence take priority |

### DETERMINISTIC INTELLIGENCE

| Item | Status | Checkpoint | Notes |
|---|---|---:|---|
| Risk Engine v0.1 specification | ✅ COMPLETE | 7 | Define inputs, weights, thresholds, reasons |
| Risk Engine implementation | ✅ COMPLETE | 8 | Deterministic weighted risk engine implemented and tested |
| Phase 8 review fixes | ✅ COMPLETE | 8R | README/spec synchronization, label provenance, OSM geometry retention, weather cache validation, risk-spec correction, immutable weights |
| Network Impact Engine | ✅ COMPLETE | 9 | Deterministic local spatial impact engine; geometry-aware segment proximity; 46 Network Impact tests passing |
| Accessibility scoring | ✅ COMPLETE | 10 | Deterministic OSM-derived infrastructure accessibility proxy; dynamic evidence normalization; 44 Accessibility tests passing |
| ETA / delay engine | ✅ COMPLETE | 11 | Deterministic baseline ETA + disruption delay engine; 60 ETA tests passing; 188 total tests passing; compileall passed; git diff --check passed; zero new external dependencies; no external routing/traffic services; no ML/LLM/RAG integration; deviation audit PASS |
| Thin Digital Twin Foundation | ✅ COMPLETE | 12 | Thin state-based/simulation-oriented foundation; operational state + deterministic events + isolated what-if scenarios; composes existing Network Impact, Accessibility, ETA, and Risk engines; 23 Digital Twin tests passing; 211 total tests passing; compileall passed; git diff --check passed; zero new dependencies/services; deviation audit PASS |
| Route candidate generation | ✅ COMPLETE | 13 | Deterministic in-memory graph construction + Yen's K-shortest simple paths algorithm; strictly physical distance cost; explicit blocked segment exclusion; 17 route candidate tests passing; 228 total tests passing; compileall passed; git diff --check passed; zero new dependencies; zero external APIs; deviation audit PASS |
| Route ranking | ✅ COMPLETE | 14 | Deterministic candidate route ranking; candidate-set min-max utility normalization; ETA, risk, accessibility, distance, vehicle profile compatibility proxy; 25 route ranking tests passing; 253 total tests passing; compileall passed; git diff --check passed; zero new dependencies; zero external APIs; deviation audit PASS |
| Explanation output | ✅ COMPLETE | 15 | Deterministic structured explanation of route ranking results; 5 decision factors (ETA, risk, accessibility, distance, vehicle profile compatibility proxy); comparative tradeoffs; risk reason preservation; honesty disclosures; 17 explanation tests passing; 270 total tests passing; compileall passed; git diff --check passed; zero new dependencies; zero external APIs; deviation audit PASS |
| Human-approval recommendation contract | ✅ COMPLETE | 16 | Deterministic incident-to-reroute orchestration; Network Impact, Route Candidate Generation, Route Ranking, and Route Explanation composed; potentially affected ≠ confirmed blocked; explicit blocked_segment_ids only; recommendation remains pending human approval; operational route changes only after explicit approval; Digital Twin route_changed event semantics preserved; 25 incident reroute tests passing; 295 total tests passing; compileall passed; git diff --check passed; zero new dependencies; zero external APIs; deviation audit PASS |
| Live weather integration into risk | ✅ COMPLETE | 17 | Deterministic live weather adapter; strict WMO & continuous input validation; piecewise scoring; length-weighted route aggregation; batched Open-Meteo cache/fallback with machine-readable state (LIVE, CACHED, NOMINAL_FALLBACK); 22 weather integration tests passing; 317 total tests passing; compileall passed; git diff --check passed; zero new dependencies; zero test network calls; deviation audit PASS |

### ML / EVALUATION

| Item | Status | Checkpoint | Notes |
|---|---|---:|---|
| ML Dataset Construction | ✅ COMPLETE | 18 | Pure standard-library ML dataset builder implemented; test-first; 16 Checkpoint 18 tests passing; 333 total repository tests passing; 8,007 road segments; 40 weather stations resolved; 2019-01-01 through 2024-12-31; exact 17,551,344 segment-day rows generated; six annual CSV partitions generated; dataset_metadata.json generated; exact canonical 30-column schema validated; zero duplicate (segment_id, date) combinations; deterministic row ordering validated; leakage audit passed; derived disruption_proxy provenance contract preserved; disaster condition (a) inactive because local disaster directory is empty (no fabricated events); compileall passed; git diff --check passed; zero new external dependencies; no external API calls; no ML training performed; no ML inference implemented; deviation audit PASS |
| ML Training + Evaluation Pipeline | ✅ COMPLETE | 19 | Implementation at 36b15e0, orchestration at b98ad7a, test-fix at a19caa7; 16/16 CP19 tests passing; 10/10 orchestration tests passing; 333 CP1–18 regression tests passing; compileall clean; Python 3.10.9 / scikit-learn 1.6.1; dataset independently reconciled (Train: 11,698,227, Val: 2,922,555, Test: 2,930,562, Total: 17,551,344 rows across 6 partitions); full-scale model training executed; all 7 artifacts generated locally under gitignored models/; champion: random_forest; frozen threshold: 0.30; 2024 test PR-AUC 1.0, ROC-AUC 1.0, F1 1.0 (0.99995); zero model artifacts committed to Git |
| Logistic Regression baseline | ✅ COMPLETE | 19 | Fitted as primary LogisticRegression on 11.7M rows without SGD fallback; Val PR-AUC 0.9678, ROC-AUC 0.9992, F1 0.8899 at threshold 0.94 |
| Random Forest comparison | ✅ COMPLETE | 19 | Fitted on 500k positive-preserving sample (281,621 positives retained, 56.32% prevalence); selected as Champion; Val PR-AUC 1.0, ROC-AUC 1.0, F1 1.0 at threshold 0.30 |
| HistGradientBoosting benchmark | ✅ COMPLETE | 19 | Fitted on full 11.7M population with balanced sample weights; Val PR-AUC 0.9991, ROC-AUC 1.0, F1 0.9849 at threshold 0.96 |
| Temporal validation & test | ✅ COMPLETE | 19 | 2023 validation tuned thresholds and selected champion; 2024 held-out test evaluated once at frozen threshold 0.30 without retuning or retraining (PR-AUC 1.0, F1 1.0) |
| Spatial-holdout evaluation | ⏳ LATER | — | Deferred to later evaluation milestone on unseen roads/coordinates |
| Decision-layer integration | ✅ COMPLETE | 20 | In-process Python inference component (DisruptionInferenceEngine) implemented; frozen Random Forest champion; frozen threshold 0.30; exact 24-feature schema; raw unscaled features; physical-length weighted route aggregation; auxiliary opt-in ML advisory; CP16 default deterministic reroute preserved; 16 inference tests, 6 integration tests, 381 total tests passing; compileall clean; git diff --check clean; deviation audit PASS |

### INTEGRATION / PRODUCT LOOP

| Item | Status | Notes |
|---|---|---|
| MERN backend intelligence boundary | ⏳ LATER | Stable API boundary after core intelligence behavior stabilizes |
| Incident → impact → risk loop | ✅ COMPLETE | Main decision-support loop; validated in Checkpoint 16 |
| Alternative route recommendation | ✅ COMPLETE | Main demo behavior; validated in Checkpoint 16 |
| Human approval → reroute | ✅ COMPLETE | Operator remains in control; validated in Checkpoint 16 |
| Live tracking integration | ⏳ LATER | Socket.IO / simulated telemetry in MERN |
| Offline field workflow | ⏳ LATER | Small queued incident sync; not a large native app |

---

## 5. Current Checkpoint

**Checkpoint 20 — Decision-Layer Integration / ML Inference Service**

Completed (Checkpoint 12 — Thin Digital Twin Foundation):
- Thin in-memory DigitalTwinState implemented for network, vehicles, shipments, and incidents
- Strict entity validation and referential integrity
- Deterministic event layer implemented with required event_id, event_type, timestamp, and payload
- Supported incident_created, vehicle_location_updated, shipment_status_changed, route_approved, and route_changed events
- Incident impact linked through existing Network Impact Engine
- Confirmed closures only may explicitly set `is_blocked = True`
- No fabricated disruption factor, speed reduction, or physical road closure
- Existing Accessibility, ETA, Network Impact, and Risk engines reused without formula duplication
- Strict Risk Engine v0.1 input contract preserved; no fabricated missing inputs
- What-if simulation implemented using isolated deep-copy scenario state
- Explicit blocked-segment, speed-reduction, and simulated-incident scenario overrides
- Baseline vs scenario ETA, passability, delay, and optional Risk comparison
- Live state mutation prevented during simulation
- Deterministic repeated simulation validated
- 23 Digital Twin tests passing
- 211 total tests passing
- compileall passed
- git diff --check passed
- Zero new external dependencies introduced for Checkpoint 12
- No databases, Redis, Kafka, brokers, WebSockets, API servers, ML, LLM, RAG, or routing algorithms introduced

Completed (Checkpoint 13 — Route Candidate Generation):
- Deterministic in-memory graph construction from normalized OSM road segment endpoints
- Coordinate quantization keying (`N_{lat:.6f}_{lon:.6f}`) preventing arbitrary road merging
- Endpoints treated as bidirectional per normalized OSM data limitations, explicitly documented
- Nearest-node resolution via deterministic haversine great-circle distance
- Yen's K-shortest simple paths algorithm implemented using Python standard library only
- Path cost strictly physical network distance (`sum(segment_length_km)`)
- Zero ranking formulas, risk scores, accessibility scores, ETAs, weather weights, or recommendation scores
- Candidate records expose route_id, segment_ids, node_ids, origin_node, destination_node, total_distance_km, segment_count, geometry, and preserved segment metadata
- Deterministic candidate ordering by total distance, segment count, segment ID sequence, and node sequence
- Explicit blocked_segment_ids exclusion without treating Network Impact's "potentially affected" segments as automatically blocked
- Strict input validation rejecting empty networks, malformed segments, invalid coordinates, invalid k, malformed blocked_segment_ids, and disconnected origin/destination
- Caller segment dictionaries preserved without mutation
- 17 route candidate tests passing across all 14 required areas
- 228 total tests passing across repository
- compileall passed
- git diff --check passed
- Zero new external dependencies introduced for Checkpoint 13
- Zero external routing APIs (no Mapbox, OSRM, Google Maps, or remote services)
- No ML, GA/PSO, databases, Kafka, Redis, or background services

Completed (Checkpoint 14 — Route Ranking):
- Deterministic candidate route ranking layer implementing candidate-set min-max utility normalization
- Supported signals: ETA (lower is better), Risk (lower is better), Accessibility (higher is better), Physical Distance (lower is better), and Vehicle Profile Compatibility Proxy (higher is better)
- Availability signal explicitly declared unsupported in v0.1 and not fabricated
- Vehicle fit honestly renamed and documented as a vehicle profile compatibility proxy, not physical vehicle clearance/load compatibility
- Risk strictly derived from precomputed candidate risk_score or complete explicit risk_context containing every required Risk Engine field (incident_severity, accessibility_score, weather_severity, road_condition_score, network_criticality, current_delay_ratio); zero default fabrication, zero ETA delay derivation, zero segment accessibility derivation
- Proportional normalized default weights mathematically summing to exactly 1.0 (ETA 30/95, Risk 20/95, Accessibility 20/95, Distance 15/95, Vehicle profile compatibility proxy 10/95)
- Strict custom-weight validation rejecting unknown metric keys
- Division-by-zero protection on constant metric sets and single-candidate collections
- Explicit deterministic tie-breaking: ranking score (descending) -> distance (ascending) -> segment count (ascending) -> segment ID sequence -> node sequence -> route ID
- Structured tradeoff summary exposed for downstream Checkpoint 15 Explanation
- Caller candidate dictionaries preserved without mutation
- 25 route ranking tests passing across all required areas
- 253 total tests passing across repository
- compileall passed
- git diff --check passed
- Zero new external dependencies introduced for Checkpoint 14
- Zero external routing APIs (no Mapbox, OSRM, Google Maps, or remote services)
- No ML, GA/PSO, databases, Kafka, Redis, or background services

Completed (Checkpoint 15 — Explanation):
- Deterministic explanation layer translating Route Ranking outputs into operator-readable explanations
- Exposes explain_ranked_route and explain_ranked_routes public APIs
- Strictly explanatory: does not recalculate ranking scores, alter route ordering, or introduce new weights
- Evaluates 5 supported decision factors: ETA, Risk, Accessibility, Distance, and Vehicle Profile Compatibility Proxy
- Retains exact weights applied and normalized utility scores from the ranking input
- Comparative tradeoff analysis against runner-up/top candidate without hardcoded or fabricated facts
- Single-route explanation supported without nonexistent alternative comparisons
- Preserves upstream Risk Engine reason codes and reasons when present; honestly notes absence without fabrication
- Explicit honesty disclosures: vehicle profile compatibility proxy (not physical vehicle passability), availability unsupported, real-world conditions require operational data, human operator retains authority
- Strict input validation rejecting missing or corrupted ranking structures, metrics, scores, and weights
- Input immutability preserved (zero caller dictionary mutation)
- 17 route explanation tests passing across all required areas
- 270 total tests passing across repository
- compileall passed
- git diff --check passed
- Zero new external dependencies introduced for Checkpoint 15
- Zero external routing/explanation APIs (no LLMs, OpenAI, Mapbox, OSRM, or remote services)
- No ML, GA/PSO, databases, Kafka, Redis, or background services

Completed (Checkpoint 16 — Incident → Reroute demo loop):
- Deterministic incident-to-reroute orchestration layer composing Network Impact, Route Candidate Generation, Route Ranking, Route Explanation, and Digital Twin state/events
- Network Impact reused without formula duplication; evaluates potentially affected segments within incident impact radius
- Potentially affected ≠ confirmed blocked semantic rule strictly enforced; segments never automatically blocked from incident severity, radius, weather, risk, or heuristics
- Explicit confirmed_blocked_segment_ids only are excluded from alternative route generation
- Route Candidate Generation reused; physical distance cost only
- Route Ranking reused; normalized utility model with approved proportional weights
- Route Explanation reused; structured decision factors, comparative tradeoffs, and honesty disclosures
- Recommendation produced in PENDING_APPROVAL status with approval_required=True
- Operational route remains unchanged during recommendation creation (side-effect free)
- Explicit approval function (approve_reroute_recommendation) requires non-empty operator identifier and PENDING_APPROVAL state
- Operational route updated only after explicit approval; applies Digital Twin route_changed event and updates status to REROUTED
- Explicit rejection function (reject_reroute_recommendation) transitions status to REJECTED without modifying state
- Approval cannot happen twice; non-pending states rejected
- Disconnection/no-alternative-route handled honestly without inventing fake routes
- Strict input validation rejecting malformed incidents, disconnected endpoints, and non-existent blocked IDs
- Caller input immutability preserved
- 25 incident reroute tests passing across all 25 required areas
- 295 total tests passing across repository
- compileall passed
- git diff --check passed
- Zero new external dependencies introduced for Checkpoint 16
- Zero external routing/explanation/traffic APIs (no Mapbox, OSRM, Google Maps, or remote services)
- No ML, GA/PSO, databases, Kafka, Redis, or background services

Completed (Checkpoint 17 — Live Weather Integration into Risk):
- Deterministic pure weather adapter converting normalized Open-Meteo current weather observations into weather_severity in [0.0, 1.0]
- Exact deterministic WMO code mapping table covering clear, fog, drizzle, rain, freezing rain, snow, showers, and convective thunderstorms (severe thunderstorm WMO 99 = 1.0)
- Strict validation via InvalidWeatherInputError rejecting unknown, unsupported, or non-finite WMO codes (never silently treated as clear weather)
- Strict validation via InvalidWeatherInputError rejecting missing, negative, or non-finite continuous weather variables (precipitation, wind speed, wind gusts)
- Exact piecewise linear scaling for precipitation (0 mm = 0.0, 50 mm/h = 1.0), wind speed (0 km/h = 0.0, 100 km/h = 1.0), and wind gusts (0 km/h = 0.0, 130 km/h = 1.0)
- Explicit combination rule: Base = 0.35*WMO + 0.35*Precip + 0.15*Wind + 0.15*Gust; Peak = max(WMO, Precip, Wind, Gust); Combined = 0.60*Base + 0.40*Peak; strictly clamped to [0.0, 1.0] and rounded to 4 decimals
- Deterministic spatial lookup mapping segment midpoint coordinates to the nearest weather sampling station via haversine distance
- Route weather aggregation strictly using length-weighted mean weather severity; no worst-case aggregation
- Risk Engine contract preservation: weather_severity supplied directly to calculate_risk without modifying Risk Engine weights (0.20), thresholds (0.75 for ADVERSE_WEATHER, 0.50 for MODERATE_WEATHER_RISK), formula, or validation
- Batched weather retrieval architecture reusing datasets/processed/weather/live_weather.json; never requests Open-Meteo per segment, per route, or per candidate
- Explicit three-tier fallback state handling exposing machine-readable state: LIVE, CACHED, and NOMINAL_FALLBACK (unverified severity 0.0 with is_live=False and clear honesty disclosure)
- Strict mode support raising LiveWeatherUnavailableError when verified weather is mandated
- Zero real network calls in tests; all network interactions mocked/fixtured
- 22 weather integration tests passing across all required areas
- 317 total tests passing across repository
- compileall passed
- git diff --check passed
- Zero new external dependencies introduced for Checkpoint 17
- No changes to src/risk/risk_engine.py
- No changes to src/routing/route_ranking.py
- No ML, LLM, RAG, Redis, Kafka, FastAPI, databases, or external routing services

Completed (Checkpoint 18 — ML Dataset Construction):
- Pure standard-library streaming dataset builder implemented (`src/data/processing/build_ml_dataset.py`) using csv, json, math, datetime, pathlib, collections (zero pandas, zero numpy, zero networkx)
- Full spatial and temporal coverage: all 8,007 eligible core segments across 2,192 consecutive days (2019-01-01 through 2024-12-31)
- Exact Cartesian structural product achieved: 17,551,344 segment-day rows generated without fabricating or omitting any records
- Six annual CSV partitions written to `datasets/processed/ml/ml_dataset_YYYY.csv` (gitignored, ~2.68 GB total, ~446 MB per partition)
- Exact canonical 30-column schema validated across every partition
- Deterministic spatial midpoint density proxy (`local_segment_density_proxy` in `connectivity_degree`) using 0.01 deg spatial hashing; order-invariant and pure stdlib
- Positional 1-to-1 array mapping for all 40 weather stations (`WX-001` through `WX-040`) from Open-Meteo batch JSON archives, avoiding coordinate snapping collisions
- Deterministic many-to-one road-to-station nearest mapping via Haversine distance with lexicographical tie-breaking for equidistant points
- Canonical `disruption_proxy` v0.1 binary rule strictly implemented: condition (a) disaster proximity, condition (b) precip >= 50mm, condition (c) wind gust >= 65km/h, condition (d) accessibility < 0.40 & precip >= 25mm
- Auxiliary bounded continuous disruption risk index in [0.0, 1.0]
- Honest label provenance contract: `label_type = "derived"`, `label_source = "GDACS + Open-Meteo + OSM"`, `label_derivation_method = "deterministic_threshold_rule_v0.1"`
- Condition (a) documented as inactive due to empty local disaster directory (`datasets/raw/disasters`); zero synthetic disaster events fabricated
- Explicit honesty disclosures in metadata and code: `disruption_proxy` is an engineered physical hazard indicator, never claimed as observed road closure, police confirmation, or traffic standstill ground truth
- Same-day historical classification framing: uses same-day historical weather; explicitly not described as genuine future forecasting
- Zero-leakage guarantees: downstream Risk Engine outputs (`risk_score`, `risk_band`), post-hoc delay ratios (`current_delay_ratio`), and future-day weather are strictly excluded
- Zero duplicate `(segment_id, date)` combinations; deterministic row ordering sorted by `date` (asc), then `segment_id` (asc)
- Actual empirical label prevalence computed and recorded in `dataset_metadata.json`: 439,916 total positive labels (overall prevalence: 2.5065%, yearly range: 1.6013% to 3.1568%)
- Test-first implementation: 16 Checkpoint 18 tests passing; 333 total repository tests passing
- compileall passed cleanly; git diff --check passed cleanly
- Zero new external dependencies introduced; zero external API calls during generation
- No ML model training performed; no ML inference implemented

Completed (Checkpoint 19 — ML Training + Evaluation):
- ML training and evaluation core module implemented (`src/ml/train_models.py`, `src/ml/__init__.py`) at commit `36b15e0`
- Training orchestration and execution layer implemented at commit `b98ad7a`
- Post-training test import isolation fixed at commit `a19caa7`
- Canonical 24-feature schema strictly enforced in deterministic order
- Dynamic cyclical temporal feature derivation (`month_sin`, `month_cos`, `dow_sin`, `dow_cos`) from real CP18 CSV columns (`month`, `day_of_week`) verified on synthetic real-schema records
- Precomputed temporal features from test fixtures seamlessly supported for full backward test compatibility
- Canonical weather code hazard mapping strictly using `src.data.weather.weather_severity.WMO_CODE_SEVERITY` into [0.0, 1.0]; zero duplicate WMO dictionaries
- Leakage isolation strictly verified: 14 forbidden columns (`segment_id`, `date`, `year`, `disruption_score_continuous`, `disruption_proxy`, `risk_score`, `risk_band`, etc.) completely isolated from features
- Strict chronological split boundaries: Train 2019–2022, Val 2023, Test 2024; zero cross-year leakage
- Train-only standardization: `StandardScaler` fit strictly on 2019–2022 training rows; tree models receive raw unscaled features
- Linear baseline with explicit fallback contract: `LogisticRegression(solver='lbfgs', class_weight='balanced')` fit successfully on full 11.7M rows without SGD fallback (`fallback_occurred=False`)
- Random Forest positive-preserving sampler retaining 100% of positive training records (281,621 rows) and sampling negatives to reach exactly 500,000 rows with fixed seed 42 (sampled prevalence: 56.3242%)
- HistGradientBoosting binned tabular benchmark fit on full 11.7M population with deterministic balanced sample weighting via `compute_sample_weight('balanced', y=y_train)`
- Validation threshold optimization on 2023 across 99 candidate thresholds (0.01 to 0.99 in 0.01 steps), precision floor >= 0.20, F1 maximization, and deterministic tie-breaking:
  - `linear`: Val PR-AUC 0.9678, ROC-AUC 0.9992, Precision 0.9251, Recall 0.8574, F1 0.8899, Selected Threshold: 0.94
  - `random_forest`: Val PR-AUC 1.0000, ROC-AUC 1.0000, Precision 1.0000, Recall 1.0000, F1 1.0000, Selected Threshold: 0.30
  - `hist_gradient_boosting`: Val PR-AUC 0.9991, ROC-AUC 1.0000, Precision 0.9902, Recall 0.9797, F1 0.9849, Selected Threshold: 0.96
- Champion model selection protocol: `random_forest` selected based strictly on highest validation PR-AUC (1.0000) and F1 (1.0000); frozen decision threshold fixed at 0.30
- Temporal held-out evaluation on 2024 (2,930,562 rows, 92,511 positive disruptions) strictly evaluated once at frozen threshold 0.30 without re-tuning or retraining:
  - PR-AUC: 1.0000, ROC-AUC: 1.0000, Decision Threshold: 0.30, Precision: 0.9999, Recall: 1.0000, F1: 1.0000 (0.99995), Brier Score: 0.0002, Log-Loss: 0.0028, TP: 92,511, FP: 9, TN: 2,838,042, FN: 0
- Memory-safe dataset loader (`load_split_matrix`) with fast binary line counting (`count_partition_rows`), bounded chunk streaming (250,000 rows), and float32/int8 preallocation
- Strict memory lifetime isolation: zero simultaneous coexisting train, validation, or test matrices
- All 7 approved model artifacts generated locally under gitignored `models/`: `scaler.joblib`, `scaler_metadata.json`, `linear_baseline.joblib`, `random_forest.joblib`, `hist_gradient_boosting.joblib`, `evaluation_summary.json`, `model_comparison_report.md`
- Zero model artifacts committed to Git (git status remains clean; `.gitignore` line 40 enforces `models/`)
- Module imports verified 100% side-effect free; isolated test verification passes post-training
- Mandatory methodology disclosure strictly preserved: "SAME-DAY HISTORICAL CLASSIFICATION / ENGINEERED-LABEL RULE-REPLICATION"
- Explicit honesty disclosures:
  - Not real-world physical road closure ground truth
  - Not true future forecasting
  - 2024 is a temporal holdout on the same road network corridor
  - Unseen-road spatial generalization remains untested and explicitly deferred to a later evaluation milestone
- Dataset row-count reconciliation verified across all 6 partitions:
  - Train (2019–2022): 11,698,227 rows
  - Validation (2023): 2,922,555 rows
  - Test (2024): 2,930,562 rows
  - Total: 17,551,344 rows
- 16/16 Checkpoint 19 contract tests passing (`tests/test_ml_training.py`)
- 10/10 Checkpoint 19 orchestration tests passing (`tests/test_ml_training_orchestration.py`)
- 333 full repository regression tests passing across Checkpoints 1–18 in active `.venv` (Python 3.10.9, scikit-learn 1.6.1, numpy 2.2.6, scipy 1.15.3)
- compileall clean; git diff --check clean

Completed (Checkpoint 20 — Decision-Layer Integration / ML Inference Service):
- In-process Python inference component and local service boundary implemented (`src/ml/inference.py`, exported in `src/ml/__init__.py`)
- Encapsulated `DisruptionInferenceEngine` with cached champion model reuse (loaded once in memory, no per-inference reload)
- Frozen Champion Random Forest (`models/random_forest.joblib`) evaluated at frozen decision threshold 0.30
- Exact CP19 24-feature schema extracted in strict deterministic canonical order without fabrication, guessing, or silent substitution
- Tree model scaler bypass verified: Random Forest consumes raw unscaled features directly (`StandardScaler` bypassed)
- Canonical WMO weather code mapping strictly reused from `src.data.weather.weather_severity.WMO_CODE_SEVERITY`; zero duplicate WMO dictionaries
- Strict weather code validation: missing, non-numeric, or unsupported WMO codes raise `InvalidWeatherInputError` (never silently converted to 0.0)
- Thresholding strictly evaluated on raw probability (`raw_prob >= 0.30`), with rounding to 4 decimal places applied only on return/display
- Physical length-weighted route aggregation strictly evaluated using actual physical `segment_length_km` (`length_weighted_mean_disruption_probability`) and `peak_segment_disruption_probability` (maximum individual segment probability)
- Auxiliary opt-in integration into Checkpoint 16 orchestration via `include_ml_assessment: bool = False` default in `create_reroute_recommendation`
- Existing CP16 deterministic reroute behavior 100% preserved as default when `include_ml_assessment=False`
- When `include_ml_assessment=True`, attached auxiliary `ml_assessment` without altering ranking score, normalized utility, weights, candidate ordering, blockage status, or approval lifecycle
- Route explanation layer extended to surface auxiliary `ml_advisory` when present while keeping the 5 core decision factors and narrative untouched
- Explicit failure degradation: when model artifact is absent or fails, records machine-readable `status: "UNAVAILABLE"` with reason provenance, allowing deterministic decision-support to proceed without interruption
- Zero synthetic or disguised ML probability fallbacks
- Protected deterministic files strictly untouched: `src/risk/risk_engine.py`, `src/impact/network_impact.py`, `src/accessibility/accessibility_scorer.py`, `src/eta/eta_engine.py`, `src/routing/route_candidates.py`, `src/routing/route_ranking.py`
- Human approval invariant preserved: AI recommends -> Backend orchestrates -> Operator approves (recommendation remains `PENDING_APPROVAL`, operational route unchanged before explicit approval)
- 16/16 Checkpoint 20 inference contract tests passing (`tests/test_ml_inference.py`)
- 6/6 Checkpoint 20 decision integration tests passing (`tests/test_ml_decision_integration.py`)
- 381/381 total repository regression tests passing across Checkpoints 1–20 (359 existing + 22 new)
- Bytecode compilation clean (`compileall src tests`)
- `git diff --check` clean with zero whitespace or line-ending errors
- Zero new external dependencies introduced
- Zero model artifacts tracked in Git (git status clean of tracked/model artifacts; `.gitignore` line 40 enforces `models/`; pre-existing `src/IntelligencePage.jsx` and `src/IntelligencePage.scss` remain intentionally untracked)

Deviation audit:
PASS

Next approved task:
Checkpoint 21 — MERN Backend Intelligence Boundary / API Integration

---

## 6. Approved Execution Order From Here

```text
Risk Engine specification
        ↓
Risk Engine implementation
        ↓
Rollback/deviation audit
        ↓
Network Impact
        ↓
Accessibility
        ↓
ETA / Delay
        ↓
Thin Digital Twin Foundation
        ↓
Route Candidates
        ↓
Route Ranking
        ↓
Explanation
        ↓
Incident → Reroute demo loop
        ↓
Live weather integration into risk
        ↓
ML dataset construction
        ↓
ML training + evaluation
        ↓
ML inference service
        ↓
MERN integration / polish
```

> **Thin Digital Twin Foundation:** Thin state-based/simulation-oriented foundation that composes existing network, incident, risk, accessibility, ETA, shipment, and vehicle state without duplicating intelligence engines.

This order intentionally keeps the deterministic system ahead of ML, matching the blueprint.

---

## 7. Hard Stop Conditions

Pause and audit before proceeding if any of these appear:

- A new framework or infrastructure service is proposed without blueprint justification.
- Historical-data work starts delaying deterministic intelligence.
- ML starts before deterministic risk/impact/routing are usable.
- AI is asked to replace the backend/operator workflow rather than recommend actions.
- External APIs become a dependency for every training/inference request.
- A feature is being added only because it sounds impressive rather than because it supports the decision loop.
- The implementation can no longer be explained as part of:

```text
TRACK → UNDERSTAND → PREDICT → ASSESS IMPACT → COMPARE → EXPLAIN → DECIDE → ACT
```

---

## 8. Completion Rule

A task is **not complete** until:

- its code/data output is validated,
- deviation from the blueprint has been checked,
- this tracker is updated,
- the checkpoint is committed and pushed,
- and `git status` is clean.

### Last updated

2026-09-14
