# SIH26002 — AI-Based Smart Logistics and Accessibility Intelligence Platform for NER
## Complete Implementation Blueprint

**Organization:** Ministry of Development of North Eastern Region (MDoNER) · **Category:** Software · **Theme:** Transportation & Logistics

---

## 0. Official vs Proposed — Read This First

**Official (verbatim from the PS you shared — do not deviate from this):**
- Monitor real-time road/bridge/transport accessibility across districts and remote locations.
- Predict route disruptions from landslides, floods, rainfall, road damage, congestion.
- Give AI-based alternate route suggestions + estimated delays.
- Track essential-commodity vehicles via GPS.
- Auto-generate alerts for blocked roads, inaccessible regions, delayed deliveries, high-risk corridors.
- Let field officials upload geo-tagged updates/photos/incident reports.
- Centralized dashboard: district connectivity status, bottlenecks/supply-chain gaps, emergency accessibility routes, real-time delivery status.
- Multilingual notifications + offline sync for low-network areas.
- Expected solution explicitly names: AI route prediction/optimization engine, GIS accessibility dashboard, GPS vehicle tracking, real-time alerts, mobile/web field app, integration with weather/transport/govt systems, cloud infra with secure data + offline support.

**Everything below this line is our proposed engineering solution to that brief — not official requirements.** Where we go beyond the brief (e.g., specific model choice, specific cloud provider, specific NER pilot districts) it is our design decision, not MDoNER's mandate, and is flagged as such.

**One important reality check to state to judges up front:** NER has thin digital infrastructure — sparse continuous traffic/telemetry data, road-closure info is often manual/PDF/press-release based, and GPS trackers on trucks are not currently mandated. So the platform is designed as a **human-in-the-loop intelligence system**: AI amplifies whatever real data exists (weather, terrain, historical incidents, field reports) rather than assuming a data-rich environment. We say this openly in the demo rather than pretending otherwise.

---

## 1. Problem Understanding

**Simple language:** In the hills of the North East, one landslide or one flood can cut off a whole district for days. Right now nobody has one place to check "is this road open, is it risky today, and what's the best way to send medicine/food/cement there." We're building that one place.

**Technical language:** A GIS-anchored decision-support system that models the NER road network as a weighted graph, ingests weather/terrain/incident/field-report signals to estimate a time-varying "accessibility risk" per road segment, uses that to do risk-aware routing and ETA estimation, tracks essential-supply vehicles spatially, and surfaces all of this through role-based dashboards and alerts, with offline-first mobile capture for field data.

**Government/logistics context:** This sits alongside MDoNER's broader NER infrastructure push (NEC funded roads, PMGSY rural roads, NERAMAC agri-logistics) and complements — not replaces — PWD/BRO road-closure bulletins, IMD/NDMA advisories, and district disaster management authorities. It's an intelligence/coordination layer, not a new road authority.

**Stakeholders:** District administration & DDMAs, State PWD/BRO field engineers, State logistics/supply-chain officers (medicine, PDS food, agri-produce), transporters/drivers of essential-goods vehicles, emergency responders, and (read-only) citizens/local businesses.

**Inputs → Processing → Outputs:**
- Inputs: road network (OSM), terrain (slope/elevation), weather/rainfall, historical incident logs, field reports (photo+geotag+text), vehicle GPS pings, manual PWD closure bulletins.
- Processing: risk scoring per road segment, disruption forecasting, risk-aware route computation, ETA/delay estimation, bottleneck/graph analysis, alert prioritization.
- Outputs: district connectivity map, route recommendation + ETA, push/SMS alerts, live vehicle position, incident feed, downloadable district reports.

**Measurable goals (illustrative, to refine with a real pilot):** % of high-risk segments flagged before an incident is reported manually; median time from field report to alert dispatch; ETA prediction error (MAE in minutes) vs actual; number of districts with live connectivity status coverage.

---

## 2. Research & Existing Solutions (gap analysis)

| Existing system | What it does | Gap for NER logistics |
|---|---|---|
| **Bhuvan (ISRO/NRSC)** | Satellite-based disaster layers incl. landslide/flood susceptibility | No live routing, no vehicle tracking, not logistics-oriented |
| **NDMA / SACHET / State DDMA bulletins** | Disaster alerts, largely manual | Not route-aware, not integrated with transport ETA |
| **PMGSY / PWD road portals** | Road asset inventory | Static, rarely real-time, no predictive layer |
| **Google Maps / OSRM public** | Consumer routing | No risk-awareness, no landslide/flood data, poor rural NER OSM data density in places |
| **State transport dept GPS/AVL systems (where they exist)** | Fleet tracking for public buses | Not extended to essential-goods private/departmental trucks; siloed per state |
| **Private logistics SaaS (Locus, FarEye, etc.)** | Route optimization for commercial fleets | Built for plains/urban dense-data logistics, not landslide/monsoon terrain risk; not govt-integrated, costly licensing |

**Genuine gap:** nobody combines (a) terrain+weather-driven **predictive** accessibility (not just after-the-fact reporting), (b) a routing engine that treats "risk of disruption" as a first-class edge cost, and (c) field-report crowdsourcing from officials as a way to keep sparse NER road data current — in one integrated, offline-tolerant, multilingual platform aimed at essential-goods movement rather than commercial fleets.

### 2a. What we deliberately borrow from Locus/FarEye (adapted, not copied)

Locus and FarEye are built for high-density commercial fleets in data-rich, plains/urban networks with paying shippers — that's a different problem from ours, so we don't adopt them wholesale. But three of their operational patterns generalize well to a government accessibility platform, and we're building them in from day one rather than bolting them on later:

- **Control Tower framing, not a static dashboard.** Both platforms center on one live operational view where exceptions surface on their own — an SLA-risk flag fires the moment a shipment falls behind pace, rather than an operator having to go looking for trouble. We rename our web dashboard the **Control Tower Dashboard** for exactly this reason (Section 5): it's not a reporting screen, it's where a segment's risk crossing a threshold becomes visible immediately, before someone phones it in.
- **Exceptions get an owner and a timer, not just a notification.** FarEye's exception playbooks assign every flagged issue to a person with an SLA clock attached, instead of firing an alert into a general feed. We adopt the same shape for our alert lifecycle (Section 9): every alert is assigned to a specific district officer and carries an acknowledged / in-progress / resolved state with a timer, not a fire-and-forget push.
- **Delivery confirmation as a first-class event, not an afterthought.** Both platforms treat proof-of-delivery (geotag/photo/signature at drop-off) as core operational data, not a bonus feature — it's both a live signal and an audit trail. We add the equivalent for essential-goods drops: a geotagged confirmation photo when a medicine/food/cement consignment actually reaches a district, closing the loop the same way a field report opens one.

**What we deliberately don't borrow:** multi-carrier marketplace features (carrier tendering across 1,000+ integrations), fully autonomous re-dispatch with no human in the loop, and branded shipper-facing tracking pages with commercial SLA-penalty language — none of these fit a single-agency government deployment where the "customer" is a district administration, not a paying shipper, and where "field reports override model predictions" (AGENTS.md) means a human always stays in the loop.

---

## 3. Proposed Solution

**What we're building:** A web dashboard (officials/admins) + a lightweight mobile-first PWA (field officials & drivers) + a backend that fuses GIS, weather, and field data into a live risk-aware routing and monitoring system for essential-goods logistics across NER districts.

**Who uses it, doing what:**
- **State/district logistics officer:** views district connectivity dashboard, sees bottlenecks, dispatches vehicles with AI-suggested routes, receives delay alerts.
- **Field official/PWD engineer:** submits geo-tagged incident reports (photo + short form) from a phone, works offline, syncs later.
- **Driver:** sees current route, live reroute suggestion if risk changes en route, one-tap "report incident."
- **DDMA/emergency responder:** views emergency-mode map (worst-case accessible routes) during a live disaster.
- **Citizen/public (read-only, optional/future):** sees district-level connectivity status only — no operational data.

**System response:** on any new weather/incident/field-report signal, the platform recomputes affected segment risk, re-evaluates active routes, and pushes alerts only to affected users/vehicles (not a blanket broadcast).

---

## 4. Features

**MVP / Must-Have**
- Road network map of a pilot state (e.g., one NER state, 2–3 districts) with accessibility status (open/partial/blocked) per segment
- Weather overlay (rainfall intensity) pulled live
- Manual + field-report incident logging with geotag + photo
- Risk-aware route suggestion between two points with ETA
- Role-based login (admin, field officer, driver)
- Control Tower Dashboard: district connectivity view, incident feed, active-vehicle list (simulated GPS is acceptable for demo)
- Basic push/SMS alert on new blockage on an active route
- Alert lifecycle: every alert assigned to a specific officer, tracked acknowledged / in-progress / resolved with an SLA timer to acknowledge — not just a broadcast (adapted from FarEye's exception-ownership pattern)
- Delivery confirmation: geotagged photo + timestamp captured when an essential-goods vehicle reaches its destination, closing the dispatch loop (our version of a Locus/FarEye proof-of-delivery event)

**Important (V2)**
- Disruption *forecasting* (next 24–48h risk, not just current state) using rainfall + historical pattern model
- ETA delay prediction (regression), not just static shortest path
- Bottleneck detection (graph centrality of frequently-blocked segments), surfaced as a **segment scorecard** — a road-segment version of the carrier/lane scorecards these platforms use to hold carriers accountable, showing which segments are chronically the problem
- Offline-first PWA with local queue + background sync
- Multilingual UI/alerts (Assamese, Bengali, Hindi, English at minimum; Bhashini API for more)
- Vehicle GPS via actual mobile-app tracking (not simulated)

**Optional**
- SMS-based (non-smartphone) reporting via IVR/USSD-like flow for very low-connectivity field staff
- Historical analytics/trend reports per district (monthly disruption count, avg delay)
- Integration with State PWD closure-bulletin scraping (semi-automated ingestion)

**Future / Production**
- Integration with actual departmental fleet telematics / OBD devices
- Cross-state interoperability (all 8 NER states)
- Predictive maintenance flags for chronically weak bridges/culverts (needs asset-condition data we don't have yet — explicitly out of scope until that data source exists)
- Full NIC/MeghRaj government cloud hosting + data-sharing MoUs with PWD/IMD/NDMA

---

## 5. Complete Architecture

```
                        ┌─────────────────────────────────────────┐
                        │              EXTERNAL DATA               │
                        │  OSM roads · Open-Meteo/IMD weather ·     │
                        │  Bhuvan/GSI landslide layers · manual PWD  │
                        │  closure bulletins                         │
                        └───────────────┬───────────────────────────┘
                                        │ scheduled pull / webhook
                                        ▼
┌───────────┐   HTTPS/REST   ┌─────────────────────┐  BSON/2dsphere  ┌───────────────┐
│  Control   │◄──────────────►│   Backend API        │◄───────────────►│   MongoDB      │
│  Tower     │                │  (FastAPI, Python)    │                 │  (road edges   │
│  Dashboard │                │  - Auth/RBAC          │                 │  as GeoJSON,   │
│ (React,    │                │  - Ingestion services  │                 │  incidents,    │
│  officials)│                │  - Risk scoring engine │                 │  vehicles,     │
└───────────┘                │  - Routing service     │                 │  users)        │
┌───────────┐   HTTPS/REST   │  - Alerts/notif engine │                 └───────────────┘
│ Mobile PWA │◄──────────────►│  - WebSocket (live pos)│
│ (field     │  + offline    └──────────┬─────────────┘
│  officers, │    queue                 │ calls
│  drivers)  │                          ▼
└───────────┘
                              ┌─────────────────────┐
                              │  GIS/Routing Engine   │
                              │  (OSRM, custom edge   │
                              │   weights = risk)     │
                              └──────────┬────────────┘
                                        │
                              ┌─────────────────────┐
                              │  AI/ML Service        │
                              │ (risk classifier,     │
                              │  ETA regressor —      │
                              │  served in-process     │
                              │  by the FastAPI app)   │
                              └─────────────────────┘
                                        │
                              ┌─────────────────────┐
                              │ Alerts: FCM push +    │
                              │ SMS (Twilio/MSG91) +   │
                              │ Bhashini translation   │
                              └─────────────────────┘
```

**Component roles (in plain terms):**
- **Control Tower Dashboard:** the officials' control room — map, live exception feed, reports; named "Control Tower" deliberately (Section 2a) because exceptions are meant to surface on their own, not require someone to go looking.
- **Mobile PWA:** what a field officer/driver actually touches — simple forms, big buttons, works with patchy signal.
- **Backend API:** the brain's traffic controller — every request goes through it; it also runs scheduled jobs to pull weather and recompute risk.
- **MongoDB:** single source of truth for everything *except* the routing graph itself — road-edge status/risk, incidents, vehicles, users, alerts, all stored as GeoJSON-bearing documents with a `2dsphere` index.
- **Routing engine (OSRM):** does the actual "shortest/safest path" math on its own pre-built graph (compiled straight from the OSM extract, independent of MongoDB) using the risk-adjusted weights the backend hands it.
- **AI/ML service:** small, explainable models that turn raw signals into a risk score and a delay estimate — not a black box.
- **Alerts:** push notification first, SMS fallback for low-connectivity, translated via a lightweight template system.

---

## 6. GIS & Routing

**A note on the MongoDB switch, up front:** the actual pathfinding graph (nodes/edges/adjacency used to compute a route) is built and held by **OSRM itself**, compiled directly from the OSM `.osm.pbf` extract — it was never stored relationally in the app database even in the PostGIS version. So switching the app database to MongoDB does **not** touch routing correctness. What MongoDB stores instead is the **overlay**: per-edge status/risk, incidents, vehicles, users — the things the app needs to query and render, keyed back to OSRM's edges by OSM way ID. The one thing we genuinely give up is native SQL-style topological joins (e.g., "all edges within this district polygon AND downstream of this blocked edge" in one query) — at pilot scale this is done in two steps (Mongo geospatial query, then a small in-memory graph pass in Python) rather than one PostGIS query, which is a real trade-off, not a free lunch, but is fine at the district/pilot scale this project targets.

**Road network representation:** Pull OSM data for the pilot state via Overpass/`osmium extract`, feed it to OSRM to build the routable graph (nodes = intersections, edges = road segments). Separately, load the same edges into MongoDB's `road_edges` collection as GeoJSON `LineString` documents (length, road class, surface type where tagged, plus the OSM way ID as the join key to OSRM). Each document gets a mutable `risk_score` (0–1) and `status` (open/partial/blocked) field that the AI layer updates — the physical graph lives in OSRM, only the status/cost overlay lives in Mongo and gets read back into the routing request.

**Accessibility status layer:** derived per edge from the latest of (a) field report, (b) PWD bulletin entry (if scraped/entered), (c) model-inferred risk crossing a threshold. Field reports always override model inference (a human on the ground beats a prediction).

**Incident layer:** point/line features (landslide, flood, bridge damage, congestion) with geotag, timestamp, source (field/official/model), and optional photo, stored in MongoDB as GeoJSON `Point`/`LineString` documents (2dsphere-indexed) and shown as map markers.

**Weather overlay:** rainfall intensity (last 24h + forecast) rendered as a heat layer over the district; used both visually and as a routing-cost input.

**Route calculation:** OSRM (self-hosted, `car` + custom rural profile) computes base shortest-time path; before calling OSRM, the backend rewrites edge weights as `adjusted_cost = base_time × (1 + risk_penalty_factor × risk_score)`, so OSRM naturally avoids high-risk edges without us reimplementing pathfinding.

**Risk-aware / dynamic rerouting:** on any risk update along an *active* route, backend recomputes; if the new best path differs materially (e.g., >15% time saved or route no longer blocked), it pushes a reroute suggestion to the relevant driver/officer rather than silently swapping the route.

**Technology choice — final:**
| Need | Choice | Why | Alternative |
|---|---|---|---|
| Road data | OpenStreetMap | Free, community-improvable, only realistic option for NER coverage | Government road GIS layers (patchy availability) |
| App database | **MongoDB** + `2dsphere` index | Flexible document model fits varied report/incident payloads, easy for a student team to iterate schema on, native GeoJSON support covers our actual query needs (nearby incidents, points-in-district) | PostgreSQL + PostGIS (stronger native topological/graph SQL queries — reconsider if the project later needs heavy in-DB spatial joins) |
| Frontend maps | MapLibre GL JS | Open-source, vector tiles, no per-tile licensing cost, good perf | Leaflet (simpler but less performant for large layers) |
| Routing engine | OSRM | Fast, mature, self-hostable, supports custom profiles/weights | GraphHopper (also good, heavier JVM footprint; fine as backup) |

---

## 7. AI/ML — where it genuinely adds value

**Where AI/ML helps (and is justified):**
1. Turning noisy, partial signals (rainfall + slope + season + history) into a single **risk score** per segment — this is a genuine prediction task.
2. **ETA/delay estimation** that accounts for risk, not just distance — regression task.
3. **Bottleneck detection** — mostly graph algorithms, lightly ML-assisted.

**Where AI/ML is *not* forced:** route pathfinding itself is a solved graph algorithm (Dijkstra/A*/contraction hierarchies via OSRM) — we don't need ML for that, just risk-adjusted weights. We explicitly avoid deep learning here: with a hackathon-scale/pilot-scale dataset, gradient-boosted trees and logistic regression will out-generalize a neural net and are explainable to a government judge.

**Task 1 — Road Segment Risk Classification/Scoring**
- Output: risk score 0–1 (or 3-class open/watch/high-risk) per segment per day.
- Features: 24h/72h cumulative rainfall, forecast rainfall next 24h, slope/elevation change along segment, historical incident count on that segment, season (monsoon flag), road surface type, days-since-last-incident, count of recent field reports nearby.
- Model: **Gradient boosted trees (XGBoost/LightGBM)** — handles mixed tabular features well, gives feature importance for explainability.
- Cold-start (no historical incidents yet in pilot): fall back to a simple rule-based score (rainfall + slope threshold weighted sum) documented as "Phase 1 heuristic," swapped for the trained model once ~1 season of data exists. **We say this openly** — synthetic/heuristic bootstrapping, not fake ML claims.

**Task 2 — ETA / Delay Prediction**
- Output: expected extra delay (minutes) over free-flow time for a given route today.
- Features: sum of segment risk along route, weather severity, time of day, vehicle type, historical average delay on similar routes.
- Model: **Gradient boosted regressor** (XGBoost regression) or simple linear regression baseline first.

**Task 3 — Bottleneck detection**
- Approach: betweenness centrality on the road graph weighted by risk × traffic-importance, recomputed periodically — a graph-analytics task (NetworkX/igraph), not a trained model.

**Training pipeline (practical, student-team scale):**
1. Assemble historical rainfall (Open-Meteo archive) + OSM terrain + any obtainable historical incident data (GSI/Bhuvan landslide inventory as one source, plus synthetic augmentation clearly labeled) for the pilot district(s).
2. Feature engineering script (Python/pandas).
3. Train/validation split by **time** (not random) since this is a forecasting problem — train on earlier season, validate on later.
4. Evaluate: risk model → ROC-AUC / F1 per class; ETA model → MAE/RMSE in minutes.
5. Explainability: SHAP values on the trained XGBoost model, surfaced in the UI as "why this segment is high-risk" (e.g., "72h rainfall: 180mm, historical incidents: 3").
6. Deployment: model serialized with `joblib`, loaded directly inside the FastAPI backend (no separate model-serving infra needed at this scale — avoids overengineering).
7. Retraining: manual/scheduled monthly retrain job as more real data accumulates; version model files (`risk_model_v1.pkl`, etc.).

**Explicit labeling rule for the whole project:** any number/prediction shown in the demo must be tagged in the UI as either "Live data," "Model prediction," or "Simulated for demo" — judges will ask, and honesty here builds credibility rather than costing points.

---

## 8. Data & Datasets

| Data need | Primary source | Backup | Fallback / demo strategy |
|---|---|---|---|
| Road network | OpenStreetMap (Overpass API / Geofabrik extracts for NE India) | State PWD GIS layers (request via RTI/portal if available) | OSM only — clearly sufficient and real |
| Weather/rainfall | Open-Meteo API (free, no key, forecast + historical archive) | IMD data via data.gov.in (authoritative but slower/patchier API access) | Open-Meteo primary, mention IMD as production upgrade path |
| Landslide/flood susceptibility | Bhuvan (ISRO/NRSC) susceptibility layers, GSI landslide inventory | NDMA/SDMA published reports (PDF, manual extraction) | Static susceptibility layer loaded once, refreshed manually |
| Traffic/congestion | Not reliably available in rural NER | Crowd/field reports as proxy | Treat congestion as a field-reported incident type, not a live feed |
| GPS vehicle position | Custom mobile app using device GPS (real, for driver-side users) | — | For hackathon demo: a small on-stage "simulated fleet" script moving markers along real roads — **clearly labeled simulated** |
| Logistics/dispatch data | Manually entered by logistics officer in-app (vehicle, cargo type, origin-destination) | — | Same — this is operational data the platform itself generates |
| Field reports | Generated by the platform itself (photo+geotag+text form) | — | Real, once officials use it |

**Real vs synthetic — our stance:** road network, weather, and terrain are **real** from day one. Historical incident volume in a specific pilot district is likely thin, so the risk model's historical-incident features will initially be sparse/synthetically augmented — we disclose this and show the retraining path rather than inventing a large fake incident history.

---

## 9. Core Intelligence Modules (design summary)

| Module | Approach |
|---|---|
| Road accessibility | Rule engine (field report > PWD bulletin > model score) determines each edge's status |
| Disruption prediction | XGBoost classifier on rainfall/terrain/history features, 24–48h horizon |
| Delay/ETA prediction | XGBoost/linear regressor on route risk + weather + time-of-day |
| Vehicle tracking | Mobile GPS ping → WebSocket → live marker on map; ping stored for route-history/audit |
| Field reporting | Offline-capable form (photo, geotag auto-captured, category, free text) queued locally, synced when online |
| Weather intelligence | Scheduled pull (every 1–3h) from Open-Meteo per district centroid + key segments; rainfall heat layer + threshold alerts |
| Alert lifecycle | Every alert assigned to a specific officer with acknowledged / in-progress / resolved states and an SLA timer to acknowledge — not a fire-and-forget push (adapted from Locus/FarEye exception-ownership patterns, Section 2a) |
| Delivery confirmation | Geotagged photo + timestamp captured at drop-off for an essential-goods dispatch, closing the loop the same way a field report opens one (our version of Locus/FarEye proof-of-delivery) |
| Bottleneck detection | Periodic graph centrality recompute, surfaced as a ranked "top 5 chronic bottlenecks" widget |
| Dynamic route optimization | OSRM with risk-adjusted weights, recomputed on trigger (new incident/weather update/periodic tick) |
| Alerts/prioritization | Severity scoring (who is affected × how severe) so only relevant users get pushed; SMS fallback if push undeliverable |

---

## 10. Frontend & Dashboard

**Screens (Web — officials):**
1. Login (role-based)
2. District connectivity map (default landing) — segment status colors, weather overlay toggle, incident markers
3. Route planner — pick origin/destination, see AI-suggested route + alternatives + ETA + risk explanation
4. Vehicle tracking view — live positions, delivery status list
5. Incident feed — chronological + filterable list of field reports/model flags
6. Bottleneck/analytics view — charts (top bottleneck segments, disruption trend)
7. Alerts/notifications center
8. Admin — user/role management, district/segment configuration

**Screens (Mobile PWA — field officer/driver):**
1. Login
2. "Report incident" (camera + auto-geotag + short form) — works offline, queues, syncs
3. My route (driver) — current route, reroute banner if risk changes, one-tap incident report
4. Alerts inbox

**UX principles:** big touch targets (field use, possibly gloved/rainy conditions), status conveyed by color+icon (not color alone, for accessibility), minimal typing (dropdowns/photo over free text where possible).

**Responsive/offline/multilingual:** PWA with service-worker caching of map tiles for the active district + local IndexedDB queue for reports; language picker (English/Hindi/Assamese/Bengali at MVP; Bhashini API integration path documented for further NER languages in production).

---

## 11. Backend & Database

**Backend architecture:** FastAPI (Python) monolith for MVP — modular internally (auth, ingestion, risk, routing, alerts as separate routers/services) so it can be split into microservices later if it needs to scale; avoids premature microservice complexity for a student team.

**Auth/roles:** JWT-based auth; roles = `admin`, `district_officer`, `field_officer`, `driver`, (`public_viewer` optional/future). Route-level permission checks via FastAPI dependencies.

**Database driver/ODM:** **Beanie** (async ODM built on `pymongo`'s `motor` driver + Pydantic) — chosen specifically because it lets each collection's document shape double as the same Pydantic model FastAPI already uses for request/response validation, so you're not maintaining a schema in three places. Plain `motor`/`pymongo` is the lighter-weight alternative if the team would rather skip the ODM layer.

**Key collections (document shape sketch — MongoDB has no enforced schema, so these shapes are enforced at the application layer via Beanie/Pydantic models, not the database):**
```
users            { _id, name, role, district_id, phone, language_pref }
districts        { _id, name, state, centroid: {type:"Point", coordinates:[lng,lat]} }
road_edges       { _id, osm_way_id, geometry: {type:"LineString", coordinates:[...]},
                    length_m, road_class, surface, risk_score, status, updated_at }
incidents        { _id, edge_id, type, source, severity,
                    location: {type:"Point", coordinates:[lng,lat]},
                    photo_url, description, reported_by, created_at }
weather_snapshots{ _id, district_id, timestamp, rainfall_24h, rainfall_forecast_24h, raw }
vehicles         { _id, reg_no, cargo_type, driver_id, current_route_id, status }
vehicle_positions{ _id, vehicle_id, location: {type:"Point", coordinates:[lng,lat]}, timestamp }
routes           { _id, vehicle_id, origin, destination,
                    path: {type:"LineString", coordinates:[...]},
                    predicted_eta_min, actual_eta_min, risk_at_creation }
alerts           { _id, type, severity, target_user_id, message, sent_via, created_at, read_at }
```
Every `geometry`/`location` field is standard GeoJSON with a `2dsphere` index, which covers the queries this platform actually needs (nearby incidents, points within a district polygon, nearest road edge to a GPS ping). Cross-collection consistency (e.g., an `incident.edge_id` pointing at a real `road_edges._id`) is enforced in the FastAPI service layer, not by the database — unlike a foreign key in Postgres, nothing stops an orphaned reference at the DB level, so this needs its own test coverage (see Section 19).

**API table (representative, not exhaustive):**

| Endpoint | Method | Purpose |
|---|---|---|
| `/auth/login` | POST | Issue JWT |
| `/districts/{id}/connectivity` | GET | Segment statuses for map |
| `/incidents` | POST/GET | Create/list field reports |
| `/route/plan` | POST | Origin+dest → risk-aware route + ETA |
| `/vehicles/{id}/position` | POST | Driver app pushes GPS ping |
| `/vehicles/active` | GET | Live fleet for dashboard (WebSocket variant also provided) |
| `/weather/{district_id}` | GET | Latest weather snapshot |
| `/analytics/bottlenecks/{district_id}` | GET | Ranked bottleneck segments |
| `/alerts/mine` | GET | User's alert inbox |
| `/admin/users` | CRUD | User management |

---

## 12. Tech Stack — Final Recommendation

| Layer | Choice | Reason | Alternative |
|---|---|---|---|
| Frontend (web) | React + Vite + Tailwind + MapLibre GL JS | Fast dev loop, huge ecosystem, free vector maps | Vue (fine, smaller ecosystem for GIS libs) |
| Mobile | Responsive React PWA (not native) for MVP | One codebase, installable, offline via service worker — realistic for a 6-person student team's timeline | React Native (better native GPS/camera access; adopt in V2/production) |
| Backend | Python + FastAPI | One language shared with the ML pipeline, async, auto-generated OpenAPI docs, easy for students | Node.js/Express (fine if team is stronger in JS; loses single-language ML integration) |
| Database | MongoDB + Beanie (async ODM on Motor) | Flexible schema for varied report/incident payloads, native GeoJSON + `2dsphere` covers our geo-query needs, one less "relational modeling" decision for a student team mid-build | PostgreSQL + PostGIS (stronger native topology/graph SQL — worth revisiting if the project scales past pilot districts) |
| GIS/Routing | OSM data + OSRM (self-hosted) | Free, fast, supports custom weight profiles | GraphHopper (viable backup, heavier to run) |
| AI/ML | scikit-learn + XGBoost, pandas, SHAP | Simple, explainable, fast to train on modest data | Deep learning (unjustified at this data scale) |
| Model serving | In-process (loaded in FastAPI via joblib) | No extra infra to run/monitor for a hackathon-scale system | TorchServe/BentoML (only if models grow complex) |
| Weather | Open-Meteo API | Free, no key, forecast+historical | IMD/data.gov.in (authoritative, adopt for production) |
| GPS | Browser/mobile Geolocation API via driver PWA | No hardware dependency for pilot | Dedicated OBD/GPS trackers (production fleets) |
| Notifications | Firebase Cloud Messaging (push) + Twilio/MSG91 (SMS fallback) | Free tier push + reliable low-connectivity SMS path | WhatsApp Business API (good future add) |
| Multilingual | Static i18n JSON (MVP) + Bhashini API (India govt, production) | Bhashini is purpose-built for Indian languages incl. NER languages | Google Translate API (works, but Bhashini fits govt-platform framing better) |
| Auth | JWT + bcrypt password hashing | Simple, stateless, well-understood | OAuth/SSO with govt ID system (future integration) |
| Hosting | Render/Railway (backend+DB) + Vercel/Netlify (frontend) for pilot | Fast, cheap/free tier, minimal DevOps for students | Self-hosted VM (more control, more ops burden) — production would move to NIC/MeghRaj govt cloud |
| Testing | Pytest (backend), Vitest/React Testing Library (frontend) | Standard, well-documented | — |
| Monitoring | Sentry (errors) + simple uptime pings | Free tier sufficient for pilot | Prometheus+Grafana (adopt at production scale) |
| Source control | GitHub | Team familiarity, Actions for CI | GitLab |

---

## 13. AI Coding Workflow

**Primary tool: Claude Code** (agentic CLI/IDE assistant) — best fit for a multi-service repo (backend+ML+frontend+GIS) because it can read across the whole repo, run tests, and make multi-file changes with a plan you review before it executes.

**Secondary tools:** Cursor or GitHub Copilot for fast in-editor completions on routine CRUD/UI code; Antigravity (Google, agent-first IDE with a "Manager" view for running multiple agents in parallel) is a reasonable second agentic option if the team wants to parallelize frontend + backend agent tasks — treat it as an alternative to Claude Code, not both at once, to avoid context fragmentation.

**Project context/rules files:** maintain a `CLAUDE.md` (or equivalent) at repo root stating: tech stack, folder structure, naming conventions, "never invent an API/library — check `requirements.txt`/`package.json` first," and how to run tests. Keep it short and current — a stale rules file is worse than none.

**Prompting workflow:** (1) describe the feature + acceptance criteria, (2) ask the agent to propose a plan before writing code, (3) review the plan, (4) let it implement, (5) require it to run the test suite before declaring done.

**Code review:** every AI-generated PR gets a human reviewer from the team (not the same person who prompted it) before merge to `develop`.

**Testing:** unit tests required for risk-scoring and routing-cost logic specifically (the parts most likely to silently misbehave); AI can draft tests but a human confirms they assert the right thing, not just that the code passes its own tests.

**Git integration:** agent works on a feature branch per task; no direct commits to `main`/`develop` by an agent without a PR.

**Preventing hallucinated APIs/unwanted changes:** pin dependency versions; ask the agent to cite the exact library docs/version before using an unfamiliar API; use `git diff` review before accepting; restrict agent file-write scope to the relevant module folder when possible.

---

## 14. Repository & Team Workflow

```
ner-logistics-platform/
├── backend/
│   ├── app/ (routers, services, models, ml/)
│   ├── tests/
│   └── requirements.txt
├── frontend-web/
│   ├── src/
│   └── package.json
├── frontend-mobile-pwa/
├── ml/
│   ├── notebooks/ (exploration only, not production code)
│   ├── training/ (feature engineering + train scripts)
│   └── models/ (versioned .pkl artifacts, gitignored if large — use releases/LFS)
├── gis/
│   ├── osm-extract-scripts/
│   └── osrm-profile/
├── infra/ (docker-compose, deployment configs)
├── docs/ (architecture.md, api.md, data-sources.md)
└── CLAUDE.md
```

**Branch strategy:** `main` (deployed/stable) ← `develop` (integration) ← `feature/xxx` branches. Hotfixes branch off `main` directly.

**Issues/milestones:** GitHub Issues tagged by module (`backend`, `ml`, `frontend`, `gis`); milestones = the phases in Section 15.

**PR/review workflow:** PR template requires: what changed, how tested, screenshot (for UI). Minimum 1 reviewer approval before merge to `develop`.

**Env vars/secrets:** `.env.example` committed, real `.env` gitignored; secrets (API keys, DB creds) via hosting platform's secret manager, never hardcoded.

**Docs:** `docs/architecture.md`, `docs/api.md` (or auto-generated OpenAPI), `docs/data-sources.md` (with license/attribution notes for OSM, Open-Meteo, Bhuvan).

---

## 15 & 16. Development Phases + Task Breakdown

| Phase | Objective | Key Tasks | Deliverable | Completion Criteria |
|---|---|---|---|---|
| **P0 — Verification** | Confirm PS + scope | Re-read official PS, define pilot district(s), write assumptions doc | `docs/scope.md` | Team agrees on 1 pilot state/2–3 districts |
| **P1 — Research & Requirements** | Lock data sources & user stories | List datasets/APIs, draft user stories per role | `docs/data-sources.md`, user stories | All data sources confirmed accessible |
| **P2 — Feasibility (POLC)** | De-risk hardest parts early | Test OSM extract for pilot area, test OSRM build, test Open-Meteo call | Working local OSRM instance | Route query returns a result locally |
| **P3 — Architecture** | Lock system design | Finalize schema, API contract, folder structure | Architecture diagram + ER diagram | Team sign-off |
| **P4 — GIS POC** | Prove routable graph works | Build OSRM graph from pilot OSM extract; load same edges into MongoDB `road_edges` (GeoJSON); render on MapLibre | Map showing pilot district roads | Can click two points, get a route |
| **P5 — ML POC** | Prove risk model adds signal | Assemble features, train baseline risk + ETA models | Notebook + metrics report | Model beats naive baseline (e.g., "always low risk") |
| **P6 — Backend Core** | Build API + DB | Implement schema, auth, CRUD for incidents/vehicles/routes | Working API (Postman-testable) | All Section 11 endpoints respond |
| **P7 — Frontend Core** | Build dashboard shell | Map view, login, route planner UI | Clickable web app against real API | Officer can log in and see the map |
| **P8 — Integrations** | Wire weather + risk into routing | Backend pulls weather, feeds risk model, adjusts OSRM weights | Live risk-colored map | Rain spike visibly changes segment color |
| **P9 — Routing & Alerts** | Dynamic reroute + notifications | Trigger-based recompute, FCM/SMS integration | Reroute alert fires on new incident | Demo: block a road, see alert + reroute |
| **P10 — Mobile/Offline** | Field officer app | Offline queue, geotag capture, sync logic | Installable PWA | Report submitted offline appears after reconnect |
| **P11 — Integration Testing** | End-to-end validation | Full user-journey test per role | Test report | All critical user journeys pass |
| **P12 — Security & Hardening** | Protect data/access | RBAC audit, input validation, rate limiting | Security checklist done | No open admin endpoints |
| **P13 — Deployment** | Get it live | Deploy backend/DB/frontend, set up CI | Public demo URL | Judges can access it |
| **P14 — Optimization & Demo Prep** | Polish for judging | Performance pass, seed realistic demo data, rehearse | Demo script | 3–5 min run-through under time |

*(Dependencies flow left-to-right; P4/P5 can run in parallel once P1–P3 are done; P7 can start as soon as P6's API contract is fixed, even before P6 is fully implemented, using mocked responses.)*

---

## 17. MVP Strategy

- **Smallest complete version (hackathon MVP):** one pilot district, real OSM roads + real weather, heuristic-then-model risk scoring, manual incident entry (web+mobile), risk-aware route planner with ETA, simulated vehicle movement along real routes, push+SMS alert on blockage, English+Hindi UI.
- **V2:** trained ML risk/ETA models on accumulated real data, offline-first mobile with real GPS tracking, bottleneck analytics, multilingual via Bhashini, multi-district coverage within the pilot state.
- **Production:** all 8 NER states, integration with actual departmental fleets, IMD/PWD data-sharing agreements, NIC/MeghRaj hosting, predictive-maintenance module once asset-condition data sources exist.

---

## 18. Timeline & Team Roles (illustrative student-team plan)

Assuming ~6 members over a typical SIH build window:

| Role | Owns | Phases |
|---|---|---|
| Team lead / PM | Scope, demo narrative, judge Q&A prep | All |
| Backend engineer | API, DB, auth | P3, P6, P8, P9, P12 |
| GIS engineer | OSM/MongoDB geo/OSRM | P2, P4, P8 |
| ML engineer | Risk/ETA models | P5, P8 |
| Frontend engineer | Web dashboard | P3, P7, P9 |
| Mobile/full-stack engineer | PWA, offline sync, integration testing | P10, P11, P13 |

Critical path: P2 (GIS feasibility) → P4 → P8 → P9, since routing+risk is the core differentiator; run P5 (ML) and P6/P7 (backend/frontend shells) in parallel with P4 to use time efficiently. Keep the last ~10–15% of the timeline as buffer for integration bugs and demo rehearsal — this always takes longer than planned.

---

## 19. Testing, Security & Failure Handling

- **Frontend:** component tests for map rendering, route-planner form validation.
- **Backend:** unit tests per service (esp. risk scoring, route weight adjustment); integration tests per endpoint.
- **GIS/Routing:** test that OSRM returns valid paths for known origin-destination pairs; test that risk-weight adjustment actually changes chosen path when a segment is marked blocked.
- **AI/ML:** offline evaluation (train/val split by time) before any model ships; sanity-check predictions against known extreme cases (e.g., very high rainfall → high risk).
- **Database:** since MongoDB doesn't enforce foreign keys or a fixed schema, add explicit tests for document-shape validation (Beanie/Pydantic model tests), GeoJSON geometry validity, and referential-integrity checks (e.g., an incident's `edge_id` actually resolves to a real `road_edges` document) at the application layer.
- **End-to-end:** scripted user journeys per role (officer plans route → driver gets it → field officer reports incident → officer sees reroute alert).
- **Security:** RBAC enforced server-side (never trust frontend role checks alone), input sanitization on all report/free-text fields, rate-limiting on public-facing endpoints, HTTPS everywhere, least-privilege DB credentials.
- **Failure handling:**
  - No internet (field officer): queue locally, sync on reconnect, never silently drop a report.
  - GPS failure: fall back to manual pin-drop on map.
  - Weather API failure: use last-known snapshot, flag as stale in UI rather than blocking the whole dashboard.
  - Outdated road data: field reports always override stale model/OSM assumptions.
  - Model failure/unavailable: fall back to the Phase-1 heuristic risk score rather than crashing routing entirely.

---

## 20. Deployment & Scalability

- **Local → test → production:** Docker Compose for local dev (API + MongoDB + OSRM containers); same containers (or a managed MongoDB) deployed to Render/Railway for the pilot; CI (GitHub Actions) runs tests on every PR and auto-deploys `develop` to a staging URL.
- **Hosting/DB:** MongoDB Atlas free/shared tier for pilot (managed, includes `2dsphere` support out of the box, no ops burden on a student team); production migrates to government cloud (NIC/MeghRaj) per standard practice for MDoNER-sponsored platforms.
- **ML serving:** in-process at pilot scale; if usage grows, extract to a small dedicated FastAPI microservice behind the main API — not before it's needed.
- **Monitoring/backups:** Sentry for error alerts; scheduled DB backups (daily); uptime check on core endpoints.
- **Growth path:** SIH prototype (1 district) → district pilot (full district, real fleet integration) → state rollout (all districts in one NER state) → regional platform (all 8 NER states, cross-state routing, formal PWD/IMD data-sharing MoUs).

---

## 21. SIH Strategy

**3–5 minute demo flow:**
1. (30s) Problem framing — one line, show a real photo/news clip of a NER road blocked by landslide.
2. (60s) Show the district connectivity dashboard live — segment colors, weather overlay.
3. (60s) Plan a route for a medicine-delivery vehicle; show AI picks the safer (not shortest) path with ETA and a plain-language "why" (SHAP-driven explanation).
4. (45s) Trigger a live incident report from the mobile app (a teammate "in the field") — show the dashboard update and an alert fire in near-real-time, and the route auto-adjust.
5. (30s) Show the bottleneck analytics view — "these 5 segments are chronically the problem, here's the data."
6. (15s) Close with the growth path (pilot → state → region) and honesty about what's real vs simulated.

**What to show live vs simulate:** live = map rendering, real weather pull, real route computation, real incident submission and alert. Simulated (clearly labeled on-screen) = vehicle GPS motion (unless you've actually walked/driven with a phone beforehand) and a compressed historical dataset for the ML demo if real data is thin.

**Innovation points:** risk-as-routing-cost (not just a separate "warning" bolted onto a normal map), explainable risk scores (SHAP, not a black box), field-report-as-ground-truth design (humans override models, not the reverse), offline-first design for a genuinely low-connectivity region, and control-tower-style exception ownership (assigned officer + SLA timer, borrowed from Locus/FarEye but never applied before to government rural-accessibility monitoring).

**Expected impact / KPIs:** reduction in average delay for essential-goods delivery on monitored routes; faster time-to-alert after a disruption; % of pilot-district road network with live status coverage; officer-reported reduction in "we didn't know the road was blocked" incidents.

**Likely judge questions + strong answers:**
- *"Where's your real data?"* → "OSM roads and live weather are real today; historical incident volume is currently thin for this pilot district, so our risk model uses a documented heuristic until we accumulate a season of real reports — here's the retraining path."
- *"How is this different from Google Maps?"* → "Google Maps optimizes for speed on data-rich, stable road networks; we optimize for accessibility risk on a road network that changes week to week due to weather, using govt/field data Google doesn't have."
- *"How is this different from a commercial logistics platform like Locus or FarEye?"* → "Those are built for high-density commercial fleets in data-rich plains/urban networks with paying shippers. We borrowed the operational patterns that generalize — a control-tower view, owned-and-timed exceptions instead of fire-and-forget alerts, delivery confirmation as core data — but built for a single government agency, monsoon-hill terrain, and sparse data, not a carrier marketplace."
- *"What happens with zero connectivity?"* → walk through the offline queue + SMS fallback.
- *"Who maintains this after the hackathon?"* → propose it sits with the district administration / MDoNER's NER data cell, with field officers as the ongoing data source, same as they already file paper reports today.

---

## 22. Non-Technical Explanation (by audience)

- **School student:** "It's like Google Maps, but it also knows when a road might get blocked by rain or a landslide, and it tells trucks carrying medicine the safest way to go."
- **Non-CS student:** "We built a website and app that watches weather and road reports for the North East, predicts which roads might get cut off, and automatically suggests safer routes for delivery trucks — plus lets local officials report problems from their phone, even without internet."
- **Logistics professional:** "A risk-aware routing layer on top of OSM/OSRM, fed by weather and field-report data, that adjusts route cost dynamically instead of relying on static shortest-path — reducing the 'we found out the road was blocked after the truck left' problem. Think Locus/FarEye-style control-tower visibility and owned-exception workflows, but built for a government agency monitoring monsoon-hill terrain instead of a commercial carrier network."
- **Government official:** "A dashboard that gives you district-wise connectivity status, an early-warning layer for supply routes, and a way for your own field staff to feed you real-time ground truth, without requiring new hardware from PWD or BRO."
- **SIH judge:** "We took the official brief's eight requirements literally, built the minimum system that satisfies all of them with real free data sources, used simple explainable ML rather than overengineering, and were explicit about what's real vs simulated in the demo."

**Problem → What We Built → How It Works → Result → Why It Matters:** NER roads get cut off unpredictably → we built a risk-aware logistics intelligence platform → it fuses weather, terrain, and field reports into a routing engine that avoids risk before it becomes a blockage → result is faster, safer essential-goods delivery and less "found out too late" → it matters because medicine, food, and construction material delays in remote NER districts have real human cost.

---

# FINAL OUTPUT

### A. Final Recommended Architecture
React/MapLibre web dashboard + React PWA mobile app → FastAPI backend (auth, ingestion, risk engine, routing orchestration, alerts) → OSRM (its own risk-weighted routing graph, compiled from OSM) + MongoDB (single source of truth for road-edge status/risk overlay, incidents, vehicles, users, alerts — all GeoJSON + `2dsphere`) → external pulls from OSM, Open-Meteo, Bhuvan/GSI layers → FCM push + SMS fallback for alerts. (Full diagram in Section 5.)

### B. Final Tech Stack
React+Vite+Tailwind+MapLibre (web) · React PWA (mobile) · FastAPI/Python (backend) · MongoDB+Beanie/Motor (DB) · OSM+OSRM (GIS/routing) · scikit-learn/XGBoost+SHAP (AI/ML, in-process serving) · Open-Meteo (weather) · Browser Geolocation (GPS, pilot) · FCM+Twilio/MSG91 (notifications) · Bhashini (multilingual, production) · JWT (auth) · Render/Railway+Vercel+MongoDB Atlas (hosting, pilot) → NIC/MeghRaj (production) · Pytest/Vitest (testing) · Sentry (monitoring) · GitHub+Actions.

### C. Final Feature List
MVP: risk-colored connectivity map, weather overlay, incident reporting (web+mobile), risk-aware route+ETA, role-based Control Tower dashboard, push/SMS alerts, alert lifecycle with officer ownership + SLA timer, delivery confirmation (geotag+photo). V2: forecasting model, offline PWA, bottleneck analytics as a segment scorecard, real GPS, multilingual. Future: cross-state, real fleet telematics, predictive maintenance, full govt cloud + data-sharing MoUs.

### D. Final AI/ML Strategy
XGBoost classifier for segment risk (rainfall, terrain, history, field-report density features), XGBoost/linear regressor for ETA delay, graph centrality for bottlenecks — explainable via SHAP, heuristic fallback documented for cold-start, no deep learning forced onto a modest dataset.

### E. Final Data Strategy
Real: OSM roads, Open-Meteo weather, Bhuvan/GSI susceptibility layers. Officer-generated real: incidents, vehicle dispatch data. Thin/bootstrapped-with-disclosure: historical incident volume for model training, GPS (simulated for demo unless field-tested beforehand). Every number in the UI tagged live/predicted/simulated.

### F. Final Development Roadmap
P0 Verify → P1 Research → P2 GIS Feasibility → P3 Architecture → P4 GIS POC → P5 ML POC (parallel with P4) → P6 Backend Core → P7 Frontend Core (parallel with P6 via mocked API) → P8 Integrations → P9 Routing & Alerts → P10 Mobile/Offline → P11 Integration Testing → P12 Security → P13 Deployment → P14 Optimization & Demo Prep.

### G. Final Timeline & Team Allocation
6 roles — PM/lead, backend, GIS, ML, frontend, mobile/full-stack — mapped to phases in Section 18; critical path runs through GIS feasibility → GIS POC → integrations → routing/alerts; buffer reserved at the end for integration + rehearsal.

### H. Final MVP Scope
One pilot NER district, real roads+weather, heuristic/light-ML risk scoring, manual+field incident entry, risk-aware route planner, simulated-but-labeled vehicle tracking, push/SMS alerts, English+Hindi UI.

### I. Final SIH Demo Plan
5-part live flow: dashboard → route planning with explainable risk → live field-report → auto-alert/reroute → bottleneck analytics, closing on real vs simulated honesty and the pilot→state→region growth story.

### J. START HERE — First 10 Concrete Actions
1. Confirm pilot state + 2–3 districts as your working scope (write it down, get whole team aligned).
2. Pull OSM extract for that area (Geofabrik or Overpass); stand up a local MongoDB instance (Docker) with a `2dsphere` index ready for the `road_edges` collection.
3. Stand up a local OSRM instance against the same extract and confirm you can query a route.
4. Call Open-Meteo for that area's coordinates and confirm you can get current + forecast rainfall.
5. Design and create the core Beanie/Pydantic document models (Section 11) against that MongoDB instance.
6. Scaffold the FastAPI backend with auth (JWT) and one working endpoint (`/districts/{id}/connectivity`) returning mock data.
7. Scaffold the React+MapLibre frontend and render the pilot district's roads from the API.
8. Build the Phase-1 heuristic risk score (rainfall+slope threshold) and wire it into edge weights feeding OSRM.
9. Build the incident-reporting form (web first, mobile PWA next) writing to the `incidents` collection.
10. Write the `CLAUDE.md` project-context file and agree on branch/PR workflow before the team starts parallel work.
