"""
WORKFACE — the synthetic thermal twin: one series per work face.  T3, Day 4.5.

    python -m scripts.make_thermal_fixtures            # writes data/fixtures/*.json
    python -m scripts.make_thermal_fixtures --check    # write + validate + summary

Why this exists
---------------
`evaluate_window` takes a `list[SeriesPoint]`. To regenerate T1's ribbon from the
REAL evaluators (Day 4.5) instead of hand-drawn states, every work face the demo
window touches needs an honest thermal series. This produces all 40 faces of the
synthetic project as a `ThermalSeriesBundle`, over the 72 h demo window
(24-27 Aug 2026), one `WorkFaceThermalSeries` each.

This is a FIXTURE generator. It lives with the other fixture generators, NOT in
`apps/api/twin/` (T2's live-capture path).

What is site-level vs per-face
------------------------------
Site-level (identical for every face): `t_air_c`, `rh_pct`, `t_dew_c`, `wind_ms`,
`cloud_octas`, clear-sky `ghi_w_m2`. The air curve is lifted UNCHANGED from the
Day-1 drivers so the weather story — and `test_fixtures.py`'s 05:00=29 C /
15:00=42 C assertions — survive; it is simply extended from 48 h to 72 h.

Per-face (DERIVED, never assigned): `t_surf_c` and `t_base_material_c`, from the
work face's `sky_view_factor`, `surface_class` and `exposure_class`. This is the
first-order surface energy balance published in WORKFACE_TECH_SPEC.md §6.2:

    t_surf = t_air + (alpha*GHI - eps*Q_lw*(1 - cloud/8)) * psi / (h_c(V) + h_r)
    h_c(V) = 5.7 + 3.8*V   (V m/s)      h_r = 5 W/m2K

Both the solar gain and the night-time longwave loss scale with the sky view
factor `psi`, so an open deck (psi 0.97) both heats hardest in sun AND sheds heat
fastest to a clear desert sky — dropping BELOW air by dawn, which is what
collapses `t_surf - t_dew` through the coating's 2.8 C offset. Under steel shading
(psi 0.45) the deck sees less than half the sky and holds above the offset. Same
coating, same weather, 187.5 m apart. The model is given honest inputs and left to
speak; if the contrast were absent it would be reported, not forced.

Coefficient sources are cited in the constants below and in docs/CITATIONS.md.

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

from apps.api.windows.psychro import dew_point_c, wet_bulb_c
from packages.schemas.thermal_series import (
    SolarIrradiance,
    ThermalPoint,
    ThermalSeriesBundle,
    WorkFaceThermalSeries,
)

# The Day-1 diurnal drivers live in make_fixtures; lift them unchanged (A1).
from scripts.make_fixtures import AIR, DEW, GHI, TZ, WIND_MPH, rh_from

HORIZON_START = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)     # demo_window.start
N_HOURS = 72                                               # 24 Aug 00:00 -> 27 Aug 00:00
STEP_MIN = 60
RUN_ID = "thermal-2026-08-24-commit"
SITE_ID = "NPX-FAB-P2"
SEED = 20260820                                            # stats.json seed (kept for provenance)

_REPO_ROOT = Path(__file__).resolve().parents[1]
WORK_FACES_PATH = _REPO_ROOT / "data" / "project_demo" / "work_faces.geojson"

# --------------------------------------------------------------------------- #
# Surface-twin coefficients — published ranges, cited in docs/CITATIONS.md.
# Day 10: ASSUMPTIONS.md — the assumptions page scrapes these.
# --------------------------------------------------------------------------- #

# Solar absorptivity (shortwave), WORKFACE_TECH_SPEC.md §6.2 / ASHRAE Fundamentals
# ch. 26 surface-property tables. Bright galvanised steel is a LOW absorber (~0.3);
# it runs hot not by absorbing much but by having almost no thermal mass to buffer.
K_ABSORB = {
    "asphalt": 0.90,
    "bare_concrete": 0.60,
    "cmu_masonry": 0.55,
    "coated_steel": 0.45,
    "galvanised_steel": 0.30,
}
# Thermal (longwave) emissivity. Weathered/erected galvanised steel oxidises to a
# high-emissivity surface (~0.85), which is why an open steel deck radiates hard to
# a clear night sky. ASHRAE Fundamentals ch. 26; Engineering Toolbox emissivity tables.
K_EMIT = {
    "asphalt": 0.93,
    "bare_concrete": 0.90,
    "cmu_masonry": 0.90,
    "coated_steel": 0.88,
    "galvanised_steel": 0.85,
}
# Substrate thermal-mass damping: the fraction of the (surface - air) swing the
# material the trade actually touches sees. Thin steel tracks its surface (1.0);
# a massive concrete slab or asphalt base is buffered toward air. This is an
# amplitude damping standing in for thermal lag — stated as a simplification.
K_MASS_DAMP = {
    "asphalt": 0.70,
    "bare_concrete": 0.65,
    "cmu_masonry": 0.65,
    "coated_steel": 1.0,
    "galvanised_steel": 1.0,
}

# Clear-sky net longwave loss flux, W/m2. Net radiative loss from a horizontal
# high-emissivity surface under a clear, dry desert sky. Arid-climate radiative-
# cooling literature reports ~90-150 W/m2 for such surfaces on clear nights
# (e.g. daytime-radiative-cooling and passive-cooling studies); 130 is a mid-upper
# value. The hero closure sits on the upper half of this range — see the report's
# sensitivity note.
Q_LW_CLEAR_W_M2 = 130.0
H_C_A, H_C_B = 5.7, 3.8      # convective coefficient 5.7 + 3.8*V (WORKFACE_TECH_SPEC §6.2)
H_R = 5.0                    # linearised radiative coefficient, W/m2K


def _cloud_octas(h: int) -> float:
    """Daytime fair-weather cumulus; clear nights (why radiative cooling wins)."""
    return 2.0 if 5 <= h <= 18 else 0.0


def _surface_offset(surface_class: str, sky_view_factor: float, ghi: float,
                    wind_ms: float, cloud_octas: float) -> float:
    alpha = K_ABSORB.get(surface_class, 0.60)
    eps = K_EMIT.get(surface_class, 0.90)
    h_c = H_C_A + H_C_B * max(0.0, wind_ms)
    net_flux = alpha * ghi - eps * Q_LW_CLEAR_W_M2 * (1.0 - cloud_octas / 8.0)
    return net_flux * sky_view_factor / (h_c + H_R)


def base_material_c(surface_class: str, t_surf_c: float, t_air_c: float) -> float:
    """The substrate the trade touches, damped from the surface by thermal mass.

    `t_base_material_c` is a `SeriesPoint` field, not a `ThermalPoint` field, so the
    ribbon builder calls this when it maps a thermal point to a SeriesPoint. Thin
    steel tracks its surface; a massive slab is buffered toward air.
    """
    return round(t_air_c + K_MASS_DAMP.get(surface_class, 0.7) * (t_surf_c - t_air_c), 2)


def _load_work_faces() -> list[dict]:
    gj = json.loads(WORK_FACES_PATH.read_text(encoding="utf-8"))
    return [f["properties"] for f in gj["features"]]


def build_series(face: dict) -> WorkFaceThermalSeries:
    sc = face["surface_class"]
    svf = float(face["sky_view_factor"])
    points: list[ThermalPoint] = []
    for i in range(N_HOURS):
        ts = HORIZON_START + timedelta(hours=i)
        h = ts.hour
        air, dew, ghi = AIR[h], DEW[h], float(GHI[h])
        rh = rh_from(air, dew)
        wind_ms = round(WIND_MPH[h] * 0.44704, 2)
        cloud = _cloud_octas(h)
        surf = round(air + _surface_offset(sc, svf, ghi, wind_ms, cloud), 2)
        points.append(ThermalPoint(
            ts=ts,
            t_air_c=air,
            rh_pct=rh,
            wet_bulb_c=round(wet_bulb_c(air, rh), 2),
            cloud_octas=cloud,
            elevation_m=face.get("elevation_m"),
            solar=SolarIrradiance(ghi_w_m2=ghi),
            wind_ms=wind_ms,
            t_surf_c=surf,
            t_dew_c=round(dew_point_c(air, rh), 2),
            # t_base_material_c is a SeriesPoint field, derived at ribbon-build time.
            # wbgt_c left null on purpose: the human evaluator models it and marks it.
        ))
    return WorkFaceThermalSeries(
        work_face_id=face["id"],
        tile_cluster_id=None,
        centroid_lon=face["centroid_lon"],
        centroid_lat=face["centroid_lat"],
        tier="commit",
        step_minutes=STEP_MIN,
        points=points,
        source="fixture",
        confidence="high",
        fg_activity_ids=[f"fg-heatmap-{face['structure_id']}-0001",
                         f"fg-envparams-{face['structure_id']}-0001"],
    )


def build_bundle() -> ThermalSeriesBundle:
    faces = _load_work_faces()
    return ThermalSeriesBundle(
        run_id=RUN_ID,
        generated_at=HORIZON_START,
        site_id=SITE_ID,
        tier="commit",
        series=[build_series(f) for f in faces],
        replay=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE thermal twin fixtures (T3, Day 4.5)")
    ap.add_argument("--out", default="data/fixtures", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    bundle = build_bundle()
    text = bundle.model_dump_json(indent=2)
    ThermalSeriesBundle.model_validate_json(text)                 # must not raise
    (args.out / "sample_thermal_bundle.json").write_text(text + "\n", encoding="utf-8")

    # sample_thermal_series.json is the WF-FAB2-11 slice of the SAME code (A3).
    wf11 = next(s for s in bundle.series if s.work_face_id == "WF-FAB2-11")
    wf11_text = wf11.model_dump_json(indent=2)
    WorkFaceThermalSeries.model_validate_json(wf11_text)
    (args.out / "sample_thermal_series.json").write_text(wf11_text + "\n", encoding="utf-8")

    print(f"[ok] sample_thermal_bundle.json  {len(bundle.series)} faces x {N_HOURS} h")
    print(f"[ok] sample_thermal_series.json  WF-FAB2-11 slice, {len(wf11.points)} points")
    if args.check:
        # Hero pair: the bare deck must cool further at dawn than the shaded one.
        bare = next(s for s in bundle.series if s.work_face_id == "WF-FAB2-07")
        shaded = next(s for s in bundle.series if s.work_face_id == "WF-FAB2-06")
        def dawn_min(s):
            return min(p.t_surf_c - p.t_air_c for p in s.points if p.ts.hour in (2, 3, 4, 5))
        assert dawn_min(bare) < dawn_min(shaded), "hero contrast absent"
        assert len(bundle.series) == 40
        p05 = next(p for p in wf11.points if p.ts.hour == 5 and p.ts.day == 24)
        p15 = next(p for p in wf11.points if p.ts.hour == 15 and p.ts.day == 24)
        assert p05.t_air_c == 29.0 and p15.t_air_c == 42.0, "air curve moved"
        print(f"[ok] hero dawn undershoot: bare {dawn_min(bare):+.1f} C vs shaded {dawn_min(shaded):+.1f} C")
        print("[ok] --check assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
