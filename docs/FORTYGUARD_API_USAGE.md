# WORKFACE — FortyGuard API Usage

---

## Team

| Name | Role |
|------|------|
| Siyona Goel | Team member |
| Aashma Varma | Team member |
| Ky Lam | Team member (T2 — external services & ingestion) |

---

## Table of contents

- [I. Approach](#i-approach)
  - [1. Live vs fixture](#1-live-vs-fixture)
  - [2. One-time live spend](#2-one-time-live-spend)
- [II. Technicalities](#ii-technicalities)
  - [1. Overview](#1-overview)
  - [2. Code map](#2-code-map)
  - [3. Env vars](#3-env-vars)
- [III. The live section](#iii-the-live-section)
  - [1. Call lifecycle](#1-call-lifecycle)
  - [2. Endpoints used](#2-endpoints-used)
  - [3. Endpoint contracts (details)](#3-endpoint-contracts-details)
    - [3.1 Heatmap](#31-heatmap)
    - [3.2 Satellite / streetview](#32-satellite--streetview)
    - [3.3 env_params](#33-env_params)
    - [3.4 heat_intelligence](#34-heat_intelligence)
- [IV. The fixture section](#iv-the-fixture-section)
  - [1. Caching and fixtures](#1-caching-and-fixtures)
- [V. Summary](#v-summary)

---

## I. Approach

FortyGuard is the thermal / geospatial data vendor. However, WORKFACE never scatters raw HTTP calls across the app. Everything goes through one client:

- **submit → `fg_activity_id` → poll until done**, with optional **REPLAY** from disk fixtures so demos, CI, and cron do not spend credits.

⇒ The website does not call FortyGuard. Only the worker/client does. Cron writes; the UI reads.

### 1. Live vs fixture

| Work | Live API? | Where data came from |
|------|-----------|----------------------|
| Initial five-endpoint capture (campus AOI / point) | **Yes** | Real FG → `data/fixtures/*` + heat-intel PDF |
| AOI clustering (40 faces → ≤5 polygons) | **No** | Geometry only (`work_faces.geojson` → `data/aoi/`) |
| Historical climatology (140-call plan) | **No** (default) | REPLAY synthetic → `data/fixtures/historical/` |
| Twin sat/streetview per face | **No** (default) | REPLAY segments at real centroids |
| January cold (`persistence` / `below`) | **No** (default) | REPLAY synthetic |
| Agent, cron, certificate export | **No FG** | Schedule, priors, twin, record fixtures |

*Naming: `fg_activity_id` = FortyGuard job · `activity_id` = construction schedule task. Never mix them.*

Live is the **one-time capture set**. Everything after is designed to run on **fixtures + REPLAY** unless someone passes `--live` / `force_live`.

### 2. One-time live spend

**Ledger:** 38,720 credits of 2,000,000 remaining **1,961,280**.

| Endpoint | Credits |
|----------|--------:|
| Satellite | 14,400 |
| Streetview | 8,600 |
| Heat intelligence | 8,600 |
| Heatmap | 4,220 |
| Env params | 2,900 |

---

## II. Technicalities

### 1. Overview

| Item | Value |
|------|--------|
| Base URL | `https://api.fortyguard.com/v1` |
| Auth | `FORTYGUARD_API_KEY` (live only) |
| Client | `apps/api/fortyguard/client.py` → `FortyGuardClient` |
| Default mode | `REPLAY_MODE=true` (no network) |
| Async pattern | Submit → poll `/v1/status/{fg_activity_id}` |
| Daily call cap | `max_fg_calls_per_day: 120` (`config/budget.yaml`) |
| Wind | **Not** from FG → Open-Meteo (`apps/api/sitefeeds/wind.py`) |

**Required call order (DAG):**

```text
heatmap(AOI, window)
    ├─→ env_params(..., temperature, date_time)   # must match heatmap — never invented
    ├─→ heat_intelligence(...)                    # hero only
    └─→ satellite / streetview(lat, lon)          # twin; no temperature
```

**Climatology cost control:**  
Naive history = 40 faces × 7 years × 4 analytics = **1,120** calls.  
Clustered = ≤5 AOIs × 7 × 4 = **140** calls. AOI merge is geometry; it does not call FG by itself.

### 2. Code map

| Module | Role |
|--------|------|
| `client.py` | Submit/poll, REPLAY, cache, credit hook |
| `cache.py` | Content-addressed fixture lookup (request-body hash) |
| `activity_store.py` | Persist `fg_activity_id` **before** poll (crash resume) |
| `credits.py` + `config/budget.yaml` | Local meter + AOI/call caps |
| `aoi.py` | 40 work faces → ≤5 polygons (no FG) |
| `historical_sweep.py` | 7-year August sweep loop (140-call plan) |
| `january_cold.py` | January `persistence` / `direction: below` |
| `twin_capture.py` | Per-face sat/SV + env chain + hero heat intel |
| `example_usage.py` | Smoke test |

### 3. Env vars

```env
FORTYGUARD_API_KEY=...       # required when REPLAY_MODE=false or force_live
REPLAY_MODE=true             # default: CI, cron, demo — no live FG
MAX_FG_CALLS_PER_DAY=120     # optional override of budget.yaml
```

---

## III. The live section

### 1. Call lifecycle

```text
request body
    → hash body (cache key)
    → if REPLAY and fixture hit → return fixture (no network)
    → else live submit → fg_activity_id
    → write fg_activity_id to activity_store BEFORE poll
    → poll with exponential backoff + hard timeout (max_poll_s)
    → on Completed: save result; heat_intelligence → download PDF, redact URL
    → bump local credit meter
```

| Control | Behavior |
|---------|----------|
| `REPLAY_MODE=true` | Never calls API; missing fixture → hard error |
| `force_live=True` | Live even when replay is on |
| `max_poll_s` | Default ~300s; heat intel often 600–1200s |
| Credit API | Vendor usage endpoint 405’d → **local** metering only |

### 2. Endpoints used

| Endpoint | Method / path | Role |
|----------|---------------|------|
| **heatmap** | `POST /v1/heatmap` | Tile temps, exceedance, persistence, peak timing |
| **satellite** | `POST /v1/satellite` | Land-cover segmentation → twin absorptivity α |
| **streetview** | `POST /v1/streetview` | Obstruction / sky view → twin ψ |
| **env_params** | `POST /v1/env_params` | RH, wet bulb, solar, heat index |
| **heat_intelligence** | `POST /v1/heat_intelligence` | Hero PDF report |
| **status** | `GET /v1/status/{fg_activity_id}` | Poll async job |

### 3. Endpoint contracts (details)

#### 3.1 Heatmap

| Parameter | Usage |
|-----------|--------|
| `polygon_aoi` | GeoJSON FeatureCollection — **AOI cluster**, not one call per face |
| `date_time.filter_type` | `1` hour · `2` hour range · `3` day · `4` day range (≤1 month) |
| `granularity` | `100` m plan/climatology · `60` m commit/hero |
| `analytic_type` | `tcm` · `time_of_measure` · `exceedance` · `persistence` |
| `threshold` + `direction` | Required for exceedance/persistence (`above` / `below`) |

**Historical plan:** 5 AOIs × 2019–2025 × (exceedance×2 + persistence×2) = **140** live calls if executed.  
**January cold capture:** `persistence`, `direction: below`, threshold **4 °C** (cold floor narrative).

#### 3.2 Satellite / streetview

- Lat/lon only; **no temperature**.
- Cached **forever** (site body does not change during the sprint).
- Design: one capture **per work face**; this build mostly **REPLAY** after a single campus sample.

#### 3.3 env_params

- `temperature` + `date_time` **must match** a heatmap for that location.
- Chained from the captured heatmap stats (e.g. mean ~39.91 °C) + matching August timestamp — **never invented**.

#### 3.4 heat_intelligence

- Same chaining rule.
- **Hero only** (one PDF, not 40).
- Signed download URL is **temporary** → PDF stored under fixtures; committed JSON **redacts** the link.
- Highest single-endpoint cost in the live capture log (~8,600 credits).

---

## IV. The fixture section

### 1. Caching and fixtures

| Tier | TTL | Applies to |
|------|-----|------------|
| Historical | Forever | `filter_type: 4`, multi-year August / January windows |
| Twin | Forever | satellite, streetview |
| Forecast | ~30 min | Near-term heatmap-style requests |

**Mechanics:**

- **Cache key** = hash of normalized request body (`cache.py`).
- **On disk** = `data/fixtures/` (plus `historical/`, `twin/`).
- **activity_store** keeps `fg_activity_id` so a crashed poll can resume without re-submit (and re-pay).
- **REPLAY_MODE=true** serves fixtures only; used by default in CI, cron, and demo.

**Fixture completeness:** required demo paths committed on disk so the product can run offline.

---

## V. Summary

FortyGuard is used only through a single async client with submit/poll, AOI batching, strict heatmap→env/heat chaining, forever-cached historical/twin fixtures, and **REPLAY_MODE** so production demos and CI never spend credits after the one-time live capture set (**38,720** credits of **2M**).
