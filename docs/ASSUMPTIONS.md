# Assumptions & limitations

*WORKFACE plans and records thermal work-windows. It is advisory and contractual —
it does not certify, and it does not replace the field measurement the referenced
standards require. Publishing this list is deliberate: it is the clearest signal
that this is a product, not a demo. — content for T1 to drop into the app
(also machine-readable at [`assumptions.json`](../data/fixtures/assumptions.json)).*

## What the model does not know

1. **No wind field.** FortyGuard's `env_params` carries no wind speed. Wind drives
   the evaporation rate (ACI 305), the WBGT, the convective term in the surface
   model, and the TMS 602 hot-weather masonry trigger. We take wind as a
   **site-level scalar** from a free feed, so it is **not spatially resolved** —
   two faces on the same site share one wind value. *(This is also the single most
   useful piece of product feedback for the data sponsor.)*
2. **The surface model is a model.** `T_surf = T_air + (α·GHI·ψ − ε·Q_lw·(1−cloud/8))
   / (h_c(V) + h_r)` is a first-order energy balance calibrated from **published**
   absorptivity/emissivity ranges and validated for plausibility — **not against a
   field probe.** It does not replace the surface thermometer an inspector uses.
3. **12-hour forecast horizon.** Handled by the three-tier architecture. Tier 0 is
   a **climatological probability, not a forecast** — the UI must say so wherever a
   Tier-0 number appears.
4. **Registry depth.** **12 trades**, US practice, **hand-curated** (registry
   `2026.08.20-a`). A real deployment needs the submittal-register integration that
   pulls the actual approved product data sheets for *that* project.
5. **Advisory, not certifying.** WORKFACE plans and records; it does not certify and
   does not replace inspection or the engineer of record.
6. **Sparse imagery on greenfield.** `streetview` and `satellite` coverage will be
   thin on a greenfield site. Coverage gaps **degrade with a visible confidence
   downgrade** — the twin steps its confidence down one level when the back
   hemisphere is unsegmented (true for all 40 demo captures).

## What the demo data is

7. **The schedule is synthetic.** The 328-activity P6 schedule is generated. The
   **geography is real** (a Phoenix-area site) and the **standards are real**
   (SSPC-PA 1, ACI 301/305, ACI 305.1, TMS 602, OSHA heat guidance). The float,
   milestone dates and sequencing are illustrative.

## The coefficients the demo stands on (calibration)

Every number below has a value, a source and a **sensitivity** — computed from the
current code, not asserted.

| Coefficient | Value | Source | Sensitivity |
|---|---|---|---|
| **ε — weathered galvanised deck** | **0.85** | ASHRAE Fundamentals ch. 26 (weathered galvanised 0.7–0.9) | **This is the knife-edge.** The hero dawn dew-point closure is the `ε·Q_lw` undershoot. Worst dawn offset margin on WF-FAB2-07: **−0.02 °C at ε=0.85** (closure holds by a hair) → **+3.47 °C at ε=0.23** (bright galvanising — closure vanishes entirely). The whole closure turns on this one number. |
| **Q_lw — clear-sky net longwave loss** | **130 W/m²** | Arid-climate clear-sky net longwave (cited in CITATIONS.md) | Same fragility as ε — the dawn closure scales linearly with it. |
| **Dew-point offset** | **2.8 °C (5 °F)** | SSPC-PA 1 (AMPP) — surface must be ≥ dew point + offset | Below the offset, coating is out-of-spec (RFI-only). |
| **WBGT work/rest bands** | 1.0 / 0.75 / 0.5 / 0.25 work fraction at ≥27.5 / 29.0 / 30.5 °C | **WORKFACE placeholder bands, pending ACGIH licence** (ACGIH table is copyrighted) | The `wbgt_rest_ratio_escalate` gate fires below 0.5 work fraction (>50% rest). |
| **SFRM continuity** | **24 h run + 24 h lead ≥ 4 °C (40 °F)**, substrate AND air | Manufacturer PDS / continuity practice | 48 protected hours inside a 72 h horizon — only one window survives per face; the rest is `NO_DATA` (fail closed). |
| **Policy thresholds** | float cap 3.0 d **and** 100 %-of-float; forecast staleness 2 h; night 19:00–05:00 | `config/policy.yaml` | The fractional float cap is what catches a thin-float near-critical activity an absolute cap never could. |
| **Crew capacity** | per-trade day-shift heads, 06:00–18:00 | `config/crews.yaml` (derived from the schedule's crew sizes) | Night-only compliant windows surface as crew-unavailable and route to a lit night-shift mitigation — never a silent night booking. |

### The condition the closure needs

The dawn dew-point closure requires a **clear, dry, calm** dawn — that is when the
open deck radiates hardest to the sky and the surface undershoots the dew point. A
**humid monsoon dawn does not close the window** (more cloud → less net longwave
loss → the `(1 − cloud/8)` term shrinks the undershoot). The demo stands on a
clear-sky August dawn; say so.
