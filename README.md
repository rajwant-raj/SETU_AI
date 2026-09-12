# SETU-AI

SETU Intelligence Engine for resilient transportation and logistics in the North Eastern Region (NER).

> **Source of truth:** `SIH26002 — MERN Prototype Blueprint, Repository Benchmark & Implementation Plan.md`
>
> The AI repository must support the SETU product loop without becoming a separate research project. Deterministic intelligence comes first; measured ML comes later.

## Product role

SETU is an intelligent logistics decision-support system that converts real-time network conditions, weather, road accessibility and field incidents into explainable route-risk assessments and actionable rerouting recommendations.

The intended decision loop is:

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

The system is **human-in-the-loop**: AI recommends; the backend orchestrates; the operator approves.

## Blueprint alignment

The blueprint defines three important milestones:

1. Build the complete Incident → Affected Shipment → Risk Recalculation → Alternative Route → Explainable Recommendation → Operator Approval → Reroute loop using MERN.
2. Add live simulated vehicle tracking and weather.
3. Replace the initial deterministic risk score with a measured ML disruption model.

This repository is being developed separately from the MERN application so the intelligence/data work can be prepared cleanly and connected later through a stable API boundary.

## Current status — DATA FOUNDATION

### Completed

- OpenStreetMap/Overpass road acquisition for the Guwahati–Imphal study area
- OSM road normalization
- Core road-network extraction: **8,007 major-road segments**
- Elevation enrichment using representative spatial sampling
- Historical weather exploration/cache for **2019–2024** at 40 representative weather points
- Live-weather module scaffold using the Open-Meteo Forecast API
- Reproducible data-processing scripts kept in Git

### Not started yet

These remain intentionally unbuilt until the deterministic intelligence stage is ready:

- deterministic risk engine
- network impact engine
- accessibility scoring
- ETA/delay engine
- route generation/ranking
- GA/PSO optimization
- ML training/evaluation
- explanation service
- FastAPI integration with the MERN backend

## Repository structure

```text
SETU_AI/
├── src/
│   ├── risk/                  # Risk intelligence
│   ├── impact/                # Network/incident impact
│   ├── eta/                   # ETA and delay estimation
│   ├── routing/               # Route generation/ranking
│   ├── optimization/          # GA/PSO experiments later
│   ├── explanation/           # Explainable recommendations
│   ├── common/                # Shared schemas/utilities/config
│   ├── api/                   # Backend integration boundary later
│   └── data/
│       ├── osm/               # OSM acquisition
│       ├── processing/         # Network/elevation processing
│       └── weather/            # Weather acquisition/cache
│
├── datasets/
│   ├── raw/                   # Downloaded source data; local only
│   ├── processed/             # Generated datasets; local only
│   └── sample/                # Small committed examples
│
├── evaluation/                # Model/algorithm evaluation later
├── tests/                     # Automated tests
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Dataset foundation

### Study area

The current prototype dataset focuses on the **Guwahati → Imphal corridor** and surrounding network required for route-risk experimentation.

### Road data

Source: OpenStreetMap through the Overpass API.

The current processing pipeline retains the normalized road network and derives an 8,007-segment core network using major road classes:

- motorway
- trunk
- primary
- secondary

Tertiary roads remain available in the normalized network for later expansion.

### Elevation

Elevation is enriched from representative spatial points rather than querying every road coordinate independently. The resulting elevation values are cached locally and associated with the 8,007 core segments.

### Weather

The SETU product requirement is **live weather**, while historical weather is useful for later ML training.

The current local cache contains six completed Open-Meteo historical batches covering 2019–2024. The 2025 batch was not completed because the historical endpoint returned repeated HTTP 429 responses. These cached files are retained as exploratory/training data and are not required for the live-weather path.

The official prototype weather direction remains:

```text
Route coordinates
      ↓
Open-Meteo live weather
      ↓
Route segments
      ↓
Risk / ETA / recommendation
```

The live module uses representative weather points so the system does not make one external request per road segment.

## ML target and honesty rule

The eventual first ML problem is:

```text
Predict disruption probability

Input examples:
- rainfall / weather
- terrain
- road condition
- incident history
- connectivity
- other validated operational features

Output:
- disruption probability 0–1
```

A prototype `disruption_proxy` may be derived from available public signals when true road-closure ground truth is unavailable. It must be described as a **derived proxy label**, not as observed road-closure ground truth.

The planned model progression is:

```text
Deterministic weighted risk
        ↓
Logistic Regression baseline
        ↓
Random Forest comparison
        ↓
XGBoost only if justified
```

Evaluation will use a time-aware split and report appropriate metrics such as precision, recall, F1 and ROC-AUC.

## AI architecture

The blueprint explicitly calls for deterministic intelligence before ML:

```text
MERN backend
     │
     ├── incident / shipment / vehicle context
     │
     ▼
Deterministic intelligence
     │
     ├── impact
     ├── accessibility
     ├── risk
     ├── ETA
     └── route ranking
     │
     ▼
Explainable recommendation
     │
     ▼
Human approval
```

Later, the measured ML model can replace the deterministic disruption component:

```text
Node/Express backend
        │
        │ POST /predict
        ▼
Python ML service
        │
        ▼
Disruption model
        │
        ▼
Probability
        │
        ▼
Risk engine
```

The Python service should not be built prematurely; the deterministic system comes first.

## Planned intelligence modules

### 1. Risk

Combine disruption, accessibility, weather and operational factors into an explainable risk assessment.

### 2. Impact

Map a geolocated incident to affected road/network segments and downstream shipments.

### 3. ETA

Estimate baseline travel time and incremental delay after disruptions or route changes.

### 4. Routing

Generate and rank alternatives using ETA, distance, road condition, weather, risk, accessibility and vehicle compatibility.

### 5. Optimization

GA/PSO experiments are later-stage work, not a prerequisite for the core prototype.

### 6. Explanation

Return operational reasons rather than opaque scores, for example:

```text
Risk score: 81

Reasons:
- Heavy rainfall forecast
- High incident exposure
- Poor road condition
- Low accessibility
```

### 7. API

Expose intelligence to the MERN backend only after the core intelligence behavior is stable and tested.

## External services

The blueprint-approved external services include:

- OpenStreetMap / Overpass for road-network data
- Open-Meteo for weather
- Mapbox Directions/Geocoding/Search for application routing and map workflows
- MongoDB Atlas for application data
- Cloudinary/ImageKit for incident photos

External APIs should be used in a **cached/batched** manner where practical. Training and inference must not repeatedly call external APIs.

## Scope guardrails

Do **not** add these merely because they sound technically impressive:

- blockchain
- complex conversational chatbot
- Kafka
- Kubernetes
- premature microservices
- Redis before an actual scaling requirement
- nationwide logistics simulation
- hardware GPS integration for the prototype
- large native mobile application
- advanced deep-learning models without data justification

The future offline mobile app is a planned client for field workflows, not a reason to move the intelligence stack onto the phone.

## Development sequence

The overall SETU blueprint sequence remains:

```text
Phase 1  Foundation
Phase 2  Logistics CRUD
Phase 3  Map
Phase 4  Tracking
Phase 5  Incidents
Phase 6  Deterministic Intelligence
Phase 7  Key Incident → Reroute Demo
Phase 8  Live Weather
Phase 9  ML
Phase 10 Polish / Offline / Deployment
```

Because `SETU_AI` is being developed as a parallel workstream, its current data preparation supports the later phases without changing that product sequence. **We must not let dataset work turn into scope creep or delay the deterministic decision loop.**

## Git/data policy

Generated raw and processed datasets are intentionally ignored by Git. Commit:

- acquisition scripts
- processing scripts
- schemas/specifications
- manifests
- tests
- small sample datasets

Do not force-add large generated data artifacts unless the project plan explicitly requires them.

## Current next step

After the data-foundation checkpoint:

1. Verify the live weather module.
2. Finish the deterministic intelligence specification.
3. Build the risk engine first.
4. Build impact, accessibility, ETA and route ranking around it.
5. Only then construct the final ML training dataset and train/evaluate the disruption model.

This order keeps SETU aligned with the original SIH26002 blueprint and preserves a defensible, explainable prototype.
