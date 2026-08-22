"""Day-4 acceptance — the assembly. `evaluate_window` turns seven evaluators into
the single WindowEval T1 renders, and its output must validate against the schema
and keep the binding constraint inside constraints[]."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.windows.evaluate import evaluate_window
from packages.schemas.window_eval import ScheduledBar, SeriesPoint, Verdict, WindowEval
from scripts.make_fixtures import AIR, DEW, GHI, SURF_BARE, WIND_MPH, rh_from

TZ = timezone(timedelta(hours=-7))
START = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)


def _coating_series(n: int = 48) -> tuple[list[SeriesPoint], list[datetime]]:
    ts = [START + timedelta(hours=i) for i in range(n)]
    series = [
        SeriesPoint(
            t_air_c=AIR[t.hour], t_surf_c=SURF_BARE[t.hour], t_dew_c=DEW[t.hour],
            rh_pct=rh_from(AIR[t.hour], DEW[t.hour]),
            wind_ms=round(WIND_MPH[t.hour] * 0.44704, 2), ghi_w_m2=float(GHI[t.hour]),
        )
        for t in ts
    ]
    return series, ts


def _bar(hour: int, dur: float) -> ScheduledBar:
    start = datetime(2026, 8, 24, hour, 0, tzinfo=TZ)
    return ScheduledBar(start=start, finish=start + timedelta(hours=dur), duration_h=dur,
                        total_float_d=1.5, is_near_critical=True, crew_size=5)


def _eval_coating(bar: ScheduledBar) -> WindowEval:
    series, ts = _coating_series()
    return evaluate_window(
        trade_id="coating_epoxy_structural_steel", series=series, ts=ts, scheduled=bar,
        activity_id="A-2009", activity_name="Structural steel coating — FAB2 L3 deck",
        work_face_id="WF-FAB2-11", work_face_name="FAB2 L3 deck — bay C3",
        run_id="test-run", fg_activity_ids=["fg-heatmap-0001"])


# --------------------------------------------------------------------------- #
# Validates, and the binding constraint is a declared constraint
# --------------------------------------------------------------------------- #

def test_evaluate_window_validates_as_window_eval() -> None:
    ev = _eval_coating(_bar(2, 6.0))
    WindowEval.model_validate(ev.model_dump())               # round-trips clean
    assert len(ev.hours) == 48
    assert ev.binding_constraint is not None
    ids = {c.constraint_id for c in ev.constraints}
    assert ev.binding_constraint.constraint_id in ids       # schema validator's invariant, asserted


def test_coating_dawn_bar_is_at_risk_and_binds_on_dew_point() -> None:
    """The hero case: a 6 h bar at 02:00 runs into the dawn condensation edge, so
    the offset (surface vs dew point) is the binding constraint, and the verdict is
    at_risk — matching the hand-written hero fixture's story."""
    ev = _eval_coating(_bar(2, 6.0))
    assert ev.verdict is Verdict.AT_RISK
    assert ev.binding_constraint.constraint_id == "offset_dew_point"
    # midday must stay open — a coatable 60 C deck is not closed by the cure clock.
    midday = next(c for c in ev.hours if c.ts.hour == 14 and c.ts.day == 24)
    assert midday.state.value == "open"


def test_coating_open_intervals_match_the_hero_fixture_shape() -> None:
    ev = _eval_coating(_bar(2, 6.0))
    durations = sorted(round(iv.duration_h, 1) for iv in ev.open_intervals)
    assert durations == [2.0, 20.0, 22.0]                   # same three intervals as the fixture


def test_usd_exposure_arithmetic() -> None:
    ev = _eval_coating(_bar(2, 6.0))
    # 4200 m2 x $34 x 3.2 rework = 456,960; at risk because the verdict is not compliant.
    assert ev.usd_exposure.at_risk_usd == pytest.approx(456960.0)
    assert ev.provenance.registry_version == "2026.08.20-a"
    assert ev.provenance.series_digest and len(ev.provenance.series_digest) == 64


# --------------------------------------------------------------------------- #
# Fail closed: missing governing input over the bar -> NO_DATA
# --------------------------------------------------------------------------- #

def test_missing_surface_over_bar_fails_closed() -> None:
    series, ts = _coating_series()
    # strip the surface temperature the coating governs on -> constraints go NO_DATA.
    series = [sp.model_copy(update={"t_surf_c": None, "t_dew_c": None}) for sp in series]
    ev = evaluate_window(
        trade_id="coating_epoxy_structural_steel", series=series, ts=ts, scheduled=_bar(2, 6.0),
        activity_id="A", activity_name="c", work_face_id="w", work_face_name="d", run_id="r")
    WindowEval.model_validate(ev.model_dump())
    assert ev.verdict is Verdict.NO_DATA
    assert ev.confidence.value in ("medium", "low")


# --------------------------------------------------------------------------- #
# The counter-trade: HMA wants the afternoon heat the others flee
# --------------------------------------------------------------------------- #

def test_hma_afternoon_bar_is_the_honest_counter_trade() -> None:
    series, ts = _coating_series()
    # base material = the bare deck surface for this synthetic tile.
    series = [sp.model_copy(update={"t_base_material_c": sp.t_surf_c}) for sp in series]
    bar = ScheduledBar(start=datetime(2026, 8, 24, 13, 0, tzinfo=TZ),
                       finish=datetime(2026, 8, 24, 18, 0, tzinfo=TZ), duration_h=5.0,
                       total_float_d=6.0, crew_size=10)
    ev = evaluate_window(
        trade_id="hma_paving_surface_course", series=series, ts=ts, scheduled=bar,
        activity_id="A-6103", activity_name="HMA surface course", work_face_id="WF-ROAD-01",
        work_face_name="ROAD grade", run_id="r")
    WindowEval.model_validate(ev.model_dump())
    # hot midday base -> compaction window open; cool dawn -> not open.
    midday = next(c for c in ev.hours if c.ts.hour == 14 and c.ts.day == 24)
    dawn = next(c for c in ev.hours if c.ts.hour == 5 and c.ts.day == 24)
    assert midday.state.value == "open"
    assert dawn.state.value != "open"
