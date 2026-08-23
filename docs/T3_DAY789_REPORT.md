# T3 — Days 7, 8, 9 report (WORKFACE)

Branch `aach-day7-8` (Days 7–8) → `aach-day9` (Day 9). Written as the work landed.
Test baseline at start of Day 7: **164 passed**. After Day 7: **186 passed, 13 skipped**
(model tests) with `LLM_BASE_URL` unset — the CI condition.

---

## Day 7 — sequencer + policy gate

### What shipped

| Deliverable | File |
|---|---|
| Greedy interval packer | [pack.py](apps/api/sequencer/pack.py) |
| Crew capacity default (on-a-slide) | [crews.yaml](config/crews.yaml) |
| Policy engine (8 rules + approve) | [policy.py](apps/api/agent/policy.py) |
| Policy thresholds (on-a-slide) | [policy.yaml](config/policy.yaml) |
| PROPOSE ladder + LLM strategy chooser | [propose.py](apps/api/agent/propose.py) |
| PROPOSE/GATE/ACT wired into the loop | [loop.py](apps/api/agent/loop.py) |
| Policy suite (incl. deny case) | [test_policy.py](tests/test_policy.py) |
| Sequencer suite (incl. 4 SFRM) | [test_sequencer.py](tests/test_sequencer.py) |
| Replay suite (10 scenarios, skips w/o LLM) | [test_agent_replay.py](tests/test_agent_replay.py) |

### §16.1 — The deny case, verbatim

The A-1237 killer shift (consumes its 0.6 d float **and** pushes A-1238 past MS-340)
is caught by **`no_move_past_milestone`**, `escalated=True`:

> Denied: the move pushes A-1238 past MS-340 Substation energisation (utility coordinated) (28 Aug 12:42) by ~8 h — a contractual milestone the contractor cannot slip. Escalating with the tradeoff.

Milestone protection is ranked above float in the gate, so this is the rule the
killer test asserts. When the same 0.6 d float spend is isolated from the milestone
(the §6.1 hole), **`max_float_days_consumed`** fires on the fractional threshold:

> Denied: this near-critical activity has only 0.6 d of float and the move spends 0.6 d — 100% of it, over the 100% cap. An absolute-days cap would never catch a float this thin. Escalating.

**These read like a human wrote them.** Both are in `tests/test_policy.py` and are green.

### §16.5 — The float-fraction result

Confirmed: **spending 100% of A-1237's 0.6 d float denies**, and the **fractional**
threshold (`max_float_fraction_consumed`, not the 3.0 d absolute cap) is what fires —
0.6 d is far under 3.0 d, so an absolute cap alone would silently pass the killer
test. The rule keeps the id `max_float_days_consumed` (T1 contract) but consults both
thresholds and names which tripped. One subtlety worth flagging: the fractional cap
fires at `>=` (spending the *whole* float trips it), because a strict `>` would let
100% slip through — the exact knife-edge §6.1 warns about.

### §16.2 — Which contended faces produced real conflicts

The CONFLICT stage found **11 conflicts across 7 faces** — and they land exactly where
§2.5 said they would (BULK / CHEM / WHSE), **not** on the FAB2 deck:

| Face | Conflicts |
|---|---|
| WF-BULK-01, WF-BULK-02, WF-CHEM-01, WF-CHEM-02 | 2 each |
| WF-BULK-03, WF-WHSE-03, WF-WHSE-04 | 1 each |

The hand fixture's WF-FAB2-11 conflict does **not** reproduce — FAB2-11 has one
thermal activity in the window, as §2.5 corrected. The contention story is BULK/CHEM/WHSE.

### §16.3 — Did the four SFRM activities pack?

Partly, and the reason is a demo beat. `continuity_40f_24h` needs a 24 h run + 24 h
lead = 48 protected hours inside a 72 h horizon, so **only one window survives the
truncation** on each FAB2 face: 25 Aug 00:00–26 Aug 00:00 (the horizon-truncation
`NO_DATA` path §2.4 predicted — each face has exactly **one** open interval).

Packing the four against that single window:
- **A-1088, A-1098 — placed** (two crews of 6 = 12 heads, the SFRM `heads` in crews.yaml).
- **A-1108, A-1118 — unplaceable, `crew_unavailable`** — the SFRM crew tops out at two
  concurrent crews, so the third and fourth cannot run in the one compliant window.

That is a clean, provable result: *"only two of the four SFRM crews fit the single
compliant 24 h window; the other two need extra crew or a schedule change."* No
exception — the blocker is named.

### §16.7 — Crew-calendar dependency (cleared) + the short-crew Wednesday

The §5 same-day dependency on T2 is **cleared** — `MockSiteSystems.crew_available`
shipped 23 Aug and is wired as an injectable override (`SiteSystemsCrewSource`); the
YAML (`config/crews.yaml`) is the CI default. **The short-crew Wednesday does change a
placement:** free structural heads drop 19 → 2 on Wed 26 Aug in T2's snapshot, so a
4-head activity that the YAML default *places* on Wednesday becomes `crew_unavailable`
under the SiteSystems override. Nameable beat: *"under the real site calendar, the
FAB1 outage support on Wednesday leaves no crew for this face — the agent flags it."*

### §16.6 — What the LLM did (dev model = Gemini)

Model / endpoint: **`gemini-3.7-flash`** via Gemini's OpenAI-compatible endpoint
(`LLM_BASE_URL` from `.env`, dev only). Findings:

- **Tool choice is correct on individual calls.** e.g. the "single healthy window,
  8 d float" scenario → the model calls `shift` with a sensible reason. The prompt
  asks for a tool plainly and never sends `tool_choice` (Ollama portability, §10).
- **The free-tier endpoint quota-throttles a burst.** The 10-scenario replay run,
  fired back-to-back, exhausts the minute/day quota and later calls return no choice.
  This is an **endpoint quota limit, not a tool-choice failure** — `llm_choose_strategy`
  now retries with backoff, which is enough for the *live* loop (its ~12 calls are
  spaced by packer/gate work between them; the first full live run against Gemini
  completed fine: resolved 11, escalated 1). Run the replay suite against **Ollama**
  (local, no quota) or the demo model for a clean pass. This is exactly the §10
  portability caveat, surfaced early.
- **Not yet run against the demo model (Ollama `qwen3:8b`)** — Day-6 item (b) still
  open; needs a machine with Ollama. The deterministic proposer is the demo insurance.

### The live run (deterministic, committed to `agent_run_live.json`)

`python -m scripts.make_agent_run_live` → scanned 62, flagged 22, conflicts 11,
**resolved 11, escalated 1**. Beats:
- **A-1205 (hold point) escalates** — the robust live deny+escalate. The escalation
  note states what was tried and why (§9), not "escalating for review".
- **A-1237 resolves via a shift consuming 0.539 d = ~90% of its 0.6 d float** — a
  knife-edge, approved just under the cap. See the note below.

### §16.4 — Id migration table for T1

The hand fixtures (`sample_agent_run.json`, `sample_gate_verdicts.json`) reference
invented ids from the Day-1 fabrication. The live loop emits real schedule ids. **The
fixtures are untouched** (T1 is mid-build); adopt the live ids deliberately.

| Fixture id (hand) | Live equivalent | Role in the demo |
|---|---|---|
| A-2003 | **A-1237** | near-critical coating, dew-point offset — the split/shift/deny hero |
| A-2006 | **A-1237** (shift) / **A-1205** (hold-point escalate) | the deny+escalate beat |
| A-2009 | **A-1088 / A-1098 / A-1108 / A-1118** | the SFRM tight-packing / crew-blocked beat |

**Rule ids preserved exactly** (the part of the contract that must not move):
`split_within_float_ok` and `max_float_days_consumed` keep those names in
`config/policy.yaml`. New rule ids added (safe to ignore until T1 wires them):
`no_move_past_milestone`, `no_precedence_violation`, `no_out_of_spec_application`,
`no_move_inspection_hold_point`, `wbgt_rest_ratio_escalate`, `no_auto_night_work`,
`fail_closed_on_stale_forecast`. Live output path unchanged: `data/fixtures/agent_run_live.json`.

### Things in the plan that changed once built against the data (§16.7)

1. **A-1237 does not deny in the *live* loop — it resolves with a shift.** Its four
   compliant ~23 h windows (dawn dew-point only closes 04:00–05:00) are wide enough
   that placing the 6.3 h coating consumes ~90% of its float without breaching MS-340.
   The **deny beat is a property of the gate**, proven by `test_policy` with the
   milestone-breaching shift (and it *would* fire live on a tighter window). The split
   beat (b) likewise doesn't trigger live because the whole activity fits one window —
   the split ladder only proposes a split when no single window holds the whole job.
   This is honest: the generated schedule is more forgiving than the hand fixture.
2. **A-1237's "~44 h" (§2.2) is the clock span of its planned bar; its work content is
   6.3 productive hours.** The packer packs against the 6.3.
3. **Night placement is a real tension in Phoenix August.** The coolest compliant hours
   are overnight; the packer is pinned to the `crews.yaml` day shift (06:00–18:00), so
   night-only windows surface as `crew_unavailable` and route to the `night_shift`
   mitigation (which needs the lighting plan) — never a silent night booking.

### Day-7 gate status

- [x] `test_policy.py` green **including the A-1237 deny case**
- [x] `test_sequencer.py` green (topo, ascending float, productive-hours, 4 SFRM, named blockers)
- [x] whole suite green with `LLM_BASE_URL` unset — **186 passed, 13 skipped**

---

## Day 8 — actions + record

_(pending)_

---

## Day 9 — calibration, assumptions, CP-SAT go/no-go

_(pending)_
