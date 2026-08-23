"""
WORKFACE — Day-7 sequencer tests.  T3, Task E (§7.2, §2.4, §8).

Asserts the greedy packer's four commitments:
  * topological order respected (a predecessor is placed before its successor);
  * ascending-float ordering (tightest float first);
  * PRODUCTIVE-hours packing, not clock hours — an activity needing 6 productive
    hours does not fit a 5-clock-hour window at a 25% rest ratio (3.75 productive);
  * the four SFRM activities from §2.4 (real data) return NAMED outcomes, never an
    exception — and the horizon-truncation path is exercised;
  * an infeasible activity returns a named BlockingConstraint, not a raise.

No model anywhere (hard rule 1). CI runs this with LLM_BASE_URL unset.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.api.sequencer.pack import (
    BlockingConstraint,
    PackActivity,
    PlaceStatus,
    YamlCrewSource,
    activity_from_eval,
    pack,
)
from packages.schemas.window_eval import Confidence, OpenInterval

TZ = timezone(timedelta(hours=-7))


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=TZ)


def _iv(a: datetime, b: datetime, productive_h: float | None = None) -> OpenInterval:
    dur = (b - a).total_seconds() / 3600.0
    return OpenInterval(
        start=a, end=b, duration_h=dur,
        productive_h=dur if productive_h is None else productive_h,
        includes_marginal=False, min_margin=1.0, confidence=Confidence.HIGH,
    )


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #

def test_topological_order_respected():
    """A must be placed before B when B depends on A (B starts no earlier than A finishes)."""
    a = PackActivity("A", "adhesive_anchor_epoxy", "WF-1", needed_productive_h=3, crew_size=3,
                     total_float_d=5.0, planned_start=_dt(24, 6), open_intervals=[_iv(_dt(24, 6), _dt(24, 18))])
    b = PackActivity("B", "adhesive_anchor_epoxy", "WF-1", needed_productive_h=3, crew_size=3,
                     total_float_d=0.1, planned_start=_dt(24, 6), open_intervals=[_iv(_dt(24, 6), _dt(24, 18))],
                     predecessors=["A"])
    # B has far tighter float, but the topo order must still place A first.
    r = pack([b, a], crew=YamlCrewSource(), anchor=_dt(24, 6))
    assert r.order.index("A") < r.order.index("B")
    pa, pb = r.placements["A"], r.placements["B"]
    assert pa.status is not PlaceStatus.UNPLACEABLE and pb.status is not PlaceStatus.UNPLACEABLE
    assert pb.start >= pa.finish            # precedence honoured in the actual placement


def test_ascending_float_order_tightest_first():
    """With no precedence, the packer processes tightest float first."""
    acts = [
        PackActivity("loose", "sealant_silicone_weatherseal", "WF-1", 2, 4, 9.0, _dt(24, 6), [_iv(_dt(24, 6), _dt(24, 18))]),
        PackActivity("tight", "sealant_silicone_weatherseal", "WF-2", 2, 4, 0.2, _dt(24, 6), [_iv(_dt(24, 6), _dt(24, 18))]),
        PackActivity("mid", "sealant_silicone_weatherseal", "WF-3", 2, 4, 3.0, _dt(24, 6), [_iv(_dt(24, 6), _dt(24, 18))]),
    ]
    r = pack(acts, crew=YamlCrewSource(), anchor=_dt(24, 6))
    assert r.order == ["tight", "mid", "loose"]


# --------------------------------------------------------------------------- #
# Productive hours, not clock hours
# --------------------------------------------------------------------------- #

def test_packs_against_productive_hours_not_clock_hours():
    """A 5-clock-hour window at a 25% rest ratio is 3.75 productive crew-hours; an
    activity needing 6 productive hours must NOT fit it — even though 5 clock hours
    'looks' like less than 6 would need. The blocker is named, not raised."""
    window = _iv(_dt(24, 12), _dt(24, 17), productive_h=3.75)     # 5 clock h, WBGT haircut to 3.75
    a = PackActivity("hot", "coating_epoxy_structural_steel", "WF-1", needed_productive_h=6.0,
                     crew_size=4, total_float_d=1.0, planned_start=_dt(24, 12), open_intervals=[window])
    r = pack([a], crew=YamlCrewSource(), anchor=_dt(24, 12))
    p = r.placements["hot"]
    assert p.status is PlaceStatus.UNPLACEABLE
    assert p.blocked_by is BlockingConstraint.INSUFFICIENT_PRODUCTIVE_HOURS

    # The same activity DOES fit a window with enough productive hours.
    a2 = PackActivity("ok", "coating_epoxy_structural_steel", "WF-1", needed_productive_h=6.0,
                      crew_size=4, total_float_d=1.0, planned_start=_dt(24, 6), open_intervals=[_iv(_dt(24, 6), _dt(24, 14), productive_h=8.0)])
    r2 = pack([a2], crew=YamlCrewSource(), anchor=_dt(24, 6))
    assert r2.placements["ok"].status is PlaceStatus.PLACED


# --------------------------------------------------------------------------- #
# Named infeasibility (never an exception)
# --------------------------------------------------------------------------- #

def test_no_open_interval_is_named_not_raised():
    a = PackActivity("closed", "coating_epoxy_structural_steel", "WF-1", 6.0, 4, 1.0, _dt(24, 6), open_intervals=[])
    r = pack([a], crew=YamlCrewSource(), anchor=_dt(24, 6))
    p = r.placements["closed"]
    assert p.status is PlaceStatus.UNPLACEABLE
    assert p.blocked_by is BlockingConstraint.NO_OPEN_INTERVAL


def test_crew_capacity_blocks_the_third_concurrent_crew():
    """coating heads = 10 in crews.yaml → two crews of 4 fit a shift (8 heads); a
    third (12 heads) contends. The third is named crew_unavailable, not raised."""
    win = lambda: _iv(_dt(24, 6), _dt(24, 18), productive_h=12.0)
    acts = [PackActivity(f"c{i}", "coating_epoxy_structural_steel", f"WF-{i}", 4.0, 4, 1.0, _dt(24, 6), [win()])
            for i in range(3)]
    r = pack(acts, crew=YamlCrewSource(), anchor=_dt(24, 6))
    placed = [p for p in r.placements.values() if p.status is not PlaceStatus.UNPLACEABLE]
    blocked = [p for p in r.placements.values() if p.status is PlaceStatus.UNPLACEABLE]
    assert len(placed) == 2 and len(blocked) == 1
    assert blocked[0].blocked_by is BlockingConstraint.CREW_UNAVAILABLE


# --------------------------------------------------------------------------- #
# The four SFRM activities from §2.4 — real data
# --------------------------------------------------------------------------- #

def _real_sfrm_pack():
    from apps.api.agent.loop import _load_activities, _load_faces, _load_thermal, ANCHOR, _horizon
    from apps.api.windows.evaluate import evaluate_window
    from apps.api.windows.registry import load_registry
    from scripts.make_ribbon_fixture import _bar, _series_for_face

    reg, faces, thermal = load_registry(), _load_faces(), _load_thermal()
    byid = {a["id"]: a for a in _load_activities()}
    pas = []
    for aid in ("A-1088", "A-1098", "A-1108", "A-1118"):
        a = byid[aid]
        wf = a["work_face_id"]
        series, ts = _series_for_face(thermal[wf], faces[wf]["surface_class"])
        ev = evaluate_window(
            trade_id=a["trade_id"], series=series, ts=ts, scheduled=_bar(a),
            activity_id=aid, activity_name=a["name"], work_face_id=wf,
            work_face_name=faces[wf]["name"], run_id="t", horizon=_horizon(), registry=reg)
        pas.append(activity_from_eval(ev, crew_size=a["crew_size"], total_float_d=a["total_float_d"]))
    return pack(pas, crew=YamlCrewSource(), anchor=ANCHOR), pas


def test_four_sfrm_activities_return_named_outcomes():
    """§2.4: SFRM's continuity_40f_24h needs a 24 h run with a 24 h lead — 48
    protected hours inside a 72 h horizon. Only the single 25 Aug window survives
    the truncation; the SFRM crew (12 heads) fits two of the four there. Every one
    of the four gets a placement with a NAMED outcome — no exception is raised."""
    result, pas = _real_sfrm_pack()
    assert len(result.placements) == 4
    for p in result.placements.values():
        if p.status is PlaceStatus.UNPLACEABLE:
            assert p.blocked_by is not None          # the constraint is always named
        else:
            assert p.start is not None and p.finish is not None
    # At least one is crew-blocked (only two crews fit the one compliant window),
    # which is the demo beat worth naming (§16.3).
    blocked = [p for p in result.unplaceable]
    assert any(p.blocked_by is BlockingConstraint.CREW_UNAVAILABLE for p in blocked)


def test_sfrm_exercises_the_horizon_truncation_path():
    """Each SFRM face carries exactly one usable interval (the 25 Aug window); the
    rest of the horizon is NO_DATA from the continuity run extending past 72 h."""
    _, pas = _real_sfrm_pack()
    for a in pas:
        assert len(a.open_intervals) == 1            # only one window survives truncation
