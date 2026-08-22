"""Day-4 acceptance — the cure clock (an integral, not a threshold).

The Q10 fit reproducing the Macropoxy 646 PDS cure table is the chart that answers
"did you make this up" before anyone asks it. The per-hour evaluator adds: if the
crew starts at hour t, when does it finish curing, and what does honesty about
extrapolation look like.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.windows.constraints import evaluate_cure_clock, recoat_window_h
from apps.api.windows.psychro import hours_to_service
from apps.api.windows.registry import load_registry
from packages.schemas.window_eval import HourState, SeriesPoint

TZ = timezone(timedelta(hours=-7))


def _ts(n: int) -> list[datetime]:
    base = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)
    return [base + timedelta(hours=i) for i in range(n)]


def _spec():
    return load_registry().get("coating_epoxy_structural_steel").constraint("cure_clock_to_service")


# --------------------------------------------------------------------------- #
# The Q10 fit reproduces the PDS drying schedule at 1.7 / 25 / 37.8 C
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("base_c, pds_hours", [(1.7, 240.0), (25.0, 168.0), (37.8, 96.0)])
def test_hours_to_service_reproduces_pds(base_c, pds_hours) -> None:
    spec = _spec()
    model = hours_to_service(base_c, spec.q10_segments, spec.hours_at_ref, spec.ref_c)
    assert model == pytest.approx(pds_hours, rel=0.03)


# --------------------------------------------------------------------------- #
# Per-hour cure clock
# --------------------------------------------------------------------------- #

def test_cure_clock_isothermal_projection_matches_hours_to_service() -> None:
    """Hold 25 C constant across a long series: the projected hours to service must
    track the isothermal reference (168 h) — the tail-hold makes it exact."""
    spec = _spec()
    series = [SeriesPoint(t_surf_c=25.0) for _ in range(6)]
    ev = evaluate_cure_clock(series, spec, _ts(6))
    assert ev.per_hour[0].state is HourState.OPEN
    assert ev.per_hour[0].margin == pytest.approx(168.0, rel=1e-3)
    assert ev.margin_unit == "h"


def test_cure_clock_below_calibration_is_closed_not_extrapolated() -> None:
    spec = _spec()                                          # calibrated 1.7-37.8 C
    series = [SeriesPoint(t_surf_c=0.0)]                    # below the lowest t_lo_c
    ev = evaluate_cure_clock(series, spec, _ts(1))
    assert ev.per_hour[0].state is HourState.CLOSED
    assert "extrapolate" in ev.per_hour[0].reason


def test_cure_clock_above_calibration_stays_open_with_capped_rate() -> None:
    """DEVIATION FROM THE BRIEF (reported): a coatable 60 C deck is not CLOSED. The
    rate is capped at the top calibration, never extrapolated, and the hour stays
    open."""
    spec = _spec()
    series = [SeriesPoint(t_surf_c=60.0) for _ in range(4)]
    ev = evaluate_cure_clock(series, spec, _ts(4))
    assert ev.per_hour[0].state is HourState.OPEN
    assert "capped" in ev.per_hour[0].reason
    # capped rate == rate at 37.8 C, so projected == hours_to_service(37.8) ~ 96 h
    assert ev.per_hour[0].margin == pytest.approx(96.0, rel=0.02)


def test_cure_clock_colder_projects_longer_and_names_the_tail() -> None:
    """Cure slows as it cools: a near-floor cure (1.7 C) projects far past the 168 h
    reference (~240 h, reproducing the PDS cold point), and the reason names the
    constant-tail extrapolation. Note the MARGINAL band (>= 1.5x ref = 252 h) is
    inert for this product — its coldest calibrated cure is 240 h, below 252 —
    which is itself the low-temperature deviation the tech spec calls out."""
    spec = _spec()
    cold = evaluate_cure_clock([SeriesPoint(t_surf_c=1.7) for _ in range(3)], spec, _ts(3))
    warm = evaluate_cure_clock([SeriesPoint(t_surf_c=25.0) for _ in range(3)], spec, _ts(3))
    assert cold.per_hour[0].margin > warm.per_hour[0].margin
    assert cold.per_hour[0].margin == pytest.approx(240.0, rel=0.03)
    assert "constant" in cold.per_hour[0].reason


# --------------------------------------------------------------------------- #
# recoat window helper
# --------------------------------------------------------------------------- #

def test_recoat_window_interpolates_min_and_caps_max() -> None:
    spec = _spec()
    lo, hi = recoat_window_h(spec, 25.0)                    # a published calibration point
    assert lo == pytest.approx(8.0)
    assert hi == pytest.approx(8760.0)
    lo_cold, _ = recoat_window_h(spec, 1.7)
    assert lo_cold == pytest.approx(48.0)
    # midway between 1.7 (48 h) and 25 (8 h) interpolates linearly
    mid, _ = recoat_window_h(spec, (1.7 + 25.0) / 2.0)
    assert mid == pytest.approx((48.0 + 8.0) / 2.0, rel=1e-6)
