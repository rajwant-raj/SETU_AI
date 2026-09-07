# Building SIH26002 in Antigravity — MCP Setup + Design Guide

Companion to `docs/blueprint.md` and `AGENTS.md`. This file covers (1) which MCP servers actually help this project and how to wire them into Antigravity, (2) how to sequence Editor vs Manager view across the build phases, and (3) a full design-token system for the "stunning white" dashboard.

---

## Part 1 — MCP Servers

### Why bother with MCP here specifically
Two of your AGENTS.md hard rules — "never invent an API/library" and "field reports override model predictions" — are exactly the failure modes MCP tools are best at preventing: they give the agent a way to *check* something (a live doc, a real DB document, a rendered screenshot) instead of guessing. Don't install every MCP server that exists — each one adds tools the agent has to consider on every turn, which costs context and can make it slower/worse. Add the two below first; treat the rest as optional.

### Where to configure them
In Antigravity: open the **Agent panel** → click the **"…" (Additional options)** button at the top → **MCP Servers → Manage MCP Servers → View raw config**. This opens `mcp_config.json` directly:
- macOS/Linux: `~/.gemini/config/mcp_config.json`
- Windows: `%USERPROFILE%\.gemini\config\mcp_config.json`

Add servers under the `mcpServers` key. Restart the agent panel (or Antigravity) after editing so it picks up the new config.

### Recommended servers, in priority order

**1. MongoDB MCP — add this first.** Lets the agent query your actual MongoDB collections (schema shape, document counts, a sample geo document) instead of assuming what's in them. Directly de-risks Phase P4 (GIS POC) and P6 (backend core), where "the agent assumed a field/collection exists that doesn't" is the single most common stall.
```json
{
  "mcpServers": {
    "mongodb": {
      "command": "npx",
      "args": ["-y", "mongodb-mcp-server",
                "--connectionString", "mongodb://localhost:27017/ner_logistics"]
    }
  }
}
```
Point the connection string at your local dev DB, not a shared/production one. Give the DB user read access to the collections the agent needs and avoid handing it an admin/root credential.

> **Note on the GIS swap:** the earlier version of this guide used PostGIS for spatial queries. MongoDB covers the common cases via `2dsphere` geospatial indexes and `$geoNear` / `$geoWithin` queries (point-in-polygon, proximity, route corridors), but it doesn't have PostGIS's deeper spatial toolkit (topology functions, network routing helpers, raster support). For Phase P4 (GIS POC) specifically, test your actual routing/catchment queries early rather than assuming feature parity — this is exactly the kind of thing the "field reports override model predictions" rule exists for.

**2. Redis MCP — add this second, for authentication.** Lets the agent inspect real session/token state (key TTLs, whether a session key exists, what an auth payload actually looks like) instead of guessing how login/session logic behaves. Scope it to this project's auth-related keys — don't point it at a shared Redis instance used by other services.
```json
{
  "mcpServers": {
    "redis": {
      "command": "npx",
      "args": ["-y", "mcp-redis",
                "--url", "redis://localhost:6379"]
    }
  }
}
```
Use a dedicated Redis DB index (or key prefix, e.g. `auth:*`) for authentication data so the agent's queries stay scoped to sessions/tokens and don't wander into unrelated cached data. Avoid pointing this at a production Redis instance.

**3. Fetch/web MCP — add this third.** Lets the agent pull the *actual current* docs page for Open-Meteo, OSRM, Overpass, or Bhashini before writing integration code, instead of relying on training-data memory of an API that may have changed its response shape.
```json
{
  "mcpServers": {
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    }
  }
}
```

**4. Playwright MCP — optional, add once you have a frontend to look at.** Lets the agent take a real screenshot of the running dashboard and self-critique layout/spacing instead of guessing how it rendered. Useful specifically for Part 2 of this guide (the design pass) — ask the agent to screenshot after each layout change.
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

**5. GitHub MCP — optional, add once you're past P3 (architecture locked).** Lets the agent open issues/PRs and keep the phase board (Section 15/16 of the blueprint) in sync with actual progress, rather than you updating it by hand.
```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "<repo-scoped token, not org-admin>" }
    }
  }
}
```
Scope the token to this one repo only, not your whole GitHub account.

**Skip for now:** a filesystem MCP (Antigravity already has native file access to your workspace — a separate one is redundant) and anything image-generation related (not part of this brief).

> Package names above (`mongodb-mcp-server`, `mcp-redis`, `@playwright/mcp`, etc.) are the commonly-used community/official ones as of writing — MCP servers update independently of Antigravity, so if a command fails, check that server's own GitHub README for the current install command before assuming Antigravity is broken.

### Sequencing: which MCP tool matters at which phase

| Blueprint phase | Primary MCP in use |
|---|---|
| P2 GIS Feasibility | Fetch (Overpass/OSRM docs) |
| P4 GIS POC | MongoDB (geospatial query testing) |
| P5 ML POC | Fetch (Open-Meteo docs) |
| P6 Backend Core | MongoDB (data layer) + Redis (auth/session) |
| P7 Frontend Core, P14 Optimization | Playwright |
| Ongoing, once repo is stable | GitHub |

---

## Part 2 — Editor vs Manager, phase by phase

- **P0–P3 (verification, research, feasibility, architecture):** Editor view, single agent, conversational — these are decisions, not parallelizable code.
- **P4 + P5 (GIS POC, ML POC):** good candidates for **Manager view in parallel** — they don't share files (one touches `gis/` + `infra/`, the other touches `ml/`). Give each its own scoped task.
- **P6 + P7 (backend core, frontend core):** parallelizable *only* once the API contract from Section 11 of the blueprint is written down — give both agents that contract as shared context so they don't drift from each other. This is also where MongoDB (data layer) and Redis (auth/session) both come into play, so make sure the API contract is explicit about which reads/writes hit which store.
- **P8–P10 (integrations, routing/alerts, mobile/offline):** back to single-agent Editor view — these phases touch the same files sequentially (risk score feeds routing feeds alerts), so parallel agents would collide.
- **P11–P14:** Editor view, with Playwright MCP in the loop for visual QA during P14 specifically.

---

## Part 3 — The Design Guide: a stunning white dashboard

### Ground it in the actual subject first
This isn't a generic SaaS analytics tool — it's a **cartographic instrument for people making road-safety decisions in monsoon-hit hill terrain.** The visual language should borrow from topographic survey sheets and route ledgers, not from startup dashboard templates. That's where "distinctive" comes from here — not from picking an unusual color for its own sake.

### Design tokens

**Color — 6 hexes, each with a job, not decoration:**
| Token | Hex | Use |
|---|---|---|
| `paper` | `#FFFFFF` | Base background |
| `fog` | `#F4F5F3` | Panel/secondary surface — a cool, faint grey-green, like aged survey paper, *not* a warm cream |
| `ink` | `#16231F` | Primary text, map line work, borders |
| `route` | `#1E4A5F` | Primary accent — links, active route line, primary buttons |
| `terrain` | `#3F6B4A` | Success/open/low-risk status only |
| `hazard` | `#C97A2B` | Watch/medium-risk status only |
| `alert` | `#A6362B` | Blocked/high-risk status only |
| `hairline` | `#DADFDC` | All dividers/borders |

Color communicates state and nothing else here: blue = network/navigation, green/amber/red = the three accessibility states, and that's the entire palette's job. No gradient washes, no decorative tints.

**Type — two families, distinct roles, no default Inter-everywhere:**
- **Headlines/section titles:** *Fraunces* (a serif with real optical-size character, reads like atlas/survey typography without tipping into the cream+serif+terracotta cliché — because it sits on white with blue/green, not cream with terracotta).
- **UI/body/labels:** *IBM Plex Sans* — a technical, government-appropriate grotesk, legible at small sizes for a data-dense dashboard.
- **Data — coordinates, ETAs, timestamps, risk scores:** *IBM Plex Mono*. This one is earned, not decorative: these genuinely are data values, not prose, so a monospace treatment tells the eye "this is a number to read precisely," not a label.

Set a clear type scale (e.g. 40/28/20/16/14px) and keep body line length under ~80 characters in any text-heavy panel (incident descriptions, report text).

**Layout — the map is the hero, panels are a ledger, not cards:**
```
┌─────────────────────────────────────────────┬───────────────────┐
│                                               │  DISTRICT: ___    │
│                                               ├───────────────────┤
│                                               │  ■ Open      12   │
│              MAP (≈70% width)                │  ▲ Watch      3   │
│         roads colored by risk state           │  ● Blocked    1   │
│                                               ├───────────────────┤
│                                               │  Recent reports    │
│                                               │  ─────────────────│
│                                               │  09:41  NH-2, ...  │
│                                               │  08:15  Bridge, .. │
│                                               ├───────────────────┤
│                                               │  Active vehicles   │
└─────────────────────────────────────────────┴───────────────────┘
```
- The map never shrinks to accommodate chrome — it's ~70% of viewport width on desktop, full width with the side panel as a bottom sheet on mobile.
- The right panel is a **ledger**: hairline-divided rows, small square/triangle status glyphs (not rounded pill badges), no card shadows, no per-item border-radius. Squares get a 2–4px radius only on genuinely interactive controls (buttons, search box) — static panels stay sharp-cornered, which is what keeps this from reading as the generic SaaS-card kit.
- Alignment: left-aligned throughout — this is a working tool people scan quickly, not a marketing page that benefits from centered hero copy.

**Principles:**
1. The map is the product; every other panel exists to support reading the map, not to compete with it visually.
2. Hairlines and alignment do the organizing work instead of shadows, rounded cards, or background tints.
3. Color = state, always, never decoration. If you reach for a gradient or a fifth accent color, stop.
4. Numbers are set in mono; everything else is set in Plex Sans; headlines only are set in Fraunces.

**What to deliberately avoid** (these are the generic "AI dashboard" tells, listed so you can catch them in review): a warm cream background with terracotta accents; ALL-CAPS tracked-out eyebrow labels above every section; meta text joined with middle dots; rounded cards with an identical soft grey shadow on every panel; a '→' tacked onto every button label; numbered 01/02/03 markers on content that isn't actually a sequence.

### Tailwind config starting point
```js
// tailwind.config.js (excerpt)
theme: {
  extend: {
    colors: {
      paper: '#FFFFFF',
      fog: '#F4F5F3',
      ink: '#16231F',
      route: '#1E4A5F',
      terrain: '#3F6B4A',
      hazard: '#C97A2B',
      alert: '#A6362B',
      hairline: '#DADFDC',
    },
    fontFamily: {
      display: ['Fraunces', 'serif'],
      sans: ['"IBM Plex Sans"', 'sans-serif'],
      mono: ['"IBM Plex Mono"', 'monospace'],
    },
    borderRadius: {
      none: '0px',
      DEFAULT: '4px', // interactive controls only
    },
  },
}
```

### A prompt you can hand to the agent directly
> "Read Part 3 of `Antigravity_Build_And_Design_Guide.md`. Build the district connectivity dashboard's layout and component shell using this token system — map at ~70% width as the hero, ledger-style status/report panels with hairline dividers (no cards, no shadows), Fraunces for headlines only, IBM Plex Sans for UI text, IBM Plex Mono for all coordinates/timestamps/ETAs. Take a Playwright screenshot when done and tell me what you'd remove to make it quieter before I look."
