# WORKFACE — Project Plan
### The multi-trade construction window agent
**FortyGuard Hackathon'26 · Build sprint 19–30 August 2026 · Primary track: AI Agents (+ Predictive Models · Interactive Maps · Dashboards)**

> ⚠️ **Verify the sprint window before you use the day numbers.** The only dated press source on Hackathon'26 says build 3–17 Aug, judging 18–31 Aug. You specified 19–30 Aug. Confirm against fortyguard.com/hackathon26 and shift `WORKFACE_SCHEDULE.md` if needed — nothing else in this plan depends on the dates.

---

## 0. The one-line version

> A construction specification is not a temperature. It is a **window** — a band, an offset from dew point, a continuous run of hours, a cure clock that runs at a temperature-dependent speed. Every trade on a site has a different one, and every one of them is written against the temperature *at the work face*, not the airport. **WORKFACE reads the project schedule, computes every trade's window at 60-metre resolution, finds the hours where nine trades are fighting over five compliant hours, and resequences the day.**

Say that and nothing else at the start of the demo.

---

## 1. Why this idea can win — and the two things that would sink it

### 1.1 The gift hiding in the API docs

FortyGuard's `heatmap` endpoint ships four `analytic_type` values. Most teams will use one of them (`tcm`, the temperature snapshot) and colour a map. Read the other three next to a construction specification:

| FortyGuard analytic | What a spec actually asks |
|---|---|
| `exceedance` — hours past a threshold, with `direction: above` **or `below`** | *"How many hours was this work face inside the manufacturer's band?"* |
| `persistence` — **longest continuous run** past a threshold | *"Was there an unbroken run long enough for the protection period?"* — ACI 306's protection period, SFRM's 24 hours ≥ 40 °F, a coating's cure-to-service |
| `time_of_measure` — **hour of day the peak occurs**, per tile | *"When does this work face peak, so when do I send the crew?"* — the sequencing primitive |

These are not weather metrics. They are the three questions a construction specification asks, already computed, already served, per 60-metre tile, by the sponsor's own API. **`persistence` is a protection period. `exceedance` is a compliance hour count. `time_of_measure` is a crew dispatch time.** You are the team that noticed.

And the `direction: below` parameter is the tell that almost nobody will use. Heat-only teams will never touch it. Construction windows are **two-sided** — every trade has a floor and a ceiling — which makes WORKFACE the only submission that uses the endpoint's full surface.

### 1.2 The second gift: the specs are written against a temperature nobody sells

FortyGuard publishes 2 m-above-ground **air** temperature. Now read what the standards actually govern:

- SSPC-PA 1 and every coating PDS govern **surface temperature** and its offset from dew point — Sherwin-Williams Macropoxy 646 requires the substrate at least **5 °F above dew point**, RH ≤ 85%, surface ≥ 35 °F.
- Asphalt placement is governed by **base surface temperature**, not air — the cessation table runs off it, and it sets how many minutes of compaction you get.
- Hilti HIT-RE 500 V3 and every adhesive anchor system govern **base material temperature**, which sets working time and cure time.
- ACI 305 governs **concrete temperature** and, through the evaporation-rate equation, a composite of concrete surface temperature, air temperature, RH and wind.

So the product is a translation layer. FortyGuard gives you a 60 m field of air temperature, humidity, solar irradiance (GHI/DNI/DHI) and land cover. **WORKFACE turns that into the surface temperature, dew point and WBGT that the specifications are actually written against.** That conversion — a small, honest surface energy balance driven by FortyGuard's own solar and land-cover data — is the moat. It is also the reason a general contractor pays for this instead of opening a weather app.

### 1.3 The trap that kills this project — answer it before a judge asks

The original brief flagged it: **"it is hot-weather concreting wearing a coat."** A judge will say exactly that. Here is why it isn't, and you must be able to say this in one breath:

**If concrete were the only trade, there is no problem to solve.** You move the pour to 5 a.m. and you're done. The problem only exists because moving the pour to 5 a.m. puts the coating crew into the dawn dew-point convergence, and the fireproofing into a slot where the 24-hour continuity can't be guaranteed, and the whole shuffle eats four days of total float on a near-critical path.

WORKFACE is not a threshold alarm. It is **contention for a scarce resource** — the compliant hours in a day — across trades with precedence links between them. On a Phoenix August day there are roughly five compliant hours and nine trades want them. That is a constrained scheduling problem, and it cannot be produced by a single trade.

To make the multi-trade framing structurally central rather than decorative, the registry is organised by **constraint type, not by trade**. Concrete is one of seven types:

| # | Constraint type | Shape | Example |
|---|---|---|---|
| 1 | **Band** | `T_min ≤ T_gov(t) ≤ T_max` | Masonry, sealant, traffic paint |
| 2 | **Offset** | `T_surface(t) ≥ T_dew(t) + Δ` | All protective coatings (SSPC-PA 1) |
| 3 | **Continuity** | compliant run ≥ N hours from placement | SFRM 24 h ≥ 40 °F; ACI 306 protection period |
| 4 | **Cure clock** | `∫ f(T) dt ≥ 1` — an integral, not a threshold | Epoxy anchors, coating recoat window, concrete maturity |
| 5 | **Composite rate** | derived rate ≤ limit | ACI 305 evaporation rate ≤ 0.2 lb/ft²/hr |
| 6 | **Decay clock** | available minutes = f(base temperature) | Asphalt compaction window |
| 7 | **Human** | WBGT → work/rest ratio → effective crew hours | OSHA / ACGIH heat stress |

Seven mathematical shapes. Concrete touches three of them. That is what makes this multi-trade in substance, not in framing.

### 1.4 The trap everyone has: the 12-hour horizon

The API forecasts 12 hours ahead. Construction plans in three-week look-aheads. Do not hand-wave this — build the answer as **three tiers**, and note that this is one tier richer than the obvious two:

- **Tier 0 · Plan (weeks to months out).** Historical heatmaps, 2019 → now, one August window per year. Produces a per-tile, per-hour **probability that each trade's window is open**: *"This work face has had a compliant coating window on 34% of August mornings over seven years, opening at a median of 06:40 and closing at 09:10."* That is a defensible look-ahead planning signal, and it uses the API's full seven-year depth, which most teams will ignore entirely.
  **Watch the constraint:** `filter_type: 4` caps at **one month per request**. The climatology is N cheap calls, one August window per year, cached forever — not one big sweep. Build the loop on Day 4; do not discover this on Day 10.
- **Tier 1 · Commit (T-12 h to now).** Live forecast heatmap. This is the go/no-go on tomorrow's work packages, in the window where a superintendent can still move a crew, a ready-mix order or a lighting plan.
- **Tier 2 · Record (after the fact).** Historical heatmap re-queried post-placement, producing an immutable **as-built thermal record** for every installed work package.

Say this on stage: *"The 12-hour horizon is a commit window, not a planning window. Planning runs on seven years of history and compliance runs on the record. We built three loops."* The limitation becomes evidence of design.

### 1.5 The sleeper feature that is probably the real business

**Tier 2 is the money.** Construction disputes are won and lost on documentation. Today the evidence that a coating was applied inside its window is a foreman with a surface thermometer writing a number on a paper log at 7 a.m. That log is what a manufacturer's warranty adjuster and an opposing delay expert both attack.

WORKFACE produces, for every work package, a **thermal certificate**: hourly air, surface and dew-point series at the work face, the manufacturer clause it was evaluated against, the pass/fail per hour, and the FortyGuard `activity_id` as provenance. It is the warranty defence and the weather-delay claim evidence in the same artifact.

Nobody else will build the backward-looking half. Put it on a slide titled **"The other half of the product looks backwards."**

---

## 2. What you are actually building

### 2.1 Product surface — four views, one system

| View | User | Track it wins | The moment |
|---|---|---|---|
| **Site Console** | Project controls / superintendent | Interactive Maps + Dashboards | A 60 m map of a 1,100-acre campus with 40 work faces; below it, one **window ribbon** per activity — a horizontal timeline with the compliant hours in green and the scheduled bar sitting half outside it |
| **Agent Trace** | Scheduler / QA-QC | AI Agents | Replayable decision log: what it saw, which clause it cited, what it proposed, which policy rule fired, who approved |
| **The Record** | Warranty / claims / EOR | Dashboards | Per-work-package thermal certificate, exportable, with FortyGuard `activity_id` provenance |
| **Morning Brief** | Foreman, on a phone | Human impact | *"Deck 4 coating: window opens 06:50, closes 09:20. Pour C-14 moved to 05:00. Fireproofing on hold — no compliant 24-hour run before Thursday."* |

Build the Site Console first. Build the Morning Brief last — two hours, and it is the slide that makes judges believe a superintendent would actually open this.

### 2.2 The window ribbon is the hero visual

One horizontal lane per activity. X-axis is 48 hours. Green where every constraint for that trade is satisfied at that work face, amber where one is marginal, red where it fails, with the *reason* on hover. The scheduled activity bar is drawn on top. **When the bar is not sitting on the green, you have a problem, and you can see it without reading a number.**

Then the money shot: two work faces on the same slab, 300 m apart, one shaded by erected steel and one bare. Same activity, same trade, same day — **one ribbon green from 05:00 to 10:00, the other green from 05:00 to 07:20.** The regional forecast is a single number for both.

### 2.3 The pipeline, end to end

```
  ┌────────────────────────────────────────────────────────────────┐
  │ 1. INGEST                                                      │
  │    Project schedule (P6 XER export or CSV)                     │
  │    → activities, trades, durations, precedence, total float    │
  │    → work faces (geometry) → 60 m tiles → AOI clusters         │
  └───────────────────────────┬────────────────────────────────────┘
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ 2. WORK FACE THERMAL TWIN            [cached, built once]      │
  │    POST /v1/satellite   → land cover → albedo, thermal inertia │
  │    POST /v1/streetview  → obstruction, orientation, shading    │
  │    → absorptivity, sky view factor, exposure class per face    │
  └───────────────────────────┬────────────────────────────────────┘
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ 3. THERMAL FIELD                                               │
  │    Tier 0: heatmap filter_type 4, one Aug window × 7 years     │
  │            exceedance + persistence, above AND below           │
  │    Tier 1: heatmap filter_type 2, next 12 h, tcm, 60 m         │
  │            + time_of_measure for peak-hour sequencing          │
  │    env_params → RH, wet bulb, solar GHI/DNI/DHI, cloud, elev   │
  │    external → wind speed (the one field the API lacks)         │
  │    → per work face: T_air(t), T_surf(t), T_dew(t), WBGT(t)     │
  └───────────────────────────┬────────────────────────────────────┘
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ 4. WINDOW ENGINE               ← this is the moat              │
  │    Trade window registry (12 trades, cited clause per row)     │
  │    7 constraint evaluators over the series                     │
  │    → per activity: open intervals, margin, binding constraint, │
  │      $ exposure, human-readable verdict + citation             │
  └───────────────────────────┬────────────────────────────────────┘
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ 5. SEQUENCER (deterministic)                                   │
  │    Interval packing under precedence + float + crew capacity   │
  │    greedy → CP-SAT upgrade. Never an LLM.                      │
  └───────────────────────────┬────────────────────────────────────┘
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ 6. AGENT LOOP                                                  │
  │    SCAN → EVALUATE → CONFLICT → PROPOSE → POLICY GATE →        │
  │    ACT → VERIFY → RECORD → (escalate?)                         │
  └───────────────────────────┬────────────────────────────────────┘
                              ▼
  ┌────────────────────────────────────────────────────────────────┐
  │ 7. SURFACES: Console · Trace · Record · Morning Brief · API    │
  └────────────────────────────────────────────────────────────────┘
```

---

## 3. The trade window registry — build this properly, it is your differentiator

Twelve trades. Depth beats breadth. **Cite a clause for every row** so the agent can quote a source, exactly as Porchlight quoted FDA labels. Full schema and the seeded values are in `WORKFACE_TECH_SPEC.md §4`; the shape:

| Field | Example |
|---|---|
| `trade_id` | `coating_epoxy_structural_steel` |
| `governing_temp` | `surface` |
| `constraint_types` | `["band", "offset", "cure_clock"]` |
| `t_min_c` / `t_max_c` | 1.7 / 121.1 |
| `dew_point_offset_c` | 2.8 (5 °F) |
| `rh_max_pct` | 85 |
| `cure_hours_at_ref` | 168 h @ 25 °C |
| `unit_cost_usd_per_m2` | 34 |
| `rework_multiplier` | 3.2 (strip, re-prep, re-apply) |
| `citation` | "Sherwin-Williams Macropoxy 646 PDS, Application Conditions: surface min 35 °F, at least 5 °F above dew point, RH max 85%" |
| `standard_ref` | "SSPC-PA 1 / AMPP" |

Seed set, chosen so that all seven constraint types are exercised and every name is one an EPC judge recognises:

1. **Cast-in-place concrete — hot weather** · ACI 305.1 / ACI 301, 95 °F (35 °C) max at discharge · types 1, 5
2. **Cast-in-place concrete — cold weather** · ACI 306R: cold weather is when air temperature has fallen to, or is expected to fall below, **40 °F (4 °C)** during the protection period · types 1, 3
3. **Structural steel protective coating** · SSPC-PA 1 + Macropoxy 646 PDS · types 1, 2, 4
4. **Sprayed fire-resistive material (SFRM)** · Isolatek: substrate and ambient ≥ 40 °F maintained before, during and **24 h after** · type 3
5. **Adhesive anchors** · Hilti HIT-RE 500 V3, base material temperature range, working/cure time as a function of base temp · types 1, 4
6. **Hot-mix asphalt paving** · base surface temperature vs lift thickness cessation table; compaction window in minutes · types 1, 6
7. **Masonry — hot weather** · TMS 602 / ACI 530.1: procedures at forecast > 100 °F, or > 90 °F with wind > 8 mph; enhanced above 115 °F · types 1, 5
8. **Masonry — cold weather** · TMS 602: procedures below 40 °F; do not lay units below 20 °F · types 1, 3
9. **Elastomeric joint sealant** · ASTM C1193 + manufacturer band; substrate dry and above dew point · types 1, 2
10. **Waterborne pavement marking** · surface temperature minimum and rising; DOT specification · types 1, 2
11. **Structural welding** · AWS D1.1 preheat as a function of base metal temperature and thickness · type 1 (with a preheat *mitigation* rather than a hard stop — good demo nuance)
12. **Crew heat exposure** · OSHA proposed heat rule triggers (80 °F HI initial, 90 °F HI high-heat with mandatory 15-min breaks every 2 h) + ACGIH WBGT work/rest · type 7

> **Rule you must follow.** Brand every output as **advisory and contractual, not a substitute for field measurement**. WORKFACE tells you when to *plan* the work and produces the record; the inspector still puts a probe on the steel. Say that in the product, in the deck, and out loud when a judge asks. Visible restraint is the fastest way to look like a real company — and the standards themselves require field measurement, so claiming otherwise is a factual error a judge may catch.

---

## 4. The agent (primary track — make it genuinely agentic)

### 4.1 What "agentic" has to mean here

A chatbot with a weather tool is not an agent. Yours qualifies because it **runs unattended on a schedule, over a work queue it wasn't handed, resolves contention between competing activities, takes actions with real-world consequence, and is accountable for every one.** Hand-roll the loop with native tool use. The trace is a feature, not a debug log.

```
SCAN → EVALUATE → CONFLICT → PROPOSE → GATE → ACT → VERIFY → RECORD → (escalate?)
```

The step that makes it interesting is **CONFLICT**. The agent is not scoring parcels independently; it is discovering that Activity A's fix breaks Activity B.

### 4.2 Tool surface

| Tool | Purpose |
|---|---|
| `list_activities_in_lookahead(days)` | The queue the agent works |
| `get_work_face_thermal(activity_id)` | heatmap + env_params + twin → the four series |
| `get_trade_window(trade_id)` | Registry lookup, returns the cited clause |
| `evaluate_window(series, trade_id)` | Deterministic → open intervals + binding constraint |
| `get_schedule_context(activity_id)` | Predecessors, successors, total float, milestone dates |
| `propose_resequence(activity_ids, horizon)` | **Deterministic solver**, not the LLM |
| `shift_activity(activity_id, window)` | **Irreversible — gated** |
| `split_activity(activity_id, windows)` | **Irreversible — gated** |
| `request_mitigation(activity_id, kind)` | Chilled water · evaporative retarder · windbreak · heated enclosure · night lighting · preheat |
| `raise_rfi(activity_id, question)` | Engineer of record — the only path to accepting out-of-spec work |
| `notify_crew(activity_id, channel, message)` | **Irreversible — gated** |
| `escalate_to_superintendent(activity_id, rationale)` | Human in the loop |
| `write_record(...)` | Append-only, hash-chained |

### 4.3 The policy gate — your enterprise credibility

The agent **proposes**; deterministic code **disposes**. Encode these as testable rules and show the suite passing on a slide:

- Never move an activity past a **contractual milestone date** — escalate.
- Never consume more than **N days of total float** on a near-critical activity without escalation. *(This is CPM vocabulary. Say "float" on stage and every construction judge knows you did the reading.)*
- Never violate a **precedence link** — no coating a substrate that hasn't cured.
- Never approve application **outside a manufacturer's published window**. That is a warranty-voiding act and only the EOR can accept it, via RFI.
- Never schedule a crew into a WBGT band requiring **> 50% rest** without flagging it against the OSHA trigger.
- **Night work is never auto-approved** — lighting plan, noise ordinance and a second-shift crew are human decisions.
- Never move an activity with an **inspection hold point** (a pour needing a city inspector) without escalation.
- Fail **closed** on a stale (> 2 h) or missing forecast — escalate, don't guess.

**The killer test.** Feed it a day where the cheapest fix is to move the pour to 05:00 — and that shift pushes the coating into the dawn dew-point convergence *and* eats four days of float on the near-critical path. Show the agent finding a split instead, and where no split exists, escalating with the tradeoff written out. Ten seconds of demo, enormous credibility.

### 4.4 The record

Every run writes an append-only, hash-chained entry: inputs, tool calls, raw FortyGuard `activity_id`s, the computed series, the clause cited, the proposal, the gate verdict, the outcome, the human who approved. This is the artifact a claims consultant buys. Render it as a clean timeline; export it as a PDF certificate.

---

## 5. Demo strategy — the thing that actually decides the outcome

### 5.1 Non-negotiable rules

1. **Never make a live API call during the demo.** `REPLAY` from committed fixtures by default, with a visible toggle to `LIVE` you flip **once**, at the end, on one work face. Credibility of live, risk of neither.
2. **One site, owned completely: a semiconductor fab campus, North Phoenix, August.** Real geography, real standards, synthetic schedule — label it exactly that way. Phoenix in monsoon August is the best possible stage because it is two-sided within a single day: afternoons blow the hot bounds (evaporation rate, masonry, WBGT, adhesive cure), and dawn brings the dew point up to the steel and closes the coating window. **The compliant band is roughly 05:00–09:00 and nine trades want it.** That is the whole product in one sentence.
3. **One extra call proves the other half.** Run a single January `persistence` heatmap with `direction: below` at 4 °C (40 °F) and put it on a slide beside the August one: *"Same site, same endpoint, opposite constraint. Cold-weather concreting is the same query with one parameter flipped."* One call, one slide, kills the "this is just heat" objection.
4. **Under three minutes for the core narrative.**

### 5.2 The demo script (2:50)

| Time | Beat |
|---|---|
| 0:00–0:20 | **Cold open.** A photo of a coating crew on a steel deck at dawn. "This crew has four hours. Not because of the schedule — because at 05:40 the steel is three degrees above dew point and the spec says five, and by 10:00 the deck is 58 °C and the spec says stop. Nobody on this site knows that until they get there." |
| 0:20–0:40 | **The gap.** One diagram: the schedule (P6, planned in months) against the window (physics, resolved in hours, varying across 300 metres). "Every trade has a published window. Nobody has ever had the temperature at the work face to check it against." |
| 0:40–1:20 | **The map + the ribbon.** Site console, 60 m tiles across the campus. Two work faces on the same slab, 300 m apart. Same trade, same day, **windows differing by two hours forty**. Then pull back: nine ribbons, five green hours, visible collision. |
| 1:20–1:55 | **The science.** Click one activity. Show T_air, T_surf and T_dew converging at dawn, the SSPC 5 °F offset drawn as a band, and the Macropoxy clause quoted inline. Then the concrete one: the ACI 305 evaporation rate crossing 0.2 lb/ft²/hr at 09:40. "We don't flag heat. We evaluate the clause." |
| 1:55–2:30 | **The agent.** Live trace. Scans 300 activities → flags 41 → resolves the pour/coating collision with a split → **then immediately the second case**, where the fix would eat the float on the near-critical path and it escalates to the superintendent with the tradeoff written out. "It knows what it isn't allowed to do." |
| 2:30–2:50 | **The business.** "Field rework runs about 5% of construction value and 12% at the 90th percentile — CII's number, not ours. This package is $180M. And when the warranty adjuster comes back in year three—" *(open the thermal certificate)* "—this is what the contractor hands them." Close on the foreman's phone. |

### 5.3 The numbers on screen

`$ at risk` and `$ protected` counters, derived from real unit costs and rework multipliers in the registry. Money is the language of impact.

---

## 6. Deliverables checklist

- [ ] **Public live URL** — Site Console in REPLAY, no login, loads under 3 s
- [ ] **Demo video ≤ 3:00** — captioned, 1080p, script in §5.2
- [ ] **GitHub repo** — clean README, architecture diagram, one-command setup, permissive licence
- [ ] **Deck, 12 slides** — Problem · The window, not the temperature · The three analytics coincidence · Work Face Twin · The seven constraint types · Three-tier temporal architecture · Agent + policy gate · Live demo · The Record (looking backwards) · Impact numbers · Architecture · Roadmap & ask
- [ ] **`PILOT.md`** — what a 90-day pilot with one GC on one project looks like: integration surface (P6 export cadence), data requirements, success metrics, pricing hypothesis. *Almost nobody writes this.*
- [ ] **One exported thermal certificate PDF**, linked from the deck
- [ ] **`heat_intelligence` PDF** for the hero work face
- [ ] **Test suite** — window evaluator golden values, policy gate cases, agent replay determinism
- [ ] **Track declaration** — primary **AI Agents**, secondary Predictive Models · Interactive Maps · Dashboards

---

## 7. Track coverage — claim all four, honestly

| Track | Your evidence |
|---|---|
| **AI Agents** (primary) | Unattended scheduled agent, 13 tools, contention resolution, irreversible actions, policy gate, RFI + escalation paths, hash-chained record |
| **Predictive Models** | Three-tier temporal model (7-year climatological window priors + 12 h forecast + retrospective record); surface energy-balance model; WBGT via the Liljegren method OSHA's own calculator uses; ACI 305 evaporation rate; temperature-dependent cure clocks |
| **Interactive Maps** | 60 m deck.gl tile map over a real campus, dual-work-face comparison, `time_of_measure` peak-hour layer, exceedance/persistence layers in **both directions**, time scrubber |
| **Dashboards** | Site Console with the window ribbon, conflict queue, $ at-risk/$ protected, agent feed, the Record timeline, distributions from `stats_data` |

---

## 8. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| **API credits exhausted mid-sprint** | 🔴 High | One AOI polygon per work-face cluster, not per activity; 100 m for the planning sweep, 60 m only for flagged faces; historical cached forever; credit meter after every batch; hard daily cap in config; fixtures frozen Day 11 |
| **Live demo fails on stage** | 🔴 High | REPLAY from committed fixtures is the default all sprint; LIVE is a one-face flourish |
| **"This is just hot-weather concreting"** | 🔴 High | §1.3, rehearsed verbatim. Seven constraint types, cross-trade contention, the two-sided January slide |
| **Judge challenges the 12 h horizon** | 🟠 Med | Three-tier architecture as deliberate design (§1.4) |
| **Substrate model reads as invented** | 🟠 Med | Publish the energy balance, its coefficients and its sources on an assumptions page in the app; show the confidence downgrade when segmentation is unavailable; state plainly that it does not replace a field probe |
| **No wind field in the API** | 🟠 Med | Pull wind as a site-level scalar from a free feed; be explicit that FortyGuard supplies the spatial field. Then say it out loud as product feedback — an API company likes hearing which field you wished they had |
| **Scheduler judges want real P6** | 🟡 Low | Ship an XER reader (PyP6Xer/xerparser) as a Day-6 item with CSV as the guaranteed fallback. Ingesting a genuine P6 export is a large credibility win for a small cost |
| **CP-SAT rabbit hole** | 🟠 Med | Greedy interval packer on Day 7 is the committed deliverable; CP-SAT is a Day-9 upgrade, only if green |
| **Synthetic schedule reads as fake** | 🟡 Low | Real campus geography, real trade sequences, real durations, real unit costs. Label it "synthetic schedule, real geography, real standards" |
| **Scope creep** | 🟠 Med | Hard freeze end of Day 10. Everything in §9 is explicitly out |

---

## 9. Explicitly out of scope

Real P6 write-back · multi-project portfolios · BIM/IFC model ingestion · crew and equipment cost modelling · procurement and ready-mix ordering integration · subcontractor accounts and permissions · anything outside the United States · IoT sensors on site · more than 12 trades · more than one project.

If a judge asks about any of these: *"That's the pilot, not the hackathon"* — and point at `docs/PILOT.md`.

---

## 10. Market case (for the deck)

- **Rework is the line item.** CII's benchmark across 144 industrial projects put direct field rework at ~**5% of total construction value**, with a **90th percentile of 12.4%**; including design rework the range is commonly quoted as **6–15%**. On a $180M package that is $9M–$27M. You do not need weather to be a large share of it for the arithmetic to work.
- **Warranty denial shifts the cost.** Manufacturer warranties on coatings, sealants, roofing and fireproofing are conditioned on application within published environmental limits. Applied outside them, the manufacturer walks and the contractor eats the recoat — and today the contractor's only rebuttal is a paper log.
- **Weather delay claims turn on documentation.** An excusable delay needs proof the condition was unusual and that it actually impacted the critical path. Contractors with a per-work-face hourly record win those; contractors with a rain gauge at the trailer lose them.
- **The buyer:** EPC firms and general contractors — project controls and construction management. The FortyGuard industry page for construction is un-demoed, private-sector and fast-moving.
- **The unit:** per project per month. A mid-size GC runs 20–40 active projects. Priced in the low hundreds against a per-project rework exposure in the millions, the ROI arithmetic fits on one slide, which is exactly where it should live.
- **The wedge into Advanced Work Packaging.** AWP and WorkFace Planning are established CII/COAA practices on capital projects — the industry already decomposes work into Installation Work Packages tied to a physical work face. WORKFACE attaches a thermal constraint to that existing unit. You are not asking anyone to change how they plan.

> **Deck line:** *"The schedule says Tuesday. The specification says between 5 and 9 a.m., and only on the shaded half of the deck. Nobody has ever had both in one place."*

---

## 11. Naming

**WORKFACE** — the work face is the exact physical location where a crew works, and it is already the unit of planning in Advanced Work Packaging. Our entire thesis is that temperature is a property of the work face, not of the site or the city. The name states the argument.

Alternates: **THE WINDOW** · **CUREGUARD** · **SIXTY** · **Placement Window** · **Look-Ahead**.

---

## 12. Do these five things and nothing else if you fall behind

Ranked. If Day 8 arrives and you're behind, cut from the bottom.

1. **The window ribbon with two work faces 300 m apart showing different windows.** This is the image judges remember.
2. **One activity opened up: T_surf and T_dew converging, the 5 °F offset band drawn, the manufacturer clause quoted inline.** This is what makes it real rather than a weather app.
3. **One complete agent trace resolving a cross-trade collision, plus one escalation.** This is the primary track and the answer to "it's just concreting."
4. **One exported thermal certificate.** This is the business, and it takes an afternoon.
5. **A three-minute video that opens on a crew at dawn.** More submissions are lost to a bad video than to bad code.

---

*Plan prepared 19 August 2026 for the FortyGuard Hackathon'26 build sprint. API behaviours are drawn from the FortyGuard Temperature API documentation supplied with the brief; trade windows are drawn from published standards and manufacturer product data sheets, cited per row in the registry; rework economics are from CII benchmark research. All outputs are advisory and contractual and do not replace field measurement required by the referenced standards.*
