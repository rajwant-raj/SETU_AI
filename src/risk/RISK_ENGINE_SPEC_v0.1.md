# SETU Risk Engine v0.1

## 1. Purpose

The Risk Engine converts incident, weather, accessibility, road-condition and operational context into a deterministic, explainable risk assessment for a road segment or route.

It is the first intelligence component in SETU's decision-support loop:

```text
Incident
  ↓
Network Impact
  ↓
Risk Assessment  ← this module
  ↓
Accessibility
  ↓
Route Alternatives
  ↓
Comparison
  ↓
Explanation
  ↓
Human Approval
```

The engine recommends a risk level; it does not autonomously reroute vehicles or replace the backend/operator.

## 2. Scope for v0.1

v0.1 is deliberately deterministic and lightweight.

Included:

- normalized feature inputs
- weighted risk score from 0–100
- LOW / MEDIUM / HIGH / CRITICAL bands
- machine-readable reason codes
- human-readable reasons
- missing-input handling
- deterministic output for identical input

Not included:

- ML models
- LLM calls
- RAG/vector databases
- GA/PSO optimization
- live API calls from inside the engine
- automatic rerouting
- traffic-provider integration
- learned weights

Those belong to later checkpoints in the approved execution order.

## 3. Input contract

The implementation should accept a plain Python object/dictionary (later formalized with shared schemas if needed).

| Input | Expected range/type | Role |
|---|---|---|
| `incident_severity` | 0–1 | Direct disruption signal |
| `accessibility_score` | 0–1 | Road/route accessibility; 1 = fully accessible |
| `weather_severity` | 0–1 | Normalized adverse-weather signal |
| `road_condition_score` | 0–1 | 1 = good condition, 0 = poor condition |
| `network_criticality` | 0–1 | Importance/connectivity of the affected segment |
| `current_delay_ratio` | 0–1 | Existing delay relative to baseline |

Raw weather variables such as precipitation, wind speed, gusts and weather code are normalized before reaching this engine. The engine should not call Open-Meteo itself.

## 4. Normalization

All six inputs must be bounded to `[0, 1]` before scoring.

For values already expressed as a normalized score:

```text
x_normalized = clamp(x, 0, 1)
```

For accessibility and road condition, higher values are safer, so convert them to risk contributions:

```text
accessibility_risk = 1 - accessibility_score
road_condition_risk = 1 - road_condition_score
```

`current_delay_ratio` is capped at 1 for v0.1. More advanced delay calibration belongs to the ETA checkpoint.

## 5. Weighted risk formula

The v0.1 score is intentionally interpretable:

```text
risk_score = 100 × (
    0.30 × incident_severity
  + 0.20 × weather_severity
  + 0.15 × accessibility_risk
  + 0.15 × road_condition_risk
  + 0.10 × network_criticality
  + 0.10 × current_delay_ratio
)
```

Weights sum to 1.00.

Rationale:

- Incident severity receives the largest weight because an active field incident is the most direct disruption signal.
- Weather is the next major external hazard signal and is central to SETU's live-weather requirement.
- Accessibility and road condition materially affect whether a route remains usable.
- Network criticality captures the operational consequence of losing an important segment.
- Existing delay is included as a supporting operational signal; the dedicated ETA/delay engine will later provide a stronger calibrated value.

These are **prototype policy weights**, not statistically learned coefficients. They must not be presented as empirically optimal.

## 6. Risk bands

| Score | Level | Operational meaning |
|---:|---|---|
| 0–24.99 | LOW | Normal or minor disruption exposure |
| 25–49.99 | MEDIUM | Monitor conditions; route may remain usable |
| 50–74.99 | HIGH | Significant disruption exposure; alternative route should be considered |
| 75–100 | CRITICAL | Severe disruption exposure; operator review and rerouting should be strongly considered |

Boundary rule: score is continuous; classification uses the lower-inclusive, upper-exclusive intervals above, except 100 remains CRITICAL.

## 7. Explainability

The engine must return both the aggregate score and the factors that materially contribute to it.

Example:

```json
{
  "risk_score": 81.0,
  "risk_level": "CRITICAL",
  "reason_codes": [
    "HIGH_INCIDENT_SEVERITY",
    "ADVERSE_WEATHER",
    "LOW_ACCESSIBILITY"
  ],
  "reasons": [
    "High incident severity",
    "Adverse weather conditions",
    "Low route accessibility"
  ]
}
```

Reason thresholds should be deterministic and documented in code. v0.1 should report the strongest contributing factors rather than generating free-form explanations with an LLM.

Recommended reason thresholds:

- factor risk >= 0.75 → HIGH reason
- factor risk >= 0.50 → MODERATE reason
- otherwise omit the factor from the primary reason list

For accessibility and road condition, use their converted risk values when applying these thresholds.

## 8. Missing inputs

The engine must not silently invent missing operational data.

For v0.1:

- required fields should be validated
- missing required fields should produce a clear validation error
- no external API fallback should occur
- no default value should be presented as observed data

A later integration layer may construct a complete context from backend data, cached weather and incident information before calling the engine.

## 9. Determinism and safety

For identical inputs, v0.1 must return the same score, level and reason codes.

The engine is decision support only:

```text
AI recommendation → Backend orchestration → Human approval → Action
```

The engine must never:

- modify shipment state
- dispatch a vehicle
- approve a reroute
- call an external service
- mutate the road network

## 10. Validation requirements before implementation checkpoint is complete

Tests must cover at minimum:

1. zero-risk operational baseline:
   incident_severity=0,
   weather_severity=0,
   accessibility_score=1,
   road_condition_score=1,
   network_criticality=0,
   current_delay_ratio=0
   → LOW / score 0
   (Note: literal all-zero raw inputs produce 30.0 / MEDIUM because accessibility and road-condition scores are inverted)
2. all-one risk inputs → CRITICAL / score 100
3. accessibility and road-condition inversion
4. each risk-band boundary
5. clamping of normalized values
6. missing required fields
7. deterministic repeated execution
8. reason-code generation
9. weights summing to 1.00

## 11. Blueprint/deviation check

This specification stays inside the approved deterministic-intelligence phase.

It directly supports:

- risk assessment after incident/network impact
- explainable recommendations
- weather and accessibility-aware routing decisions
- later route comparison
- later replacement of the disruption component with measured ML

It deliberately does **not** introduce a new framework, external service, ML model, chatbot, optimization system or infrastructure dependency.

## 12. Next checkpoint

Implement the deterministic Risk Engine in Python as a pure, testable module using this specification. Keep API/FastAPI integration, ML and automatic rerouting out of this checkpoint.
