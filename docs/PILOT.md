# PILOT.md — a 90-day pilot with one GC on one project

*What it would actually take to run WORKFACE on a real job, written before anyone
asks. The hackathon build is the evidence that the physics and the agent work. This
document is the separate question: what does the first customer engagement look
like, what do we need from them, and how do we both know whether it worked.*

**Everything below marked *(hypothesis)* is untested and stated as a hypothesis on
purpose.** The externally sourced numbers are marked with their source. Nothing in
this document is a commitment we can keep today.

---

## 1. The shape of the pilot

**One general contractor. One project. One superintendent. 90 days.**

Not one GC across three projects, and not three GCs. The failure mode for a pilot
like this is being interesting to nobody in particular; a single superintendent who
opens the Morning Brief every day is worth more evidence than three who open it
twice.

| | Target |
|---|---|
| Project | One active industrial or commercial build, US, in a hot or two-season climate |
| Package value | $50M–$250M — large enough that rework is a line item someone owns |
| Work faces instrumented | 20–40 |
| Trades in scope | The 12 in the registry; realistically 4–6 are load-bearing on any one project |
| Users | 1 superintendent, 1 project-controls scheduler, 1 QA/QC lead. Three named people. |
| Duration | 90 days, structured as 2 weeks setup · 10 weeks running · 2 weeks readout |

**Why 90 days and not 30:** the record half of the product (Tier 2) only produces
evidence once work packages have actually closed out. Thirty days shows the window
maths works. Ninety days produces a stack of thermal certificates at handover, which
is the artifact that decides whether there is a business here.

---

## 2. Integration surface

The design rule is that **WORKFACE reads, and never writes back.** No P6 write-back,
no touching the schedule of record. Everything WORKFACE proposes lands as a
recommendation in front of a human who makes the change in their own system. This is
not a hedge — it is what makes the security review survivable and the pilot
approvable by someone who is not in the room.

### 2.1 Schedule — P6 export cadence

| | |
|---|---|
| **Format** | Primavera P6 **XER export** (preferred) or CSV. Both supported; CSV is the guaranteed fallback. |
| **Cadence** | **Weekly**, following the schedule update meeting — that is the natural rhythm on a real job, and it means WORKFACE is never more than one update stale. |
| **Transport** | Drop to an SFTP folder or a monitored mailbox. Not an API integration in the pilot: the P6 instance is usually on a corporate network and getting API access takes longer than the pilot does. |
| **What we read** | Activity id, name, trade/discipline code, planned start/finish, remaining duration, total float, predecessor links, milestone dates, hold points, WBS. |
| **What we ignore** | Cost loading, resource assignments beyond crew size, baselines, anything financial. |

The intra-week loop runs on the last export. The 12-hour commit loop (Tier 1) runs
daily off live weather against that schedule, which is exactly the cadence mismatch
the three-tier architecture exists to handle.

### 2.2 Work-face geometry

The one genuinely manual step, and worth naming honestly: **someone has to draw the
work faces.** A "work face" is a physical area a crew occupies — a deck, a bay, a
pour, an elevation. It does not exist in P6, which knows activities and WBS but not
where on the site they happen.

Pilot approach: a half-day session with the superintendent over the site plan,
drawing 20–40 polygons and mapping activity codes onto them. This is the highest-risk
setup task and the strongest candidate for automation later (BIM/IFC zone extraction,
explicitly out of scope for the pilot).

### 2.3 Site systems

Read-only, best-effort, and the pilot works without all of them:

- Crew calendar (who is on site, which shift) — drives the "can this actually be
  resequenced" answer. Manual weekly CSV is acceptable.
- Ready-mix supplier delivery windows — only matters if concrete is in scope.
- Lighting plan and heated-enclosure availability — drives which mitigations are real
  rather than theoretical.

### 2.4 What we do not integrate with

P6 write-back · BIM/IFC ingestion · procurement and ready-mix ordering ·
subcontractor accounts and permissions · IoT sensor networks · the GC's ERP. If it
comes up, it is the deployment conversation, not the pilot.

---

## 3. Data requirements

### 3.1 What the GC provides

1. The weekly schedule export (§2.1).
2. Work-face polygons, once, in the setup session (§2.2).
3. **The approved submittal register for the trades in scope** — the actual product
   data sheets for the coatings, sealants, fireproofing and adhesives approved for
   *that* project. This is the single most important input and the one most likely
   to be slow. The hackathon registry is 12 hand-curated trades; a real project's
   window is whatever *its* approved PDS says, and if we evaluate against a generic
   clause we are wrong in a way that matters.
4. Three named users and thirty minutes a week of the superintendent's time.
5. **Field surface-temperature readings** for validation (§4.1) — the crew is already
   taking these for coating work; we need them written down and timestamped rather
   than newly collected.

### 3.2 What we source

FortyGuard heatmap, `env_params`, `satellite` and `streetview` for the site; a
site-level wind scalar from a free feed; the published standards (SSPC-PA 1, ACI
301/305/305.1, TMS 602, OSHA heat guidance) already cited in `docs/CITATIONS.md`.

### 3.3 Where the data will be thin, and what happens

Stated up front because these are the conditions under which the pilot returns a
weaker answer, not a wrong one:

| Condition | Effect | Behaviour |
|---|---|---|
| Greenfield site, sparse `streetview`/`satellite` coverage | The thermal twin has less to work with | Confidence downgrades visibly; the window is still computed, and the UI says why it is less certain |
| Forecast series stale or missing | No trustworthy Tier-1 answer | **Fails closed** — escalates, never guesses |
| Wind matters (evaporation rate, WBGT, masonry trigger) | Wind is a site-level scalar, not spatially resolved | Stated as a limitation on every affected verdict. A ~$300 site anemometer is a cheap pilot add-on and worth proposing. |
| A trade's approved PDS is not in the register | We cannot evaluate that trade honestly | It is out of scope for the pilot rather than evaluated against a generic clause |

All of these, and the rest, are in `docs/ASSUMPTIONS.md`, which ships inside the app.

---

## 4. Success metrics

Agreed **in writing before day one**, because a pilot with metrics chosen at the
readout always succeeds and never sells anything.

### 4.1 Does the physics hold? — the gate metric

This is the one that decides everything else, and it is the pilot's job to answer the
limitation the product cannot answer for itself: *the surface model is a model,
calibrated from published values and validated for plausibility, not against a field
probe.*

- **≥ 200 paired readings**: crew surface-temperature measurement vs. WORKFACE's
  predicted `T_surf` at the same work face and hour.
- **Primary metric — window-boundary error, in minutes.** Not degrees. The product's
  claim is *"the window opens at 06:50 and closes at 09:20"*, so the error that
  matters is how far off those two times are. *(hypothesis: median absolute boundary
  error ≤ 30 minutes is useful to a superintendent; ≥ 90 minutes is not a product.)*
- **Secondary — MAE on `T_surf`**, reported by surface class, because we already know
  bare weathered metal is where the model is most sensitive and most load-bearing.
- **Reported honestly by class.** If the model works on concrete and fails on
  galvanised deck, that is the finding, and it is a useful one.

### 4.2 Does anyone act on it?

- **Morning Brief open rate** — daily, by the superintendent. Below ~50% and nothing
  else matters.
- **Resequence accept rate** — of the agent's proposals that pass the policy gate,
  what fraction does the superintendent actually adopt? *(hypothesis: 30–50%. A
  number near 100% would mean the proposals are trivial; near 0% means they are
  ignorable.)*
- **Escalation precision** — of the activities the agent escalated rather than
  resolved, what fraction did the superintendent agree needed a human call? This is
  the metric that tests whether the policy gate is calibrated or just noisy.

### 4.3 Did it catch anything?

The number a GC actually cares about:

- **Documented near-misses** — thermally non-compliant work identified *before*
  placement, with the clause cited, logged with the superintendent's acknowledgement.
  One prevented coating recoat on a large deck plausibly pays for the pilot several
  times over. We count events, not dollars; the dollar attribution is a fight we do
  not need to pick in 90 days.
- **Record completeness** — the share of thermally-sensitive work packages closing out
  with a complete thermal certificate. Target 100% for packages inside the pilot
  window, because unlike the others this one is entirely within our control, and a
  gap in it is a product bug.

### 4.4 What we deliberately do not claim in 90 days

Rework reduction attributable to WORKFACE. Rework surfaces over months to years and
is multi-causal; any number we produced in 90 days would be marketing, and a project
controls director will know it. The market framing — direct field rework at ~5% of
construction value across 144 industrial projects, with a 90th percentile of 12.4%
(CII benchmark, cited in `WORKFACE_PROJECT_PLAN.md` §10) — is context for why this is
worth trying, not a result we will claim to have produced.

---

## 5. Pricing hypothesis

**All of this is a hypothesis.** Nobody has been quoted, nothing has been sold, and
the purpose of the pilot is as much to test this as to test the model.

### 5.1 The shape: per project, per month

Priced **per active project**, not per seat and not per activity.

The reason is a real property of the system rather than a preference: **API cost
scales with AOI polygons and granularity tiers, not with activity count.** A
1,100-acre campus with 40 work faces collapses to 3–5 AOI polygons; historical
climatology is cached forever; one call covers a whole day for a whole AOI. Adding
the 300th activity to a project we are already covering costs essentially nothing.
So per-seat or per-activity pricing would charge for something we do not consume, and
would punish exactly the behaviour we want (more of the schedule in scope).

### 5.2 The anchor

The comparison is not other software; it is **one avoided recoat**. Re-blasting and
recoating a large structural steel deck after a warranty denial is a five-figure
event before the schedule impact. *(hypothesis)* If the annual price of WORKFACE on a
project is below the cost of a single such event, the arithmetic does not need weather
to be a large share of rework for the purchase to make sense — which is the whole
argument in §10 of the project plan.

### 5.3 The pilot itself

*(hypothesis)* **Paid, at a materially reduced rate, not free.** A free pilot has no
internal owner and dies quietly when the superintendent gets busy. A small invoice
creates someone whose job it is to make it work. The price is not the point; the
existence of the invoice is.

What we ask for instead of full price: the field readings in §4.1, a reference
conversation if the metrics land, and permission to cite the project type (not the
name) in future work.

### 5.4 Cost structure to understand before quoting

- **FortyGuard credits are the COGS**, and they are controllable by design: AOI
  clustering, 100 m for planning and 60 m only for flagged faces, historical cached
  forever, batching by day. A hard daily call cap sits in config, and the credit meter
  reads after every batch.
- **Setup labour is the real cost of the first customer** — the work-face drawing
  session and the submittal-register load. It does not repeat monthly, but it is why
  the first ten customers cost more than the next hundred, and any pricing model built
  on the marginal case will be wrong at the start.

---

## 6. Week by week

| Weeks | Work |
|---|---|
| 1–2 | Setup. Work-face polygons with the superintendent. First XER export ingested. Submittal register loaded for the trades in scope. Thermal twin built and cached. Baseline: which activities in the current look-ahead are already outside their window. |
| 3–4 | Read-only shadow mode. The agent runs and records; nothing is shown to the crew. Confirms the pipeline holds against a real schedule before anyone's morning depends on it. |
| 5–10 | Live. Morning Brief to the superintendent daily. Agent proposals through the policy gate. Field readings collected against the model. Weekly 30-minute review. |
| 11–12 | Readout. §4 metrics against the targets agreed in week 0. Thermal certificates for every work package closed out during the pilot. An honest write-up of what failed. |

---

## 7. How this pilot fails

Written down now, so that if it happens we recognise it rather than explain it away:

1. **The model misses the window boundaries by more than an hour on the surfaces that
   matter.** The most likely single failure, and the reason §4.1 is the gate metric.
   Recoverable — the twin is calibratable against field data — but it must be found
   and said, not smoothed.
2. **The submittal register never arrives.** Then we evaluate against generic clauses
   and the whole product is advisory in the weakest sense. Mitigation: make it a
   week-1 deliverable with a named owner, and cut trades from scope rather than
   substitute a generic PDS.
3. **The superintendent stops opening it.** The most quietly fatal one. A daily brief
   that is right but not read is not a product. Mitigation: the weekly 30-minute
   review is not a status meeting, it is the instrument for detecting this in week 5
   instead of week 11.
4. **Nothing happens.** A mild season, a schedule with slack, no near-misses. Not a
   failure of the product but a failure of site selection — which is why the pilot
   site should be a hot-climate summer or a genuinely two-season job, and why the
   `direction: below` cold-weather half is in scope from day one.

---

## 8. What is explicitly not in the pilot

Real P6 write-back · multi-project portfolios · BIM/IFC ingestion · crew and equipment
cost modelling · procurement and ready-mix ordering integration · subcontractor
accounts and permissions · anything outside the United States · IoT sensors on site ·
more than 12 trades · more than one project.

WORKFACE is **advisory**. It plans and it records. It does not certify, and it does
not replace inspection, the engineer of record, or the surface thermometer the
standards require an inspector to use.
