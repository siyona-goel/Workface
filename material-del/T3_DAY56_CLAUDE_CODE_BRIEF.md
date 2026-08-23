# WORKFACE — T3, Days 5 and 6
### Brief for Claude Code · Sun 23 – Mon 24 Aug 2026

You are working as **T3** on the WORKFACE repo. T3 owns *domain models and the agent*: everything that transforms data already sitting on disk. Read this whole brief before writing code. Day 5 and Day 6 are both here because Day 6's surface model is what makes Day 5's priors worth having; do them in order and do not start Day 6 until Day 5's gate is green.

---

## 0. Orient yourself first

1. `material-del/WORKFACE_SCHEDULE.md` — the Day 5 and Day 6 rows for T3, and the handoff table.
2. `material-del/WORKFACE_TECH_SPEC.md` — **§6 (the Work Face Thermal Twin)** is Day 6's specification, in full, including the coefficient table and the two things it tells you to say out loud. **§8 (the agent)** is the loop. **§10** is the LLM decision.
3. `material-del/T3_DAY4_CLAUDE_CODE_BRIEF.md` §2 — the hard rules. They still bind.
4. `packages/schemas/historical_readings.py` — `HistoricalSweepBundle`, `TileSweep`, `SweepWindow`, `TileReading`. Day 5's input contract.
5. `packages/schemas/twin_segmentation.py` — Day 6's input contract.
6. `packages/schemas/agent_trace.py` — `StepType`, `ToolName`, `Conflict`, `AgentStep`, `AgentRun`. Day 6's output contract, and it already exists.
7. `apps/api/db/migrations/001_init.sql` — the `climatology_prior` and `agent_*` table shapes you are populating.
8. `data/fixtures/historical/manifest.json` and `data/fixtures/twin/twin/manifest.json` — **read both before you design anything.** They tell you what T2 actually captured, which is not the same as what the plan assumed.

---

## 1. State of play

**T2 has shipped Days 4 and 5.** Both of your blocking handoffs have landed:

- **Handoff #3 — the 7-year historical sweep.** `data/fixtures/historical/sweep_bundle.json` (1.66 MB), plus 140 raw per-call files under `raw/`. Five AOIs, seven Augusts, four analytics each.
- **Handoff #4 — the raw Twin capture.** `data/fixtures/twin/twin/twin_bundle.json` (131 KB). Forty work faces, satellite land-cover segmentation and streetview obstruction segmentation on each, plus chained `env_params` and the hero `heat_intelligence` PDF.
- Also new and useful: `data/aoi/assignments.json` (all 40 work faces → their AOI), `data/aoi/tile_clusters.geojson`, `apps/api/sitefeeds/wind.py` with `data/fixtures/wind_open_meteo.json`, `config/budget.yaml`, and migration `002_t2_day3.sql`.

**T1 has shipped Day 4.** `apps/web/components/window-ribbon.tsx` and `apps/web/data/ribbon.json` (612 KB) — the ribbon now renders your real evaluator output from Day 4.5.

**T3 stands at:** all seven evaluators, `psychro.py` with WBGT, `evaluate.py`, the real thermal bundle and ribbon fixtures, and the Day-5 agent-trace fixtures already written ahead of schedule (`sample_agent_run.json`, `sample_gate_verdicts.json`). **That last item is the second half of the schedule's Day-5 row and it is already done** — do not redo it. Day 5 for you is the climatology half only.

---

## 2. Read the sweep before you design the aggregator

**This is the most important section in the brief.** The sweep is real and it is good, but it does not contain three of the things the plan's Day-5 sentence assumes. Design around what is there. Do not fill gaps with invention — Day-4 hard rule 6 (*fail closed, never guess*) governs today exactly as it did then.

What is actually in `sweep_bundle.json`:

| | |
|---|---|
| AOIs | 5 — `AOI-FAB2` (70 tiles), `AOI-UTIL` (72), `AOI-SOUTH` (72), `AOI-PARK` (20), `AOI-ROAD` (60) |
| Years | 7 — 2019…2025, August only, `filter_type: 4`, 100 m granularity |
| Windows per AOI | 28 = 7 years × 4 analytics |
| Analytics | `exceedance above 35.0 °C`, `exceedance below 4.0 °C`, `persistence above 35.0 °C`, `persistence below 4.0 °C` |
| Units | `hour` |
| Tile readings | **8,232** — each one a single scalar `value` |

### 2.1 Two thresholds were swept, not thirteen

`manifest.json` lists `registry_thresholds_c` with all 13 distinct thresholds in the trade registry. **Only 35.0 and 4.0 were actually captured.** Verify this yourself before you build on it.

That still buys you three genuine, directly-derivable priors, and they line up with the registry exactly:

| Swept analytic | The registry constraint it answers |
|---|---|
| exceedance **above 35.0 °C** | `concrete_cip_hot_weather / band_concrete_discharge_max` (`t_max_c` 35.0) |
| exceedance **below 4.0 °C** | `concrete_cip_cold_weather / band_cold_weather_trigger` (`t_min_c` 4.0) |
| **persistence** below 4.0 °C | `sfrm_spray_applied_fireproofing / continuity_40f_24h` (`t_min_c` 4.0, `run_hours` 24) |

That third row is the good one. The `persistence` analytic returns *run length*, and `continuity` is the only evaluator that asks a run-length question. They are the same question asked by two different systems. **Say that on stage** — it is the cleanest evidence in the project that the registry and the data source were designed against each other rather than bolted together.

Every other trade gets `p_open = None` and an explicit `coverage: "insufficient_threshold"` marker naming the threshold that would be needed. Not a guess, not an interpolation, not a nearby threshold pressed into service.

### 2.2 The 35 trap — read this twice

`coating_epoxy_structural_steel` has `band_air_application.t_min_f = 35` and `band_surface_application.t_min_f = 35`. **That is 35 °F — 1.7 °C.** The sweep's 35 is **°C**. They are not the same number and joining them produces a coating prior that is wrong by 33 degrees while looking perfectly plausible.

Write a test that fails if any prior joins a `_f`-suffixed registry field to a `_c` sweep threshold. This trap is going to be sprung by somebody on this project; make it be caught by CI instead.

### 2.3 There is no hour-of-day data. At all.

`climatology_prior`'s primary key is `(tile_id, trade_id, month, hour)`. The sweep cannot fill `hour`:

- `stats` is `null` on **all 140 windows**.
- `TileReading.hourly_tcm_c` exists in the schema and is populated on **0 of 8,232 tiles**.
- Each tile carries one scalar for a whole August.

So *"opening at a median of 06:40"* is **not observable from this data**. You have two honest routes and you must take the second:

- ❌ Drop `hour` and store a monthly prior. Breaks the table's PK and throws away the one thing that makes a Tier-0 prior useful to a planner.
- ✅ **Model the hour-of-day shape and label it as modelled.** Use the deterministic diurnal from `scripts/make_thermal_fixtures.py` as the shape, scale or offset it per tile so that its hours-above-35 °C matches that tile's observed August exceedance count, then read the crossing hours off the calibrated curve. The *count* is observed; the *timing* is modelled. Carry a field — `hour_of_day_source: "modelled"` — on every row, surface it in the formatter's sentence, and never let it be dropped in a summary.

Then **escalate to T2**, in your report, in one line they can act on: *`TileReading.hourly_tcm_c` is in the schema and is empty; populating it on the next sweep converts every modelled opening hour into an observed one.* The schema already anticipated this. That is a small ask, not a re-architecture.

### 2.4 There is no humidity and no dew point anywhere in the sweep

Which means the demo's hero constraint — `offset_dew_point` on the coating — **has no Tier-0 prior and cannot have one from this data.** Do not produce a coating prior by proxying dew point off air temperature.

Re-scope the Day-5 demo sentence onto a trade the data actually supports. The concrete hot-weather one works and is true:

> *"This work face exceeded the 35 °C concrete discharge limit for a median of 298 hours across seven Augusts — 40% of the month. Modelled crossing at 09:20, closing at 19:40."*

Put the coating-prior gap in your report as a known limitation for the assumptions page. Tier-0 is a *probability, not a forecast*, and it is also *not every constraint* — both caveats belong in the same sentence.

---

## 3. Task A — `apps/api/climatology/priors.py`

The folder exists with a `.gitkeep` and nothing else. This is the whole of Day 5.

### A1. Join work faces to tiles

Priors are keyed by `tile_id`; everything else in T3 is keyed by `work_face_id`. `data/aoi/assignments.json` maps each of the 40 faces to its AOI but not to a tile. Resolve the face to the **nearest tile centroid within its assigned AOI** — 100 m tiles, so nearest-centroid is honest at this granularity. Expose the mapping as a pure function and cache it; do not recompute per query.

### A2. Aggregate

For each (tile, trade, month, hour) produce:

- `p_open` — across the seven years, the fraction in which that trade's binding threshold was satisfied at that hour. Derived from the observed exceedance count via the calibrated diurnal of §2.3. `None` where coverage is insufficient.
- `median_peak_c` — the median across years of the tile's August peak. Derive it from the exceedance counts at the two thresholds plus the diurnal; if you cannot do so without inventing a distribution shape, return `None` and say why in the docstring. **`None` is an acceptable answer here and a fabricated number is not.**
- `n_years` — 7 where all seven years reported, lower where any year is missing. Count it, do not assume it.
- `coverage` — `"observed"` / `"modelled_hour"` / `"insufficient_threshold"`.

Persist to the `climatology_prior` shape in `001_init.sql`. Stdlib + pydantic only; no numpy.

### A3. Tier-0 is a probability, not a forecast

Label it in the returned model, in the formatter's output, in the docstring, and in any field name where it fits. Every place the number can escape from, it escapes wearing that label. This is Day-4 hard rule 8 applied to a new object.

---

## 4. Task B — the sentence

A planner does not read a probability table. Write a small formatter that turns one prior row into exactly the sentence in the schedule:

> *"This work face had a compliant coating window on 34% of August mornings over seven years, opening at a median of 06:40 and closing at 09:10."*

with the modelled-timing caveat carried, not stripped. Test the string. It goes on a slide and into the UI, so it is a deliverable, not a debug helper.

---

## 5. Task C — Day-5 tests

`tests/test_priors.py`:

- A small synthetic sweep in, known priors out.
- `n_years` counts real reporting years, including a deliberately gappy fixture.
- The °F/°C guard from §2.2.
- Every trade without threshold coverage returns `p_open is None` and `coverage == "insufficient_threshold"` — **assert the count**, so that a future sweep silently widening coverage shows up as a failing test rather than as silence.
- The formatter's exact string.

**Day 5 gate:** a Tier-0 prior exists for every demo work face · trace and gate fixtures committed (already done) · `pytest tests/ -q` green.

---

# Day 6

Do not start until the Day-5 gate is green.

## 6. Task D — the surface model from real segmentation

Today `scripts/make_thermal_fixtures.py` derives `t_surf_c` from a **guessed** `k_absorb` / `k_emit` per `surface_class`, because on Day 4.5 the twin had not landed. It has now landed. Replace the guess with the real thing.

**New file: `apps/api/twin/surface.py`.** (`apps/api/twin/capture.py` is T2's; `twin_capture.py` is theirs too. A new `surface.py` in that folder is T3's transform of their capture and does not collide — but say so in your report so nobody is surprised.)

Implement §6.2 of the tech spec as written:

```
T_surf(t) = T_air(t) + (α · GHI(t) · ψ(t)) / (h_c(V) + h_r)  −  ε · ΔLW_night(t)
h_c(V) = 5.7 + 3.8·V          h_r ≈ 5 W/m²K          ΔLW scaled by (1 − cloud_octas/8)
```

### D1. α from the satellite segmentation

Each capture carries land-cover fractions. `WF-FAB2-06`, for example: `metal 53.27, concrete 20.77, shadow 15.58, vegetation 5.19, other 5.19`. Take α as the fraction-weighted mean of per-class absorptivities. The spec gives you five (asphalt ≈ 0.90, aged concrete ≈ 0.65, galvanised steel ≈ 0.25, coated steel ≈ 0.45, vegetation ≈ 0.75); you will need `bare_soil` and a policy for `other`. Cite each addition in `docs/CITATIONS.md`.

**`shadow` is not a material.** It is an artefact of when the satellite image was taken, and averaging an absorptivity into it is meaningless. Renormalise the remaining fractions with `shadow` excluded, and say in the docstring that you did and why. If you instead treat it as reduced insolation, you are asserting that the shadow is present at all hours, which it is not.

### D2. ψ from the streetview segmentation

`ψ` = the `sky` fraction of the front streetview segmentation. `WF-FAB2-06` reads `sky: 45.0`; `WF-FAB2-07` reads `sky: 97.0`.

**Two honesty requirements here, and they matter more than the arithmetic:**

1. **`back` is empty on every one of the 40 captures.** Only the front hemisphere was segmented. So ψ is a single-hemisphere estimate presented as a whole-sky one. That is a real confidence downgrade under §6.2's *degrade gracefully* rule — not `confidence: high` — and the downgrade must reach the UI.
2. **The twin's sky percentages match `work_faces.geojson`'s `sky_view_factor` exactly** (45 ↔ 0.45, 97 ↔ 0.97) because T2's replay fixture was seeded from the same generator record. **This is not independent validation and must never be presented as any.** Do not write a test that asserts agreement and calls it a check — it checks nothing. Write instead a test that asserts the *derivation path* runs, and note the circularity in your report and on the assumptions page.

### D3. The coefficient that decides your demo

The hero story is: the bare deck radiates to a clear sky overnight, falls below air temperature, and hits the dew-point offset at dawn. That undershoot is the `ε · ΔLW_night` term, and **ε for galvanised steel is the single most load-bearing number in this project.** Bright new galvanising has a low thermal emissivity (roughly 0.2–0.3); weathered galvanising is far higher (roughly 0.7–0.9). At the low end the deck barely cools and the demo's dawn closure weakens or disappears.

So: pick a value, cite it, state which weathering condition it assumes, and **run the sensitivity** — report what the hero contrast looks like at both ends of that range. If the story only survives at ε ≈ 0.9, we need to know today, and we need to be able to say "weathered galvanised deck, four months of Phoenix sun" and mean it. This is precisely the question a coatings inspector in the audience asks.

### D4. Confidence downgrades

Per §6.2: no segmentation → land-cover-only α, `confidence: medium`. No streetview → ψ = 1, `confidence: low`. Add: front-hemisphere-only ψ → one step down from whatever the capture claims. All 40 captures currently claim `capture_confidence: high`; your derived confidence should not simply inherit that.

### D5. Re-derive, then compare

Regenerate `sample_thermal_bundle.json` through the real coefficients and **diff the hero pair against the Day-4.5 synthetic version**. Report where the guessed model and the derived model disagree, and by how much. If the ribbon's verdicts move, T1 needs to know before they build on them.

---

## 7. Task E — agent loop v1

**New: `apps/api/agent/loop.py`.** Three stages only — **`SCAN` → `EVALUATE` → `CONFLICT`. No `PROPOSE`, no `GATE`, no `ACT`.** Those are Day 7.

- **SCAN** — `list_activities_in_lookahead(72)` over `data/project_demo/activities.json` from the demo data date. 62 activities in window, 37 thermal-sensitive.
- **EVALUATE** — for each, `get_work_face_thermal` then `evaluate_window`. This is your existing, tested, deterministic code. The agent calls it; the agent does not reimplement it.
- **CONFLICT** — group by work face and shift; emit a `Conflict` wherever `demanded_hours > compliant_hours`. `demanded_hours` sums **productive** hours (post-WBGT haircut) — `productive_hours()` already exists in `constraints.py` and this is what it was written for. Use the real `Conflict` model; it is already in `agent_trace.py` with all its fields.

Emit a real `AgentRun` with real `AgentStep`s, same schema as the hand-written `sample_agent_run.json`, so T1's Trace view — which they are building today against that fixture — renders live output with no changes. **Do not overwrite `sample_agent_run.json`.** Write to a new path and diff the two; report any field the real loop populates differently. T1 is building against the fixture right now and having it change under them mid-day is the one thing that would cost them the day.

**Day 6 gate:** the agent evaluates the lookahead and flags a sane subset. Note that **the gate is pure Python** — no LLM step exists in Day 6's loop. Do not let a model problem block it.

---

## 8. The LLM — wire it, then leave it alone

§10 of the tech spec is decided: **open-weight models behind one env var**, because a contractor's P6 schedule never leaves their network and that is a procurement unlock, not a cost saving. `.env.example` already carries `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Setup steps are in **`docs/LLM_SETUP.md`** (delivered alongside this brief); do not re-derive them.

For today, all that is required is:

- A single client constructed from those three env vars and nothing else. No provider branching, no `if model.startswith(...)`, no hardcoded fallback model. The whole value of §10 is that swapping providers is an env change.
- `apps/api/requirements.txt` currently has `httpx`, `pydantic`, `python-dotenv`, `PyYAML`, `pytest` and **no LLM client**. Adding `openai>=1.40` is the right call — it is the standard client and it speaks to Ollama, DeepInfra and OpenAI identically. **This is a deliberate new dependency: put it in your report** so nobody is surprised by a CI change.
- A single smoke test that the configured model responds and can return a tool call. Not ten scenarios — `tests/test_agent_replay.py` is Day 7 work.
- **One portability note to write into the client's docstring now:** Ollama's OpenAI-compatible endpoint does **not** support `tool_choice`. A prompt that works locally by forcing a tool will behave differently on a hosted provider that honours it. Design the prompt so it never needs forcing.

§10's warning is the real point and it applies from today: *do not swap blind at the end.* Run the loop against the model you intend to demo with, starting now, not on Day 9.

---

## 9. Handoffs and rules

Day-4 hard rules 1–10 all still bind. Re-read them. In addition:

- **Do not touch `apps/web/`.** T1 is mid-build on the Trace view.
- **Do not edit `data/project_demo/activities.json` or `stats.json`.**
- **Do not modify anything under `data/fixtures/historical/` or `data/fixtures/twin/`.** Those are T2's captures. You read them; you never write them.
- **Do not overwrite `sample_agent_run.json` or `sample_gate_verdicts.json`.** T1 is building against both today.
- `packages/schemas/` changes must be flagged loudly in the report so T1 and T2 can be tagged.
- Branch `intel/day56-priors-twin-agent`. Commit, do not push, no co-author trailer.

---

## 10. Definition of done

**Day 5**

- [ ] `apps/api/climatology/priors.py` — priors for every demo work face, populating the `climatology_prior` shape
- [ ] Trades without threshold coverage return `p_open is None` with an explicit reason — no interpolation, no nearest-threshold substitution
- [ ] Hour-of-day is labelled `modelled` on every row it appears in
- [ ] The °F/°C guard is a test, not a comment
- [ ] The planner sentence is implemented and its exact string is asserted
- [ ] `tests/test_priors.py` green

**Day 6**

- [ ] `apps/api/twin/surface.py` implements §6.2 with α and ψ derived from T2's segmentation
- [ ] Every coefficient cited in `docs/CITATIONS.md`; `shadow` handled explicitly and explained
- [ ] Confidence downgrades implemented, including the front-hemisphere-only ψ downgrade
- [ ] The ε sensitivity for the hero pair is reported at both ends of the galvanised range
- [ ] `apps/api/agent/loop.py` — scan → evaluate → conflict over the 72 h lookahead, emitting a valid `AgentRun`
- [ ] The LLM client is env-var-only and smoke-tested; `openai` added to requirements and flagged
- [ ] `pytest tests/ -q` green; nothing touched in `apps/web/`, T2's fixture folders, or the agent fixtures

---

## 11. Report back with

1. **What the sweep could and could not support.** Which trades got a real prior, which got `insufficient_threshold`, and the one-line ask to T2 about `hourly_tcm_c`.
2. **The ε sensitivity result.** The hero contrast at the low and high end of galvanised emissivity. If the demo is fragile to this number, put it in your first line.
3. **Where the derived surface model disagrees with Day 4.5's guessed one**, and whether any ribbon verdict moved.
4. **The circularity note** — confirm you did not write a test that treats the twin/generator sky-view agreement as validation.
5. **The dependency addition** (`openai`) and any `packages/schemas/` change.
6. **What the agent flagged** — scanned count, flagged count, conflicts found, and whether the subset looks sane to you. If the agent flags 3 of 37 or 36 of 37, something is wrong and your judgement on that is worth more than the number.
7. Anything in this brief you think is wrong. You have read the data; if §2's reading of the sweep is mistaken, say so before building on it.
