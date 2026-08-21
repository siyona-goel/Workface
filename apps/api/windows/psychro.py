"""
WORKFACE — psychrometrics and cure kinetics.  T3, TASK 4.

Pure functions. No classes, no I/O, full type hints. Every formula cites its
source in its docstring, and every published number is reproduced exactly by the
golden tests in tests/test_psychro.py at rel=1e-3.

THE PHYSICS NEVER GOES IN THE LLM. Dew point, wet bulb, heat index, evaporation
rate and cure integrals are plain unit-tested Python; the model only picks a
resolution strategy and writes prose. Nothing here calls an LLM.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Literal, Sequence

__all__ = [
    "dew_point_c", "wet_bulb_c", "heat_index_f",
    "evaporation_rate_lb_ft2_hr", "evaporation_verdict",
    "cure_rate", "cure_progress", "hours_to_service", "nurse_saul_maturity",
]

# Magnus-Tetens coefficients (Alduchov & Eskridge, 1996 refinement).
_MAGNUS_A = 17.625
_MAGNUS_B = 243.04


# --------------------------------------------------------------------------- #
# Dew point — Magnus-Tetens
# --------------------------------------------------------------------------- #

def dew_point_c(t_air_c: float, rh_pct: float) -> float:
    """Dew-point temperature (deg C) from air temperature and relative humidity.

    Magnus-Tetens with the Alduchov-Eskridge coefficients (a=17.625, b=243.04):

        gamma = ln(RH/100) + a*T/(b + T)
        T_dew = b*gamma / (a - gamma)

    Valid -40..+60 C. This is THE dew point the SSPC-PA 1 surface offset is
    evaluated against; never approximate it.

    Raises:
        ValueError: rh_pct <= 0 or > 100, or t_air_c outside -40..+60 C.
    """
    if not (0.0 < rh_pct <= 100.0):
        raise ValueError(f"rh_pct must be in (0, 100], got {rh_pct}")
    if not (-40.0 <= t_air_c <= 60.0):
        raise ValueError(f"t_air_c must be in [-40, 60] C, got {t_air_c}")
    gamma = math.log(rh_pct / 100.0) + _MAGNUS_A * t_air_c / (_MAGNUS_B + t_air_c)
    return _MAGNUS_B * gamma / (_MAGNUS_A - gamma)


# --------------------------------------------------------------------------- #
# Wet bulb — Stull (2011)
# --------------------------------------------------------------------------- #

def wet_bulb_c(t_air_c: float, rh_pct: float) -> float:
    """Wet-bulb temperature (deg C), Stull (2011) empirical fit.

    Stull, R. (2011), "Wet-Bulb Temperature from Relative Humidity and Air
    Temperature", J. Applied Meteorology and Climatology 50(11):2267-2269:

        Tw = T*atan(0.151977*sqrt(RH + 8.313659)) + atan(T + RH)
             - atan(RH - 1.676331) + 0.00391838*RH^1.5*atan(0.023101*RH)
             - 4.686035

    Approximation, +/-1 C, valid RH 5-99 %, T -20..+50 C. Used ONLY as a fallback
    where FortyGuard's env_params.wet_bulb_temperature_celsius is unavailable.
    """
    rh = rh_pct
    return (
        t_air_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t_air_c + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
        - 4.686035
    )


# --------------------------------------------------------------------------- #
# Heat index — NWS Rothfusz regression
# --------------------------------------------------------------------------- #

def heat_index_f(t_air_f: float, rh_pct: float) -> float:
    """NWS heat index (deg F) from air temperature (deg F) and RH (%).

    NWS Weather Prediction Center algorithm. A simple Steadman estimate is
    computed and averaged with the air temperature; if that average is below
    80 F it is returned, otherwise the full Rothfusz regression is applied with
    the two adjustments:
      * RH < 13 % and 80 <= T <= 112 F  -> subtract a low-humidity correction
      * RH > 85 % and 80 <= T <=  87 F  -> add a high-humidity correction

    This is what the OSHA triggers (80 F initial / 90 F high heat) are evaluated
    against.
    """
    t, rh = t_air_f, rh_pct
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    hi = (simple + t) / 2.0
    if hi < 80.0:
        return hi
    hi = (
        -42.379 + 2.04901523 * t + 10.14333127 * rh
        - 0.22475541 * t * rh - 6.83783e-3 * t * t - 5.481717e-2 * rh * rh
        + 1.22874e-3 * t * t * rh + 8.5282e-4 * t * rh * rh
        - 1.99e-6 * t * t * rh * rh
    )
    if rh < 13.0 and 80.0 <= t <= 112.0:
        hi -= ((13.0 - rh) / 4.0) * math.sqrt((17.0 - abs(t - 95.0)) / 17.0)
    elif rh > 85.0 and 80.0 <= t <= 87.0:
        hi += ((rh - 85.0) / 10.0) * ((87.0 - t) / 5.0)
    return hi


# --------------------------------------------------------------------------- #
# Evaporation rate — Menzel / NRMCA (the ACI 305 nomograph as an equation)
# --------------------------------------------------------------------------- #

def evaporation_rate_lb_ft2_hr(tc_f: float, ta_f: float, rh_pct: float, wind_mph: float) -> float:
    """Surface evaporation rate of bleed water, lb/ft^2/hr (Menzel / NRMCA form).

        E = (Tc^2.5 - r * Ta^2.5) * (1 + 0.4 * V) * 1e-6

    Tc = concrete surface temperature (deg F), Ta = air temperature (deg F),
    r = RH/100, V = wind speed (mph). This is the algebraic form of the ACI 305
    nomograph. ACI 305 defines hot weather as "any combination of high air
    temperature, low relative humidity, wind, and solar radiation" — NOT a
    temperature — which is exactly why a cold, dry, windy morning can beat a hot,
    calm afternoon here.
    """
    r = rh_pct / 100.0
    return (tc_f ** 2.5 - r * ta_f ** 2.5) * (1.0 + 0.4 * wind_mph) * 1e-6


def evaporation_verdict(e: float, low_bleed: bool = False) -> Literal["not_anticipated", "possible", "expected"]:
    """Map an evaporation rate to the ACI 305 precaution bands.

    Conventional concrete: precautions expected at 0.2 lb/ft^2/hr, possible from
    0.1. Low-bleed mixes (Type 1L blended cements) drop the limit to 0.1, and the
    "possible" band with it (0.05..0.1). Fail-safe: exactly on a boundary reads as
    the more cautious band.
    """
    limit = 0.1 if low_bleed else 0.2
    possible = limit / 2.0
    if e >= limit:
        return "expected"
    if e >= possible:
        return "possible"
    return "not_anticipated"


# --------------------------------------------------------------------------- #
# Cure kinetics — piecewise Q10 (ASTM-style rate model)
# --------------------------------------------------------------------------- #

def _seg_field(seg: Any, name: str) -> float:
    """Read a q10-segment field from either a dict or a pydantic model."""
    return seg[name] if isinstance(seg, dict) else getattr(seg, name)


def cure_rate(t_c: float, q10_segments: Sequence[Any], ref_c: float) -> float:
    """Relative cure rate at temperature t_c, integrated across the Q10 segments.

        rate(T) = exp( integral_ref^T  ln(q10(x))/10  dx )

    so rate(ref) = 1 and the local Q10 changes at each segment boundary. For
    Macropoxy 646 the registry gives q10=1.17 below 25 C and q10=1.55 above: the
    epoxy accelerates MORE per 10 C once it is warm, and stalls disproportionately
    near its minimum application temperature. That is a real observation, not a
    modelling convenience.
    """
    lo, hi = min(ref_c, t_c), max(ref_c, t_c)
    ln_total = 0.0
    for seg in q10_segments:
        a = max(lo, _seg_field(seg, "t_lo_c"))
        b = min(hi, _seg_field(seg, "t_hi_c"))
        if b > a:
            ln_total += (b - a) * math.log(_seg_field(seg, "q10")) / 10.0
    if t_c < ref_c:
        ln_total = -ln_total
    return math.exp(ln_total)


def cure_progress(series: Iterable[tuple[float, float]], q10_segments: Sequence[Any],
                  hours_at_ref: float, ref_c: float) -> float:
    """Fraction of cure accumulated over a temperature history.

        progress = sum( rate(T_i) * dt_i ) / hours_at_ref        cured iff >= 1

    `series` is an iterable of (temperature_C, dt_hours) samples. `hours_at_ref`
    is the manufacturer's cure duration at the reference temperature (168 h to
    service for Macropoxy 646 at 25 C).
    """
    equiv = sum(cure_rate(t_c, q10_segments, ref_c) * dt for t_c, dt in series)
    return equiv / hours_at_ref


def hours_to_service(base_t_c: float, q10_segments: Sequence[Any],
                     hours_at_ref: float, ref_c: float) -> float:
    """Cure-to-service hours at a CONSTANT base temperature.

        H(T) = hours_at_ref / rate(T)

    The inverse of cure_progress for an isothermal cure; used to plot the Q10 fit
    against the manufacturer's published cure-schedule points.
    """
    return hours_at_ref / cure_rate(base_t_c, q10_segments, ref_c)


def nurse_saul_maturity(series: Iterable[tuple[float, float]], t0_c: float = -10.0) -> float:
    """Nurse-Saul maturity index (deg C * h), ASTM C1074.

        M = sum( (T_i - T_0) * dt_i ),   T_0 = -10 C datum

    `series` is an iterable of (temperature_C, dt_hours). Contributions below the
    datum are negative (no maturity gained), consistent with ASTM C1074.
    """
    return sum((t_c - t0_c) * dt for t_c, dt in series)
