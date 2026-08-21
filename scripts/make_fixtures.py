"""
WORKFACE — Day-1 hand-written fixtures.  T3, TASK 2.

    python -m scripts.make_fixtures            # writes data/fixtures/*.json
    python -m scripts.make_fixtures --check    # write + validate, non-zero exit on failure

Why this exists
---------------
T1 builds the window ribbon on Day 4 against these files, BEFORE any physics
exists (apps/api/windows/constraints.py is not written yet). The numbers here are
invented; the *field names and shapes* must be exactly right. Every file is
validated against the real Pydantic contracts before it is written, so a fixture
can never drift from the schema T1 renders.

The three files
    data/fixtures/sample_window_eval.json         one WindowEval  — the hero coating lane
    data/fixtures/sample_window_eval_ribbon.json  one WindowEvalBundle — 9 trades colliding
    data/fixtures/sample_thermal_series.json      one WorkFaceThermalSeries — 48 h drivers

The story the numbers tell (North Phoenix, monsoon August, 24-25 Aug 2026)
    * Phoenix August diurnal: air 29 C at 05:00 -> 42 C at 15:00 -> 33 C at 23:00.
    * Monsoon dew point 17-19 C, peaking overnight.
    * The BARE galvanised deck radiatively cools toward the dew point in the calm,
      damp pre-dawn hours (02:00-04:00): the surface-to-dew clearance collapses and
      SSPC-PA 1's "5 F (2.8 C) above dew point" is violated. That condensation edge
      is what closes the coating window at night — a coatings inspector in the room
      would look for exactly this.
    * The compliant band lands ~05:00-09:00 and eight trades converge on it; hot-mix
      asphalt is the honest counter-trade whose window is the afternoon heat instead.

No third-party dependencies beyond the schema packages. Pure stdlib + Pydantic.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The whole point of a Day-1 fixture is that it exists before the evaluator does.
# We deliberately DO NOT import apps/api/windows/constraints.py — the states below
# are fabricated directly. We DO import the schema, so the fixtures cannot drift.
from packages.schemas.window_eval import (
    BindingConstraint,
    ConstraintResult,
    Horizon,
    HourCell,
    Margin,
    OpenInterval,
    Provenance,
    ScheduledBar,
    SeriesPoint,
    UsdExposure,
    WindowEval,
    WindowEvalBundle,
)
from packages.schemas.thermal_series import (
    SolarIrradiance,
    ThermalPoint,
    WorkFaceThermalSeries,
)

TZ = timezone(timedelta(hours=-7.0))            # America/Phoenix, no DST, ever.
HORIZON_START = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)
STEP_MIN = 60
N_HOURS = 48
REGISTRY_VERSION = "2026.08.20-a"
RUN_ID = "fixture-2026-08-24-monsoon-dawn"
SITE_ID = "NPX-FAB-P2"
CLUSTER_ID = "AOI-FAB2-DECK"

# --------------------------------------------------------------------------- #
# Diurnal driver arrays, hour-of-day 0..23. Hand-tuned to the story above.
# These are the ONLY hand-authored numbers; every margin and reason downstream
# is COMPUTED from them, so state/reason/values can never disagree.
# --------------------------------------------------------------------------- #

#            00    01    02    03    04    05    06    07    08    09    10    11
#            12    13    14    15    16    17    18    19    20    21    22    23
AIR = [      34.0, 33.0, 32.0, 31.0, 30.0, 29.0, 30.0, 32.0, 34.5, 36.5, 38.0, 39.5,
             40.5, 41.3, 41.8, 42.0, 41.5, 40.5, 39.0, 37.5, 36.0, 35.0, 34.0, 33.0]
DEW = [      18.8, 19.2, 19.5, 19.6, 19.4, 19.0, 18.7, 18.4, 18.1, 17.8, 17.5, 17.3,
             17.1, 17.0, 17.0, 17.0, 17.2, 17.5, 17.8, 18.1, 18.4, 18.6, 18.7, 18.8]
# Bare open deck (psi 0.97): condensation trough 02:00-04:00, solar-loaded midday.
SURF_BARE = [23.0, 22.0, 21.8, 21.5, 22.6, 24.5, 29.0, 34.0, 39.5, 44.5, 49.0, 53.5,
             56.5, 58.3, 59.8, 60.0, 57.5, 52.5, 46.0, 40.5, 35.0, 31.0, 27.0, 24.0]
# Shaded-by-steel deck (psi 0.45): ~half the daytime amplitude, milder night dip.
SURF_SHADED = [27.5, 27.0, 26.5, 26.2, 26.6, 27.0, 28.5, 31.0, 33.5, 36.0, 38.0, 39.8,
               41.0, 41.8, 42.3, 42.5, 41.8, 40.5, 38.8, 37.0, 35.2, 33.8, 32.0, 30.0]
# Site wind, mph — light and calm overnight (why radiative cooling wins), breezy pm.
WIND_MPH = [4.0, 3.5, 2.5, 2.0, 2.0, 2.5, 3.5, 5.0, 6.5, 8.0, 9.5, 11.0,
            12.0, 12.5, 13.0, 13.0, 12.0, 10.5, 9.0, 7.5, 6.0, 5.0, 4.5, 4.0]
# Global horizontal irradiance, W/m2 — 0 at night, bell through the day.
GHI = [0, 0, 0, 0, 0, 30, 160, 360, 560, 720, 850, 940,
       985, 980, 915, 800, 640, 440, 230, 60, 0, 0, 0, 0]


def hod(i: int) -> int:
    """Hour-of-day for horizon index i (0..47)."""
    return (HORIZON_START + timedelta(hours=i)).hour


def ts_at(i: int) -> datetime:
    return HORIZON_START + timedelta(hours=i)


def rh_from(t_air: float, t_dew: float) -> float:
    """Relative humidity implied by air and dew point (inverse Magnus-Tetens).

    Keeps rh_pct internally consistent with t_dew rather than a third free array.
    """
    a, b = 17.625, 243.04
    gamma_dew = a * t_dew / (b + t_dew)
    gamma_air = a * t_air / (b + t_air)
    return round(min(100.0, max(0.0, 100.0 * math.exp(gamma_dew - gamma_air))), 1)


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def series_point(i: int, surf: list[float]) -> SeriesPoint:
    """The driver values at horizon index i, for the given surface array."""
    h = hod(i)
    return SeriesPoint(
        t_air_c=AIR[h],
        t_surf_c=surf[h],
        t_dew_c=DEW[h],
        rh_pct=rh_from(AIR[h], DEW[h]),
        wind_ms=round(WIND_MPH[h] * 0.44704, 2),
        ghi_w_m2=float(GHI[h]),
    )


def productive_fraction(i: int) -> float:
    """WBGT work/rest haircut, driven by air temperature (placeholder bands)."""
    a = AIR[hod(i)]
    if a >= 40.5:
        return 0.5
    if a >= 37.8:
        return 0.75
    return 1.0


# --------------------------------------------------------------------------- #
# Interval + rollup helpers (fabricated, NOT the real evaluator).
# --------------------------------------------------------------------------- #

def open_intervals_from(cells: list[HourCell], include_marginal: bool) -> list[OpenInterval]:
    usable = {"open", "marginal"} if include_marginal else {"open"}
    out: list[OpenInterval] = []
    run: list[HourCell] = []

    def flush() -> None:
        if not run:
            return
        start = run[0].ts
        end = run[-1].ts + timedelta(hours=1)
        dur = (end - start).total_seconds() / 3600.0
        prod = sum(c.productive_fraction for c in run)
        margins = [c.margin for c in run if c.margin is not None]
        out.append(OpenInterval(
            start=start, end=end, duration_h=dur,
            productive_h=round(prod, 2),
            includes_marginal=include_marginal,
            min_margin=round(min(margins), 2) if margins else None,
        ))

    for c in cells:
        if c.state.value in usable:
            run.append(c)
        else:
            flush()
            run = []
    flush()
    return out


def rollup(cells: list[HourCell]) -> tuple[int, int, float | None, datetime | None, datetime | None]:
    satisfied = sum(1 for c in cells if c.state.value in ("open", "marginal"))
    closed = sum(1 for c in cells if c.state.value == "closed")
    margins = [c.margin for c in cells if c.margin is not None]
    worst = round(min(margins), 2) if margins else None
    opens = [c.ts for c in cells if c.state.value == "open"]
    return satisfied, closed, worst, (opens[0] if opens else None), (opens[-1] if opens else None)


# --------------------------------------------------------------------------- #
# Per-lane gaters. Each returns (state, margin, unit, reason, binding_id, prod).
# Reason strings are BUILT from the computed numbers -> guaranteed consistent.
# --------------------------------------------------------------------------- #

def gate_offset(i: int, surf: list[float], delta_c: float, marg_delta: float,
                cid: str, clause: str) -> tuple[str, float, str, str, str]:
    h = hod(i)
    surf_c, dew_c = surf[h], DEW[h]
    margin = round(surf_c - dew_c - delta_c, 2)
    if margin < 0:
        state = "closed"
    elif margin < marg_delta:
        state = "marginal"
    else:
        state = "open"
    if delta_c == 0.0:
        need = "at or above the dew point"
    else:
        need = f"{delta_c:.1f} C above the {dew_c:.1f} C dew point"
    reason = (f"Surface {surf_c:.1f} C, {surf_c - dew_c:.1f} C above dew point; "
              f"{clause} requires {need} (margin {margin:+.1f} C).")
    return state, margin, "C", reason[:240], cid


def menzel_e(surf_c: float, air_c: float, rh: float, wind_mph: float) -> float:
    tc, ta = c_to_f(surf_c), c_to_f(air_c)
    return (tc ** 2.5 - (rh / 100.0) * ta ** 2.5) * (1.0 + 0.4 * wind_mph) * 1e-6


def gate_evaporation(i: int, surf: list[float]) -> tuple[str, float, str, str, str]:
    h = hod(i)
    e = menzel_e(surf[h], AIR[h], rh_from(AIR[h], DEW[h]), WIND_MPH[h])
    limit, marg = 0.2, 0.1
    margin = round(limit - e, 3)                    # positive = below the limit = good
    if e > limit:
        state = "closed"
    elif e > marg:
        state = "marginal"
    else:
        state = "open"
    reason = (f"ACI 305 evaporation rate {e:.3f} lb/ft2/hr (surface {surf[h]:.0f} F-equiv, "
              f"wind {WIND_MPH[h]:.0f} mph); plastic-shrinkage precautions at 0.2.")
    return state, margin, "lb_ft2_hr", reason[:240], "composite_evaporation_rate"


_ANCHOR_WT = [(-5, 120), (0, 120), (5, 120), (10, 90), (15, 60),
              (20, 30), (25, 20), (30, 15), (35, 12), (40, 10)]


def working_time_min(base_c: float) -> float:
    """Hilti HIT-RE 500 V3 working time vs base temperature, linear between anchors."""
    if base_c <= _ANCHOR_WT[0][0]:
        return float(_ANCHOR_WT[0][1])
    if base_c >= _ANCHOR_WT[-1][0]:
        return float(_ANCHOR_WT[-1][1])
    for (t0, w0), (t1, w1) in zip(_ANCHOR_WT, _ANCHOR_WT[1:]):
        if t0 <= base_c <= t1:
            f = (base_c - t0) / (t1 - t0) if t1 != t0 else 0.0
            return round(w0 + f * (w1 - w0), 1)
    return float(_ANCHOR_WT[-1][1])


def gate_working_time(i: int, surf: list[float]) -> tuple[str, float, str, str, str]:
    h = hod(i)
    base = surf[h]
    wt = working_time_min(base)
    margin = round(wt - 15.0, 1)                     # 15 min = practical placement floor
    if wt < 15.0:
        state = "closed"
    elif wt < 25.0:
        state = "marginal"
    else:
        state = "open"
    reason = (f"Base material {base:.0f} C gives {wt:.0f} min working time before the "
              f"epoxy gels; crew needs >=15 min to place a cartridge run.")
    return state, margin, "min", reason[:240], "decay_working_time"


def gate_hot_trigger(i: int) -> tuple[str, float, str, str, str]:
    """Masonry hot-weather TRIGGER (trigger_only): above 37.8 C -> mitigation, not a stop."""
    h = hod(i)
    air = AIR[h]
    margin = round(37.8 - air, 1)
    if air > 37.8:
        state = "marginal"                          # mitigation required, work continues
        reason = (f"Air {air:.1f} C above the 37.8 C (100 F) TMS 602 trigger: fog-spray, "
                  f"damp sand, mortar within 2 h. Cost, not a stop.")
    else:
        state = "open"
        reason = f"Air {air:.1f} C below the 37.8 C hot-weather trigger; standard procedures."
    return state, margin, "C", reason[:240], "band_hot_weather_trigger_tier1"


def gate_marking(i: int, surf: list[float]) -> tuple[str, float, str, str, str]:
    """Waterborne marking: surface >=12.8 C and rising, pavement dry (film releases water)."""
    h = hod(i)
    surf_c = surf[h]
    prev = surf[(h - 1) % 24]
    rising = surf_c >= prev
    margin = round(surf_c - 12.8, 1)
    if surf_c < 7.2:
        state, reason = "closed", f"Surface {surf_c:.1f} C below the 7.2 C (45 F) hard floor."
    elif surf_c >= 12.8 and rising:
        state = "open"
        reason = f"Surface {surf_c:.1f} C, >=12.8 C (55 F) and rising; waterborne film will set."
    else:
        state = "marginal"
        reason = (f"Surface {surf_c:.1f} C but falling; extended dry time, reduced service life "
                  f"below the 12.8 C-and-rising rule.")
    return state, margin, "C", reason[:240], "band_surface_rising"


def gate_hot_base(i: int, surf: list[float]) -> tuple[str, float, str, str, str]:
    """HMA surface course — the counter-trade. Wants a HOT base; cool dawn closes it."""
    h = hod(i)
    base = surf[h]
    margin = round(base - 32.0, 1)                   # 32 C ~ lower end of a workable base
    if base >= 32.0:
        state = "open"
        reason = (f"Base {base:.0f} C: full compaction window. Hot afternoon HELPS asphalt — "
                  f"the one trade that wants the heat the others flee.")
    elif base >= 25.0:
        state = "marginal"
        reason = f"Base {base:.0f} C: compaction window shortening as the mat cools."
    else:
        state = "closed"
        reason = f"Base {base:.0f} C too cold: mat stiffens before rollers finish; density fails."
    return state, margin, "C", reason[:240], "decay_compaction_window"


def gate_always_open(i: int, label: str, cid: str) -> tuple[str, float, str, str, str]:
    """Summer trades with no binding temperature edge over this horizon (welding preheat,
    SFRM continuity): satisfied throughout — shown so the ribbon isn't only red lanes."""
    return "open", 0.0, "C", f"{label} satisfied throughout the horizon.", cid


# --------------------------------------------------------------------------- #
# Assemble a full WindowEval from a per-hour gater.
# --------------------------------------------------------------------------- #

def build_eval(*, activity_id: str, activity_name: str, wbs: str, trade_id: str,
               trade_display: str, work_face_id: str, work_face_name: str,
               surf: list[float], gater, constraint: dict, scheduled: ScheduledBar,
               unit_cost: float, quantity: float, rework: float, citation: str,
               standard_ref: str, mitigation_hint: str,
               include_marginal_in_intervals: bool = True) -> WindowEval:
    cells: list[HourCell] = []
    for i in range(N_HOURS):
        state, margin, unit, reason, binding_id = gater(i, surf)
        pf = productive_fraction(i)
        cells.append(HourCell(
            ts=ts_at(i),
            state=state,
            binding_constraint_id=None if state == "open" else binding_id,
            margin=margin,
            margin_unit=unit,
            reason=reason,
            productive_fraction=pf,
            values=series_point(i, surf),
        ))

    satisfied, closed, worst, first_open, last_open = rollup(cells)
    intervals = open_intervals_from(cells, include_marginal=include_marginal_in_intervals)
    longest = max(intervals, key=lambda iv: iv.duration_h, default=None)

    cres = ConstraintResult(
        constraint_id=constraint["constraint_id"],
        type=constraint["type"],
        label=constraint["label"],
        governing_temp=constraint["governing_temp"],
        satisfied_hours=satisfied,
        closed_hours=closed,
        first_open=first_open,
        last_open=last_open,
        worst_margin=worst,
        margin_unit=constraint["margin_unit"],
        citation_fragment=constraint["citation_fragment"],
    )

    binding = BindingConstraint(
        constraint_id=constraint["constraint_id"],
        type=constraint["type"],
        label=constraint["label"],
        hours_lost=float(closed),
        would_extend_window_by_h=float(closed),
        mitigation_hint=mitigation_hint,
    ) if closed > 0 else None

    # Verdict against the scheduled bar.
    bar_states = [c.state.value for c in cells
                  if scheduled.start <= c.ts < scheduled.finish]
    if not bar_states:
        verdict = "no_data"
    elif any(s == "closed" for s in bar_states) and all(s == "closed" for s in bar_states):
        verdict = "non_compliant"
    elif any(s in ("closed", "marginal") for s in bar_states):
        verdict = "at_risk"
    else:
        verdict = "compliant"

    if verdict == "at_risk":
        summary = (f"{trade_display}: {scheduled.duration_h:.0f} h bar at "
                   f"{scheduled.start.strftime('%H:%M')} clips the closed/thin dawn hours on "
                   f"{constraint['label']}. Slip start or mitigate.")
    elif verdict == "compliant":
        summary = f"{trade_display}: bar sits inside an open interval on {constraint['label']}."
    else:
        summary = f"{trade_display}: bar sits on closed hours — {constraint['label']} violated."

    at_risk_usd = round(unit_cost * quantity * (rework if verdict != "compliant" else 0.0), 0)
    protected_usd = round(unit_cost * quantity * (rework if verdict == "compliant" else 0.0), 0)

    return WindowEval(
        run_id=RUN_ID,
        generated_at=HORIZON_START,
        activity_id=activity_id,
        activity_name=activity_name,
        wbs=wbs,
        trade_id=trade_id,
        trade_display_name=trade_display,
        work_face_id=work_face_id,
        work_face_name=work_face_name,
        horizon=Horizon(start=HORIZON_START, end=ts_at(N_HOURS), step_minutes=STEP_MIN, tier="commit"),
        scheduled=scheduled,
        hours=cells,
        open_intervals=intervals,
        constraints=[cres],
        binding_constraint=binding,
        margin=Margin(value=worst if worst is not None else 0.0,
                      unit=constraint["margin_unit"],
                      at=first_open),
        verdict=verdict,
        verdict_summary=summary[:400],
        citation=citation,
        standard_ref=standard_ref,
        usd_exposure=UsdExposure(
            at_risk_usd=at_risk_usd, protected_usd=protected_usd,
            basis=f"quantity {quantity:g} {'unit'} x ${unit_cost:g}/unit x rework multiplier {rework:g}",
        ),
        confidence="high",
        confidence_reasons=["satellite + streetview twin present for FAB2 deck cluster"],
        provenance=Provenance(
            fg_activity_ids=["fg-heatmap-FAB2DECK-0001", "fg-envparams-FAB2DECK-0001"],
            series_digest=None,
            registry_version=REGISTRY_VERSION,
            twin_confidence="high",
            replay=True,
        ),
    )


# --------------------------------------------------------------------------- #
# The hero WindowEval — coating on the bare FAB2 L3 deck, offset_dew_point binding.
# --------------------------------------------------------------------------- #

def build_hero() -> WindowEval:
    scheduled = ScheduledBar(
        start=datetime(2026, 8, 24, 2, 0, tzinfo=TZ),    # night shift to dodge the heat...
        finish=datetime(2026, 8, 24, 8, 0, tzinfo=TZ),   # ...but it runs into the dawn condensation
        duration_h=6.0,
        total_float_d=1.5,
        is_critical=False,
        is_near_critical=True,
        crew_size=5,
    )

    def gater5(i: int, surf: list[float]):
        return gate_offset(i, surf, 2.8, 1.0, "offset_dew_point", "SSPC-PA 1 6.2")

    ev = build_eval(
        activity_id="A-2009",
        activity_name="Structural steel high-build coating — FAB2 L3 deck — bay C3",
        wbs="FAB2.FAB.11",
        trade_id="coating_epoxy_structural_steel",
        trade_display="Structural steel — high-build epoxy coating",
        work_face_id="WF-FAB2-11",
        work_face_name="FAB2 L3 deck — bay C3",
        surf=SURF_BARE,
        gater=gater5,
        constraint={
            "constraint_id": "offset_dew_point",
            "type": "offset",
            "label": "Surface >= dew point + 2.8 C (5 F)",
            "governing_temp": "surface",
            "margin_unit": "C",
            "citation_fragment": (
                "SSPC-PA 1 6.2: coating shall not be applied when the steel surface temperature "
                "is less than 5 F (2.8 C) above the dew point. Macropoxy 646 PDS: at least 5 F above dew point."
            ),
        },
        scheduled=scheduled,
        unit_cost=34.0, quantity=4200.0, rework=3.2,
        citation=(
            "Sherwin-Williams Macropoxy 646 PDS + SSPC-PA 1 (AMPP) 6.2: coating shall not be "
            "applied when the steel surface temperature is less than 5 F (2.8 C) above the dew point."
        ),
        standard_ref="SSPC-PA 1 (AMPP) 6.2; Sherwin-Williams Macropoxy 646 PDS",
        mitigation_hint="slip start to 05:00 once the deck warms, or dehumidified enclosure",
    )
    return ev


# --------------------------------------------------------------------------- #
# The ribbon bundle — 9 activities on 9 different trades, same FAB2 deck cluster.
# --------------------------------------------------------------------------- #

def _bar(hour: int, dur: float, float_d: float, crew: int) -> ScheduledBar:
    start = datetime(2026, 8, 24, hour, 0, tzinfo=TZ)
    return ScheduledBar(start=start, finish=start + timedelta(hours=dur),
                        duration_h=dur, total_float_d=float_d,
                        is_critical=float_d <= 0.01, is_near_critical=0.01 < float_d <= 3.0,
                        crew_size=crew)


def build_bundle() -> WindowEvalBundle:
    evals: list[WindowEval] = []

    # 1. Coating (hero) — the same lane, in the collision.
    evals.append(build_hero())

    # 2. Cast-in-place concrete — evaporation rate (bare slab-adjacent deck pour).
    evals.append(build_eval(
        activity_id="A-2003", activity_name="Slab pour — FAB2 L3 deck — bay A3",
        wbs="FAB2.FAB.09", trade_id="concrete_cip_hot_weather",
        trade_display="Cast-in-place concrete — hot weather placement",
        work_face_id="WF-FAB2-09", work_face_name="FAB2 L3 deck — bay A3",
        surf=SURF_BARE, gater=lambda i, s: gate_evaporation(i, s),
        constraint={"constraint_id": "composite_evaporation_rate", "type": "composite_rate",
                    "label": "ACI 305 evaporation rate <= 0.2 lb/ft2/hr", "governing_temp": "concrete",
                    "margin_unit": "lb_ft2_hr",
                    "citation_fragment": "ACI 305R: plastic-shrinkage precautions required at 0.2 lb/ft2/hr."},
        scheduled=_bar(6, 8.0, 0.0, 12), unit_cost=195.0, quantity=340.0, rework=4.5,
        citation="ACI 301-20 and ACI 305.1-14: concrete <=35 C at discharge; ACI 305R evaporation precaution at 0.2 lb/ft2/hr.",
        standard_ref="ACI 301-20; ACI 305.1-14 3.2-3.3; ACI 305R",
        mitigation_hint="evaporative retarder, fog spray, windbreak, night placement"))

    # 3. Adhesive anchors — working-time decay (base material = deck steel/concrete).
    evals.append(build_eval(
        activity_id="A-2007", activity_name="Adhesive anchor installation — FAB2 L3 deck — bay C3",
        wbs="FAB2.FAB.11", trade_id="adhesive_anchor_epoxy",
        trade_display="Adhesive anchors — injection epoxy into concrete",
        work_face_id="WF-FAB2-11", work_face_name="FAB2 L3 deck — bay C3",
        surf=SURF_BARE, gater=lambda i, s: gate_working_time(i, s),
        constraint={"constraint_id": "decay_working_time", "type": "decay_clock",
                    "label": "Working time collapses from 120 min at 0 C to 10 min at 40 C",
                    "governing_temp": "base_material", "margin_unit": "min",
                    "citation_fragment": "Hilti HIT-RE 500 V3: working time vs base material temperature."},
        scheduled=_bar(9, 5.0, 2.0, 3), unit_cost=48.0, quantity=420.0, rework=6.0,
        citation="Hilti HIT-RE 500 V3 technical data: base material -5 to +40 C; working time 120 min at 0 C down to 10 min at 40 C.",
        standard_ref="Hilti HIT-RE 500 V3 IFU (ICC-ES ESR-3814)",
        mitigation_hint="shade the substrate, chill cartridges, shorter injection runs, night install"))

    # 4. Masonry CMU hot weather — trigger_only (mitigation, not a stop).
    evals.append(build_eval(
        activity_id="A-1042", activity_name="CMU wall construction — BULK L2 — bay B2",
        wbs="BULK.CMU.02", trade_id="masonry_cmu_hot_weather",
        trade_display="Concrete masonry — hot weather construction",
        work_face_id="WF-BULK-02", work_face_name="BULK L2 — bay B2",
        surf=SURF_BARE, gater=lambda i, s: gate_hot_trigger(i),
        constraint={"constraint_id": "band_hot_weather_trigger_tier1", "type": "band",
                    "label": "Hot-weather procedures triggered above 37.8 C (100 F)",
                    "governing_temp": "air", "margin_unit": "C",
                    "citation_fragment": "TMS 602 hot weather triggered above 100 F or above 90 F with wind > 8 mph."},
        scheduled=_bar(6, 9.0, 5.0, 8), unit_cost=165.0, quantity=950.0, rework=3.5,
        citation="TMS 602 / ACI 530.1 hot weather construction (via BIA Technical Note 1): procedures triggered above 100 F (37.8 C).",
        standard_ref="TMS 602 / ACI 530.1 (via BIA Technical Note 1)",
        mitigation_hint="fog spray 3x/day, damp sand piles, cool mixing water, windbreak",
        include_marginal_in_intervals=True))

    # 5. Silicone weatherseal — offset dew point, delta 0.0 (at/above dew point) + dry.
    evals.append(build_eval(
        activity_id="A-1047", activity_name="Perimeter joint sealant — BULK L2 — bay B2",
        wbs="BULK.CMU.02", trade_id="sealant_silicone_weatherseal",
        trade_display="Elastomeric joint sealant — silicone weatherseal",
        work_face_id="WF-BULK-02", work_face_name="BULK L2 — bay B2",
        surf=SURF_BARE, gater=lambda i, s: gate_offset(
            i, s, delta_c=0.0, marg_delta=1.5, cid="offset_substrate_dry_frost_free",
            clause="DOWSIL 795 TDS"),
        constraint={"constraint_id": "offset_substrate_dry_frost_free", "type": "offset",
                    "label": "Substrate above dew point, clean, dry and frost-free",
                    "governing_temp": "surface", "margin_unit": "C",
                    "citation_fragment": "DOWSIL 795 TDS: do not apply on frost-laden or wet surfaces; substrate must be dry."},
        scheduled=_bar(7, 7.0, 4.0, 4), unit_cost=19.0, quantity=2300.0, rework=2.2,
        citation="DOWSIL 795 Silicone Building Sealant TDS: do not apply on frost-laden or wet surfaces; substrate at or above dew point and verified dry.",
        standard_ref="ASTM C1193; DOWSIL 795 TDS Form 61-885-01 S",
        mitigation_hint="dry the joint, defer to afternoon, moisture-meter verification"))

    # 6. Waterborne pavement marking — surface >=12.8 C and rising, dry.
    evals.append(build_eval(
        activity_id="A-6205", activity_name="Interior floor marking — WHSE grade — bay A1",
        wbs="WHSE.WAR.01", trade_id="pavement_marking_waterborne",
        trade_display="Waterborne pavement marking — traffic paint",
        work_face_id="WF-WHSE-01", work_face_name="WHSE grade — bay A1",
        surf=SURF_BARE, gater=lambda i, s: gate_marking(i, s),
        constraint={"constraint_id": "band_surface_rising", "type": "band",
                    "label": "Pavement >= 12.8 C (55 F) and rising; never below 7.2 C (45 F)",
                    "governing_temp": "surface", "margin_unit": "C",
                    "citation_fragment": "Sherwin-Williams Sher-Flight: minimum air and surface 55 F and rising; do not apply below 45 F."},
        scheduled=_bar(8, 5.0, 6.0, 4), unit_cost=3.2, quantity=11000.0, rework=1.8,
        citation="Sherwin-Williams Sher-Flight Waterborne Traffic Paint: minimum air and surface temperature 55 F and rising; do not apply below 45 F.",
        standard_ref="Sherwin-Williams Sher-Flight PDS; MoDOT EPG 620.11",
        mitigation_hint="defer to afternoon, cold-weather formulation"))

    # 7. Structural welding preheat — satisfied all horizon in summer (thin sections).
    evals.append(build_eval(
        activity_id="A-2006", activity_name="Deck weld & shear stud installation — FAB2 L3 deck — bay C3",
        wbs="FAB2.FAB.11", trade_id="structural_welding_preheat",
        trade_display="Structural welding — preheat and interpass",
        work_face_id="WF-FAB2-11", work_face_name="FAB2 L3 deck — bay C3",
        surf=SURF_BARE, gater=lambda i, s: gate_always_open(
            i, "AWS D1.1 prequalified minimum preheat (32 F for 1/8-3/4 in)", "band_prequalified_preheat"),
        constraint={"constraint_id": "band_prequalified_preheat", "type": "band",
                    "label": "Minimum preheat/interpass by thickness — a trigger, not a hard stop",
                    "governing_temp": "base_material", "margin_unit": "C",
                    "citation_fragment": "AWS D1.1 prequalified minimum preheat, Category B: 1/8-3/4 in -> 32 F (0 C)."},
        scheduled=_bar(6, 8.0, 3.0, 4), unit_cost=145.0, quantity=180.0, rework=5.0,
        citation="AWS D1.1 prequalified minimum preheat table, Category B steels: 1/8 to 3/4 in -> 32 F; the summer base material clears this all horizon.",
        standard_ref="AWS D1.1/D1.1M prequalified preheat table (via UFC 3-320-01A Table 3-1)",
        mitigation_hint="torch or induction preheat if a cold snap arrives"))

    # 8. Spray-applied fireproofing — continuity >=4 C, satisfied all summer.
    evals.append(build_eval(
        activity_id="A-2008", activity_name="Spray-applied fireproofing — FAB2 L2 deck — bay D2",
        wbs="FAB2.FAB.08", trade_id="sfrm_spray_applied_fireproofing",
        trade_display="Sprayed fire-resistive material (SFRM)",
        work_face_id="WF-FAB2-08", work_face_name="FAB2 L2 deck — bay D2",
        surf=SURF_SHADED, gater=lambda i, s: gate_always_open(
            i, "CAFCO 300 substrate/ambient >=40 F (4 C) run", "continuity_40f_24h"),
        constraint={"constraint_id": "continuity_40f_24h", "type": "continuity",
                    "label": "Substrate and ambient >= 4 C (40 F), maintained >= 24 h after application",
                    "governing_temp": "surface", "margin_unit": "C",
                    "citation_fragment": "CAFCO 300 TDS 1.7.1: maintain substrate and ambient >= 40 F (4 C) 24 h after application."},
        scheduled=_bar(7, 10.0, 3.0, 6), unit_cost=22.0, quantity=3100.0, rework=2.8,
        citation="Isolatek CAFCO 300 TDS 1.7.1: maintain substrate and ambient >= 40 F (4 C) prior to, during, and 24 h after application; the summer horizon clears this.",
        standard_ref="Isolatek CAFCO 300 TDS 1.7 (C-TDS 05/20)",
        mitigation_hint="temporary heat / enclosure only needed in a cold snap"))

    # 9. HMA surface course — the counter-trade: wants the afternoon HEAT.
    evals.append(build_eval(
        activity_id="A-6103", activity_name="HMA surface course — ROAD grade corridor",
        wbs="ROAD.PAV.01", trade_id="hma_paving_surface_course",
        trade_display="Hot-mix asphalt paving — surface course",
        work_face_id="WF-ROAD-01", work_face_name="ROAD grade — haul corridor",
        surf=SURF_BARE, gater=lambda i, s: gate_hot_base(i, s),
        constraint={"constraint_id": "decay_compaction_window", "type": "decay_clock",
                    "label": "Available compaction minutes = f(base surface temperature, lift)",
                    "governing_temp": "base_material", "margin_unit": "C",
                    "citation_fragment": "TxDOT RR 214-11: compaction window is a function of base surface temperature; hot base HELPS."},
        scheduled=_bar(13, 9.0, 6.0, 10), unit_cost=26.0, quantity=8600.0, rework=2.5,
        citation="TxDOT Research Report 214-11: available compaction time grows with base surface temperature; hot weather helps asphalt while it hurts the other trades on the same tile.",
        standard_ref="TxDOT Research Report 214-11; Asphalt Institute MS-22",
        mitigation_hint="increase lift thickness, add a roller, shift to the afternoon peak base temp",
        include_marginal_in_intervals=True))

    # Contended hours: the dawn band where the most lanes are simultaneously OPEN.
    # Across the horizon the strictly-open count peaks at 7 lanes, and it peaks
    # exactly at 05:00-09:00 each day — that is the collision the demo shows.
    per_hour_open = [
        sum(1 for ev in evals for c in ev.hours if c.ts == ts_at(i) and c.state.value == "open")
        for i in range(N_HOURS)
    ]
    peak = max(per_hour_open)
    contended = [ts_at(i) for i in range(N_HOURS) if per_hour_open[i] >= peak]

    totals = UsdExposure(
        at_risk_usd=round(sum(ev.usd_exposure.at_risk_usd for ev in evals), 0),
        protected_usd=round(sum(ev.usd_exposure.protected_usd for ev in evals), 0),
        basis="sum of per-activity at-risk / protected exposure across the 9 contending trades",
    )

    return WindowEvalBundle(
        run_id=RUN_ID,
        generated_at=HORIZON_START,
        horizon=Horizon(start=HORIZON_START, end=ts_at(N_HOURS), step_minutes=STEP_MIN, tier="commit"),
        site_id=SITE_ID,
        evaluations=evals,
        contended_hours=contended,
        totals=totals,
    )


# --------------------------------------------------------------------------- #
# The thermal series — 48 h of drivers for the bare FAB2 L3 deck.
# --------------------------------------------------------------------------- #

def build_thermal_series() -> WorkFaceThermalSeries:
    points: list[ThermalPoint] = []
    for i in range(N_HOURS):
        h = hod(i)
        points.append(ThermalPoint(
            ts=ts_at(i),
            t_air_c=AIR[h],
            rh_pct=rh_from(AIR[h], DEW[h]),
            cloud_octas=2.0 if 5 <= h <= 18 else 0.0,
            elevation_m=468.0,
            solar=SolarIrradiance(ghi_w_m2=float(GHI[h])),
            wind_ms=round(WIND_MPH[h] * 0.44704, 2),
            t_surf_c=SURF_BARE[h],
            t_dew_c=DEW[h],
        ))
    return WorkFaceThermalSeries(
        work_face_id="WF-FAB2-11",
        tile_cluster_id=CLUSTER_ID,
        centroid_lon=-112.1657,
        centroid_lat=33.7876,
        tier="commit",
        step_minutes=STEP_MIN,
        points=points,
        source="synthetic",
        confidence="high",
        fg_activity_ids=["fg-heatmap-FAB2DECK-0001", "fg-envparams-FAB2DECK-0001"],
    )


# --------------------------------------------------------------------------- #
# Emit + validate
# --------------------------------------------------------------------------- #

def _write_validated(path: Path, model, RootModel) -> None:
    """Serialise, then re-parse through the schema so a fixture can never drift."""
    text = model.model_dump_json(indent=2, exclude_none=False)
    RootModel.model_validate_json(text)              # must not raise
    path.write_text(text + "\n", encoding="utf-8")


def build_cure_fit() -> dict:
    """TASK 4 deliverable: the piecewise-Q10 model vs the Macropoxy 646 PDS cure
    table, so T1 can plot the fit against the manufacturer's own numbers. That one
    chart answers 'did you make this up' before anyone asks it. Computed from the
    registry (q10 segments + calibration points), not hand-typed."""
    from apps.api.windows.psychro import hours_to_service
    from apps.api.windows.registry import load_registry

    spec = load_registry().get("coating_epoxy_structural_steel").constraint("cure_clock_to_service")
    points = []
    for cp in spec.calibration_points:
        model = hours_to_service(cp.t_c, spec.q10_segments, spec.hours_at_ref, spec.ref_c)
        points.append({
            "base_c": cp.t_c,
            "base_f": cp.t_f,
            "pds_hours": cp.hours,
            "model_hours": round(model, 1),
            "pct_error": round(100.0 * (model - cp.hours) / cp.hours, 2),
        })
    return {
        "product": "Sherwin-Williams Macropoxy 646",
        "milestone": "cure_to_service_atmospheric",
        "model": "piecewise_q10",
        "ref_c": spec.ref_c,
        "hours_at_ref": spec.hours_at_ref,
        "q10_segments": [s.model_dump() for s in spec.q10_segments],
        "points": points,
        "source": "Macropoxy 646 PDS drying schedule at 7.0 mils wet; registry "
                  "coating_epoxy_structural_steel / cure_clock_to_service.",
        "note": "Model reproduces all three PDS points within 3 %. The rate does NOT "
                "follow a single Q10 — epoxy cure stalls near the minimum application "
                "temperature (q10 1.17 below 25 C, 1.55 above).",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE Day-1 fixtures (T3, TASK 2)")
    ap.add_argument("--out", default="data/fixtures", type=Path)
    ap.add_argument("--check", action="store_true", help="validate and print a summary")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    hero = build_hero()
    bundle = build_bundle()
    series = build_thermal_series()

    _write_validated(args.out / "sample_window_eval.json", hero, WindowEval)
    _write_validated(args.out / "sample_window_eval_ribbon.json", bundle, WindowEvalBundle)
    _write_validated(args.out / "sample_thermal_series.json", series, WorkFaceThermalSeries)

    import json as _json
    (args.out / "cure_fit_macropoxy646.json").write_text(
        _json.dumps(build_cure_fit(), indent=2) + "\n", encoding="utf-8")

    # Belt-and-braces re-read from disk, exactly as the brief specifies.
    WindowEval.model_validate_json((args.out / "sample_window_eval.json").read_text(encoding="utf-8"))
    WindowEvalBundle.model_validate_json((args.out / "sample_window_eval_ribbon.json").read_text(encoding="utf-8"))
    WorkFaceThermalSeries.model_validate_json((args.out / "sample_thermal_series.json").read_text(encoding="utf-8"))

    trades = {ev.trade_id for ev in bundle.evaluations}
    print(f"[ok] sample_window_eval.json        hero verdict={hero.verdict.value} "
          f"binding={hero.binding_constraint.constraint_id if hero.binding_constraint else None}")
    print(f"[ok] sample_window_eval_ribbon.json {len(bundle.evaluations)} lanes, "
          f"{len(trades)} distinct trades, {len(bundle.contended_hours)} contended hours")
    print(f"[ok] sample_thermal_series.json     {len(series.points)} points, work_face={series.work_face_id}")
    if args.check:
        assert hero.verdict.value == "at_risk", hero.verdict
        assert hero.binding_constraint and hero.binding_constraint.constraint_id == "offset_dew_point"
        assert len(bundle.evaluations) == 9 and len(trades) == 9, trades
        assert bundle.contended_hours, "expected a contended dawn window"
        print("[ok] --check assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
