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
    evaluate_offset,
    intersect,
    to_intervals,
)
from apps.api.windows.registry import load_registry
from packages.schemas.trade_window import BandSpec, OffsetSpec
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
