# WORKFACE — Build Schedule
### 12-day sprint · 19–30 August 2026 · three-person team, distributed

> ⚠️ **Confirm the sprint window before you trust these day numbers.**
> The only dated press source on Hackathon'26 reports **build 3–17 Aug, judging 18–31 Aug, winners 1 Sept**. You specified **19–30 Aug**, which is what this schedule is built on. The `fortyguard.com/hackathon26` page is JavaScript-rendered and can't be read programmatically — **open it, confirm the deadline, and shift the day numbers if needed.** Nothing else in the plan changes; only the calendar does. Do this in the first ten minutes of Day 1.

---

## Roles

| | Owner | Scope |
|---|---|---|
| **T1** | **Product surface** | Site Console, deck.gl 60 m map, **the window ribbon**, activity detail drawer, Agent Trace view, The Record timeline, Morning Brief, $ counters, notification templates, Vercel + Supabase, realtime channel, public deploy |
| **T2** | **External services + ingestion** | FortyGuard client, Postgres cache, credit meter, AOI clustering, historical sweep, raw Twin capture, `env_params` chaining, `heat_intelligence`, wind feed, **schedule import (P6 XER + CSV)**, mock site-systems adapter, PDF/CSV export pipeline, GitHub Actions cron, fixtures |
| **T3** | **Domain models + agent** | Trade window registry, psychrometrics, the seven constraint evaluators, surface model, climatology priors, schedule generator, DB schema, sequencer, agent loop, tools, policy gate, record hash chain, `PILOT.md` |

Deck and video are shared. **The deck starts on Day 8 as a background thread — one slide a day — not on Day 11.** This sprint is one day shorter than the last one and the endgame is where that day gets taken from.

### How this was balanced

Two principles, same as last time, and they worked:

1. **Cluster by boundary, not by topic.** T2 owns everything that talks to an external service or file format. T1 owns everything inside the Next.js app. T3 owns everything that transforms data already sitting on disk. Fewer cross-boundary handoffs means fewer blocks.
2. **Producer ships one day before consumer.** Anything T3 aggregates, T2 fetched the day before. **There are no same-day dependencies anywhere in this plan.**

One deliberate change from Porchlight: **schedule import moved to T2** (it is a file-format boundary, not a transform) and **the PDF export pipeline moved to T2** (they already own the `heat_intelligence` PDF path). That keeps T3 — who has the heaviest domain load — off two things that would otherwise pile onto their Day 8 and Day 9.

---

## The data handoffs

Agree these on Day 1 before anyone writes real code. Lock the shapes in `packages/schemas`, then everyone builds against fake data and nobody waits on anyone.

1. **T3 → T2** — the project schedule: activities, trades, work-face geometry, precedence, float *(Day 2, because T2 can't cluster work faces that don't exist yet)*
2. **T2 → T3** — hourly `T_air(t)` per work face, plus `env_params` (RH, wet bulb, solar, cloud, elevation) and site wind
3. **T2 → T3** — raw 7-year historical readings per tile → T3 aggregates into window priors
4. **T2 → T3** — raw `satellite` + `streetview` segmentation → T3 derives α, ψ and `T_surf(t)`
5. **T3 → T1** — `{activity_id, open_intervals[], binding_constraint, margin, verdict, citation, usd_exposure, confidence}` — **the ribbon contract**
6. **T3 → T1** — the agent's step-by-step trace, and the record entries
7. **T3 → T2** — the record payload to render as a certificate PDF

### Handoff timing — producer always one day ahead

| T2 ships | Day | T3 consumes | Day |
|---|---|---|---|
| Raw 7-year sweep | 4 | Climatology / window priors | 5 |
| Raw Twin segmentation | 5 | Surface model → `T_surf(t)` | 6 |
| Mock site-systems adapter | 7 | Agent actions wired | 8 |
| **T3 ships** | | **consumer** | |
| Hand-written `window_eval` fixture | 1 | T1 builds the ribbon | 4 |
| Project schedule + work faces | 2 | T2 clusters into AOIs | 3 |
| Trace + gate-verdict schema and fixtures | 5 | T1 builds Trace and escalation UI | 6–7 |
| Record payload shape | 8 | T2 renders the certificate PDF | 9 |

### The naming rule — settle it in hour one

FortyGuard calls its async job an `activity_id`. Construction calls a scheduled task an *activity*. **Everywhere: the FortyGuard one is `fg_activity_id`, the schedule one is `activity_id`.** Write it into `packages/schemas` on Day 1. If you don't, you will lose an hour to it around Day 6.

---

## Day 1 · Wed 19 — contracts before code

**All three, first hour, together:** confirm the hackathon deadline. Agree the seven handoffs and write them into `packages/schemas`. Settle the `fg_activity_id` naming rule. Pin the demo site polygon and the hero work face. Nothing else starts until this is done.

- **T1** — Next.js scaffold. Supabase project up. Vercel deployed with a blank page and a **public URL today**. Wireframe the four views, with the window ribbon drawn on paper first.
- **T2** — Hit all five FortyGuard endpoints by hand in a notebook. Save every raw response to `data/fixtures/`. **Log the credit balance somewhere visible.** Commit `.env.example`.
- **T3** — Publish the `window_eval` contract. Hand-written fixture files with the right field names and made-up numbers, so T1 can build the ribbon before any maths exists. `.github/workflows/ci.yml`. Start reading standards.

**Gate:** every endpoint returns 200 once · public URL exists · schemas committed

---

## Day 2 · Thu 20

- **T1** — Mapbox + deck.gl rendering T2's saved heatmap GeoJSON in the browser, over the site polygon.
- **T2** — `FortyGuardClient`: submit, poll, exponential backoff, activity store written to Postgres **before** polling, content-addressed cache.
- **T3** — `data/trade_windows.json` — **12 trades, a citation per row.** Plus the **synthetic project generator**: ~300 activities, 40 work faces on real campus geometry, realistic trade sequences, durations, precedence links, float. **Ship this today; T2 needs it tomorrow.**

**Gate:** heatmap GeoJSON in a browser · registry + schedule exist

> The registry is the long pole for T3 — finding a citable clause per trade takes longer than writing the JSON. Start it Day 1 evening if you can.

---

## Day 3 · Fri 21

- **T1** — Site Console layout: activity table, trade filter, window state chips, work-face selector.
- **T2** — AOI clustering over T3's work faces (40 faces → 3–5 polygons). Credit meter wired. Wind feed adapter (Open-Meteo or NWS).
- **T3** — `psychro.py` (Magnus dew point, wet bulb, heat index) + the **band** and **offset** evaluators + golden-value tests. DB schema and migrations for `thermal_series`, `window_eval`, `agent_*`, `record_entry`.

**Gate:** dew point matches a hand-worked example · AOI plan is ≤ 5 polygons and the projected daily call count is written down

---

## Day 4 · Sat 22 — the visual lands today

- **T1** — **The window ribbon.** Hand-rolled SVG, one lane per activity, green/amber/red bands, scheduled bar drawn on top, reason on hover. This is the hero visual — give it the whole day and get it right.
- **T2** — **Historical sweep, fetch only.** One August window per year, 2019→2025, `exceedance` **and** `persistence`, **both directions**. `filter_type: 4` caps at one month per request — build the loop now, do not discover this on Day 10. Dump raw readings to disk; cache permanently.
- **T3** — The remaining five evaluators: **continuity**, **cure clock**, **composite rate** (ACI 305 evaporation), **decay clock** (asphalt), **human** (WBGT → work/rest → productive-hour haircut). Intersection logic and the `binding_constraint` field.

**Gate:** all seven constraint types evaluate against a synthetic series · raw 7-year readings on disk · ribbon renders from T3's Day-1 fake fixtures

---

## Day 5 · Sun 23

- **T1** — Activity detail drawer: `T_air`/`T_surf`/`T_dew` chart with the offset band drawn, the cited clause inline, the cure-fit plot.
- **T2** — Raw Twin capture: `satellite` + `streetview` per work face, saved as-is. Plus `env_params` chaining (correct `temperature` and `date_time` from the heatmap — never invented) and the `heat_intelligence` PDF for the hero work face.
- **T3** — **Climatology aggregation** → per-tile, per-trade, per-hour `p_open`, median peak, opening/closing hour distribution. Output reads: *"this work face had a compliant coating window on 34% of August mornings, opening at a median of 06:40."* **Then, last thirty minutes of the day: publish the agent-trace and gate-verdict schemas plus hand-written fixtures**, so T1 can build the Trace view tomorrow and the escalation UI on Day 7 without waiting on the real loop.

**Gate:** Tier-0 prior exists for every demo work face · trace + gate fixtures committed

---

## Day 6 · Mon 24

- **T1** — Agent Trace view, streaming step cards, conflict grouping — built against T3's Day-5 fixtures, not against the live loop.
- **T2** — **Schedule import**: P6 XER reader (PyP6Xer / xerparser) → canonical activity model, with the CSV path as the guaranteed fallback. Then buffer — this is where a sweep overrun gets absorbed.
- **T3** — Surface model from T2's segmentation: α, ψ, the night longwave term → `T_surf(t)` with confidence downgrades. Then **agent loop v1**: scan → evaluate → detect conflicts, **no actions yet**. **Run it against the demo model today**, not the dev model.

**Gate:** agent evaluates 300 activities and flags a sane subset · a real XER file imports (or CSV, documented as the fallback)

---

## Day 7 · Tue 25

- **T1** — Supabase realtime channel pushing agent events into the UI. Conflict view. Escalation UI showing the gate verdict and rule id — again against Day-5 fixtures; swap to live data when T3 merges the gate tonight.
- **T2** — Mitigation catalog + **mock site-systems adapter**: crew calendar, ready-mix order slots, lighting plan availability, heated-enclosure inventory. This is the agent's action surface — make it realistic, it's what makes the actions feel consequential.
- **T3** — **Sequencer v1** (greedy interval packer: topological order, ascending float, earliest feasible interval, crew capacity). Then the **policy engine + tests**, gate wired into the loop.

**Gate:** policy test suite green **including the deny case**

> The deny case — the cheapest fix eats four days of float on the near-critical path, so the agent escalates instead — is ten seconds of demo that buys enormous credibility. Do not let it slide to "if there's time."

---

## Day 8 · Wed 26

- **T1** — Morning Brief (phone view) + notification templates. **Deck thread starts: outline + slides 1–3.**
- **T2** — GitHub Actions cron: the agent runs unattended on a schedule against production Supabase.
- **T3** — Actions live: `shift_activity`, `split_activity`, `propose_resequence`, `request_mitigation`, `raise_rfi`, `notify_crew`, `escalate_to_superintendent`. Record hash chain. Ship the record payload shape to T2 today.

**Gate:** a full unattended run completes and writes a chained record

---

## Day 9 · Thu 27

- **T1** — **The Record** view: per-work-package timeline, `$ at risk` / `$ protected` counters, embed T2's `heat_intelligence` PDF. **Deck slides 4–7.**
- **T2** — Fixture completeness pass: every demo path has a committed response. Certificate PDF + CSV export pipeline. **The January `persistence` / `direction: below` call** — one extra call, one slide, kills the "this is just heat" objection.
- **T3** — CP-SAT upgrade **only if everything above is green**; otherwise calibration pass. Write down every assumption for the in-app assumptions page.

**Gate:** end to end with zero manual steps · a certificate exports and opens

> **Read this before starting CP-SAT.** The greedy packer is the committed deliverable. If the trace is clean and the ribbon is right, spend today on the deck and the calibration instead. A half-finished solver on Day 12 is how teams lose.

---

## Day 10 · Fri 28 — last day of building

- **T1** — Deploy everything public. Smoke test from a phone on cellular. Visual polish; empty, loading and error states. **Deck slides 8–12.**
- **T2** — Deploy the worker. Verify the cron fires against production Supabase. Begin freezing fixtures.
- **T3** — `docs/PILOT.md`. Final calibration. The in-app assumptions page (model coefficients, sources, known limitations from `WORKFACE_TECH_SPEC.md §12`).

**Gate:** public URL works on a stranger's device

> **Feature freeze tonight.** Days 11–12 are polish, story and submission. Teams lose this competition on the last day with a half-finished feature and no video, not on Day 4 with a missing one.

---

## Day 11 · Sat 29 — all three

- T2 freezes fixtures and switches on `REPLAY_MODE`; verify with the **network switched off**
- Group bug bash — everyone clicks everyone else's surface
- Deck to v1 complete (12 slides)
- `ARCHITECTURE.md`, `API.md`, README with quickstart and architecture diagram
- **Record demo take 1** — full script, no editing yet

**Gate:** REPLAY runs with the network off · deck complete · one full take exists

---

## Day 12 · Sun 30 — all three

- Re-record the demo, edit under 3:00, add captions
- **Submit early in the day**, not at the deadline
- Verify every link from a clean browser and an incognito window
- Rehearse the three answers out loud: the 12-hour horizon, "it's just hot-weather concreting," and "how do you know your surface model is right"

**Gate:** SUBMITTED

---

## Load check — is this balanced?

| | Heaviest days | Slack |
|---|---|---|
| **T1** | Day 4 (ribbon), Day 9 (Record + counters) | Days 3 and 8 are light — pull deck work forward into them |
| **T2** | Day 4 (sweep), Day 5 (twin + chaining + PDF) | Day 6 is a deliberate buffer; Day 7 is moderate |
| **T3** | Day 4 (five evaluators), Day 7 (sequencer + policy) | Day 9 is optional work — that's the release valve |

If someone falls behind, the cut order is: **CP-SAT → the January cold slide → the Morning Brief → XER import (fall back to CSV) → the second scenario.** Do not cut the ribbon, the citation inline, the deny case, or the certificate. Those four are the submission.

---

## Working across timezones

- Branch per scope (`web/*`, `platform/*`, `intel/*`), PR to `main`, no direct pushes
- **Commit fixtures early and often.** Nobody should ever be blocked waiting on a live API call
- CI runs the constraint golden-value tests and the policy tests on every PR
- One shared doc for "what I'm blocked on." Async teams lose more time to silent blockers than to hard problems
- **A daily 15-minute overlap window, same time every day.** With a 12-day sprint you cannot afford a 24-hour round trip on a schema question

---

## Where the sample data comes from

| What | Source |
|---|---|
| Project schedule | **Synthetic.** Generated by T3 on Day 2. Real campus geography, real trade sequences and durations, realistic precedence and float. Label it *"synthetic schedule, real geography, real standards."* |
| Work-face geometry | Real parcel and campus boundaries; work faces drawn as polygons over them |
| Trade window registry | **Real.** Hand-curated by T3 from published standards and manufacturer PDSs, with a citation per row |
| FortyGuard responses | **Real.** Hit once by T2, saved to `data/fixtures/` and committed. These become the REPLAY demo on Day 11 — not a scaffold to throw away |
| Wind | Real, from a free external feed, site-level scalar, labelled as such |
| Unit costs and rework multipliers | Public trade pricing ranges; rework multipliers from CII benchmark research. Cite them on the counter tooltip |
