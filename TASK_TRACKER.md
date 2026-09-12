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

**Checkpoint 13 — Route Candidate Generation complete**

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

Deviation audit:
PASS

Next approved task:
Checkpoint 14 — Route Ranking

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

2026-09-13
