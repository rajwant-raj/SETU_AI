# SETU

### Intelligent, disruption-aware logistics decision support for the North Eastern Region

**SETU** is an intelligent logistics decision-support platform designed for the challenges of transportation through disruption-prone terrain in the North Eastern Region of India.

SETU helps a logistics operator answer a practical question:

> **When something changes on the route, what is the impact, which alternatives are available, how do they compare, and why should one be chosen?**

Instead of relying on a single routing algorithm or an opaque AI decision, SETU combines **road-network intelligence, weather, risk, accessibility, ETA, route alternatives, machine-learning disruption assessment, and explainable recommendations** into one decision loop.

The core principle is simple:

**AI recommends → Backend orchestrates → Operator approves → SETU executes the decision.**

SETU is designed to support the SIH26002 logistics problem statement while keeping operational decisions explainable, testable, and under human control.

---

## 1. The Problem

Logistics routes do not fail only because a road disappears from a map. In the North Eastern Region, heavy rainfall, difficult terrain, road conditions, incidents, accessibility constraints, delays, and network connectivity can all affect whether a route remains practical.

A conventional shortest-path system can answer **"What is the shortest route?"** but an operations team needs more:

- Which part of the network is affected by an incident?
- How severe is the disruption?
- How accessible is the affected road infrastructure?
- How much additional travel time could be introduced?
- What alternative routes are available?
- Which alternative provides the best trade-off between time, risk, accessibility and distance?
- Why is that route being recommended?
- Should the operator actually approve the change?

SETU is built around this complete operational decision rather than routing alone.

---

## 2. Our Proposed Solution

SETU turns a disruption into an **evidence-backed route decision**.

When an incident or changing condition is introduced, SETU can identify potentially affected road segments, assess their risk and accessibility, estimate delay, generate alternative routes, compare those routes, and produce an explanation for the recommendation.

A machine-learning model adds an additional disruption assessment to the decision context, but it does not replace the deterministic intelligence or automatically make the operational decision.

The resulting recommendation remains subject to human approval before the operational route is changed.

```text
Incident / Changing Condition
            │
            ▼
     Network Impact
            │
            ▼
   Risk + Weather +
     Accessibility
            │
            ▼
       ETA / Delay
            │
            ▼
   Alternative Routes
            │
            ▼
     Route Ranking
            │
       ┌────┴────┐
       │         │
       ▼         ▼
 Explanation   ML Disruption
               Advisory
       │         │
       └────┬────┘
            ▼
     Human Approval
            │
      ┌─────┴─────┐
      │           │
   Approve      Reject
      │           │
      ▼           ▼
   Reroute    Keep Current
      │
      ▼
 Updated Operational State
```

---

## 3. What SETU Presents

SETU is intended to give an operator a **single decision-support view of a disruption**, rather than forcing them to interpret separate systems.

The intelligence layer can provide:

- **Current route and shipment context**
- **Incident location and network impact**
- **Potentially affected road segments**
- **Risk level and contributing factors**
- **Weather severity**
- **Infrastructure accessibility**
- **Estimated travel time and delay**
- **Alternative route candidates**
- **Route scores and trade-offs**
- **ML-based disruption advisory**
- **Human-readable explanation of the recommendation**
- **Pending approval state before operational commitment**

The goal is not simply to tell an operator *where to go*. It is to make the reasoning behind a route decision visible.

---

## 4. Key Features

### 🛣️ Road Network Intelligence

SETU builds a structured road network from **OpenStreetMap (OSM)** data for the Guwahati–Imphal study corridor and surrounding network. The current core network contains **8,007 major-road segments**.

### ⚠️ Network Impact Analysis

A geolocated incident can be projected onto the road network using spatial proximity and impact radius. SETU identifies **potentially affected segments** without automatically declaring them closed.

> **Potentially affected ≠ confirmed blocked.**

### 🌧️ Weather Intelligence

Historical and live/cached weather pipelines provide precipitation, wind, gust, temperature and weather-severity information that can feed route-risk assessment.

### 📊 Risk Assessment

A deterministic risk engine combines incident severity, weather, accessibility, road condition, network criticality and current delay into a normalized risk score with explicit risk bands.

### 🚧 Accessibility Scoring

SETU evaluates road infrastructure characteristics such as road class, surface and lanes to produce an **OSM-derived accessibility proxy**.

This represents infrastructure characteristics; it is **not a claim of observed real-time passability**.

### ⏱️ ETA & Delay Estimation

The ETA engine calculates baseline and disruption-aware travel time for different vehicle profiles and can account for blocked segments and disruption-induced delay.

### 🗺️ Alternative Route Generation

SETU generates multiple route candidates over the road graph rather than relying on one alternative.

### ⚖️ Route Ranking

Candidate routes are compared using deterministic factors including:

- ETA
- Risk
- Accessibility
- Distance
- Vehicle compatibility

This makes route selection a transparent multi-factor decision instead of a black-box prediction.

### 🧠 ML Disruption Advisory

The trained Random Forest model provides an additional disruption assessment for route segments. It is integrated as an **auxiliary decision signal**, not as the authority for blocking roads or changing routes.

### 💡 Explainable Recommendations

SETU generates structured explanations showing the relevant trade-offs behind a route recommendation so that an operator can understand the decision before approving it.

### 🔄 Digital Twin / What-If Simulation

A lightweight in-memory Digital Twin provides state and event handling for fleet, shipment and network scenarios and supports isolated what-if evaluation without introducing unnecessary infrastructure.

### 👤 Human-in-the-Loop Rerouting

Recommendations enter a `PENDING_APPROVAL` state. The operational route is changed only after an authorized operator explicitly approves the recommendation.

---

## 5. End-to-End SETU Workflow

The complete intelligence workflow is:

**1. Detect / receive a disruption**  
An incident or changing environmental condition enters the operational context.

**2. Identify network impact**  
SETU maps the disruption to potentially affected road segments.

**3. Assess risk**  
Incident, weather, accessibility, road and delay factors are evaluated deterministically.

**4. Estimate accessibility and ETA**  
The system evaluates infrastructure constraints and expected travel-time impact.

**5. Generate alternatives**  
Multiple feasible route candidates are generated from the road network.

**6. Rank alternatives**  
Routes are compared using deterministic multi-factor scoring.

**7. Add ML advisory**  
The disruption model provides an additional segment/route-level disruption assessment.

**8. Explain the recommendation**  
SETU presents the important factors and trade-offs in human-readable form.

**9. Request human approval**  
The recommendation remains pending until an operator reviews it.

**10. Reroute and update state**  
Only an approved decision changes the operational route/state.

This architecture deliberately separates **prediction, recommendation and operational authority**.

---

## 6. Architecture

```text
                         SETU PLATFORM
                              │
             ┌────────────────┴────────────────┐
             │                                 │
       Application Layer                 Intelligence Layer
             │                                 │
        MERN Backend                    Deterministic Engines
             │                                 │
       Shipments / Routes          ┌───────────┼───────────┐
       Tracking / Operators        │           │           │
       APIs / Events              Risk       Impact       ETA
                                  │           │           │
                           Accessibility   Weather      Routing
                                  │           │           │
                                  └──────┬────┴───────────┘
                                         │
                                  Digital Twin
                                         │
                                  ML Advisory
                                         │
                                   Explanation
                                         │
                                  Human Approval
                                         │
                                  Route Decision
```

The current intelligence workstream is implemented in Python and is designed to connect to the MERN application through a stable backend integration boundary.

The current ML inference component is an **in-process Python `DisruptionInferenceEngine`**. It is intentionally not deployed as a separate FastAPI/Flask microservice at this stage.

The next approved integration step is:

**Checkpoint 21 — MERN Backend Intelligence Boundary / API Integration**

A future offline mobile client is intended to act as a field-facing client for assigned shipments/routes, GPS updates, incidents, notifications and offline synchronization. The AI intelligence remains server-side; the mobile layer is a client and synchronization layer.

---

## 7. Where AI / ML Fits

SETU is not designed as an LLM that independently decides where a truck should travel.

The intelligence stack has two complementary parts:

### Deterministic Intelligence

Provides the authoritative operational calculations:

- Risk
- Network Impact
- Accessibility
- ETA / Delay
- Route Candidate Generation
- Route Ranking
- Explanation
- Digital Twin state and simulation

### Machine Learning

The current ML model provides an additional **disruption assessment** based on historical environmental, spatial and infrastructure features.

The model does not:

- declare a road closed by itself
- replace the Risk Engine
- change deterministic route-ranking weights
- autonomously reroute a shipment
- bypass operator approval

The intended decision relationship is:

```text
ML / Intelligence
       ↓
Recommendation + Evidence
       ↓
Backend Orchestration
       ↓
PENDING_APPROVAL
       ↓
Operator Review
       ↓
Approve / Reject
       ↓
Operational Action
```

This keeps AI useful without making the system dependent on an opaque autonomous decision.

---

## 8. Dataset & Data Foundation

SETU's intelligence layer is built on a combination of **road-network, terrain, weather and disruption-context data**.

### Road Network — OpenStreetMap

- Source: **OpenStreetMap**, acquired through the Overpass API
- Study area: **Guwahati–Imphal corridor and surrounding network**
- Core network: **8,007 major-road segments**
- Main core road classes: motorway, trunk, primary and secondary

OSM attributes are also used for infrastructure accessibility features such as road class, surface and lane information.

### Elevation

Road segments are enriched with representative elevation data to capture terrain context and support the route intelligence and ML feature foundation.

### Weather — Open-Meteo

Historical weather data covers:

- **2019–2024**
- **40 representative weather points**
- **2,192 calendar days**

The weather foundation includes precipitation, rainfall duration, temperature, wind, gusts and WMO weather codes. A separate live/cached weather path supports current-condition integration.

### ML Dataset

The ML dataset contains **17,551,344 segment-day observations** across the six-year 2019–2024 period.

Each observation represents one road segment on one calendar day and combines spatial, road, accessibility and weather context.

The model uses a strict **24-feature canonical input vector**, including:

- temporal encodings
- latitude / longitude
- elevation
- road-type rank
- paved-surface indicator
- lane count
- connectivity proxy
- accessibility score
- weather-point distance
- precipitation and rainfall
- precipitation duration
- temperature features
- wind and gust
- WMO weather severity

### Important Dataset Limitation

The ML target, `disruption_proxy`, is a **deterministically engineered prototype label**, derived from environmental/disruption thresholds and infrastructure conditions. It is not observed road-closure ground truth.

Therefore, the ML evaluation demonstrates how well the model reproduces the engineered disruption rule. It should **not** be interpreted as proof of real-world road-closure forecasting or real-time physical passability prediction.

This distinction is an intentional part of SETU's technical methodology.

---

## 9. ML Training & Inference

The supervised ML pipeline evaluates three models:

- Logistic Regression baseline
- Random Forest
- HistGradientBoosting

The current champion is the **Random Forest** model.

Training follows a chronological split:

| Dataset | Period | Purpose |
|---|---|---|
| Train | 2019–2022 | Model training |
| Validation | 2023 | Model/threshold selection |
| Test | 2024 | Final holdout evaluation |

The frozen Random Forest decision threshold is **0.30**.

Inference uses the same canonical 24-feature contract established during training. The Random Forest receives raw, unscaled features; the StandardScaler is reserved for the linear baseline.

At inference, SETU can produce segment-level disruption probability and route-level aggregation such as mean disruption probability, peak probability and disrupted segment count.

The model artifacts remain local/gitignored rather than being committed to the repository.

---

## 10. Safety, Explainability & Governance

SETU intentionally avoids turning an uncertain model output into an irreversible operational action.

Three rules are central:

### 1. Affected does not automatically mean blocked

Spatial impact analysis identifies potentially affected infrastructure. A segment becomes operationally blocked only through the appropriate explicit operational state.

### 2. AI does not silently override deterministic intelligence

The ML assessment is an auxiliary signal. Deterministic route generation and ranking remain the operational foundation.

### 3. Human approval is mandatory

A reroute recommendation remains `PENDING_APPROVAL` until an authorized operator explicitly approves it.

This provides an auditable path from **incident → evidence → recommendation → human decision → action**.

---

## 11. Current Implementation Status

| Capability | Status |
|---|:---:|
| OSM road acquisition | ✅ |
| OSM normalization | ✅ |
| Core road network | ✅ |
| Elevation enrichment | ✅ |
| Historical weather foundation | ✅ |
| Live/cached weather integration | ✅ |
| Risk Engine | ✅ |
| Network Impact Engine | ✅ |
| Accessibility scoring | ✅ |
| ETA / Delay Engine | ✅ |
| Thin Digital Twin | ✅ |
| Route candidate generation | ✅ |
| Route ranking | ✅ |
| Explainable recommendations | ✅ |
| Incident → Reroute / Human Approval loop | ✅ |
| ML dataset construction | ✅ |
| ML training & evaluation | ✅ |
| ML inference / decision-layer integration | ✅ |
| MERN Backend Intelligence Boundary | 🔜 Next |
| Offline mobile client integration | 🔜 Future |

### Current checkpoint

**Checkpoint 20 — Decision-Layer Integration / ML Inference Service — COMPLETE**

### Next approved checkpoint

**Checkpoint 21 — MERN Backend Intelligence Boundary / API Integration**

---

## 12. Technology Stack

**Application:** MERN architecture, React, Node.js/Express, Socket.IO where applicable  
**Intelligence:** Python 3.10, scikit-learn, NumPy, SciPy  
**Road data:** OpenStreetMap / Overpass  
**Weather:** Open-Meteo  
**ML:** Logistic Regression, Random Forest, HistGradientBoosting  
**Architecture:** deterministic intelligence + ML advisory + human approval

The intelligence layer deliberately avoids unnecessary infrastructure such as Kafka, Redis, or separate ML microservices for the current prototype stage.

---

## 13. Project Structure & Further Documentation

```text
SETU_AI/
├── src/
│   ├── data/          # OSM, weather and data-processing pipelines
│   ├── risk/          # Deterministic risk engine
│   ├── impact/        # Network impact analysis
│   ├── accessibility/ # Infrastructure accessibility
│   ├── eta/           # ETA and delay calculation
│   ├── digital_twin/  # State, events and simulation
│   ├── routing/       # Candidate generation and ranking
│   ├── explanation/   # Explainable recommendations
│   ├── reroute/       # Incident-to-reroute orchestration
│   └── ml/            # ML training and inference
├── datasets/          # Specifications, samples and local data
├── models/            # Local, gitignored model artifacts
├── tests/             # Regression and component tests
├── README.md
├── HOW-TO-BUILD.md
└── TASK_TRACKER.md
```

For the detailed engineering architecture, checkpoint methodology, validation rules, invariants, build process and rollback discipline, see **`HOW-TO-BUILD.md`**.

For checkpoint-by-checkpoint development history and active implementation work, see **`TASK_TRACKER.md`**.

---

## 14. Vision

SETU is intended to become a practical bridge between **logistics operations and intelligent infrastructure decision-making** for difficult and disruption-prone corridors.

The long-term goal is not simply to build another route planner. It is to build a system that can:

**Understand the network → assess disruption → generate alternatives → explain the trade-offs → let an operator decide → execute and track the approved plan.**

That is the role of SETU: **an intelligent, explainable and human-governed decision layer for resilient logistics.**
