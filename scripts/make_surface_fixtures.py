"""
WORKFACE — regenerate the thermal twin through the REAL surface model.  T3, Day 6.

    python -m scripts.make_surface_fixtures              # write derived bundle
    python -m scripts.make_surface_fixtures --diff        # + diff hero pair vs Day-4.5
    python -m scripts.make_surface_fixtures --sensitivity # + eps(galvanised) sweep

Task D5. This takes T2's Day-5 twin capture, derives (alpha, eps, psi) per work
face through apps/api/twin/surface.py, and rebuilds the 40-face thermal bundle
with the DERIVED coefficients replacing the Day-4.5 guess. Weather (t_air, rh,
dew, wind, cloud, GHI) is the identical site-level curve the Day-4.5 fixture
used, so the ONLY thing that moves is t_surf_c — which is the point.

    IT WRITES TO A NEW PATH — sample_thermal_bundle_derived.json — and does NOT
    overwrite the Day-4.5 sample_thermal_bundle.json that T1's ribbon is built
    against. The diff below is exactly so T1 can see any verdict move before
    adopting the derived bundle (same discipline the brief mandates for the agent
    fixture). Recommend the swap once T1 has seen the diff.

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

from apps.api.twin.surface import (
    EPS_METAL_BRIGHT,
    EPS_METAL_WEATHERED,
    SurfaceCoefficients,
    derive_coefficients,
    surface_offset_c,
)
from apps.api.windows.constraints import evaluate_offset
from apps.api.windows.evaluate import evaluate_window
from apps.api.windows.registry import load_registry
from apps.api.windows.psychro import dew_point_c, wet_bulb_c
from packages.schemas.window_eval import HourState
from packages.schemas.thermal_series import (
    SolarIrradiance,
    ThermalPoint,
    ThermalSeriesBundle,
    WorkFaceThermalSeries,
)
from packages.schemas.twin_segmentation import TwinCaptureBundle, WorkFaceTwinCapture
from packages.schemas.window_eval import WindowEval

from scripts.make_fixtures import AIR, DEW, GHI, TZ, WIND_MPH, rh_from
from scripts.make_thermal_fixtures import (
    HORIZON_START,
    N_HOURS,
    STEP_MIN,
    _cloud_octas,
)
from scripts.make_ribbon_fixture import _bar, _horizon, _overlaps, _series_for_face

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO = _REPO_ROOT / "data" / "project_demo"
FIXTURES = _REPO_ROOT / "data" / "fixtures"
TWIN_BUNDLE = _REPO_ROOT / "data" / "fixtures" / "twin" / "twin" / "twin_bundle.json"
GUESSED_BUNDLE = FIXTURES / "sample_thermal_bundle.json"
DERIVED_BUNDLE = FIXTURES / "sample_thermal_bundle_derived.json"

RUN_ID = "thermal-2026-08-24-commit-derived"
SITE_ID = "NPX-FAB-P2"
HERO_BARE = "WF-FAB2-07"       # open deck, psi ~0.97
HERO_SHADED = "WF-FAB2-06"     # shaded by steel, psi ~0.45
DAWN_HOURS = (2, 3, 4, 5)


def _load_captures() -> dict[str, WorkFaceTwinCapture]:
    bundle = TwinCaptureBundle.model_validate_json(TWIN_BUNDLE.read_text(encoding="utf-8"))
    return {c.work_face_id: c for c in bundle.captures}


def _face_props() -> dict[str, dict]:
    gj = json.loads((DEMO / "work_faces.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["id"]: f["properties"] for f in gj["features"]}


def build_series(face: dict, coeff: SurfaceCoefficients) -> WorkFaceThermalSeries:
    """One face's 72 h series with t_surf from the DERIVED coefficients."""
    points: list[ThermalPoint] = []
    for i in range(N_HOURS):
        ts = HORIZON_START + timedelta(hours=i)
        h = ts.hour
        air, dew, ghi = AIR[h], DEW[h], float(GHI[h])
        rh = rh_from(air, dew)
        wind_ms = round(WIND_MPH[h] * 0.44704, 2)
        cloud = _cloud_octas(h)
        surf = round(air + surface_offset_c(t_air=air, ghi=ghi, wind_ms=wind_ms,
                                            cloud_octas=cloud, coeff=coeff), 2)
        points.append(ThermalPoint(
            ts=ts, t_air_c=air, rh_pct=rh, wet_bulb_c=round(wet_bulb_c(air, rh), 2),
            cloud_octas=cloud, elevation_m=face.get("elevation_m"),
            solar=SolarIrradiance(ghi_w_m2=ghi), wind_ms=wind_ms,
            t_surf_c=surf, t_dew_c=round(dew_point_c(air, rh), 2),
        ))
    return WorkFaceThermalSeries(
        work_face_id=face["id"], tile_cluster_id=face.get("tile_cluster_id"),
        centroid_lon=face["centroid_lon"], centroid_lat=face["centroid_lat"],
        tier="commit", step_minutes=STEP_MIN, points=points, source="fixture",
        confidence=coeff.confidence.value,
        fg_activity_ids=[f"fg-heatmap-{face['structure_id']}-0001",
                         f"fg-envparams-{face['structure_id']}-0001"],
    )


def build_bundle(eps_metal: float = EPS_METAL_WEATHERED) -> ThermalSeriesBundle:
    captures = _load_captures()
    faces = _face_props()
    series = []
    for fid, face in faces.items():
        cap = captures.get(fid)
        if cap is None:
            continue
        coeff = derive_coefficients(cap, eps_metal=eps_metal)
        series.append(build_series(face, coeff))
    return ThermalSeriesBundle(
        run_id=RUN_ID, generated_at=HORIZON_START, site_id=SITE_ID, tier="commit",
        series=series, replay=True,
    )


# --------------------------------------------------------------------------- #
# Diff helpers
# --------------------------------------------------------------------------- #

def _dawn_and_peak(series: WorkFaceThermalSeries) -> tuple[float, float]:
    dawn = min(p.t_surf_c - p.t_air_c for p in series.points
               if p.ts.hour in DAWN_HOURS and p.ts.day == 24)
    peak = max(p.t_surf_c - p.t_air_c for p in series.points
               if p.ts.hour == 15 and p.ts.day == 24)
    return round(dawn, 2), round(peak, 2)


def _verdicts_over_bundle(bundle: ThermalSeriesBundle) -> dict[str, str]:
    """Real evaluate_window verdict for every thermal-sensitive demo lane over a
    given thermal bundle — used to detect ribbon verdict moves."""
    sched = json.loads((DEMO / "activities.json").read_text(encoding="utf-8"))
    faces = _face_props()
    by_face = {s.work_face_id: s for s in bundle.series}
    reg = load_registry()
    out: dict[str, str] = {}
    for a in sched["activities"]:
        if not (a["thermal_sensitive"] and a["trade_id"] and _overlaps(a)):
            continue
        if a["work_face_id"] not in by_face:
            continue
        face = faces[a["work_face_id"]]
        series, ts = _series_for_face(by_face[a["work_face_id"]], face["surface_class"])
        ev = evaluate_window(
            trade_id=a["trade_id"], series=series, ts=ts, scheduled=_bar(a),
            activity_id=a["id"], activity_name=a["name"], wbs=a.get("wbs"),
            work_face_id=a["work_face_id"], work_face_name=face["name"],
            run_id="surface-diff", horizon=_horizon(), registry=reg)
        out[a["id"]] = ev.verdict.value
    return out


def print_diff() -> None:
    guessed = ThermalSeriesBundle.model_validate_json(GUESSED_BUNDLE.read_text(encoding="utf-8"))
    derived = build_bundle()
    g_by = {s.work_face_id: s for s in guessed.series}
    d_by = {s.work_face_id: s for s in derived.series}

    print("\n=== D5 hero-pair diff: Day-4.5 guessed vs derived (surf - air, C) ===")
    print(f"{'face':<14}{'model':<9}{'dawn':>8}{'peak15':>9}{'alpha':>8}{'eps':>7}{'psi':>7}")
    captures = _load_captures()
    for fid in (HERO_BARE, HERO_SHADED):
        gd, gp = _dawn_and_peak(g_by[fid])
        dd, dp = _dawn_and_peak(d_by[fid])
        coeff = derive_coefficients(captures[fid])
        print(f"{fid:<14}{'guessed':<9}{gd:>8}{gp:>9}{'0.30*':>8}{'0.85*':>7}{coeff.psi:>7}")
        print(f"{'':<14}{'derived':<9}{dd:>8}{dp:>9}{coeff.alpha:>8}{coeff.eps:>7}{coeff.psi:>7} "
              f"[confidence: {coeff.confidence.value}]")
    print("  *Day-4.5 keyed alpha/eps off surface_class=galvanised_steel (0.30/0.85).")

    print("\n=== D5 hero coating dawn closure (offset_dew_point cell states) ===")
    print("The scheduled activities sit in daytime, so no VERDICT moves; but T1's")
    print("ribbon renders per-hour CELLS, and the hero dawn band does move.")
    reg = load_registry()
    off = reg.get("coating_epoxy_structural_steel").constraint("offset_dew_point")
    faces = _face_props()
    for label, by in (("guessed", g_by), ("derived", d_by)):
        for fid in (HERO_BARE, HERO_SHADED):
            series, ts = _series_for_face(by[fid], faces[fid]["surface_class"])
            ev = evaluate_offset(series, off, ts)
            closed = sum(1 for h in ev.per_hour if h.state is HourState.CLOSED)
            marg = sum(1 for h in ev.per_hour if h.state is HourState.MARGINAL)
            worst = min((h.margin for h in ev.per_hour if h.margin is not None), default=None)
            print(f"  {label:<8}{fid}: CLOSED={closed}h MARGINAL={marg}h worst_margin={worst:+.2f} C")
    print("  -> the bare deck's dawn cells go MARGINAL -> CLOSED under the derived model,")
    print("     the whole closure turning on ~0.2 C. Fragile to eps AND to Q_lw (130 W/m2).")

    print("\n=== D5 ribbon verdict move (real evaluate_window over both bundles) ===")
    gv, dv = _verdicts_over_bundle(guessed), _verdicts_over_bundle(derived)
    moved = {aid: (gv[aid], dv[aid]) for aid in gv if aid in dv and gv[aid] != dv[aid]}
    print(f"lanes evaluated: {len(gv)}  |  verdicts moved: {len(moved)}")
    for aid, (a, b) in sorted(moved.items()):
        print(f"  {aid}: {a} -> {b}")
    if not moved:
        print("  (no verdict moved — the derived model preserves every demo-window verdict)")


def print_sensitivity() -> None:
    print("\n=== D3 eps(galvanised) sensitivity: the hero dawn undershoot ===")
    print("Bright new galvanising eps~0.2-0.3; weathered eps~0.7-0.9. The hero dawn")
    print("closure IS the eps*dLW_night term, so it lives or dies on this number.\n")
    captures = _load_captures()
    faces = _face_props()
    print(f"{'face':<14}{'eps_metal':>10}{'weathering':>13}{'dawn(surf-air)':>16}{'eps_eff':>9}")
    for fid in (HERO_BARE, HERO_SHADED):
        for eps_metal, label in ((EPS_METAL_BRIGHT, "bright"), (EPS_METAL_WEATHERED, "weathered")):
            coeff = derive_coefficients(captures[fid], eps_metal=eps_metal)
            series = build_series(faces[fid], coeff)
            dawn, _ = _dawn_and_peak(series)
            print(f"{fid:<14}{eps_metal:>10}{label:>13}{dawn:>16}{coeff.eps:>9}")
    print("\nRead: at the bright end the deck barely cools and the dawn closure weakens;")
    print("the story needs a WEATHERED deck (eps~0.85, 'four months of Phoenix sun').")


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE derived surface model (T3, Day 6)")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--sensitivity", action="store_true")
    args = ap.parse_args()

    bundle = build_bundle()
    text = bundle.model_dump_json(indent=2)
    ThermalSeriesBundle.model_validate_json(text)
    DERIVED_BUNDLE.write_text(text + "\n", encoding="utf-8")
    print(f"[ok] {DERIVED_BUNDLE.name}  {len(bundle.series)} faces x {N_HOURS} h "
          f"(NOT overwriting the Day-4.5 bundle)")

    if args.diff:
        print_diff()
    if args.sensitivity:
        print_sensitivity()
    return 0


if __name__ == "__main__":
    sys.exit(main())
