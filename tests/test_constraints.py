"""TASK 5 acceptance — the band and offset evaluators, hand-worked and asserted.

Series are tiny and computed by hand so a regression is obvious. The two cases
that catch a naive implementation — the offset boundary and the leave-one-out
binding constraint — are written as literals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.windows.constraints import (
    BindingConstraint,
    ConstraintEvaluation,
    HourVerdict,
    Interval,
    binding_constraint,
    closed_intervals,
    evaluate_band,
    evaluate_continuity,
    evaluate_decay_clock,
    evaluate_human,
    evaluate_offset,
    intersect,
    productive_hours,
    to_intervals,
)
from apps.api.windows.registry import load_registry
from packages.schemas.trade_window import BandSpec, ContinuitySpec, OffsetSpec
from packages.schemas.window_eval import HourState, SeriesPoint

TZ = timezone(timedelta(hours=-7))


def _ts(n: int, start_h: int = 0) -> list[datetime]:
    base = datetime(2026, 8, 24, start_h, 0, tzinfo=TZ)
    return [base + timedelta(hours=i) for i in range(n)]


def _air(temps: list[float]) -> list[SeriesPoint]:
    return [SeriesPoint(t_air_c=t) for t in temps]


# --------------------------------------------------------------------------- #
# 1. Band, both bounds
# --------------------------------------------------------------------------- #

def test_band_both_bounds() -> None:
    spec = BandSpec(constraint_id="b", label="20-35 C", citation_fragment="x",
                    on="air", t_min_c=20.0, t_max_c=35.0, marginal_delta_c=1.5)
    ev = evaluate_band(_air([30, 34, 36, 34, 30]), spec, _ts(5))
    states = [h.state for h in ev.per_hour]
    assert states == [HourState.OPEN, HourState.MARGINAL, HourState.CLOSED,
                      HourState.MARGINAL, HourState.OPEN]
    assert ev.worst_margin == pytest.approx(-1.0)
    # "one interval" = a single closed excursion splitting the window
    assert len(closed_intervals(ev.per_hour)) == 1


# --------------------------------------------------------------------------- #
# 2. Band, rising_required
# --------------------------------------------------------------------------- #

def test_band_rising_required_descending_never_opens() -> None:
    spec = BandSpec(constraint_id="b", label=">=10 and rising", citation_fragment="x",
                    on="air", t_min_c=10.0, rising_required=True, marginal_delta_c=2.0)
    ev = evaluate_band(_air([20, 18, 16, 14, 12]), spec, _ts(5))
    assert ev.per_hour[0].state is HourState.NO_DATA          # t_0 can't confirm "and rising"
    assert all(h.state is not HourState.OPEN for h in ev.per_hour)  # descending -> never open


# --------------------------------------------------------------------------- #
# 3. Offset, SSPC — the boundary case
# --------------------------------------------------------------------------- #

def test_offset_sspc_boundary() -> None:
    spec = OffsetSpec(constraint_id="offset_dew_point", label="surface >= dew + 2.8",
                      citation_fragment="SSPC-PA 1 6.2", on="surface", above="dew_point",
                      delta_c=2.8, marginal_delta_c=1.0)
    series = [SeriesPoint(t_surf_c=s, t_dew_c=14.0) for s in (12, 14, 16, 18, 20)]
    ev = evaluate_offset(series, spec, _ts(5))
    margins = [h.margin for h in ev.per_hour]
    assert margins == pytest.approx([-4.8, -2.8, -0.8, 1.2, 3.2])
    states = [h.state for h in ev.per_hour]
    assert states == [HourState.CLOSED, HourState.CLOSED, HourState.CLOSED,
                      HourState.OPEN, HourState.OPEN]                 # -0.8 is still closed
    assert len(ev.intervals) == 1                                    # one open interval {3,4}


# --------------------------------------------------------------------------- #
# 4. Offset, missing data -> NO_DATA (never OPEN, never a guessed dew point)
# --------------------------------------------------------------------------- #

def test_offset_missing_data_is_no_data_not_open() -> None:
    spec = OffsetSpec(constraint_id="offset_dew_point", label="surface >= dew + 2.8",
                      citation_fragment="x", on="surface", above="dew_point", delta_c=2.8)
    # surface present, but no dew point and no (air, rh) to derive one
    series = [SeriesPoint(t_surf_c=20.0, t_dew_c=None, t_air_c=None, rh_pct=None)]
    ev = evaluate_offset(series, spec, _ts(1))
    assert ev.per_hour[0].state is HourState.NO_DATA
    assert ev.per_hour[0].margin is None                             # nothing substituted


# --------------------------------------------------------------------------- #
# 5. Intersection
# --------------------------------------------------------------------------- #

def test_interval_intersection() -> None:
    def iv(h0: int, h1: int) -> Interval:
        d = datetime(2026, 8, 24, tzinfo=TZ)
        return Interval(d + timedelta(hours=h0), d + timedelta(hours=h1))
    a = [iv(5, 10)]
    b = [iv(7, 14)]
    out = intersect(a, b)
    assert len(out) == 1
    assert out[0].start.hour == 7 and out[0].end.hour == 10


# --------------------------------------------------------------------------- #
# 6. Binding constraint, leave-one-out (the case that catches "most closed hours")
# --------------------------------------------------------------------------- #

def _eval_from_states(cid: str, states: list[HourState]) -> ConstraintEvaluation:
    ts = _ts(len(states))
    per_hour = [HourVerdict(t, s) for t, s in zip(ts, states)]
    ev = ConstraintEvaluation(cid, per_hour,
                              intervals=to_intervals(per_hour),
                              closed_hours=sum(1 for s in states if s is HourState.CLOSED))
    return ev


def test_binding_constraint_is_not_most_closed_hours() -> None:
    O, C = HourState.OPEN, HourState.CLOSED
    n = 12
    a = _eval_from_states("A", [C, C, C, C] + [O] * 8)          # closes 4 hours (the most)
    b = _eval_from_states("B", [O] * 6 + [C] + [O] * 5)          # closes 1 hour, but splits the best window
    c = _eval_from_states("C", [O] * n)                          # closes nothing
    assert a.closed_hours == 4 and b.closed_hours == 1
    binding = binding_constraint({"A": a, "B": b, "C": c})
    assert isinstance(binding, BindingConstraint)
    assert binding.constraint_id == "B"                         # NOT "A", despite A closing more
    assert binding.would_extend_window_by_h == pytest.approx(3.0)


# --------------------------------------------------------------------------- #
# 7. The real registry row on a 48 h dawn-convergence series
# --------------------------------------------------------------------------- #

def test_real_coating_row_binding_is_dew_point() -> None:
    from scripts.make_fixtures import AIR, DEW, SURF_BARE, rh_from

    start = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)
    ts = [start + timedelta(hours=i) for i in range(48)]
    series = [
        SeriesPoint(t_air_c=AIR[t.hour], t_surf_c=SURF_BARE[t.hour], t_dew_c=DEW[t.hour],
                    rh_pct=rh_from(AIR[t.hour], DEW[t.hour]))
        for t in ts
    ]

    coating = load_registry().get("coating_epoxy_structural_steel")
    results: dict[str, ConstraintEvaluation] = {}
    for spec in coating.constraints:
        if isinstance(spec, BandSpec):
            results[spec.constraint_id] = evaluate_band(series, spec, ts)
        elif isinstance(spec, OffsetSpec):
            results[spec.constraint_id] = evaluate_offset(series, spec, ts)
        # cure_clock is a Day-4 evaluator; it does not gate per-hour here.

    binding = binding_constraint(results)
    assert binding is not None and binding.constraint_id == "offset_dew_point"

    # After the pre-dawn condensation closure, the dew-point window reopens 05:00-07:00.
    offset_opens = [iv for iv in results["offset_dew_point"].intervals if 5 <= iv.start.hour <= 7]
    assert offset_opens, "expected the coating window to open between 05:00 and 07:00"
    assert offset_opens[0].start.hour in (5, 6, 7)


# --------------------------------------------------------------------------- #
# 8. Continuity — horizon truncation must be NO_DATA, never OPEN
# --------------------------------------------------------------------------- #

def test_continuity_truncation_is_no_data_never_open() -> None:
    """A 24 h protected run requested on a 12 h series can never be confirmed: every
    hour is NO_DATA, not OPEN. A short horizon must not paint a long window green."""
    spec = ContinuitySpec(constraint_id="c", label="24 h run", citation_fragment="x",
                          on="surface", t_min_c=4.0, run_hours=24.0)
    series = [SeriesPoint(t_surf_c=10.0) for _ in range(12)]   # comfortably warm
    ev = evaluate_continuity(series, spec, _ts(12))
    assert all(h.state is HourState.NO_DATA for h in ev.per_hour)
    assert not any(h.state is HourState.OPEN for h in ev.per_hour)


# --------------------------------------------------------------------------- #
# 9. Continuity — dual series (SFRM): ambient cold closes even when substrate warm
# --------------------------------------------------------------------------- #

def test_continuity_dual_series_ambient_closes_a_warm_substrate() -> None:
    warm_sub, cold_air = 10.0, 2.0                            # substrate warm, ambient below 4 C
    # substrate warm throughout; ambient dips at index 2 (inside the run of index 1).
    air = [10.0, 10.0, cold_air, 10.0, 10.0]
    series = [SeriesPoint(t_surf_c=warm_sub, t_air_c=a) for a in air]
    ts = _ts(5)

    dual = ContinuitySpec(constraint_id="c", label="substrate AND ambient", citation_fragment="x",
                          on="surface", also_on="air", t_min_c=4.0, run_hours=1.0, lead_hours=0.0)
    solo = ContinuitySpec(constraint_id="c", label="substrate only", citation_fragment="x",
                          on="surface", t_min_c=4.0, run_hours=1.0, lead_hours=0.0)

    ev_dual = evaluate_continuity(series, dual, ts)
    ev_solo = evaluate_continuity(series, solo, ts)
    # index 1's run [1,2] hits the cold ambient -> dual CLOSED; substrate-only stays OPEN.
    assert ev_dual.per_hour[1].state is HourState.CLOSED
    assert ev_solo.per_hour[1].state is HourState.OPEN


def test_continuity_grouted_selects_longer_run() -> None:
    spec = ContinuitySpec(constraint_id="c", label="masonry", citation_fragment="x",
                          on="air", t_min_c=0.0, run_hours=24.0, grouted_run_hours=48.0)
    warm = [SeriesPoint(t_air_c=5.0) for _ in range(30)]
    ts = _ts(30)
    # hour 0 can confirm a 24 h run (needs index 24) but not a 48 h run (needs index 48).
    assert evaluate_continuity(warm, spec, ts).per_hour[0].state is HourState.OPEN
    assert evaluate_continuity(warm, spec, ts, grouted=True).per_hour[0].state is HourState.NO_DATA


# --------------------------------------------------------------------------- #
# 10. Decay clock — asphalt inversion (hotter base -> more compaction minutes)
#                    and out-of-range refusal to extrapolate
# --------------------------------------------------------------------------- #

def _base(temps: list[float]) -> list[SeriesPoint]:
    return [SeriesPoint(t_base_material_c=t) for t in temps]


def test_decay_asphalt_inversion_hotter_base_more_minutes() -> None:
    """One trade's red is another's green: a hotter base yields MORE available
    compaction minutes than a colder one (thin 25 mm lift). Asphalt runs opposite
    to every other trade on the same tile in the same hour."""
    spec = load_registry().get("hma_paving_surface_course").constraint("decay_compaction_window")
    ev = evaluate_decay_clock(_base([40.0, 5.0]), spec, _ts(2), lift_mm=25)
    hot_minutes, cold_minutes = ev.per_hour[0].margin, ev.per_hour[1].margin
    assert hot_minutes > cold_minutes                        # the required inversion
    assert ev.per_hour[0].state is HourState.OPEN
    assert ev.margin_unit == "min"


def test_decay_out_of_range_is_closed_not_extrapolated() -> None:
    spec = load_registry().get("adhesive_anchor_epoxy").constraint("decay_working_time")
    ev = evaluate_decay_clock(_base([60.0]), spec, _ts(1))    # qualified only to +40 C
    assert ev.per_hour[0].state is HourState.CLOSED
    assert "extrapolate" in ev.per_hour[0].reason


def test_decay_minutes_required_gates_and_reports_margin() -> None:
    spec = load_registry().get("adhesive_anchor_epoxy").constraint("decay_working_time")
    # 40 C base -> ~10 min working time; a 15 min requirement closes it, a 5 min one does not.
    ev = evaluate_decay_clock(_base([40.0]), spec, _ts(1), minutes_required=15.0)
    assert ev.per_hour[0].state is HourState.CLOSED
    ev2 = evaluate_decay_clock(_base([40.0]), spec, _ts(1), minutes_required=5.0)
    assert ev2.per_hour[0].state is HourState.OPEN


# --------------------------------------------------------------------------- #
# 11. Human — WBGT bands, and heat never fully closes an hour
# --------------------------------------------------------------------------- #

def _human_wbgt_spec():
    return load_registry().get("crew_heat_exposure").constraint("human_wbgt_work_rest")


def test_human_wbgt_bands_map_to_work_fraction() -> None:
    spec = _human_wbgt_spec()
    series = [SeriesPoint(wbgt_c=w) for w in (27.4, 28.0, 29.5, 31.0)]
    ev = evaluate_human(series, spec, _ts(4))
    fractions = [h.productive_fraction for h in ev.per_hour]
    assert fractions == pytest.approx([1.0, 0.75, 0.5, 0.25])
    states = [h.state for h in ev.per_hour]
    assert states == [HourState.OPEN, HourState.MARGINAL, HourState.MARGINAL, HourState.MARGINAL]
    assert ev.margin_unit == "ratio"


def test_human_never_closes() -> None:
    """Neither the WBGT band map nor the heat-index triggers may return CLOSED —
    heat shrinks a window, it does not close one."""
    wbgt_spec = _human_wbgt_spec()
    hi_spec = load_registry().get("crew_heat_exposure").constraint("human_osha_high_heat_trigger")
    hostile = [SeriesPoint(t_air_c=48.0, rh_pct=60.0, wind_ms=0.5, ghi_w_m2=1000.0, wbgt_c=35.0)]
    ev_wbgt = evaluate_human(hostile, wbgt_spec, _ts(1))
    ev_hi = evaluate_human(hostile, hi_spec, _ts(1))
    assert ev_wbgt.per_hour[0].state is not HourState.CLOSED
    assert ev_hi.per_hour[0].state is not HourState.CLOSED


def test_human_wbgt_modelled_when_series_lacks_it() -> None:
    spec = _human_wbgt_spec()
    # no wbgt_c, but air/RH/wind/GHI present -> modelled, reason names the method.
    sp = SeriesPoint(t_air_c=42.0, rh_pct=24.0, wind_ms=1.0, ghi_w_m2=985.0)
    ev = evaluate_human([sp], spec, _ts(1))
    assert "modelled" in ev.per_hour[0].reason
    assert ev.per_hour[0].state in (HourState.OPEN, HourState.MARGINAL)


def test_productive_hours_applies_the_haircut() -> None:
    """A five-hour window at a 25%% rest ratio is 3.75 productive crew-hours."""
    ts = _ts(5)
    per_hour = [HourVerdict(t, HourState.OPEN, productive_fraction=0.75) for t in ts]
    iv = Interval(ts[0], ts[-1] + timedelta(hours=1))
    assert productive_hours(iv, per_hour) == pytest.approx(3.75)
