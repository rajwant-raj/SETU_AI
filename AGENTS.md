# AGENTS.md — SIH26002 NER Logistics Platform

Read `docs/blueprint.md` for full context before any non-trivial task. This file is the short version you must follow on every task.

## Tech stack (do not substitute without asking)
- Backend: Python + FastAPI
- DB: MongoDB + Beanie (async ODM on Motor) — GeoJSON documents with `2dsphere` indexes, not a relational/SQL schema
- GIS/Routing: OpenStreetMap data + OSRM (self-hosted) — OSRM builds and holds its own routing graph directly from the OSM extract; MongoDB never stores the pathfinding graph itself, only the status/risk overlay and everything else (incidents, vehicles, users, alerts)
- AI/ML: scikit-learn / XGBoost + SHAP — no deep learning, no new ML framework without asking
- Frontend (web): React + Vite + Tailwind + MapLibre GL JS
- Mobile: React PWA (not React Native, not a separate native app)
- Auth: JWT (no OAuth/session-based auth)
- Notifications: FCM (push) + Twilio/MSG91 (SMS)

## Folder structure
backend/ · frontend-web/ · frontend-mobile-pwa/ · ml/ · gis/ · infra/ · docs/
Put code only in the folder that matches its layer. Don't create new top-level folders without asking.

## Hard rules
1. **Never invent an API response, library, or dataset.** If a package isn't already in `requirements.txt` / `package.json`, or you're unsure an endpoint/field exists, stop and ask — don't guess and don't silently add a new dependency.
2. **Field reports always override model predictions.** Never write logic where a model-inferred risk score silently overrules a human-submitted incident report.
3. **Label simulated data as simulated.** Any mock GPS position, seed data, or placeholder prediction must be flagged in code comments and, where user-facing, in the UI (`source: "simulated"` vs `"live"` vs `"model"`).
4. **No direct commits to `main` or `develop`.** Work on a `feature/xxx` branch, open a PR, wait for human review.
5. **Show the plan before writing code** for anything touching more than one file or an external service (OSRM, weather API, DB schema). Wait for approval on non-trivial plans.
6. **Time-based train/test splits only** for any ML model here — this is a forecasting problem; random splits will overstate accuracy and must not be used.
7. **RBAC checks happen server-side.** Never rely on the frontend hiding a button as the only access control for admin/officer-only actions.
8. **Run the test suite before declaring a task done.** If tests don't exist yet for the touched code, write them first.

## Current phase
Check `docs/blueprint.md` Section 15 for the phase list. State which phase a task belongs to before starting it, and don't jump ahead of unfinished dependencies (e.g., don't build the risk model before the road edges exist in MongoDB and the OSRM graph is built from the same extract).
