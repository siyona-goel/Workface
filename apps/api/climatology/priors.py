"""
WORKFACE — climatology / Tier-0 window priors.  T3, Day 5.

    from apps.api.climatology.priors import build_priors, summarize, face_tile_map
    priors = build_priors()                       # list[ClimatologyPrior], cached
    face_tile_map()["WF-FAB2-07"]                 # -> "AOI-FAB2-r00c07"
    summarize("AOI-FAB2-r00c07", "concrete_cip_hot_weather")   # -> TradePriorSummary

Handoff #3 (T2 -> T3): the raw 7-year August heatmap sweep
(`data/fixtures/historical/sweep_bundle.json`) aggregated into per-tile,
per-trade, per-hour window priors in the `climatology_prior` shape of
`apps/api/db/migrations/001_init.sql`.

A Tier-0 prior is a PROBABILITY, NOT A FORECAST (WORKFACE_TECH_SPEC §1.4 /
Day-4 hard rule 8). Every field, docstring and formatted sentence says so; the
number never escapes without that label.

WHAT THE SWEEP ACTUALLY SUPPORTS (verify against manifest.json, do not assume)
-----------------------------------------------------------------------------
The manifest lists 13 registry thresholds; only TWO were swept — 35.0 C and
4.0 C — so exactly three registry constraints have a real Tier-0 prior:

    exceedance above 35.0 C  -> concrete_cip_hot_weather / band_concrete_discharge_max
    exceedance below  4.0 C  -> concrete_cip_cold_weather / band_cold_weather_trigger
    persistence below 4.0 C  -> sfrm_spray_applied_fireproofing / continuity_40f_24h

The third is the clean one: `persistence` returns a RUN LENGTH and `continuity`
is the only evaluator that asks a run-length question — the same question asked
by the data source and the registry. Say that on stage.

Every OTHER trade gets `p_open = None` and `coverage = "insufficient_threshold"`,
naming the Celsius threshold that a future sweep would need. No interpolation, no
nearest-threshold substitution, no dew-point proxy off air temperature (Day-4
hard rule 6: fail closed, never guess).

THE 35 TRAP (WORKFACE_T3_DAY56 §2.2)
------------------------------------
`coating_epoxy_structural_steel` carries `t_min_f = 35` (= 1.7 C). The sweep's 35
is CELSIUS. Joining a `_f` registry field to a `_c` sweep threshold produces a
prior wrong by 33 degrees while looking plausible. `_binding_threshold_c` reads
Celsius fields ONLY and never a `_f` field; `tests/test_priors.py` fails if that
ever changes.

HOUR-OF-DAY IS MODELLED, AND LABELLED SO (WORKFACE_T3_DAY56 §2.3)
----------------------------------------------------------------
`stats` is null on all 140 windows and `TileReading.hourly_tcm_c` is populated on
0 of 8,232 tiles, so the *timing* of the hot band is not observable — only the
monthly *count* is. For the hot ceiling we take the deterministic diurnal shape
from `scripts.make_fixtures.AIR`, solve a single per-year vertical offset so its
hours-above-35 match that tile-year's observed exceedance count, and read the
crossing hours off the calibrated curve. The COUNT is observed; the TIMING is
modelled. Every such row carries `hour_of_day_source = "modelled"` and it is
surfaced in the formatter, never dropped in a summary.

    ESCALATION TO T2: `TileReading.hourly_tcm_c` is in the schema and is empty on
    every tile; populating it on the next sweep converts every modelled opening
    hour into an observed one. The schema already anticipated this.

WHY `median_peak_c` IS None EVERYWHERE
--------------------------------------
The sweep captured only exceedance/persistence COUNTS — no temperature
magnitude (`stats` null, `hourly_tcm_c` empty). A tile's August peak would
require inventing the diurnal AMPLITUDE (peak = trough + swing), which §A2
forbids ("None is an acceptable answer here and a fabricated number is not").
Modelling the crossing TIMING off a fixed shape is sanctioned by §2.3; inventing
a magnitude is not. So `median_peak_c` is None on every row, with the same one-
line ask to T2 (populate `hourly_tcm_c`) as the fix.

WHAT IS NOT HERE
----------------
No Tier-0 prior for the coating hero constraint (`offset_dew_point`): the sweep
has no humidity and no dew point anywhere, so it cannot exist from this data and
is NOT proxied off air temperature. Known limitation for the assumptions page.

Stdlib + pydantic only; no numpy.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import math
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from apps.api.windows.registry import Registry, load_registry
from packages.schemas.historical_readings import HistoricalSweepBundle
from packages.schemas.trade_window import BandSpec, ContinuitySpec

# apps/api/climatology/priors.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
SWEEP_PATH = _REPO_ROOT / "data" / "fixtures" / "historical" / "sweep_bundle.json"
ASSIGNMENTS_PATH = _REPO_ROOT / "data" / "aoi" / "assignments.json"
WORK_FACES_PATH = _REPO_ROOT / "data" / "project_demo" / "work_faces.geojson"

MONTH = 8                       # the August climatology window
N_DAYS = 31                     # days in August; window_hours = N_DAYS * 24
WINDOW_HOURS = N_DAYS * 24

# The two thresholds actually captured (verified against the sweep, not assumed).
CEILING_C = 35.0
FLOOR_C = 4.0

# The diurnal SHAPE used only to place the modelled hot band. This is the same
# published deterministic curve the thermal fixtures use; we calibrate its
# vertical offset per tile-year, never its amplitude. Cited in docs/CITATIONS.md.
from scripts.make_fixtures import AIR as _DIURNAL  # noqa: E402  (shape, not data)

DIURNAL_SHAPE_REF = "scripts.make_fixtures.AIR (deterministic Phoenix-August diurnal)"


class Coverage(str, Enum):
    """How a prior's p_open was obtained. The number never escapes without it."""
    OBSERVED = "observed"                        # floor rate straight from the counts
    MODELLED_HOUR = "modelled_hour"              # hot band placed on a modelled diurnal
    INSUFFICIENT_THRESHOLD = "insufficient_threshold"  # threshold never swept


class HourSource(str, Enum):
    MODELLED = "modelled"      # crossing hours read off the calibrated diurnal
    OBSERVED = "observed"      # monthly rate, not differentiated by hour of day
    NONE = "none"              # no prior


# --------------------------------------------------------------------------- #
# The persisted row: the `climatology_prior` shape of 001_init.sql, plus the two
# provenance fields the brief mandates be carried on every row and never dropped.
# `to_db_row` returns exactly the SQL columns; migration 003 adds coverage +
# hour_of_day_source columns so the mandated fields have a home (flagged in the
# Day-5/6 report — additive, IF NOT EXISTS).
# --------------------------------------------------------------------------- #

class ClimatologyPrior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tile_id: str
    trade_id: str
    month: int = MONTH
    hour: int = Field(..., ge=0, le=23)

    p_open: float | None = Field(
        None, description="Tier-0 PROBABILITY (not a forecast) the binding threshold "
                          "was satisfied at this hour across the reporting years. None "
                          "when the threshold was never swept.",
    )
    median_peak_c: float | None = Field(
        None, description="None everywhere: the sweep carries no temperature magnitude "
                          "(stats null, hourly_tcm empty), so a peak cannot be derived "
                          "without inventing the diurnal amplitude. See T2 ask.",
    )
    n_years: int = Field(0, description="Years that actually reported the binding analytic. "
                                        "0 when the threshold was never swept.")

    coverage: Coverage
    hour_of_day_source: HourSource

    def to_db_row(self) -> dict:
        """Exactly the `climatology_prior` columns of 001_init.sql."""
        return {
            "tile_id": self.tile_id,
            "trade_id": self.trade_id,
            "month": self.month,
            "hour": self.hour,
            "p_open": self.p_open,
            "median_peak_c": self.median_peak_c,
            "n_years": self.n_years,
        }


class TradePriorSummary(BaseModel):
    """One (tile, trade) rolled up for a human: what the formatter reads."""
    model_config = ConfigDict(extra="forbid")

    tile_id: str
    trade_id: str
    trade_display_name: str
    coverage: Coverage
    hour_of_day_source: HourSource
    n_years: int

    # Present only for a real prior (None for insufficient_threshold) ----------
    p_open_overall: float | None = None          # mean p_open across the 24 hours
    p_open_morning: float | None = None          # mean p_open over 05:00-11:00
    median_hours_exceeded: float | None = None   # median monthly count past the threshold
    pct_of_month: int | None = None              # that count as a % of the month
    cross_up_hhmm: str | None = None             # modelled: threshold crossed going up
    cross_down_hhmm: str | None = None           # modelled: crossed coming back down
    median_peak_c: float | None = None           # always None; see module docstring

    threshold_c: float | None = None             # the Celsius threshold this prior used
    reason: str = ""                             # why insufficient, or the T2/limitation note


# --------------------------------------------------------------------------- #
# The binding threshold per trade — the ONLY place trades meet sweep thresholds.
# Returns (threshold_c, direction, kind) or None. Celsius fields ONLY: a `_f`
# field is never read, so the 35-trap cannot be sprung here.
# --------------------------------------------------------------------------- #

# kind: "ceiling" (compliant below), "floor" (compliant above),
#       "floor_run" (a run-length floor answered by the persistence analytic).
_TRADE_BINDING: dict[str, tuple[str, str, str]] = {
    # trade_id: (binding constraint_id, analytic, kind)
    "concrete_cip_hot_weather":      ("band_concrete_discharge_max", "exceedance",  "ceiling"),
    "concrete_cip_cold_weather":     ("band_cold_weather_trigger",   "exceedance",  "floor"),
    "sfrm_spray_applied_fireproofing": ("continuity_40f_24h",        "persistence", "floor_run"),
}


class ThirtyFiveTrapError(ValueError):
    """Raised if a prior would join a Fahrenheit registry field to a Celsius sweep
    threshold (WORKFACE_T3_DAY56 §2.2). Caught by CI, not by somebody on stage."""


def _binding_threshold_c(constraint) -> float:
    """The Celsius threshold a constraint binds on. Celsius fields ONLY.

    A `t_*_f` value is NEVER read: the sweep is in Celsius, and 35 F (1.7 C) is
    not 35 C. If a constraint carries only a Fahrenheit bound this raises rather
    than silently producing a prior wrong by 33 degrees.
    """
    for attr in ("t_max_c", "t_min_c"):
        v = getattr(constraint, attr, None)
        if v is not None:
            return float(v)
    # No Celsius bound. If a Fahrenheit one exists this is exactly the 35 trap.
    for attr in ("t_max_f", "t_min_f"):
        if getattr(constraint, attr, None) is not None:
            raise ThirtyFiveTrapError(
                f"{constraint.constraint_id}: only a Fahrenheit bound ({attr}) is present; "
                f"the sweep is Celsius. Refusing to join F to C (the 35 trap)."
            )
    raise ValueError(f"{constraint.constraint_id}: no temperature bound to bind a prior on")


# --------------------------------------------------------------------------- #
# A1. Join work faces to tiles: nearest tile centroid WITHIN the assigned AOI.
# 100 m tiles -> nearest-centroid is honest at this granularity. Pure + cached.
# --------------------------------------------------------------------------- #

def _equirect_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Small-distance planar approximation of metres between two lon/lat points.
    Exact enough to rank tile centroids 100 m apart; no geodesy library needed."""
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    dx = math.radians(lon2 - lon1) * math.cos(mean_lat) * 6_371_000.0
    dy = math.radians(lat2 - lat1) * 6_371_000.0
    return math.hypot(dx, dy)


@lru_cache(maxsize=1)
def _tiles_by_aoi() -> dict[str, list[tuple[str, float, float]]]:
    """AOI id -> [(tile_id, lon, lat)]. One tile grid per AOI; taken from the
    first window of each sweep (every window shares the grid)."""
    bundle = _load_sweep()
    out: dict[str, list[tuple[str, float, float]]] = {}
    for sweep in bundle.sweeps:
        first = sweep.windows[0]
        out[sweep.tile_cluster_id] = [
            (t.tile_id, t.centroid_lon, t.centroid_lat) for t in first.tiles
        ]
    return out


@lru_cache(maxsize=1)
def _face_centroids() -> dict[str, tuple[float, float]]:
    gj = json.loads(WORK_FACES_PATH.read_text(encoding="utf-8"))
    out: dict[str, tuple[float, float]] = {}
    for feat in gj["features"]:
        p = feat["properties"]
        out[p["id"]] = (float(p["centroid_lon"]), float(p["centroid_lat"]))
    return out


@lru_cache(maxsize=1)
def face_tile_map() -> dict[str, str]:
    """Each work face -> the nearest tile centroid within its assigned AOI.

    Pure and cached: computed once, never per query. Raises if a face's AOI has
    no swept tiles (fail closed rather than mis-assign across AOIs).
    """
    assignments = json.loads(ASSIGNMENTS_PATH.read_text(encoding="utf-8"))
    centroids = _face_centroids()
    tiles = _tiles_by_aoi()
    mapping: dict[str, str] = {}
    for face_id, aoi in assignments.items():
        if aoi not in tiles or not tiles[aoi]:
            raise ValueError(f"work face {face_id}: AOI {aoi} has no swept tiles")
        if face_id not in centroids:
            raise ValueError(f"work face {face_id} not found in {WORK_FACES_PATH.name}")
        flon, flat = centroids[face_id]
        best = min(tiles[aoi], key=lambda t: _equirect_m(flon, flat, t[1], t[2]))
        mapping[face_id] = best[0]
    return mapping


# --------------------------------------------------------------------------- #
# The diurnal calibration: solve a per-year vertical offset so the modelled
# hours-above-CEILING match the observed monthly exceedance count.
# --------------------------------------------------------------------------- #

def _hours_above_per_day(offset: float, threshold: float = CEILING_C) -> float:
    """Hours in one day the offset diurnal spends strictly above `threshold`,
    counting fractional crossings via piecewise-linear interpolation between the
    hourly shape points (wrapping midnight)."""
    n = len(_DIURNAL)
    total = 0.0
    for h in range(n):
        a = _DIURNAL[h] + offset
        b = _DIURNAL[(h + 1) % n] + offset
        lo, hi = min(a, b), max(a, b)
        if lo >= threshold:
            total += 1.0
        elif hi <= threshold:
            continue
        else:
            # Linear segment crosses the threshold once within this hour.
            frac = (hi - threshold) / (hi - lo)
            total += frac if a >= b else frac  # fraction of the hour above
    return total


def _calibrate_offset(observed_month_hours: float) -> float:
    """Vertical offset for the diurnal so hours-above-CEILING * N_DAYS == observed.

    Bisection on the offset (monotone: raising the curve only adds hot hours).
    The amplitude is never touched — only the offset — so this places the band
    without claiming a magnitude.
    """
    target_per_day = max(0.0, min(24.0, observed_month_hours / N_DAYS))
    lo, hi = -60.0, 60.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _hours_above_per_day(mid) < target_per_day:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _crossing_hours(offset: float, threshold: float = CEILING_C) -> tuple[float | None, float | None]:
    """(up_crossing, down_crossing) in fractional hours for the offset diurnal, or
    (None, None) if it never crosses (always below or always above)."""
    n = len(_DIURNAL)
    ups: list[float] = []
    downs: list[float] = []
    for h in range(n):
        a = _DIURNAL[h] + offset
        b = _DIURNAL[(h + 1) % n] + offset
        if (a < threshold) and (b >= threshold):
            frac = (threshold - a) / (b - a) if b != a else 0.0
            ups.append(h + frac)
        elif (a >= threshold) and (b < threshold):
            frac = (a - threshold) / (a - b) if a != b else 0.0
            downs.append(h + frac)
    up = min(ups) if ups else None
    down = max(downs) if downs else None
    return up, down


def _hhmm(frac_hour: float | None) -> str | None:
    if frac_hour is None:
        return None
    frac_hour %= 24.0
    hh = int(frac_hour)
    mm = int(round((frac_hour - hh) * 60.0))
    if mm == 60:
        hh, mm = (hh + 1) % 24, 0
    return f"{hh:02d}:{mm:02d}"


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=8)
def _load_sweep(path: str | None = None) -> HistoricalSweepBundle:
    p = Path(path) if path else SWEEP_PATH
    return HistoricalSweepBundle.model_validate_json(p.read_text(encoding="utf-8"))


def _year_values(sweep, analytic: str, direction: str, threshold: float,
                 tile_id: str) -> list[float]:
    """Observed values for one tile across years, for one analytic/threshold/dir.
    Skips years where the tile reported no value (drives the honest n_years)."""
    out: list[float] = []
    for w in sweep.windows:
        if (w.analytic_type.value == analytic
                and w.direction is not None and w.direction.value == direction
                and w.threshold_c == threshold):
            tr = next((t for t in w.tiles if t.tile_id == tile_id), None)
            if tr is not None and tr.value is not None:
                out.append(float(tr.value))
    return out


def _swept_coverage(sweep) -> set[tuple[str, float, str]]:
    """The (analytic, threshold_c, direction) triples this sweep actually carries.
    Verified from the data, so a future sweep widening coverage is visible."""
    return {
        (w.analytic_type.value, float(w.threshold_c), w.direction.value)
        for w in sweep.windows
        if w.threshold_c is not None and w.direction is not None
    }


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

def _hot_rows(tile_id: str, trade_id: str, threshold: float,
              year_counts: list[float]) -> tuple[list[ClimatologyPrior], TradePriorSummary]:
    """concrete-hot ceiling: per-year offset calibration -> per-hour p_open."""
    offsets = [_calibrate_offset(c) for c in year_counts]
    n_years = len(year_counts)

    rows: list[ClimatologyPrior] = []
    p_by_hour: list[float] = []
    for h in range(24):
        # Compliant (below the ceiling) if the calibrated curve at h is <= threshold.
        compliant = sum(1 for off in offsets if (_DIURNAL[h] + off) <= threshold)
        p = round(compliant / n_years, 4) if n_years else None
        p_by_hour.append(p if p is not None else 0.0)
        rows.append(ClimatologyPrior(
            tile_id=tile_id, trade_id=trade_id, hour=h, p_open=p,
            median_peak_c=None, n_years=n_years,
            coverage=Coverage.MODELLED_HOUR, hour_of_day_source=HourSource.MODELLED,
        ))

    median_offset = _median(offsets)
    up, down = _crossing_hours(median_offset, threshold)
    median_count = _median(year_counts)
    morning = [p_by_hour[h] for h in range(5, 12)]
    summary = TradePriorSummary(
        tile_id=tile_id, trade_id=trade_id, trade_display_name="",
        coverage=Coverage.MODELLED_HOUR, hour_of_day_source=HourSource.MODELLED,
        n_years=n_years,
        p_open_overall=round(sum(p_by_hour) / 24.0, 4),
        p_open_morning=round(sum(morning) / len(morning), 4),
        median_hours_exceeded=round(median_count, 1),
        pct_of_month=round(100.0 * median_count / WINDOW_HOURS),
        cross_up_hhmm=_hhmm(up), cross_down_hhmm=_hhmm(down),
        median_peak_c=None, threshold_c=threshold,
        reason="Count observed; crossing hours MODELLED from the diurnal shape "
               "(hourly_tcm empty). Tier-0 probability, not a forecast.",
    )
    return rows, summary


def _floor_rows(tile_id: str, trade_id: str, threshold: float, kind: str,
                year_values: list[float]) -> tuple[list[ClimatologyPrior], TradePriorSummary]:
    """A floor (compliant above `threshold`). In Phoenix August the floor is
    essentially always met, so p_open is the OBSERVED monthly compliance rate,
    flat across hours (the hour of day does not change the answer at this
    resolution). No diurnal modelling — coverage is `observed`.

      * "floor"      : exceedance count of hours below the floor  -> 1 - count/window
      * "floor_run"  : persistence run length below the floor, against the
                       continuity requirement -> 1 - run/run_hours. This is the
                       run-length question the persistence analytic answers
                       directly — the clean registry/data-source match.
    """
    n_years = len(year_values)
    if kind == "floor_run":
        run_req = 24.0   # sfrm continuity_40f_24h run_hours
        per_year = [max(0.0, min(1.0, 1.0 - v / run_req)) for v in year_values]
        reason = (f"Run-length prior straight from the `persistence` analytic vs the "
                  f"{run_req:g} h continuity requirement — the same run-length question "
                  f"the registry and the data source both ask. Observed, not modelled.")
    else:
        per_year = [max(0.0, min(1.0, 1.0 - v / WINDOW_HOURS)) for v in year_values]
        reason = ("Compliance rate straight from the observed below-floor exceedance "
                  "count; the floor is essentially always met in August. Observed, "
                  "flat across hours (the rare cold-night tail is not placeable on the "
                  "clock without hourly_tcm).")
    p = round(sum(per_year) / n_years, 4) if n_years else None

    rows = [
        ClimatologyPrior(
            tile_id=tile_id, trade_id=trade_id, hour=h, p_open=p,
            median_peak_c=None, n_years=n_years,
            coverage=Coverage.OBSERVED, hour_of_day_source=HourSource.OBSERVED,
        )
        for h in range(24)
    ]
    summary = TradePriorSummary(
        tile_id=tile_id, trade_id=trade_id, trade_display_name="",
        coverage=Coverage.OBSERVED, hour_of_day_source=HourSource.OBSERVED,
        n_years=n_years, p_open_overall=p, p_open_morning=p,
        median_hours_exceeded=round(_median(year_values), 2),
        median_peak_c=None, threshold_c=threshold, reason=reason,
    )
    return rows, summary


def _insufficient(tile_id: str, trade_id: str, needed: str
                  ) -> tuple[list[ClimatologyPrior], TradePriorSummary]:
    """A single marker row: threshold never swept -> p_open None, no guessing."""
    row = ClimatologyPrior(
        tile_id=tile_id, trade_id=trade_id, hour=0, p_open=None,
        median_peak_c=None, n_years=0,
        coverage=Coverage.INSUFFICIENT_THRESHOLD, hour_of_day_source=HourSource.NONE,
    )
    summary = TradePriorSummary(
        tile_id=tile_id, trade_id=trade_id, trade_display_name="",
        coverage=Coverage.INSUFFICIENT_THRESHOLD, hour_of_day_source=HourSource.NONE,
        n_years=0, reason=needed,
    )
    return [row], summary


def _needed_threshold_note(trade, reg: Registry) -> str:
    """Name the Celsius threshold(s) a future sweep would need for this trade."""
    bounds: list[str] = []
    for c in trade.constraints:
        for attr in ("t_min_c", "t_max_c"):
            v = getattr(c, attr, None)
            if v is not None:
                bounds.append(f"{v:g} C ({c.constraint_id})")
    if trade.trade_id == "coating_epoxy_structural_steel":
        return ("insufficient_threshold: the hero constraint is offset_dew_point and the "
                "sweep has no humidity/dew point anywhere — no Tier-0 prior is possible "
                "from this data and it is NOT proxied off air temperature.")
    if bounds:
        return "insufficient_threshold: sweep captured only 35.0/4.0 C; would need " + ", ".join(sorted(set(bounds)))
    return "insufficient_threshold: no swept threshold matches this trade's bounds"


def _priors_for_tile(tile_id: str, sweep, reg: Registry
                     ) -> tuple[list[ClimatologyPrior], dict[str, TradePriorSummary]]:
    swept = _swept_coverage(sweep)
    rows: list[ClimatologyPrior] = []
    summaries: dict[str, TradePriorSummary] = {}

    for trade in reg.all():
        tid = trade.trade_id
        binding = _TRADE_BINDING.get(tid)
        if binding is None:
            r, s = _insufficient(tile_id, tid, _needed_threshold_note(trade, reg))
            rows.extend(r); s.trade_display_name = trade.display_name; summaries[tid] = s
            continue

        constraint_id, analytic, kind = binding
        constraint = trade.constraint(constraint_id)
        threshold = _binding_threshold_c(constraint)   # Celsius only; raises on the 35 trap
        direction = "above" if kind == "ceiling" else "below"

        if (analytic, threshold, direction) not in swept:
            r, s = _insufficient(tile_id, tid, _needed_threshold_note(trade, reg))
            rows.extend(r); s.trade_display_name = trade.display_name; summaries[tid] = s
            continue

        values = _year_values(sweep, analytic, direction, threshold, tile_id)
        if not values:
            r, s = _insufficient(tile_id, tid, "insufficient_threshold: no reporting years for the binding analytic")
            rows.extend(r); s.trade_display_name = trade.display_name; summaries[tid] = s
            continue

        if kind == "ceiling":
            r, s = _hot_rows(tile_id, tid, threshold, values)
        else:
            r, s = _floor_rows(tile_id, tid, threshold, kind, values)
        rows.extend(r); s.trade_display_name = trade.display_name; summaries[tid] = s

    return rows, summaries


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _build() -> tuple[tuple[ClimatologyPrior, ...], dict[str, dict[str, TradePriorSummary]]]:
    sweep_bundle = _load_sweep()
    reg = load_registry()
    tiles = sorted({t for face, t in face_tile_map().items()})
    all_rows: list[ClimatologyPrior] = []
    all_summaries: dict[str, dict[str, TradePriorSummary]] = {}
    by_cluster = {s.tile_cluster_id: s for s in sweep_bundle.sweeps}
    tile_to_aoi = {tid: aoi for aoi, ts in _tiles_by_aoi().items() for tid, _, _ in ts}
    for tile_id in tiles:
        sweep = by_cluster[tile_to_aoi[tile_id]]
        rows, summaries = _priors_for_tile(tile_id, sweep, reg)
        all_rows.extend(rows)
        all_summaries[tile_id] = summaries
    return tuple(all_rows), all_summaries


def build_priors() -> list[ClimatologyPrior]:
    """All climatology priors for every tile that carries a demo work face.
    Cached; call freely."""
    return list(_build()[0])


def summarize(tile_id: str, trade_id: str) -> TradePriorSummary:
    """The (tile, trade) roll-up the formatter reads. Raises on an unknown pair."""
    summaries = _build()[1]
    if tile_id not in summaries or trade_id not in summaries[tile_id]:
        raise KeyError(f"no prior summary for tile {tile_id!r} trade {trade_id!r}")
    return summaries[tile_id][trade_id]


def summarize_face(work_face_id: str, trade_id: str) -> TradePriorSummary:
    """Convenience: resolve a work face to its tile, then summarize."""
    return summarize(face_tile_map()[work_face_id], trade_id)


__all__ = [
    "Coverage", "HourSource", "ClimatologyPrior", "TradePriorSummary",
    "ThirtyFiveTrapError", "build_priors", "summarize", "summarize_face",
    "face_tile_map", "MONTH", "CEILING_C", "FLOOR_C",
]
