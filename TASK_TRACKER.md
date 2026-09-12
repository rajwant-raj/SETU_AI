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

## 4. Current Project State — 2026-09-12

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
| Network Impact Engine | ⏳ PENDING | — | Incident → affected segments/shipments |
| Accessibility scoring | ⏳ PENDING | — | Route/segment accessibility |
| ETA / delay engine | ⏳ PENDING | — | Baseline ETA + disruption delay |
| Route candidate generation | ⏳ PENDING | — | Generate alternatives |
| Route ranking | ⏳ PENDING | — | Compare ETA, risk, accessibility, distance, vehicle fit |
| Explanation output | ⏳ PENDING | — | Operational reasons, not opaque scores |
| Human-approval recommendation contract | ⏳ PENDING | — | Recommendation → approve/reject → reroute |

### ML / EVALUATION

| Item | Status | Notes |
|---|---|---|
| Final training dataset | ⏳ LATER | Build only after deterministic loop is stable |
| `disruption_proxy` label | ⏳ LATER | Derived prototype label; never claim it as observed road-closure ground truth |
| Logistic Regression baseline | ⏳ LATER | First ML baseline |
| Random Forest comparison | ⏳ LATER | Compare against baseline |
| XGBoost | ⏳ LATER | Only if justified |
| Time-aware evaluation | ⏳ LATER | Precision, recall, F1, ROC-AUC |
| ML inference service | ⏳ LATER | FastAPI only after model + deterministic system are ready |

### INTEGRATION / PRODUCT LOOP

| Item | Status | Notes |
|---|---|---|
| MERN backend intelligence boundary | ⏳ LATER | Stable API boundary after core intelligence behavior stabilizes |
| Incident → impact → risk loop | ⏳ PENDING | Main decision-support loop |
| Alternative route recommendation | ⏳ PENDING | Main demo behavior |
| Human approval → reroute | ⏳ PENDING | Operator remains in control |
| Live tracking integration | ⏳ LATER | Socket.IO / simulated telemetry in MERN |
| Offline field workflow | ⏳ LATER | Small queued incident sync; not a large native app |

---

## 5. Current Checkpoint

**Checkpoint 8 — Risk Engine v0.1 complete + review fixes**

Completed:
- Risk specification finalized
- Internal specification contradiction corrected
- Deterministic Python implementation completed
- 34 original Risk Engine tests passed before review fixes
- Risk policy weights made immutable with a standard-library read-only mapping
- Added explicit immutability tests
- README status synchronized with implementation/tracker
- Dataset label provenance contract added
- OSM acquisition changed to retain full way geometry; normalization now splits geometry into measurable segments with endpoints and haversine segment lengths
- Historical weather cache now records and validates sampling-point, date-range and selection configuration plus per-batch integrity metadata
- Maximum-risk specification case corrected to use accessibility_score=0 and road_condition_score=0 with the other four inputs at 1
- `.gitignore` was already correct and required no change

Deviation audit:
PASS

Review finding disposition:
- README risk status — VALID; fixed
- Dataset label provenance — VALID; fixed
- OSM geometry retention — VALID; fixed, including the downstream normalization required to use geometry
- Weather cache configuration validation — VALID; fixed with a manifest and per-batch integrity checks
- Maximum-risk specification case — VALID; fixed
- Immutable WEIGHTS — VALID; fixed and tested
- `.env` ignore rules — ALREADY SATISFIED; `.gitignore` already contained `.env`, `.env.*`, `!.env.example`, plus the requested environment/cache/log/generated-artifact exclusions; no unnecessary change made

Next approved task:
Network Impact Engine

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

2026-09-12
