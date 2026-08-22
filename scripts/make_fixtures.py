"""
WORKFACE — Day-1 diurnal drivers + the cure-fit data artifact.  T3.

    python -m scripts.make_fixtures            # writes data/fixtures/cure_fit_macropoxy646.json

History
-------
Through Day 4 this module ALSO hand-fabricated the window-eval fixtures — it drew
per-hour states directly instead of calling the evaluators, because on Day 1 the
evaluators did not exist. On Day 4.5 that fabrication path was deleted: the ribbon
and hero fixtures are now produced by `scripts/make_ribbon_fixture.py` from the
real `evaluate_window`, and the thermal twin by `scripts/make_thermal_fixtures.py`.
A fabricated verdict is a loaded gun once the real path works, so it is gone.

What remains here:
  * the Phoenix late-August diurnal driver arrays (hour-of-day 0..23), still used
    as hand-worked inputs by the Day-4 evaluator unit tests;
  * `build_cure_fit()`, the piecewise-Q10 model vs the Macropoxy 646 PDS cure
    table — a genuine data artifact (T1 plots it), computed from the registry.

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
from datetime import timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=-7.0))            # America/Phoenix, no DST, ever.

# --------------------------------------------------------------------------- #
# Diurnal driver arrays, hour-of-day 0..23. Hand-tuned to the Phoenix monsoon
# story. Site-level air/dew/wind/GHI are lifted UNCHANGED into
# make_thermal_fixtures.py (which extends them to 72 h); SURF_BARE is the Day-1
# hand surface, retained ONLY as a convenient input for the Day-4 evaluator unit
# tests — the real per-face surface twin is derived in make_thermal_fixtures.py.
# --------------------------------------------------------------------------- #

#            00    01    02    03    04    05    06    07    08    09    10    11
#            12    13    14    15    16    17    18    19    20    21    22    23
AIR = [      34.0, 33.0, 32.0, 31.0, 30.0, 29.0, 30.0, 32.0, 34.5, 36.5, 38.0, 39.5,
             40.5, 41.3, 41.8, 42.0, 41.5, 40.5, 39.0, 37.5, 36.0, 35.0, 34.0, 33.0]
DEW = [      18.8, 19.2, 19.5, 19.6, 19.4, 19.0, 18.7, 18.4, 18.1, 17.8, 17.5, 17.3,
             17.1, 17.0, 17.0, 17.0, 17.2, 17.5, 17.8, 18.1, 18.4, 18.6, 18.7, 18.8]
# Bare open deck (Day-1 hand array): condensation trough 02:00-04:00, solar-loaded midday.
SURF_BARE = [23.0, 22.0, 21.8, 21.5, 22.6, 24.5, 29.0, 34.0, 39.5, 44.5, 49.0, 53.5,
             56.5, 58.3, 59.8, 60.0, 57.5, 52.5, 46.0, 40.5, 35.0, 31.0, 27.0, 24.0]
# Site wind, mph — light and calm overnight (why radiative cooling wins), breezy pm.
WIND_MPH = [4.0, 3.5, 2.5, 2.0, 2.0, 2.5, 3.5, 5.0, 6.5, 8.0, 9.5, 11.0,
            12.0, 12.5, 13.0, 13.0, 12.0, 10.5, 9.0, 7.5, 6.0, 5.0, 4.5, 4.0]
# Global horizontal irradiance, W/m2 — 0 at night, bell through the day.
GHI = [0, 0, 0, 0, 0, 30, 160, 360, 560, 720, 850, 940,
       985, 980, 915, 800, 640, 440, 230, 60, 0, 0, 0, 0]


def rh_from(t_air: float, t_dew: float) -> float:
    """Relative humidity implied by air and dew point (inverse Magnus-Tetens).

    Keeps rh_pct internally consistent with t_dew rather than a third free array.
    """
    import math
    a, b = 17.625, 243.04
    gamma_dew = a * t_dew / (b + t_dew)
    gamma_air = a * t_air / (b + t_air)
    return round(min(100.0, max(0.0, 100.0 * math.exp(gamma_dew - gamma_air))), 1)


# --------------------------------------------------------------------------- #
# The cure-fit data artifact — the piecewise-Q10 model vs the Macropoxy 646 PDS.
# --------------------------------------------------------------------------- #

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
    ap = argparse.ArgumentParser(description="WORKFACE cure-fit data artifact (T3)")
    ap.add_argument("--out", default="data/fixtures", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cure_fit_macropoxy646.json").write_text(
        json.dumps(build_cure_fit(), indent=2) + "\n", encoding="utf-8")
    print("[ok] cure_fit_macropoxy646.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
