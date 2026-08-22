"""
WORKFACE — regenerate the ribbon from the REAL evaluator.  T3, Day 4.5.

    python -m scripts.make_ribbon_fixture            # writes data/fixtures/*.json
    python -m scripts.make_ribbon_fixture --check    # write + validate + summary

The fabrication path is dead. Every state, margin, reason, interval and verdict in
`sample_window_eval_ribbon.json` and `sample_window_eval.json` is now the output of
`evaluate_window` — unit-tested physics — run against a schedule row that exists in
`data/project_demo/activities.json`, over the synthetic thermal twin in
`sample_thermal_bundle.json`. Re-running reproduces the fixtures byte-for-byte.

Provenance: seed 20260820 (stats.json), thermal bundle run `thermal-2026-08-24-commit`.

Lanes (38 across 9 trades):
  * every activity overlapping stats.demo_window with thermal_sensitive == true and a
    non-null trade_id — 37 lanes, each on its own work face's series;
  * one site-wide `crew_heat_exposure` lane (SITE-CREW-HEAT), which is NOT a schedule
    row and must be rendered by T1 as a site lane, not an activity row. It closes the
    `human` evaluator gap honestly: heat stress applies to every crew every hour and
    can never return CLOSED.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from apps.api.windows.evaluate import evaluate_window
from apps.api.windows.registry import load_registry
from packages.schemas.thermal_series import ThermalSeriesBundle, WorkFaceThermalSeries
from packages.schemas.window_eval import (
    Horizon,
    ScheduledBar,
    SeriesPoint,
    UsdExposure,
    WindowEval,
    WindowEvalBundle,
)

from scripts.make_thermal_fixtures import TZ, base_material_c

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO = _REPO_ROOT / "data" / "project_demo"
FIXTURES = _REPO_ROOT / "data" / "fixtures"

HORIZON_START = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)
HORIZON_END = datetime(2026, 8, 27, 0, 0, tzinfo=TZ)          # stats.demo_window
STEP_MIN = 60
RUN_ID = "ribbon-2026-08-24-commit"                          # deterministic; provenance in the docstring
SITE_CREW_LANE_ID = "SITE-CREW-HEAT"
HERO_ACTIVITY_ID = "A-1069"                                  # bare deck WF-FAB2-07, 25 Aug

# Placeholder site crew-capacity proxy: the demo site is taken to concurrently staff
# this many trade crews. Contended hours are those whose simultaneous open-and-
# scheduled demand exceeds it. A real capacity model is the sequencer's job (Day 7).
SITE_CREW_CAPACITY = 8


def _load(name: str) -> dict:
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def _overlaps(a: dict) -> bool:
    s = datetime.fromisoformat(a["planned_start"])
    f = datetime.fromisoformat(a["planned_finish"])
    return s < HORIZON_END and f > HORIZON_START


def _series_for_face(face_series: WorkFaceThermalSeries, surface_class: str
                     ) -> tuple[list[SeriesPoint], list[datetime]]:
    """Map a WorkFaceThermalSeries to (list[SeriesPoint], ts), deriving base material."""
    series: list[SeriesPoint] = []
    ts: list[datetime] = []
    for p in face_series.points:
        base = (base_material_c(surface_class, p.t_surf_c, p.t_air_c)
                if p.t_surf_c is not None and p.t_air_c is not None else None)
        series.append(SeriesPoint(
            t_air_c=p.t_air_c, t_surf_c=p.t_surf_c, t_dew_c=p.t_dew_c,
            t_base_material_c=base, rh_pct=p.rh_pct, wbgt_c=p.wbgt_c,
            wind_ms=p.wind_ms, ghi_w_m2=p.solar.ghi_w_m2, cloud_octas=p.cloud_octas,
        ))
        ts.append(p.ts)
    return series, ts


def _bar(a: dict) -> ScheduledBar:
    return ScheduledBar(
        start=datetime.fromisoformat(a["planned_start"]),
        finish=datetime.fromisoformat(a["planned_finish"]),
        duration_h=a["duration_h"],
        total_float_d=a["total_float_d"],
        is_critical=a["is_critical"],
        is_near_critical=a["is_near_critical"],
        milestone_date=datetime.fromisoformat(a["milestone_date"]) if a.get("milestone_date") else None,
        hold_point=a.get("hold_point"),
        crew_size=a.get("crew_size"),
    )


def _horizon() -> Horizon:
    return Horizon(start=HORIZON_START, end=HORIZON_END, step_minutes=STEP_MIN, tier="commit")


def build_bundle() -> WindowEvalBundle:
    sched = _load("activities.json")
    faces = {f["properties"]["id"]: f["properties"]
             for f in _load("work_faces.geojson")["features"]}
    bundle = ThermalSeriesBundle.model_validate_json(
        (FIXTURES / "sample_thermal_bundle.json").read_text(encoding="utf-8"))
    series_by_face = {s.work_face_id: s for s in bundle.series}
    reg = load_registry()

    evals: list[WindowEval] = []
    lanes = [a for a in sched["activities"]
             if a["thermal_sensitive"] and a["trade_id"] and _overlaps(a)]
    for a in lanes:
        face = faces[a["work_face_id"]]
        series, ts = _series_for_face(series_by_face[a["work_face_id"]], face["surface_class"])
        evals.append(evaluate_window(
            trade_id=a["trade_id"], series=series, ts=ts, scheduled=_bar(a),
            activity_id=a["id"], activity_name=a["name"], wbs=a.get("wbs"),
            work_face_id=a["work_face_id"], work_face_name=face["name"],
            run_id=RUN_ID, horizon=_horizon(),
            fg_activity_ids=series_by_face[a["work_face_id"]].fg_activity_ids, registry=reg))

    # The site-wide crew-heat lane — closes the `human` gap honestly (§5).
    hero_face = faces["WF-FAB2-07"]
    site_series, site_ts = _series_for_face(series_by_face["WF-FAB2-07"], hero_face["surface_class"])
    site_bar = ScheduledBar(start=HORIZON_START, finish=HORIZON_END, duration_h=72.0,
                            total_float_d=999.0, is_critical=False, is_near_critical=False)
    evals.append(evaluate_window(
        trade_id="crew_heat_exposure", series=site_series, ts=site_ts, scheduled=site_bar,
        activity_id=SITE_CREW_LANE_ID, activity_name="Site-wide crew heat exposure (all crews)",
        work_face_id="SITE", work_face_name="Site-wide", run_id=RUN_ID, horizon=_horizon(),
        registry=reg))

    contended = _contended_hours(evals)
    totals = UsdExposure(
        at_risk_usd=round(sum(e.usd_exposure.at_risk_usd for e in evals), 0),
        protected_usd=round(sum(e.usd_exposure.protected_usd for e in evals), 0),
        basis="sum of per-lane usd_exposure across the demo-window lanes (evaluator output; "
              "quantities are registry typical_quantity, not per-activity)")

    return WindowEvalBundle(
        run_id=RUN_ID, generated_at=HORIZON_START, horizon=_horizon(),
        site_id=sched["project_id"], evaluations=evals,
        contended_hours=contended, totals=totals)


def _contended_hours(evals: list[WindowEval]) -> list[datetime]:
    """Hours whose simultaneous open-and-scheduled demand exceeds the crew capacity
    proxy. Excludes the site-wide crew lane (it is not an activity competing for crews)."""
    activity_evals = [e for e in evals if e.activity_id != SITE_CREW_LANE_ID]
    demand: dict[datetime, int] = {}
    for e in activity_evals:
        for c in e.hours:
            if c.state.value == "open" and e.scheduled.start <= c.ts < e.scheduled.finish:
                demand[c.ts] = demand.get(c.ts, 0) + 1
    return sorted(t for t, n in demand.items() if n > SITE_CREW_CAPACITY)


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE ribbon from the real evaluator (T3, Day 4.5)")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    bundle = build_bundle()
    text = bundle.model_dump_json(indent=2)
    WindowEvalBundle.model_validate_json(text)
    (FIXTURES / "sample_window_eval_ribbon.json").write_text(text + "\n", encoding="utf-8")

    hero = next(e for e in bundle.evaluations if e.activity_id == HERO_ACTIVITY_ID)
    hero_text = hero.model_dump_json(indent=2)
    WindowEval.model_validate_json(hero_text)
    (FIXTURES / "sample_window_eval.json").write_text(hero_text + "\n", encoding="utf-8")

    trades = {e.trade_id for e in bundle.evaluations}
    print(f"[ok] sample_window_eval_ribbon.json  {len(bundle.evaluations)} lanes, "
          f"{len(trades)} trades, {len(bundle.contended_hours)} contended hours")
    print(f"[ok] sample_window_eval.json         hero {hero.activity_id} verdict={hero.verdict.value} "
          f"binding={hero.binding_constraint.constraint_id if hero.binding_constraint else None}")
    if args.check:
        assert len(bundle.evaluations) == 38, len(bundle.evaluations)
        assert len(trades) == 9, sorted(trades)
        assert all(HORIZON_START <= t < HORIZON_END for t in bundle.contended_hours)
        print("[ok] --check assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
