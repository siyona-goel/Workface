# WORKFACE — Repo Guide & Ownership

Companion to `WORKFACE_SCHEDULE.md` and `WORKFACE_TECH_SPEC.md`. How the repo gets built, who owns which folders, and the conventions that stop three people in three timezones stepping on each other.

---

## Step 0 — one person scaffolds, everyone else waits

**Do not have three people create the repo structure in parallel.** You will get three conflicting `package.json` files, two `.gitignore`s and a merge that eats an hour you do not have in a 12-day sprint.

**T2 does the initial commit** — they're closest to the backend, which is most of the tree. Everyone else pulls once it's pushed, then branches.

```bash
# T2, Day 1, first thing
mkdir workface && cd workface
git init -b main
```

Create the full tree with placeholder files so every folder exists from commit one. Empty folders don't survive git, and a missing folder is an invitation to invent a different path.

```bash
mkdir -p apps/api/{fortyguard,sitefeeds,schedule,twin,climatology,windows,sequencer,agent,export,routers,db}
mkdir -p apps/web
mkdir -p packages/schemas
mkdir -p data/{fixtures,project_demo,templates}
mkdir -p tests notebooks docs .github/workflows

find apps packages data tests notebooks docs -type d -empty -exec touch {}/.gitkeep \;
```

Root `.gitignore` covering `.env`, `__pycache__/`, `node_modules/`, `.next/`, `venv/`, `*.pyc`, `.DS_Store`. **Do not gitignore `data/fixtures/` — those captures are the demo, and they must be in the repo.** Then:

```bash
git add -A && git commit -m "scaffold: repo skeleton"
git remote add origin git@github.com:<org>/workface.git
git push -u origin main
```

Add T1 and T3 as collaborators. Everyone clones, and nobody touches `main` directly again.

---

## The ownership map

The rule: **one owner per folder.** If you need a change in someone else's folder, open a PR and tag them — don't push into it because it's faster.

Folders are grouped by **boundary, not topic**: T2 owns everything that talks to an external service or file format, T1 owns everything inside the Next.js app, T3 owns everything that transforms data already on disk. That's why the twin, the climatology and the schedule work are each split across two people — split at the fetch/transform line, not by subject.

```
workface/
├─ apps/
│  ├─ api/
│  │  ├─ fortyguard/          ← T2   client.py, poller.py, cache.py, credits.py, aoi.py
│  │  ├─ sitefeeds/           ← T2   wind.py, sitesystems_mock.py (crews, ready-mix, lighting)
│  │  ├─ schedule/
│  │  │  ├─ importer.py       ← T2   P6 XER + CSV → canonical Activity
│  │  │  └─ generator.py      ← T3   synthetic project generator, Day 2
│  │  ├─ twin/
│  │  │  ├─ capture.py        ← T2   raw satellite + streetview fetch
│  │  │  └─ surface.py        ← T3   → α, ψ, T_surf(t), confidence
│  │  ├─ climatology/
│  │  │  ├─ sweep.py          ← T2   7-year fetch loop, permanent cache
│  │  │  └─ priors.py         ← T3   p_open, percentiles, opening-hour distribution
│  │  ├─ windows/             ← T3   registry.py, psychro.py, constraints.py, evaluate.py
│  │  ├─ sequencer/           ← T3   greedy.py, cpsat.py, float.py
│  │  ├─ agent/               ← T3   loop.py, tools.py, policy.py, record.py
│  │  ├─ export/              ← T2   certificate_pdf.py, csv.py
│  │  ├─ routers/             ← T2 owns, T3 adds agent endpoints via PR
│  │  ├─ db/                  ← T3   models, migrations
│  │  └─ main.py              ← T2
│  └─ web/                    ← T1   entire Next.js app, sole owner
├─ packages/schemas/          ← SHARED — see below, treat with care
├─ data/
│  ├─ trade_windows.json      ← T3   12 trades, citation per row
│  ├─ project_demo/           ← T3   activities.json, work_faces.geojson, site.geojson
│  ├─ fixtures/               ← T2 owns real captures; T3 adds agent-replay fixtures
│  └─ templates/              ← T1   notification + brief templates (Day 8)
├─ config/
│  ├─ policy.yaml             ← T3   gate thresholds — this file goes on a slide
│  └─ budget.yaml             ← T2   MAX_FG_CALLS_PER_DAY, granularity tiers
├─ tests/
│  ├─ test_psychro.py         ← T3
│  ├─ test_constraints.py     ← T3
│  ├─ test_cure.py            ← T3
│  ├─ test_evaporation.py     ← T3
│  ├─ test_sequencer.py       ← T3
│  ├─ test_policy.py          ← T3
│  ├─ test_agent_replay.py    ← T3
│  ├─ test_fortyguard.py      ← T2
│  └─ test_import.py          ← T2
├─ notebooks/                 ← anyone, never imported by app code
├─ docs/
│  ├─ PILOT.md                ← T3 (Day 10)
│  ├─ ASSUMPTIONS.md          ← T3 (Day 10) — also rendered in-app
│  └─ ARCHITECTURE.md, API.md ← shared, Day 11
└─ .github/workflows/
   ├─ ci.yml                  ← T3 (Day 1)
   └─ agent-cron.yml          ← T2 (Day 8)
```

The three split folders — `schedule/`, `twin/`, `climatology/` — are the seams where T2 fetches and T3 transforms. Separate files, separate owners, one-day gap between them. That's deliberate; **don't merge them back into single modules** because it feels tidier.

### `packages/schemas` is the one shared folder

It holds the seven handoff contracts from `WORKFACE_SCHEDULE.md`. Rules:

- **Day 1: all three of you edit it together in one sitting**, then commit once
- After Day 1, any change needs a PR that tags the other two
- Never rename a field silently — rename in one PR, everyone updates in the next
- Keep Pydantic and Zod versions side by side and matching

**Put the naming rule at the top of the file as a comment:**

```python
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit → /v1/status/{id})
# These are different things. They will collide if you blur them.
```

This folder is where distributed teams break. Guard it.

---

## Step 1 — Day 1, in order

### T2 (do this first — the others are blocked)

```bash
cd apps/api
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn pydantic httpx python-dotenv supabase openai \
            shapely pyproj ortools PyP6Xer reportlab
pip freeze > requirements.txt
```

Then: `.env.example` committed (names only, no values), real `.env` local and gitignored. Push. Tell the others it's up.

> `ortools` is a large wheel and occasionally slow to install on some platforms. Install it on Day 1 even though T3 doesn't need it until Day 9 — you do not want to discover a build problem on the second-to-last day.

### T1 (once T2's scaffold is pushed)

```bash
cd apps/web
npx create-next-app@latest . --typescript --tailwind --app
npx shadcn@latest init
npm install deck.gl mapbox-gl recharts @supabase/supabase-js
```

**Deploy to Vercel today, even showing nothing.** A public URL on Day 1 removes a whole class of Day-10 panic.

Do **not** install a Gantt library. The window ribbon is hand-rolled SVG — roughly 150 lines — and a Gantt library will fight you for a day over exactly the thing that makes the ribbon good (per-hour constraint bands under a scheduled bar).

### T3 (can start immediately, no dependencies)

1. Write `packages/schemas/window_eval.py` + `window_eval.ts` — the `evaluate_window` output shape, the ribbon contract.
2. Hand-write `data/fixtures/sample_window_eval.json` with plausible fake numbers so **T1 can build the ribbon on Day 4 before any maths exists.**
3. `.github/workflows/ci.yml` — on every PR, install Python deps and run `pytest tests/`. Ten lines. T3 owns it because it exists to run T3's golden-value and policy tests.
4. Start reading standards. The registry is the long pole; finding a citable clause per trade takes longer than writing the JSON.

---

## Environment variables

One `.env.example` at the repo root, committed. Real values go in a shared password manager or a pinned private message — **never in the repo**, even in a branch, even briefly.

```bash
FORTYGUARD_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_MAPBOX_TOKEN=
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
WIND_FEED_URL=
REPLAY_MODE=true
MAX_FG_CALLS_PER_DAY=120
```

`REPLAY_MODE=true` is the **default from Day 1**, not something you add on Day 11. If replay is the normal path all sprint, it cannot be broken on demo day.

---

## Branches and PRs

| Prefix | Owner |
|---|---|
| `web/*` | T1 |
| `platform/*` | T2 |
| `intel/*` | T3 |

- Branch off `main`, one branch per unit of work, **merge daily**. Long-lived branches across timezones become merge archaeology.
- PR title = what changed. Body = anything the other two need to know.
- **Protect `main`:** require a PR, require CI green. Settings → Branches → add rule. Two minutes on Day 1, prevents the 3 a.m. force-push.
- Tag reviewers only when the change crosses a boundary (schemas, shared fixtures, `config/`). Otherwise self-merge — three people can't afford mandatory review latency on a 12-day sprint.

---

## CI — T3 sets this up Day 1

`.github/workflows/ci.yml`: on every PR, install Python deps and run `pytest tests/`. That's it.

The value isn't sophistication. It's that the constraint golden-value tests, the policy-gate tests and the agent replay tests run automatically when anyone touches anything. Across three timezones that's your only cheap defence against silent breakage.

`.github/workflows/agent-cron.yml` comes Day 8 — scheduled run, writes to Supabase, no server to keep alive.

---

## Three decisions to settle on Day 1 — write them down, don't leave them ambiguous

**1. Cache: Postgres, not Redis.** `WORKFACE_TECH_SPEC.md §0` drops Redis. Cache FortyGuard responses in a Postgres table keyed on the normalised request body, plus `data/fixtures/` on disk. One less service, one less thing to explain on stage, and it suits the cron-based architecture. *If you disagree and keep Redis, T2 owns Upstash setup on Day 3 and it goes in the env vars above.*

**2. Sequencer: greedy first, CP-SAT as a Day-9 upgrade.** The greedy interval packer is the committed deliverable. CP-SAT only ships if Days 1–8 are green. Agree now that this is the rule, so nobody spends Day 7 on a solver.

**3. Schedule import: CSV is guaranteed, XER is the stretch.** T2 builds the canonical `Activity` model against CSV first, then adds the XER reader on top of the same model. A real P6 export is a big credibility win with EPC judges, but it must never be on the critical path to a working demo.

Don't leave any of these open. They're exactly the kind of thing that surfaces on Day 8 as *"wait, I thought you were doing that."*

---

## Definition of done for a PR

- Runs locally
- Tests pass in CI
- No secrets, no `.env`, no large binaries
- If it changes a schema, the other two are tagged
- If it adds a fixture, **the fixture is committed** — a fixture on someone's laptop is not a fixture
- If it adds a registry row, that row has a `citation` a human could go and check
- If it adds a policy rule, that rule has a test — including the case where it *denies*
