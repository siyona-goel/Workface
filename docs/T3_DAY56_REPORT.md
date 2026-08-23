# T3 — Days 5 & 6 report
### Climatology priors · surface model · agent loop v1 · LLM wiring — 23–24 Aug 2026

Branch `aach-day5-6`. `pytest tests/ -q` green (**164 passed**, of which 2 are the
live LLM smoke test — they **skip** when `LLM_*` is unset, so CI stays model-free).
Nothing touched under `apps/web/`, `data/fixtures/historical/`,
`data/fixtures/twin/`, or the agent fixtures (`sample_agent_run.json`,
`sample_gate_verdicts.json`).

> **Headline (put this first): the hero demo is fragile to one number.** The
> dawn coating closure on the bare deck exists *only* for a **weathered**
> galvanised deck (ε ≈ 0.85). At bright galvanising (ε ≈ 0.23) it disappears
> entirely, and even at 0.85 the worst dew-point margin is ≈ **−0.02 °C**. Say
> "weathered galvanised deck, four months of Phoenix sun" and mean it. Detail in §2.

---

## 1. What the sweep could and could not support

Verified against the data (not the manifest's aspiration): **only 35.0 °C and
4.0 °C were swept**, on `exceedance` and `persistence`, both directions. That
yields exactly **three** real Tier-0 priors, matching the registry's binding
constraints one-for-one:

| Trade | Binding constraint | Analytic | Coverage |
|---|---|---|---|
| `concrete_cip_hot_weather` | `band_concrete_discharge_max` (t_max 35 °C) | exceedance > 35 | `modelled_hour` |
| `concrete_cip_cold_weather` | `band_cold_weather_trigger` (t_min 4 °C) | exceedance < 4 | `observed` |
| `sfrm_spray_applied_fireproofing` | `continuity_40f_24h` (t_min 4 °C, 24 h run) | persistence < 4 | `observed` |

The SFRM row is the clean one: the `persistence` analytic returns a **run
length**, and `continuity` is the only evaluator asking a run-length question —
the same question, asked by the data source and the registry. p_open falls
straight out of `1 − persistence/24 h`, no modelling. **Worth saying on stage.**

The **other 9 trades return `p_open = None`, `coverage = "insufficient_threshold"`**,
each naming the Celsius threshold a future sweep would need. No interpolation, no
nearest-threshold substitution. In particular the coating hero constraint
`offset_dew_point` has **no humidity/dew point anywhere in the sweep** and is
**not** proxied off air temperature — it simply has no Tier-0 prior from this data.

Row counts: 36 tiles (40 faces collapse to 36 unique nearest tiles) × (24 h × 3
covered trades + 9 insufficient markers) = **2,916 rows**
(`data/fixtures/climatology_priors.json`). A Tier-0 prior exists for **every**
demo work face.

**`median_peak_c` is `None` on every row — deliberately.** The sweep carries only
exceedance/persistence *counts*; `stats` is null on all 140 windows and
`hourly_tcm_c` is empty on all 8,232 tiles, so there is **no temperature
magnitude to observe**. A peak would require inventing the diurnal amplitude,
which §A2 forbids. Modelling the crossing *timing* off a fixed diurnal shape is
sanctioned by §2.3 and is what we do (labelled `hour_of_day_source="modelled"`);
inventing a magnitude is not.

### The one-line ask to T2
> **`TileReading.hourly_tcm_c` is in the schema and is empty on every tile.
> Populating it on the next sweep converts every modelled opening hour into an
> observed one, and makes `median_peak_c` a real number instead of `None`.** The
> schema already anticipated this — it is a small ask, not a re-architecture.

Example planner sentences (real data, hero tile `AOI-FAB2-r03c04`):
- concrete-hot: *"This work face exceeded the 35 C concrete discharge limit for a median of 257 hours across seven Augusts — 35% of the month. Modelled crossing at 10:11, closing at 18:29."*
- coating: *"No Tier-0 prior for structural steel — high-build epoxy coating: … the sweep has no humidity/dew point anywhere …"*

---

## 2. The ε sensitivity result (the fragile number)

`eps` for galvanised steel (segmentation class `metal`) drives the entire hero
story. Hero deck **WF-FAB2-07** (open, ψ 0.97), dawn `surf − air` undershoot:

| ε (metal) | Weathering | Dawn undershoot | Coating dew-point offset at dawn |
|---|---|---|---|
| **0.85** | weathered | **−7.81 °C** | **3 h CLOSED + 3 h MARGINAL**, worst margin −0.02 °C |
| **0.23** | bright | **−4.32 °C** | **0 h CLOSED / 0 MARGINAL**, worst +3.47 °C |

The shaded neighbour **WF-FAB2-06** (ψ 0.45) never closes at either ε. So the
hero contrast is real **only for a weathered deck**, and even then it hangs on
~0.2 °C — it is also fragile to the `Q_lw = 130 W/m²` assumption (upper half of
the arid-climate range). Default is ε 0.85 (weathered), cited in
`docs/CITATIONS.md`. Reproduce: `python -m scripts.make_surface_fixtures --sensitivity`.

---

## 3. Where the derived surface model disagrees with Day 4.5

`apps/api/twin/surface.py` derives α/ε from the real satellite land cover and ψ
from the real streetview sky fraction, replacing the Day-4.5 per-`surface_class`
guess. Hero pair, guessed vs derived (`surf − air`, °C):

| Face | dawn (guessed→derived) | peak15 (guessed→derived) | α | ε | ψ |
|---|---|---|---|---|---|
| WF-FAB2-07 | −7.61 → **−7.81** | 4.65 → **7.00** | 0.30→0.40 | 0.85→0.87 | 0.97 |
| WF-FAB2-06 | −3.53 → **−3.62** | 2.16 → **3.23** | 0.30→0.40 | 0.85→0.87 | 0.45 |

α rises (~0.30→0.40) because the deck is ~20 % concrete, not pure metal, so the
**daytime peak rises noticeably**; ε is ~unchanged so the **dawn is ~same**.

**Ribbon impact:** running the real `evaluate_window` over both bundles, **0 of
37 activity verdicts move** — the scheduled bars sit in daytime. BUT the hero
deck's **dawn coating cells shift MARGINAL → CLOSED** (worst margin +0.18 →
−0.02 °C): the ribbon's dawn band on WF-FAB2-07 goes amber → red at the cell
level even though no activity verdict flips. **T1 should know** before adopting
the derived bundle. It is written to a **new path**
(`sample_thermal_bundle_derived.json`); the Day-4.5 `sample_thermal_bundle.json`
T1's ribbon uses is **untouched**. Recommend the swap once T1 has seen the diff:
`python -m scripts.make_surface_fixtures --diff`.

---

## 4. The circularity note (confirmed)

The twin's sky percentages equal `work_faces.geojson`'s `sky_view_factor`
exactly (45 ↔ 0.45, 97 ↔ 0.97) **only because T2's replay fixture was seeded from
the same generator record.** This is **not independent validation** and is never
presented as any. `tests/test_surface.py` asserts the **derivation path runs**
(sky % → ψ, the downgrades, the energy balance); it contains **no test that
asserts twin/generator agreement**, because that would check nothing. Noted here
and belongs on the assumptions page.

Also handled explicitly (§6 D1): **`shadow` is dropped and fractions
renormalised** — it is an image artefact, not a surface present at all hours;
treating it as reduced insolation would assert it is there every hour, which it
is not. `other` is a recognised material and keeps its mass at a neutral policy
value (α 0.60 / ε 0.90). `bare_soil` added (α 0.75). All cited in CITATIONS.

**Confidence downgrade reaches the UI:** all 40 captures claim
`capture_confidence: high`, but `back` is empty on every one, so ψ is
front-hemisphere-only → derived confidence is **medium**, not inherited-high.

---

## 5. Dependencies and schema changes

- **New dependency: `openai>=1.40`** added to `apps/api/requirements.txt`. It is
  the standard OpenAI-compatible client and speaks to Ollama, DeepInfra, OpenAI
  and Gemini identically — the whole point of §10 (no provider branching). **CI
  installs from this file; expect the new package.**
- **No `packages/schemas/` changes.** New models (`ClimatologyPrior`,
  `SurfaceCoefficients`) live in `apps/api/` (T3-internal), so no T1/T2 contract
  is touched.
- **New migration `003_climatology_prior_provenance.sql`** (T3-owned,
  additive `ADD COLUMN IF NOT EXISTS`): gives `coverage` and `hour_of_day_source`
  a home on `climatology_prior`. `median_peak_c` stays and is NULL everywhere.
- **New files** `apps/api/twin/surface.py` and `apps/api/agent/loop.py` /
  `llm.py`. `twin/surface.py` is T3's transform of T2's capture and does **not**
  collide with T2's `twin/capture.py` or `twin/twin_capture.py`.

---

## 6. What the agent flagged

`apps/api/agent/loop.py`, SCAN → EVALUATE → CONFLICT over the 72 h lookahead
(anchor 2026-08-24 00:00, overlap semantics):

- **Scanned: 62** activities in window · **37** thermal-sensitive with a trade.
- **Flagged: 22 of 37** (`at_risk` / `non_compliant` / `insufficient_window`).
  Verdict mix: 7 compliant, 20 at_risk, 2 non_compliant, 8 no_data.
- **`no_data`: 8**, surfaced separately and **not** counted as flagged — mostly
  continuity runs (72 h cold-weather protection, etc.) that extend past the 72 h
  horizon and fail closed. Honest, expected.
- **Conflicts: 11** across bulk/chem/warehouse faces — shifts where the
  productive hours demanded (post-WBGT haircut, clipped to the shift day) exceed
  the open hours available.

**Is the subset sane?** Yes. 22 of 37 is a middle, not the 3-or-36 the brief
warns about — and in Phoenix August most *daytime* thermal work genuinely is at
risk, so a majority-flagged result is the honest reading, not a bug. The loop is
**pure Python, no LLM** (the Day-6 gate); `model_name` is recorded as `none`.
Emitted to `data/fixtures/agent_run_live.json`; `sample_agent_run.json` untouched.

---

## 7. Things in the brief worth flagging

1. **`median_peak_c`.** The brief's A2 lists it as a derivable output but also
   sanctions `None`. We chose `None` **everywhere**, because the sweep has no
   temperature magnitude at all — deriving a peak means inventing the diurnal
   amplitude, which the brief's own §2.3/A2 honesty rule forbids. This is a
   slightly stronger reading than "return None where you can't"; we think it is
   the correct one and it strengthens the T2 `hourly_tcm_c` ask.
2. **The "62 in window / 37 thermal-sensitive" count** reproduces only with
   **overlap** semantics anchored at the **demo window start 2026-08-24**, not at
   the `data_date` (2026-08-20) and not with start-in-window semantics. The brief
   says "from the demo data date"; the numbers say the demo *window* start. We
   used the latter (it also matches the thermal bundle's horizon).
3. **`demanded_hours` semantics.** The brief ties `productive_hours()` to
   `demanded_hours`. We compute demanded_hours as each competing activity's
   productive crew-hours on the shift (bar clipped to the day, WBGT haircut
   applied) and `compliant_hours` as that shift's open clock-hours. Documented in
   `loop.py` in case the intended split was the reverse.
4. **The LLM is wired to Gemini for dev/smoke only** (per the day's decision), via
   the OpenAI-compatible endpoint — proving the env-var-only design works against
   a real hosted provider (smoke test passes live, tool call and all, with no
   `tool_choice` forcing). **Ollama remains the documented demo path**; Gemini is
   a closed model and using it as the demo would break the §10 open-weight pitch
   (LLM_SETUP §5, "break-glass").
