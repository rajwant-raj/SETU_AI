# SETU

### Intelligent, disruption-aware logistics decision support for the North Eastern Region

**SETU** is an intelligent logistics decision-support platform designed for transportation through disruption-prone terrain in the North Eastern Region of India.

SETU is built around a simple operational question:

> **When something changes on a route, what is affected, how risky is it, what alternatives exist, how do they compare, and why should an operator choose one?**

A conventional routing system can answer **“What is the shortest route?”**. Real logistics operations need a much richer answer. A route may be geographically available but operationally undesirable because of rainfall, terrain, infrastructure limitations, an incident, increased delay, or network-level consequences.

SETU therefore combines **road-network intelligence, weather, risk, accessibility, ETA, route alternatives, machine-learning disruption assessment, explainable recommendations, secure AI processing, and human approval** into one decision loop.

The core principle is:

**AI recommends → Backend orchestrates → Operator approves → SETU executes the decision.**

SETU is designed for the **SIH26002 logistics problem statement**, with a focus on making route decisions more disruption-aware, explainable, secure, and operationally useful.

---

## 1. The Problem We Are Solving

Logistics routes in the North Eastern Region can be affected by heavy rainfall, difficult terrain, road conditions, incidents, accessibility constraints, delays, and limited network connectivity.

The problem is therefore not simply finding a path between two locations. The real operational problem is:

- understanding what part of the road network is affected;
- estimating the severity and operational risk of the disruption;
- understanding infrastructure accessibility;
- estimating additional travel time and delay;
- finding practical alternative routes;
- comparing alternatives using more than distance alone;
- explaining why one route is preferable;
- protecting sensitive shipment, vehicle, location and operational data; and
- ensuring that an AI recommendation does not silently become an operational decision.

SETU treats these as one connected decision problem instead of separate tools.

---

## 2. Our Proposed Solution

SETU turns a disruption into an **evidence-backed route decision**.

When an incident or changing environmental condition enters the system, SETU can identify potentially affected road segments, assess risk and accessibility, estimate delay, generate alternative routes, compare them, add an ML disruption advisory, explain the trade-offs, and request human approval.

The system deliberately separates **prediction, recommendation, operational authority, and security**.

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
      Secure AI Boundary
       / TEE Protection
            │
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

The important idea is that SETU does not ask an ML model to independently control a shipment. Intelligence produces evidence and recommendations; the application backend controls workflow; an authorized operator controls the final operational decision.

---

## 3. What SETU Provides

SETU is intended to give a logistics operator a **single decision-support view of a disruption** instead of requiring them to manually interpret several disconnected systems.

The platform brings together:

- **Shipment and route context**
- **Incident location and network impact**
- **Potentially affected road segments**
- **Risk level and contributing factors**
- **Weather severity**
- **Infrastructure accessibility**
- **Estimated travel time and delay**
- **Alternative route candidates**
- **Route scores and trade-offs**
- **ML-based disruption advisory**
- **Human-readable explanations**
- **Human approval before operational rerouting**
- **Secure handling of sensitive operational and AI data**

The goal is not simply to tell an operator *where to go*. The goal is to make the reasoning, evidence, uncertainty, and trade-offs behind a route decision visible and controllable.

---

## 4. Key Features

### 🛣️ Road Network Intelligence

SETU builds a structured road network from **OpenStreetMap (OSM)** data for the Guwahati–Imphal study corridor and surrounding network. The core network contains **8,007 major-road segments**.

The network provides the physical foundation on which impact analysis, accessibility, ETA estimation, and route generation operate.

### ⚠️ Network Impact Analysis

A geolocated incident can be projected onto the road network using spatial proximity and an impact radius. SETU identifies **potentially affected segments** without automatically declaring them closed.

> **Potentially affected ≠ confirmed blocked.**

This distinction is important because a spatially nearby incident does not necessarily mean that every nearby road is physically impassable.

### 🌧️ Weather Intelligence

Historical and live/cached weather pipelines provide precipitation, rainfall duration, wind, gust, temperature and WMO weather-code information that can contribute to route-risk assessment and ML features.

### 📊 Risk Assessment

A deterministic risk engine combines incident severity, weather severity, accessibility risk, road-condition risk, network criticality and current delay into a normalized risk score with explicit risk bands.

The deterministic engine remains an authoritative operational calculation rather than allowing a learned model to silently replace it.

### 🚧 Accessibility Scoring

SETU evaluates infrastructure characteristics such as road class, surface and lane information to produce an **OSM-derived accessibility proxy**.

This represents mapped infrastructure characteristics. It is **not a claim of observed real-time physical passability**.

### ⏱️ ETA & Delay Estimation

The ETA engine calculates baseline and disruption-aware travel time for different vehicle profiles and can account for blocked segments and disruption-induced delay.

### 🗺️ Alternative Route Generation

SETU generates multiple feasible route candidates over the road graph rather than relying on one shortest-path answer.

### ⚖️ Route Ranking

Candidate routes are compared using deterministic factors including:

- ETA
- Risk
- Accessibility
- Distance
- Vehicle compatibility

This makes route selection a transparent multi-factor decision rather than an opaque prediction.

### 🧠 ML Disruption Advisory

A trained Random Forest model provides an additional disruption assessment for road segments. It is an **auxiliary decision signal**, not the authority for declaring roads blocked or changing routes.

### 💡 Explainable Recommendations

SETU produces structured explanations showing the important factors and trade-offs behind a recommendation so that an operator can understand the reasoning before approving it.

### 🔄 Digital Twin / What-If Simulation

A lightweight in-memory Digital Twin provides state and event handling for fleet, shipment and network scenarios and supports isolated what-if evaluation without introducing unnecessary infrastructure.

### 👤 Human-in-the-Loop Rerouting

Recommendations enter a `PENDING_APPROVAL` state. The operational route changes only after an authorized operator explicitly approves the recommendation.

### 🔐 Secure AI Processing with a Trusted Execution Environment

SETU is designed to protect sensitive logistics and AI workloads with a **Trusted Execution Environment (TEE)** as part of its security architecture.

A TEE is a hardware-backed isolated execution environment in which sensitive computation can run separately from the normal host operating environment. The objective is to reduce the amount of sensitive information exposed to the host OS, hypervisor, administrators, or other workloads, while providing a way to cryptographically verify that approved code is running.

For SETU, the TEE is especially relevant because the intelligence layer may process sensitive operational information such as:

- shipment details;
- vehicle and driver context;
- GPS/location information;
- incident information;
- route plans and alternative routes;
- operational timing and ETA information; and
- ML model inputs and inference results.

The intended security boundary is:

```text
                    SETU Backend
                         │
                 Authenticated Request
                         │
                         ▼
              ┌─────────────────────┐
              │   TEE Boundary      │
              │                     │
              │ Sensitive Inputs    │
              │ Feature Construction│
              │ ML Inference        │
              │ Sensitive Decisions │
              │ Key Material Access │
              │                     │
              └─────────┬───────────┘
                        │
                 Attested Result
                        │
                        ▼
              Backend / Operator UI
```

The TEE should not become a replacement for SETU's deterministic safety rules or human approval. It is a **security boundary around sensitive computation**.

#### What we should implement

The TEE design for SETU should include the following controls:

1. **Hardware-backed isolation**  
   Run the protected inference workload inside a hardware-backed confidential-computing environment rather than treating a normal process boundary as sufficient protection.

2. **Remote attestation**  
   Before releasing protected data or keys, a trusted verifier should be able to verify that the expected TEE workload is running. Attestation should bind the workload identity/version to the security decision.

3. **Encrypted data in transit and at rest**  
   TEE protection should complement, not replace, TLS and encrypted storage. Sensitive information should remain encrypted outside the protected execution boundary.

4. **Minimal plaintext exposure**  
   Shipment, GPS, incident and model-sensitive data should enter plaintext only where required for the protected computation. Logs, telemetry and debugging output must avoid leaking sensitive values.

5. **Protected model and inference inputs**  
   The ML model and sensitive feature vector should be handled inside the protected execution boundary where the deployment environment supports it. Model access should not expose unnecessary sensitive artifacts to the host.

6. **Sealed / protected secrets**  
   Keys, credentials or other sensitive inference secrets should be released to the workload only after the required attestation and authorization checks succeed.

7. **Measured, versioned workload**  
   The TEE workload should have a reproducible identity so that the verifier can distinguish an approved SETU inference build from an unexpected or modified workload.

8. **Fail-closed security behavior**  
   If attestation fails, the expected workload identity does not match, or required protected resources cannot be established, sensitive data should not be released to the protected workload.

9. **No autonomous operational authority**  
   Even inside a TEE, ML inference must not receive authority to silently reroute shipments. The secure computation produces evidence/advisory output; backend policy and authorized human approval remain the operational control plane.

10. **Auditable security events**  
    Record security-relevant events such as attestation success/failure, workload version, authorization decisions and inference request identifiers without logging the sensitive payload itself.

#### How TEE fits the SETU architecture

TEE should protect the **confidentiality and integrity of sensitive intelligence processing**; it does not solve every security problem. Authentication, authorization, API security, device security, encrypted communication, secure storage, audit logging and operator access control remain necessary.

The exact TEE technology should be selected according to the deployment hardware. Candidate confidential-computing approaches include CPU-based technologies such as **Intel TDX** or **AMD SEV-SNP**, while deployments requiring confidential GPU inference can use a compatible **GPU confidential-computing architecture**. The deployment layer should remain abstract so SETU's intelligence contract is not tied to one vendor.

The architectural principle is therefore:

**Protect the data → attest the workload → execute sensitive AI → return the minimum necessary result → keep operational authority outside the model.**

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

**8. Protect sensitive AI processing**  
Where confidential-computing infrastructure is available, sensitive feature construction and inference are executed inside the TEE after the workload passes the required authorization/attestation checks.

**9. Explain the recommendation**  
SETU presents the important factors, evidence and trade-offs in human-readable form.

**10. Request human approval**  
The recommendation remains pending until an authorized operator reviews it.

**11. Reroute and update state**  
Only an approved decision changes the operational route/state.

This architecture deliberately separates **prediction, secure computation, recommendation, operational authority, and execution**.

---

## 6. System Architecture

```text
                              SETU PLATFORM
                                   │
                  ┌────────────────┴────────────────┐
                  │                                 │
           Application Layer                  Intelligence Layer
                  │                                 │
             MERN Backend                    Deterministic Engines
                  │                         ┌────────┼────────┐
      Shipments / Routes / Users            │        │        │
      Tracking / APIs / Events            Risk     Impact     ETA
                  │                         │        │        │
                  │                  Accessibility Weather Routing
                  │                         │        │        │
                  │                         └────────┼────────┘
                  │                                  │
                  │                           Digital Twin
                  │                                  │
                  │                             ML Advisory
                  │                                  │
                  │                         ┌────────▼────────┐
                  │                         │ Secure AI Layer │
                  │                         │       TEE       │
                  │                         │ Attestation     │
                  │                         │ Protected ML    │
                  │                         └────────┬────────┘
                  │                                  │
                  │                           Explanation
                  │                                  │
                  └──────────────────────────► Human Approval
                                                     │
                                             Approve / Reject
                                                     │
                                                     ▼
                                             Route Decision
                                                     │
                                                     ▼
                                          Operational State
```

### Application layer

The MERN application is responsible for operational entities, APIs, authentication/authorization, shipment and route state, operator interaction, tracking, events, and integration with field clients.

### Intelligence layer

The Python intelligence layer contains the deterministic engines and ML advisory responsible for understanding network impact, risk, accessibility, ETA, routes, explanations and disruption signals.

### Secure AI layer

The TEE forms a security boundary around sensitive computation where confidential-computing hardware is available. It should expose only the minimum result required by the application while keeping protected inputs, secrets and model execution inside the attested environment.

### Operational authority

The backend and authorized operator remain outside the ML model's control loop. A model output is never equivalent to a route-change command.

### Offline field client

A future offline mobile application is intended to act as the field-facing client for assigned shipments/routes, GPS updates, incidents, notifications and offline synchronization. The AI intelligence remains server-side; the mobile layer is a field client and synchronization layer.

---

## 7. Where AI / ML Fits

SETU is **not** designed as an LLM that independently decides where a truck should travel.

The intelligence stack has two complementary parts.

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

- declare a road closed by itself;
- replace the Risk Engine;
- change deterministic route-ranking weights;
- autonomously reroute a shipment; or
- bypass operator approval.

### Secure ML

Where TEE infrastructure is deployed, sensitive ML inference can be isolated from the normal host environment. The TEE protects the computation; the ML model still remains an advisory component and does not receive operational authority.

The intended relationship is:

```text
Sensitive Operational Data
          │
          ▼
   Authenticated Request
          │
          ▼
   Attested TEE Workload
          │
          ▼
   ML / Intelligence
          │
          ▼
Recommendation + Evidence
          │
          ▼
Backend Orchestration
          │
          ▼
PENDING_APPROVAL
          │
          ▼
Operator Review
       /       \
   Approve     Reject
      │           │
      ▼           ▼
 Operational   Keep Current
   Action         Route
```

This keeps AI useful without making the system dependent on an opaque autonomous decision.

---

## 8. Dataset & Data Foundation

SETU's intelligence layer is built on **road-network, terrain, weather and disruption-context data**.

### Road Network — OpenStreetMap

- Source: **OpenStreetMap**, acquired through the Overpass API
- Study area: **Guwahati–Imphal corridor and surrounding network**
- Core network: **8,007 major-road segments**
- Main core road classes: motorway, trunk, primary and secondary

OSM attributes are also used for infrastructure accessibility features such as road class, surface and lane information.

### Elevation

Road segments are enriched with representative elevation data to capture terrain context and support route intelligence and the ML feature foundation.

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

- temporal encodings;
- latitude / longitude;
- elevation;
- road-type rank;
- paved-surface indicator;
- lane count;
- connectivity proxy;
- accessibility score;
- weather-point distance;
- precipitation and rainfall;
- precipitation duration;
- temperature features;
- wind and gust; and
- WMO weather severity.

### Important Dataset Limitation

The ML target, `disruption_proxy`, is a **deterministically engineered prototype label**, derived from environmental/disruption thresholds and infrastructure conditions. It is not observed road-closure ground truth.

Therefore, ML evaluation demonstrates how well the model reproduces the engineered disruption rule. It should **not** be interpreted as proof of real-world road-closure forecasting or real-time physical passability prediction.

This distinction is an intentional part of SETU's technical methodology.

---

## 9. ML Training & Inference

The supervised ML pipeline evaluates:

- Logistic Regression baseline
- Random Forest
- HistGradientBoosting

The selected model is the **Random Forest** model.

Training follows a chronological split:

| Dataset | Period | Purpose |
|---|---|---|
| Train | 2019–2022 | Model training |
| Validation | 2023 | Model/threshold selection |
| Test | 2024 | Final holdout evaluation |

The frozen Random Forest decision threshold is **0.30**.

Inference uses the same canonical 24-feature contract established during training. The Random Forest receives raw, unscaled features; the StandardScaler is reserved for the linear baseline.

At inference, SETU can produce segment-level disruption probability and route-level aggregation such as mean disruption probability, peak probability and disrupted segment count.

The ML probability is an **advisory model output**, not a calibrated claim of real-world road-closure probability.

Model artifacts remain local/gitignored rather than being committed to the repository.

---

## 10. Safety, Explainability, Security & Governance

SETU intentionally avoids turning an uncertain model output into an irreversible operational action.

### 1. Affected does not automatically mean blocked

Spatial impact analysis identifies potentially affected infrastructure. A segment becomes operationally blocked only through the appropriate explicit operational state.

### 2. AI does not silently override deterministic intelligence

ML is an auxiliary signal. Deterministic route generation, ranking, risk and ETA remain the operational foundation.

### 3. Human approval is mandatory

A reroute recommendation remains `PENDING_APPROVAL` until an authorized operator explicitly approves it.

### 4. Sensitive AI computation should be protected

A TEE provides an additional hardware-backed security boundary for sensitive inference workloads. Attestation and authorization should be required before protected secrets or sensitive inputs are released.

### 5. Security should fail closed

If the protected execution environment cannot be trusted, the system should not release sensitive information merely to obtain an AI result. A secure failure should preserve the existing operational route rather than silently degrade into an untrusted sensitive computation path.

### 6. Explanations remain part of the decision

The operator should be able to understand the important factors behind a recommendation rather than receiving an unexplained model score.

Together these controls provide an auditable path from:

**incident → evidence → risk → alternatives → ML advisory → secure computation → recommendation → human decision → action**

---

## 11. Technology Architecture

### Application

**MERN architecture** with React, Node.js/Express and Socket.IO where applicable.

### Intelligence

**Python 3.10**, scikit-learn, NumPy and SciPy.

### Road data

**OpenStreetMap / Overpass**.

### Weather

**Open-Meteo** historical and live/cached weather paths.

### Machine Learning

Logistic Regression, Random Forest and HistGradientBoosting, with the Random Forest used for the disruption advisory.

### Security

TLS, authenticated/authorized application access, encrypted storage, audit controls and a **TEE/confidential-computing boundary for sensitive AI processing** where supported by the deployment hardware.

The architecture deliberately avoids unnecessary infrastructure such as Kafka, Redis, or a separate ML microservice unless a later deployment requirement justifies it.

The Python ML inference contract is intentionally kept independent from the final confidential-computing platform so that SETU can be deployed on compatible CPU or GPU confidential-computing infrastructure without redesigning the decision layer.

---

## 12. Project Structure

```text
SETU_AI/
├── src/
│   ├── data/           # OSM, weather and data-processing pipelines
│   ├── risk/           # Deterministic risk engine
│   ├── impact/         # Network impact analysis
│   ├── accessibility/  # Infrastructure accessibility
│   ├── eta/            # ETA and delay calculation
│   ├── digital_twin/   # State, events and simulation
│   ├── routing/        # Candidate generation and ranking
│   ├── explanation/    # Explainable recommendations
│   ├── reroute/        # Incident-to-reroute orchestration
│   └── ml/             # ML training and inference
├── datasets/           # Specifications, samples and local data
├── models/             # Local, gitignored model artifacts
├── tests/              # Regression and component tests
├── README.md           # Product, problem and architecture overview
├── HOW-TO-BUILD.md     # Engineering build and validation guide
└── TASK_TRACKER.md     # Checkpoint development history
```

The repository documentation is intentionally separated by purpose:

- **README.md** explains the problem, proposed solution, architecture, AI/ML role, security model and overall product so a new reader can understand SETU without reading the implementation history first.
- **HOW-TO-BUILD.md** contains the detailed engineering methodology, validation rules, invariants, build process and rollback discipline.
- **TASK_TRACKER.md** contains checkpoint-by-checkpoint engineering history and development decisions.

---

## 13. Why This Approach Fits the Problem

SETU is designed around the reality that logistics disruption management is not a single prediction problem.

A useful system must combine several kinds of reasoning:

**Where is the disruption?**  
Network Impact answers this spatially.

**How dangerous or operationally important is it?**  
Risk and weather intelligence provide deterministic assessment.

**Can the road infrastructure reasonably support the movement?**  
Accessibility provides an infrastructure-based proxy.

**How much time could the disruption add?**  
ETA and delay estimation quantify the operational consequence.

**What else can the vehicle do?**  
Route generation creates alternatives.

**Which alternative is the best trade-off?**  
Deterministic route ranking compares ETA, risk, accessibility, distance and vehicle compatibility.

**What does the ML model think?**  
The disruption model adds an independent advisory signal.

**Why is this route recommended?**  
The explanation layer exposes the important evidence and trade-offs.

**Can sensitive information be protected while AI is running?**  
The TEE architecture provides a hardware-backed confidential-computing boundary for sensitive inference where supported.

**Who makes the final operational decision?**  
The authorized operator does.

This produces a complete decision-support loop rather than an isolated route predictor.

---

## 14. Vision

SETU aims to become a practical bridge between **logistics operations and intelligent infrastructure decision-making** for difficult and disruption-prone corridors.

The long-term goal is not simply to build another route planner. It is to build a system that can:

- understand the road network;
- understand changing environmental and incident conditions;
- estimate operational consequences;
- generate and compare alternatives;
- use ML without surrendering operational control;
- protect sensitive logistics and AI workloads;
- explain its recommendations; and
- keep a human decision-maker in control of consequential actions.

The vision can be summarized as:

> **A secure, explainable and disruption-aware logistics intelligence system that helps operators make better route decisions when the real world does not behave like a static map.**

SETU is therefore not just a shortest-path engine and not an autonomous AI dispatcher. It is a **secure human-in-the-loop decision-support platform for disruption-aware logistics**.
