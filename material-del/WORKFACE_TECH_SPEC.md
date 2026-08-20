# WORKFACE — Technical Specification
### Architecture, models, API strategy and stack decisions · 19 Aug 2026

Companion to `WORKFACE_PROJECT_PLAN.md`. This is the document the three of you build against. Where the plan says *what* and *why*, this says *how*, with the formulas and the request bodies.

---

## 0. TL;DR — nine decisions

1. **Carry over the Porchlight stack.** Next.js on Vercel, Supabase Postgres + PostGIS, deck.gl, GitHub Actions cron, open-weight LLM behind one env var. It fits, the team knows it, and the ramp-up cost is zero.
2. **One addition: a deterministic scheduler.** Greedy interval packer first, **OR-Tools CP-SAT** as the upgrade. The LLM never sequences anything.
3. **Drop Redis.** Cache FortyGuard responses in a Postgres table keyed on the normalised request body, plus `data/fixtures/` on disk. One less service to explain.
4. **The website never calls FortyGuard or the LLM.** Cron worker writes; site reads. Judge traffic costs zero credits.
5. **The unit of everything is the work face**, not the activity and not the site. Many activities map to one work face; one work face maps to one 60 m tile cluster.
6. **The governing temperature is usually not air temperature.** A surface energy-balance model converts FortyGuard's 2 m air temperature into the substrate temperature the specifications are written against, using FortyGuard's own solar irradiance and land-cover data.
7. **Wind is the one input FortyGuard does not provide.** Take it as a site-level scalar from a free external feed. Be explicit about it everywhere.
8. **All window evaluation is plain Python.** Unit-testable, auditable, cheap. The LLM only chooses a resolution strategy and writes the rationale.
9. **`REPLAY_MODE=true` is the default from Day 1**, not something added on Day 11.

---

## 1. System architecture

```
WORKER PATH (GitHub Actions, every 4 h)          READ PATH (what judges hit)
Python worker                                    Next.js on Vercel
  FortyGuard ─┐                                    │
  wind feed  ─┼→ twin → thermal → windows →        │
  LLM        ─┘   sequencer → agent → policy       │
                        │                          │
                        └──writes──► Supabase Postgres ──reads──► browser
                                     (+ PostGIS)    ZERO LLM · ZERO FortyGuard calls
```

Consequences, all of which are demo-day insurance:

- A thousand judges viewing the site costs 0 tokens and 0 credits.
- If the worker dies at 3 a.m., the site still works — it shows slightly older decisions.
- No cold start on anything a judge touches. Rate limits stop being a threat.
- It is also honest about what the product is. A site console is a window onto an autonomous system, not a button that summons one.

**One live affordance:** a single *"Re-run the agent on this activity"* button on the detail page. Server-side, globally rate-limited to ~20/hour via a Postgres counter, falling back to the cached trace when the budget is spent. A judge proves it's live in one click and no input can break it.

---

## 2. Data model

Postgres 16 + PostGIS. Tables that matter:

| Table | Key columns | Owner |
|---|---|---|
| `work_face` | `id`, `name`, `geom (POLYGON, 4326)`, `centroid`, `elevation_m`, `exposure_class`, `twin_json`, `tile_cluster_id` | T3 |
| `tile_cluster` | `id`, `aoi_geom (POLYGON)`, `granularity_m`, `h3_cells[]` | T2 |
| `activity` | `id`, `wbs`, `name`, `trade_id`, `work_face_id`, `planned_start`, `planned_finish`, `duration_h`, `total_float_d`, `is_critical`, `milestone_date`, `hold_point` | T2 (import) / T3 (generator) |
| `activity_pred` | `activity_id`, `pred_id`, `link_type`, `lag_h` | T2 |
| `trade_window` | `trade_id`, JSON constraint spec, `citation`, `standard_ref`, costs | T3 |
| `fg_activity` | `activity_id (FortyGuard)`, `request_hash`, `endpoint`, `status`, `submitted_at`, `result_ref` | T2 |
| `fg_cache` | `request_hash`, `endpoint`, `response_jsonb`, `tier`, `expires_at` | T2 |
| `thermal_series` | `work_face_id`, `ts`, `t_air_c`, `t_surf_c`, `t_dew_c`, `rh_pct`, `wbgt_c`, `ghi`, `wind_ms`, `source`, `confidence` | T3 |
| `window_eval` | `activity_id`, `run_id`, `open_intervals jsonb`, `binding_constraint`, `margin`, `verdict`, `citation`, `usd_exposure` | T3 |
| `climatology_prior` | `tile_id`, `trade_id`, `month`, `hour`, `p_open`, `median_peak_c`, `n_years` | T3 |
| `agent_run` / `agent_step` | run metadata, tool calls, proposals, gate verdicts | T3 |
| `record_entry` | `seq`, `prev_hash`, `hash`, `payload jsonb` — append-only | T3 |

**Naming rule that will save an argument.** FortyGuard calls its async job an `activity_id`. Construction calls a scheduled task an *activity*. These are different things and they will collide. **Everywhere in the codebase, the FortyGuard one is `fg_activity_id` and the schedule one is `activity_id`. No exceptions.** Write this in the schemas package on Day 1.

---

## 3. The FortyGuard integration

### 3.1 The client — get this right on Day 1

Every core endpoint is **submit → `fg_activity_id` → poll `/v1/status/{id}`**. One client, once:

- Async submit with `httpx.AsyncClient`; bounded polling with exponential backoff, hard cap, never poll forever.
- **Persistent activity store** — write `fg_activity_id` to Postgres *before* polling, so a restart resumes instead of re-billing.
- Content-addressed cache keyed on the normalised request body. TTL by tier: historical = forever, forecast = 30 min, twin = forever.
- A **credit meter** calling `/v1/system/fetch-api-key-usage` after every batch, logging remaining balance to a table the console displays.
- `Failed` is terminal. Record the `fg_activity_id`, surface it, move on.
- `heat_intelligence`: the `download_link` is temporary and signed. Fetch immediately, store the PDF yourself, **never log the full URL.** The docs ask for this explicitly; respecting it costs nothing and reads as professionalism.

### 3.2 Endpoint chaining — the dependency most teams miss

`env_params`, `heat_intelligence` and `satellite` all take a `temperature` and/or `date_time` that the docs say **must match the heatmap you generated for that location.** The call order is fixed and one-directional. Model it as an explicit DAG in the worker; never let the agent invent a temperature.

```
heatmap(AOI, window)  →  tile temperature at the work face centroid
        │
        ├─→ env_params(lat, lon, temperature, same date_time)     # RH, wet bulb, solar, cloud, elevation
        ├─→ heat_intelligence(lat, lon, temperature, same date)   # PDF, hero work face only
        └─→ satellite / streetview(lat, lon)                      # twin, no temperature needed
```

### 3.3 The call plan — exactly which analytic answers which question

This table is a slide. It is also the thing that shows you read the docs harder than anyone else.

| Question | Endpoint + parameters |
|---|---|
| What is the temperature at each work face for the next 12 h? | `heatmap`, `filter_type: 2`, `analytic_type: tcm`, `granularity: 60` |
| When does each tile peak, so how do I sequence crews across the site? | `heatmap`, `filter_type: 3`, `analytic_type: time_of_measure` |
| How many hours today is this face **above** the trade's ceiling? | `heatmap`, `analytic_type: exceedance`, `threshold: T_max`, `direction: above` |
| How many hours is it **below** the trade's floor? | `heatmap`, `analytic_type: exceedance`, `threshold: T_min`, **`direction: below`** |
| Is there a continuous run long enough for the protection period? | `heatmap`, `analytic_type: persistence`, `threshold`, `direction` |
| **In-band hours** (the actual window length) | `hours_total − exceedance(T_max, above) − exceedance(T_min, below)` — the two-sided trick |
| What is the seven-year prior for this window in August? | `heatmap`, `filter_type: 4`, one August window per year 2019→2025, `exceedance` + `persistence`, **cached forever** |
| Dew point, wet bulb, solar irradiance, cloud, elevation | `env_params` with the full `analysis` list (Premium gives you all of them — use it) |
| Land cover → albedo and thermal inertia for the substrate model | `satellite`, per work face, cached forever |
| Shading and orientation for elevated work faces | `streetview`, per work face, cached forever |
| The hero artifact for the deck | `heat_intelligence` on the hero work face, all five analyses |

> **The two-sided trick is the headline.** Every other team will run `exceedance` with the default `direction: above` and call it heat. A trade window is a band. Running the same endpoint twice — once against the ceiling with `above`, once against the floor with `below` — and subtracting from the period length gives you **compliant hours per tile in two calls**. Put that arithmetic on a slide.

### 3.4 Credit budget — treat it as a design constraint

Tile-level heatmaps across a large campus burn credits fast. This is a real risk and also a real story.

- **Cluster, don't iterate.** Snap work faces to their 60 m tiles and merge into a small number of AOI polygons. A 1,100-acre campus with 40 work faces collapses to **3–5 AOI polygons**, not 40 calls. Every activity on that campus is served by those polygons.
- **Tier your granularity.** 100 m for the Tier-0 planning sweep; 60 m only for the Tier-1 commit pass on faces the coarse pass flagged.
- **Cache historical forever.** A 2019–2025 August climatology for a tile never changes.
- **Batch by day, not by activity.** One `filter_type: 3` call covers a whole day for the whole AOI; slicing it per activity is free in Python.
- **Precompute the entire demo dataset by Day 10** and commit the fixtures.

Put a slide up titled *"We designed for API cost from hour one."* Judges who run an API business will love you for it.

**Hard budget in config:** `MAX_FG_CALLS_PER_DAY`, enforced in the client, with the credit meter reading logged after every batch. Fail loudly at 80%.

---

## 4. The trade window registry

`data/trade_windows.json`. One row per trade. Schema:

```jsonc
{
  "trade_id": "coating_epoxy_structural_steel",
  "display_name": "Structural steel — high-build epoxy",
  "governing_temp": "surface",          // "air" | "surface" | "base_material"
  "constraints": [
    { "type": "band",   "t_min_c": 1.7, "t_max_c": 121.1, "on": "surface" },
    { "type": "band",   "t_min_c": 1.7, "t_max_c": 48.9,  "on": "air" },
    { "type": "offset", "on": "surface", "above": "dew_point", "delta_c": 2.8 },
    { "type": "band",   "rh_max_pct": 85 },
    { "type": "cure_clock", "ref_c": 25.0, "hours_at_ref": 168, "q10": 2.0,
      "milestone": "cure_to_service" }
  ],
  "duration_h": 6,
  "crew_size": 5,
  "unit_cost_usd": 34,                  // per m² installed
  "quantity": 4200,
  "rework_multiplier": 3.2,
  "warranty_conditioned": true,
  "citation": "Sherwin-Williams Macropoxy 646 Fast Cure Epoxy PDS, Application Conditions: air 35–120 °F, surface 35–250 °F, material min 40 °F, at least 5 °F above dew point, RH max 85%. Cure to service (atmospheric): 10 days @ 35 °F, 7 days @ 77 °F, 4 days @ 100 °F.",
  "standard_ref": "SSPC-PA 1 (AMPP) — Shop, Field and Maintenance Coating of Metals"
}
```

Seed set and the constraint types each exercises are in `WORKFACE_PROJECT_PLAN.md §3`. **Every row must have a `citation` string a human could go and check.** If you cannot find a citable clause, the row does not go in.

---

## 5. The seven constraint evaluators

All in `apps/api/windows/constraints.py`. Each takes the four series and the constraint spec and returns a list of `(start, end)` open intervals plus a margin. The activity's window is the **intersection** of its constraints' intervals; the **binding constraint** is the one whose removal would most extend the window. That single field — "what is stopping me" — is what makes the UI feel intelligent.

### 5.1 Band
```
open(t) ⟺ t_min ≤ T_gov(t) ≤ t_max
margin  = min(T_gov − t_min, t_max − T_gov)
```
Trivial, and the most common. Applies to masonry, sealant, marking, welding preheat trigger, and the air/surface pair on coatings.

### 5.2 Offset (dew point) — the one that wins the demo
```
open(t) ⟺ T_surface(t) ≥ T_dew(t) + Δ          Δ = 2.8 °C (5 °F) for SSPC-PA 1
```
Dew point from air temperature and RH via the **Magnus–Tetens** approximation:
```
γ(T, RH) = ln(RH/100) + (17.625·T) / (243.04 + T)
T_dew    = 243.04·γ / (17.625 − γ)                    # T in °C, valid −40…+60 °C
```
Sanity check to keep in a unit test: T = 25 °C, RH = 60% → T_dew ≈ 16.7 °C.

This constraint is the reason night and dawn work is not a free escape hatch, and it is what makes the Phoenix-monsoon demo two-sided within a single day.

### 5.3 Continuity
```
open(t) ⟺ ∃ an unbroken run [t, t + N] where every hour satisfies the base constraint
```
Not "is it compliant now" but "is it compliant *and stays* compliant for N hours." This is SFRM's *substrate and ambient ≥ 40 °F maintained before, during and a minimum of 24 hours after application*, and it is ACI 306's protection period. **This is exactly what FortyGuard's `persistence` analytic computes**, which means you can pre-screen tiles with one API call before running the local evaluation — a genuinely elegant chaining and worth saying out loud.

### 5.4 Cure clock
Cure is an integral, not a threshold. Use a Q10 (Arrhenius-equivalent) rate model, calibrated where the PDS gives you multiple points:
```
rate(T)   = q10 ^ ((T − T_ref) / 10)
progress  = Σ rate(T_i) · Δt_i / hours_at_ref
cured     ⟺ progress ≥ 1
```
Calibrate `q10` per product from the PDS cure table. Macropoxy 646 gives you three points for cure-to-service — **10 days at 35 °F, 7 days at 77 °F, 4 days at 100 °F** — and fitting them is more interesting than it looks:

- Between 77 °F and 100 °F the ratio 7/4 over 12.8 °C implies **q10 ≈ 1.55**.
- Between 35 °F and 77 °F the ratio 10/7 over 23.3 °C implies **q10 ≈ 1.17**.

The rate does **not** follow a single Q10 across the whole range — epoxy cure stalls disproportionately as you approach the product's minimum application temperature. So fit a piecewise or two-parameter model, **plot it against the manufacturer's three published points, and put that plot in the app.** You are not asserting a model; you are showing it reproduces the manufacturer's own table, and you are showing you noticed the low-temperature deviation. That single chart answers "did you make this up" before anyone asks it.

Concrete uses the same shape via **Nurse–Saul maturity (ASTM C1074)** if you want the stricter version:
```
M = Σ (T_i − T_0) · Δt_i           T_0 = −10 °C datum
```

### 5.5 Composite rate — ACI 305 evaporation
The rate a judge will recognise instantly. The Menzel/NRMCA formula behind the ACI nomograph, English units:
```
E = (Tc^2.5 − r · Ta^2.5) · (1 + 0.4·V) × 10⁻⁶

E  = evaporation rate, lb/ft²/hr
Tc = concrete surface temperature, °F        ← from the twin, or the mix design temp
Ta = air temperature, °F                      ← FortyGuard
r  = RH / 100                                 ← FortyGuard env_params
V  = wind velocity, mph                       ← external feed (the missing field)
```
Thresholds: **> 0.2 lb/ft²/hr → plastic shrinkage cracking expected, precautions mandatory. 0.1–0.2 → possible, precautions recommended. < 0.1 → not anticipated.** Low-bleed mixes (Type 1L blended cements) drop the limit to 0.1.

This one constraint is worth a slide on its own, because it demonstrates the whole thesis: ACI 305 defines hot weather as *"any combination of high air temperature, low relative humidity, wind, and solar radiation"* — **not a temperature.** A 75 °F morning with 15% RH and wind can be worse than a 95 °F calm afternoon. Every "if temp > X" competitor is wrong about this by construction.

### 5.6 Decay clock — asphalt
Material leaves the plant hot and the clock starts. Available compaction time is a function of base surface temperature and lift thickness, from the placement cessation tables:
```
minutes_available = f(T_base_surface, lift_thickness)
open(t) ⟺ minutes_available(t) ≥ minutes_required(crew, roller pattern, area)
```
Seed the lookup from the published cessation table (e.g. base at 33–40 °F requires a mat at 280–305 °F depending on lift; above 90 °F base the window runs 4 min at ½-inch to 15+ min at 3-inch). Note the direction: **hot weather *helps* asphalt compaction and hurts everything else.** Show that in the demo. It is the single cheapest proof that this is not a heat alarm — one trade's red is another trade's green, on the same tile, in the same hour.

### 5.7 Human — WBGT and work/rest
`env_params` returns `wet_bulb_temperature_celsius` and `solar_irradiance` (GHI/DNI/DHI). OSHA's own outdoor WBGT calculator uses the **Liljegren et al. (2008)** heat-and-mass-transfer model with air temperature, RH, wind, barometric pressure, and lat/lon/time — estimating solar irradiance via Kasten–Czeplak where it isn't measured. **We don't have to estimate it: FortyGuard gives us the irradiance directly**, which makes our WBGT better-conditioned than the free calculator's, not worse.

```
WBGT_outdoor = 0.7·T_nwb + 0.2·T_globe + 0.1·T_air
```
Implement Liljegren (there are open Python ports) or, as a documented fallback, a published approximation — but *label which one you used in the UI*. Then map WBGT to a work/rest ratio via the ACGIH screening table, and to OSHA's proposed triggers: **80 °F heat index = initial trigger** (water, shade, acclimatisation), **90 °F heat index = high-heat trigger** (mandatory 15-minute paid breaks every two hours, symptom monitoring). The rule is still in rulemaking as of 2026 and OSHA enforces heat in the interim under the General Duty Clause — say that accurately, it shows you checked rather than assumed.

The output that matters to a superintendent is not a safety score. It is: **a five-hour window at a 25% rest ratio is 3.75 productive crew-hours, and your activity needs 6.** The heat constraint doesn't just close windows, it *shrinks* them, and that feeds straight into the sequencer.

---

## 6. The Work Face Thermal Twin

FortyGuard gives 2 m air temperature at 60 m. Most specifications govern surface temperature. The twin is the bridge.

### 6.1 Inputs (all cached forever, built once per work face)

| Source | Yields |
|---|---|
| `satellite` segmentation | Land-cover class fractions → **solar absorptivity α**, **thermal inertia class** (bare concrete, asphalt, steel deck, soil, vegetation) |
| `streetview` segmentation | Vertical obstruction fraction → **sky view factor ψ**, façade orientation for elevated faces |
| `env_params` | GHI/DNI/DHI, cloud cover octas, elevation, RH, wet bulb |
| External | Wind speed (site-level scalar) |
| Site model | Erected-steel shading mask for elevated work faces — a manual polygon per face is fine and honest |

### 6.2 The model

A first-order surface energy balance, deliberately simple and fully published in the app's assumptions page:

```
T_surf(t) = T_air(t) + (α · GHI(t) · ψ(t)) / (h_c(V) + h_r)   −   ε · ΔLW_night(t)

α        solar absorptivity by land cover  (asphalt ≈ 0.90, aged concrete ≈ 0.65,
         galvanised steel ≈ 0.25, coated steel ≈ 0.45, vegetation ≈ 0.75)
ψ        sky view factor from streetview obstruction
h_c(V)   convective coefficient ≈ 5.7 + 3.8·V        (V in m/s)
h_r      linearised radiative coefficient ≈ 5 W/m²K
ΔLW      night-time longwave loss term, scaled by (1 − cloud_octas/8)
```

Two things to get right and to say out loud:

1. **The night term is not decoration.** Clear-sky radiative cooling drives a surface *below* air temperature after sunset — typically 2–5 °C on a clear night. That undershoot is precisely what brings the steel down to dew point at dawn and closes the coating window. Without it your model would say night work is always fine, which is wrong, and a coatings inspector in the audience would know it.
2. **Degrade gracefully.** No segmentation for a face → fall back to a land-cover-only α, mark `confidence: medium`. No streetview → ψ = 1, `confidence: low`. Show the downgrade in the UI. This reads as maturity, and it is the same move that worked in Porchlight.

### 6.3 Validation

You will not have a field probe. What you can do, and should, is a **consistency panel**: plot modelled T_surf against the FortyGuard `tcm` air series and against the published expectation (asphalt in full sun runs 20–30 °C above air; galvanised steel far less), and state the coefficient sources. One notebook, one figure in the deck, labelled *"model, not measurement."* Honest, and it inoculates you against the "you made this up" question.

---

## 7. The sequencer

**No LLM ever touches this.** It is a constrained scheduling problem and it must be deterministic, testable and explicable.

### 7.1 What it solves

Given, for a rolling 72-hour horizon:
- Activities with a trade, a work face, a duration, precedence links, total float, milestone dates
- Per-activity open intervals from the window engine
- Crew capacity per trade per shift
- The productivity haircut from the WBGT constraint

Find an assignment of start times such that every activity sits inside an open interval, precedence holds, crew capacity is respected, and **float consumption is minimised**.

### 7.2 Two implementations, in order

**Greedy interval packer (Day 7, committed).** Topologically sort by precedence, order by ascending total float (critical first), place each activity in its earliest feasible open interval that satisfies crew capacity. Backtrack one level on failure. ~200 lines, always ships, and for a 300-activity demo it is fast and usually optimal enough.

**CP-SAT (Day 9, only if green.)** OR-Tools `NewOptionalIntervalVar` per activity per candidate window, `AddNoOverlap` per crew, `AddCumulative` for capacity, precedence as linear constraints, objective = minimise total float consumed + weighted count of unplaceable activities. Free, Python, deterministic, and it gives you provable infeasibility — which is the *good* answer to give a superintendent: *"there is no compliant sequence before Thursday's milestone; here is the minimal set of constraints you'd have to relax."*

Guard rail: **CP-SAT is a Day-9 upgrade, not a Day-7 dependency.** If the greedy packer is working and the trace is clean, do the deck instead.

---

## 8. The agent

### 8.1 The loop

Hand-rolled with native tool use. No framework — you want the trace to be a feature, not something you have to explain.

```
SCAN       list_activities_in_lookahead(72)
EVALUATE   for each: get_work_face_thermal → evaluate_window   [deterministic]
CONFLICT   group by work face + shift; find activities competing for the same open hours
PROPOSE    LLM picks a strategy: shift · split · resequence · mitigate · RFI · escalate
           and calls propose_resequence for the actual arithmetic
GATE       deterministic policy engine — approve, modify, or deny with a reason
ACT        gated tools only
VERIFY     re-evaluate the affected activities against the new plan
RECORD     append to the hash chain
```

### 8.2 What the LLM actually does (it is a small job)

| Step | AI? |
|---|---|
| Fetch thermal series | No |
| Dew point, WBGT, evaporation rate, cure integrals | **No — plain Python** |
| Window evaluation | **No** |
| Sequencing arithmetic | **No — solver** |
| Choose which resolution strategy to attempt, in what order, and write the rationale a human reads | **Yes** |
| Draft the escalation note and the RFI text | **Yes** |

Keeping the physics out of the model is not a cost decision, it is a correctness decision — but it happens to also be why the token bill is trivial.

### 8.3 The policy gate

Full rule list in `WORKFACE_PROJECT_PLAN.md §4.3`. Implementation notes:

- Rules live in `apps/api/agent/policy.py` as pure functions `(proposal, context) → Verdict(approve|modify|deny, reason, rule_id)`.
- Every rule has a test in `tests/test_policy.py`, including **the deny case**, and CI runs them on every PR.
- Config-driven thresholds (`max_float_days_consumed`, `wbgt_rest_ratio_escalate`, `usd_threshold_for_approval`) in one YAML file — **show that file on a slide.** It makes the system auditable, which is the point.

### 8.4 The record (hash chain)

```
entry_n.hash = sha256( entry_n.payload_canonical_json || entry_{n-1}.hash )
```
Payload includes: run id, timestamp, activity id, trade, work face, the FortyGuard `fg_activity_id`s the decision rests on, the computed series digest, the clause cited, the proposal, the gate verdict and rule id, the action taken, the approver. Export as CSV and as the **thermal certificate PDF**.

Provenance is the point: a claims consultant can take the `fg_activity_id` back to FortyGuard and re-derive the number. Say that.

---

## 9. Stack

| Layer | Choice | Why this one |
|---|---|---|
| Backend | **Python 3.11 + FastAPI + Pydantic v2** | Every FortyGuard endpoint is async submit-and-poll; `httpx.AsyncClient` + `asyncio` is the natural shape |
| Scheduling solver | **OR-Tools CP-SAT** (greedy fallback) | Free, deterministic, provable infeasibility. This is the one genuine addition over the Porchlight stack |
| Worker | **GitHub Actions cron** | No server to keep alive. Logs are public and timestamped, which suits the audit story |
| DB | **Supabase Postgres 16 + PostGIS** | Polygons, tiles and time series. Auth + realtime + free tier in ten minutes |
| Cache | **Postgres table**, content-addressed on the normalised request body | Redis dropped — one less service, one less thing to explain |
| Agent | **Open-weight model, native tool use, hand-rolled loop** | See §10 |
| Frontend | **Next.js 15 + TypeScript + Tailwind + shadcn/ui** | Fast, and shadcn makes a controls console look expensive for free |
| Map | **deck.gl `GeoJsonLayer` over Mapbox GL** | `map_data` arrives as a GeoJSON FeatureCollection; deck.gl renders thousands of tiles at 60 fps. Highest-impact visual decision in the project |
| Window ribbon | **Hand-rolled SVG** (or visx) | Do **not** reach for a Gantt library. The ribbon is ~150 lines of SVG and a Gantt lib will fight you for a day |
| Charts | **Recharts** | T(t) curves, the offset band, the cure-fit plot, `stats_data` distributions |
| Schedule import | **PyP6Xer** or **xerparser** (P6 XER) + CSV fallback | Ingesting a genuine P6 export is a large credibility win with EPC judges for ~a half-day of work. CSV is the guaranteed path |
| Wind | **Open-Meteo** or NWS point forecast | Free, no key, site-level scalar |
| Notifications | **Resend** (email) + simulated SMS inbox in-app | Do not burn a day on Twilio verification |
| Deploy | Vercel (web) · GitHub Actions (worker) · Supabase (DB) | Public URLs matter. A judge who can click your link is a judge who remembers you |

⚠️ **Do not use a sleeping free tier for anything judge-facing.** A 30-second cold start is a dead demo.

---

## 10. The LLM decision

**Carry over the Porchlight answer: open-weight models behind one env var.** The reasoning is *stronger* here, not weaker.

> **WORKFACE runs entirely on open-weight models. A contractor's P6 schedule — activity durations, float, milestone dates, subcontractor sequencing — never leaves their network.**

A project schedule is one of the most commercially sensitive documents a contractor has; it is the thing their delay claim and their competitors' bids both turn on. "It runs on your infrastructure" is a **procurement unlock** for construction buyers, exactly as it was for pharmacy buyers. Their IT will ask. You have the good answer for free.

One client, one env var:
```python
client = OpenAI(base_url=os.environ["LLM_BASE_URL"],
                api_key=os.environ["LLM_API_KEY"])
```
```bash
# laptop
LLM_BASE_URL=http://localhost:11434/v1              LLM_MODEL=qwen3:8b
# live
LLM_BASE_URL=https://api.deepinfra.com/v1/openai    LLM_MODEL=llama-3.3-70b-instruct-turbo
```

**Budget.** The agent reasons over only the flagged subset (~40 of 300 activities), and the physics is Python. Expect a few cents per run, single-digit dollars for the whole sprint. **FortyGuard credits are the real constraint** — design around those, not the tokens.

**The trap: don't swap blind at the end.** Models are interchangeable in API shape, not behaviour. A prompt tuned on a local 8B can call the wrong tool on a 70B. **Run the full agent against the demo model on Day 6, and every couple of days after.** `tests/test_agent_replay.py` — ten fixed scenarios, assert the chosen tool — run against both models. Thirty minutes to write, turns "did the swap break anything" into a ten-second check.

---

## 11. Testing

| Suite | Owner | What it protects |
|---|---|---|
| `test_psychro.py` | T3 | Magnus dew point against known pairs; WBGT against published examples |
| `test_constraints.py` | T3 | Each of the seven evaluators against hand-worked series; the two-sided in-band arithmetic |
| `test_cure.py` | T3 | Q10 fit reproduces the Macropoxy PDS cure table within tolerance |
| `test_evaporation.py` | T3 | ACI 305 formula against nomograph readings |
| `test_sequencer.py` | T3 | Precedence never violated; float minimised; known-infeasible case reports infeasible |
| `test_policy.py` | T3 | Every rule, **including the deny case** |
| `test_agent_replay.py` | T3 | Ten fixed scenarios, both models |
| `test_fortyguard.py` | T2 | Submit/poll/backoff/cache/credit meter against recorded responses |
| `test_import.py` | T2 | XER and CSV → canonical activity model |

CI runs `pytest tests/` on every PR. Ten lines of YAML. Across three timezones it is your only cheap defence against silent breakage.

---

## 12. Known limitations — write these down, then say them first

Putting these in the app and the deck is not a weakness. It is the single clearest signal that you built a product rather than a demo.

1. **No wind field.** FortyGuard's `env_params` has no wind speed. Wind enters the evaporation rate, the WBGT, the convective term in the surface model and the TMS 602 hot-weather masonry trigger. We take it as a site-level scalar from a free feed, so wind is not spatially resolved. *(This is also the most useful piece of product feedback you can hand the sponsor.)*
2. **The surface model is a model.** It is calibrated from published absorptivity values and validated for plausibility, not against a field probe. It does not replace the surface thermometer the standards require an inspector to use.
3. **12-hour forecast horizon.** Handled by the three-tier architecture; Tier 0 is a probability, not a forecast, and the UI must say so.
4. **Registry depth.** Twelve trades, US practice, hand-curated. Real deployment needs the submittal-register integration that pulls the actual approved product data sheets for *that* project.
5. **Advisory only.** WORKFACE plans and records. It does not certify, and it does not replace inspection or the engineer of record.
6. **`streetview` and `satellite` coverage** will be sparse on a greenfield site. Degrade with a visible confidence downgrade.

---

## 13. Rules we're committing to

1. The window math, the psychrometrics and the sequencing are **never** done by an LLM
2. The website **never** calls FortyGuard or the LLM on page load
3. Cache every FortyGuard response; historical and twin data cached forever
4. Cluster work faces into AOI polygons before any heatmap call — never one call per activity
5. Poll the credit meter after every batch; hard daily cap in config; fail loudly at 80%
6. `fg_activity_id` vs `activity_id` — never blurred, anywhere
7. Dev on the small model, demo on the large one; replay tests run against both
8. Every registry row carries a citation a human can check
9. `REPLAY_MODE=true` is the default from Day 1
10. Feature freeze end of Day 10 — Days 11–12 are video, deck, submission

---

## 14. Day-1 action items

- [ ] Confirm the FortyGuard credit balance via `/v1/system/fetch-api-key-usage` and write the number somewhere visible
- [ ] Sign up for the inference provider, key into shared secrets
- [ ] `llm_client.py` against the OpenAI-compatible interface — env var only, no hardcoded provider
- [ ] Supabase (Postgres + PostGIS) up; Vercel deployed with a public URL even if it shows nothing
- [ ] GitHub Actions cron skeleton writing a dummy row to Supabase
- [ ] `packages/schemas` — all three of you, one sitting, including the `fg_activity_id` naming rule
- [ ] Pin the demo site polygon and the hero work face; everything downstream depends on that geometry

---

*Technical specification prepared 19 August 2026. Formulas are cited to their sources in the text; the evaporation-rate equation is the Menzel/NRMCA form behind the ACI 305 nomograph, the dew point is Magnus–Tetens, and the WBGT method follows Liljegren et al. (2008) as used by OSHA's published outdoor WBGT calculator. All model coefficients are published in the application's assumptions page.*
