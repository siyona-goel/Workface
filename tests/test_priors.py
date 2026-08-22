"""
WORKFACE — Day-5 climatology prior tests.  T3.

Covers the five things the brief (WORKFACE_T3_DAY56 §5) names:
  * a small synthetic sweep in -> known priors out;
  * n_years counts real reporting years, including a deliberately gappy fixture;
  * the F/C guard (§2.2 — the 35 trap) is a TEST, not a comment;
  * every trade without threshold coverage returns p_open is None and
    coverage == insufficient_threshold, with the COUNT asserted so a future
    sweep silently widening coverage fails here instead of passing in silence;
  * the formatter's exact string.
"""

from __future__ import annotations

import pytest

from apps.api.climatology import formatter as F
from apps.api.climatology import priors as P
from apps.api.climatology.priors import (
    Coverage,
    HourSource,
    ThirtyFiveTrapError,
    _binding_threshold_c,
    _floor_rows,
    _hot_rows,
    _year_values,
)
from apps.api.windows.registry import load_registry
from packages.schemas.historical_readings import (
    HistoricalSweepBundle,
    SweepWindow,
    TileReading,
    TileSweep,
)
from packages.schemas.trade_window import BandSpec, ContinuitySpec


# --------------------------------------------------------------------------- #
# Synthetic sweep helpers
# --------------------------------------------------------------------------- #

def _window(year: int, analytic: str, threshold: float, direction: str,
            values: dict[str, float | None]) -> SweepWindow:
    return SweepWindow(
        year=year, start_date=f"{year}-08-01", end_date=f"{year}-08-31",
        analytic_type=analytic, threshold_c=threshold, direction=direction, units="hour",
        tiles=[TileReading(tile_id=tid, centroid_lon=-112.0, centroid_lat=33.7, value=v)
               for tid, v in values.items()],
        fg_activity_id=f"syn-{year}-{analytic}-{direction}",
    )


def _sweep(windows: list[SweepWindow], cluster: str = "AOI-SYN") -> TileSweep:
    return TileSweep(
        tile_cluster_id=cluster,
        aoi_geojson={"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
        month=8, years=sorted({w.year for w in windows}),
        requested_thresholds_c=[35.0, 4.0], windows=windows,
    )


# --------------------------------------------------------------------------- #
# 1. Synthetic sweep in -> known priors out
# --------------------------------------------------------------------------- #

def test_hot_rows_known_priors_from_offset():
    """With counts calibrated so the diurnal sits unshifted, the trough hour is
    always compliant (p_open 1.0) and the peak hour never is (0.0)."""
    # base hours-above-35 per day * 31 -> the count that yields offset ~ 0.
    base_per_day = P._hours_above_per_day(0.0)
    count = base_per_day * P.N_DAYS
    rows, summary = _hot_rows("AOI-SYN-r00c00", "concrete_cip_hot_weather", 35.0, [count] * 7)

    trough_h = P._DIURNAL.index(min(P._DIURNAL))   # 05:00, 29 C
    peak_h = P._DIURNAL.index(max(P._DIURNAL))     # 15:00, 42 C
    assert rows[trough_h].p_open == 1.0
    assert rows[peak_h].p_open == 0.0
    assert all(r.coverage is Coverage.MODELLED_HOUR for r in rows)
    assert all(r.hour_of_day_source is HourSource.MODELLED for r in rows)
    assert summary.cross_up_hhmm is not None and summary.cross_down_hhmm is not None
    # A cooler tile (fewer hot hours) must be compliant at least as often.
    rows_cool, _ = _hot_rows("t", "concrete_cip_hot_weather", 35.0, [count * 0.5] * 7)
    assert (rows_cool[peak_h].p_open or 0) >= (rows[peak_h].p_open or 0)


def test_hot_p_open_is_a_probability_across_years():
    """Mixed years -> a fractional p_open at a borderline hour (a probability,
    not a 0/1 forecast)."""
    base = P._hours_above_per_day(0.0) * P.N_DAYS
    # Half the years hot, half cool -> some borderline hour lands fractional.
    rows, _ = _hot_rows("t", "concrete_cip_hot_weather", 35.0,
                        [base * 1.3, base * 1.3, base * 1.3, base * 0.6, base * 0.6, base * 0.6, base])
    fractional = [r.p_open for r in rows if r.p_open not in (0.0, 1.0)]
    assert fractional, "expected at least one borderline hour with a fractional p_open"


def test_floor_run_uses_persistence_directly():
    """SFRM's run-length prior comes straight from the persistence value against
    the 24 h continuity requirement — the clean registry/data-source match."""
    rows, summary = _floor_rows("t", "sfrm_spray_applied_fireproofing", 4.0, "floor_run",
                                [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert all(r.p_open == 1.0 for r in rows)          # no below-4 run -> always holdable
    assert summary.coverage is Coverage.OBSERVED
    assert summary.hour_of_day_source is HourSource.OBSERVED
    rows2, _ = _floor_rows("t", "sfrm", 4.0, "floor_run", [12.0] * 7)   # 12 h breach of 24 h
    assert rows2[0].p_open == 0.5


# --------------------------------------------------------------------------- #
# 2. n_years counts real reporting years, including a gappy fixture
# --------------------------------------------------------------------------- #

def test_n_years_counts_reporting_years():
    rows, summary = _hot_rows("t", "concrete_cip_hot_weather", 35.0, [300.0] * 5)
    assert summary.n_years == 5
    assert all(r.n_years == 5 for r in rows)


def test_year_values_skips_gaps():
    """A year whose tile reported no value (null) is not counted — n_years is
    counted, not assumed."""
    windows = [
        _window(2019, "exceedance", 35.0, "above", {"T1": 300.0}),
        _window(2020, "exceedance", 35.0, "above", {"T1": None}),   # gap: no data
        _window(2021, "exceedance", 35.0, "above", {"T1": 280.0}),
    ]
    sweep = _sweep(windows)
    vals = _year_values(sweep, "exceedance", "above", 35.0, "T1")
    assert vals == [300.0, 280.0]      # 2020 skipped
    assert len(vals) == 2


# --------------------------------------------------------------------------- #
# 3. The 35 trap — F/C guard is a test, not a comment (§2.2)
# --------------------------------------------------------------------------- #

def test_binding_threshold_reads_celsius():
    spec = BandSpec(constraint_id="c", label="l", citation_fragment="x",
                    t_max_c=35.0, t_max_f=95.0)
    assert _binding_threshold_c(spec) == 35.0


def test_binding_threshold_refuses_fahrenheit_only():
    """A constraint whose only '35' is Fahrenheit (35 F = 1.7 C) must NOT be
    joined to the sweep's 35 C. This is the coating trap; catch it in CI."""
    trap = BandSpec(constraint_id="band_air_application", label="l", citation_fragment="x",
                    t_min_f=35.0)   # 35 F only, no Celsius bound
    with pytest.raises(ThirtyFiveTrapError):
        _binding_threshold_c(trap)


def test_coating_gets_no_prior_from_the_sweep():
    """The real coating row: no Celsius match, hero constraint is dew-point, so it
    is insufficient_threshold and never proxied off air temperature."""
    s = P.summarize_face("WF-FAB2-07", "coating_epoxy_structural_steel")
    assert s.coverage is Coverage.INSUFFICIENT_THRESHOLD
    assert s.p_open_overall is None
    assert "dew point" in s.reason.lower()


# --------------------------------------------------------------------------- #
# 4. Insufficient-coverage count is asserted (so silent widening fails loudly)
# --------------------------------------------------------------------------- #

def test_exactly_three_trades_have_a_prior():
    reg = load_registry()
    covered = set(P._TRADE_BINDING)
    assert covered == {
        "concrete_cip_hot_weather",
        "concrete_cip_cold_weather",
        "sfrm_spray_applied_fireproofing",
    }
    # 12 trades in the registry, 3 covered -> 9 insufficient per tile.
    assert len(reg) - len(covered) == 9


def test_insufficient_count_matches_tiles_times_nine():
    rows = P.build_priors()
    tiles = {r.tile_id for r in rows}
    insuff = {(r.tile_id, r.trade_id) for r in rows
              if r.coverage is Coverage.INSUFFICIENT_THRESHOLD}
    # Every insufficient row has p_open None and n_years 0 — no guessing.
    for r in rows:
        if r.coverage is Coverage.INSUFFICIENT_THRESHOLD:
            assert r.p_open is None and r.n_years == 0
            assert r.hour_of_day_source is HourSource.NONE
    assert len(insuff) == len(tiles) * 9


def test_every_demo_face_has_a_tier0_prior():
    """The Day-5 gate: a Tier-0 prior exists for every demo work face (via its
    tile) for each supported trade."""
    fm = P.face_tile_map()
    assert len(fm) == 40
    for face_id in fm:
        for trade in P._TRADE_BINDING:
            s = P.summarize_face(face_id, trade)
            assert s.p_open_overall is not None
            assert s.coverage in (Coverage.MODELLED_HOUR, Coverage.OBSERVED)


def test_face_tile_map_stays_within_aoi_and_is_cached():
    import json
    assignments = json.loads(P.ASSIGNMENTS_PATH.read_text(encoding="utf-8"))
    fm = P.face_tile_map()
    for face_id, tile_id in fm.items():
        assert tile_id.startswith(assignments[face_id])   # nearest tile WITHIN the AOI
    assert P.face_tile_map() is fm                          # cached, not recomputed


# --------------------------------------------------------------------------- #
# 5. median_peak_c is None everywhere, hour source never dropped
# --------------------------------------------------------------------------- #

def test_median_peak_is_none_everywhere():
    """No temperature magnitude is observable from the sweep; a peak would invent
    the diurnal amplitude, so it is None (a fabricated number is not acceptable)."""
    assert all(r.median_peak_c is None for r in P.build_priors())


def test_hour_source_never_silently_dropped():
    for r in P.build_priors():
        if r.coverage is Coverage.MODELLED_HOUR:
            assert r.hour_of_day_source is HourSource.MODELLED
        elif r.coverage is Coverage.OBSERVED:
            assert r.hour_of_day_source is HourSource.OBSERVED


# --------------------------------------------------------------------------- #
# 6. The formatter's exact string
# --------------------------------------------------------------------------- #

def test_canonical_compliant_window_sentence_exact():
    got = F.compliant_window_sentence(
        trade_word="coating", pct_mornings=34, open_hhmm="06:40",
        close_hhmm="09:10", n_years=7,
    )
    assert got == (
        "This work face had a compliant coating window on 34% of August mornings "
        "over seven years, opening at a median of 06:40 and closing at 09:10. "
        "Opening and closing times are modelled from the diurnal shape, not observed."
    )


def test_exceedance_sentence_exact():
    s = P.TradePriorSummary(
        tile_id="AOI-FAB2-r03c04", trade_id="concrete_cip_hot_weather",
        trade_display_name="Cast-in-place concrete — hot weather",
        coverage=Coverage.MODELLED_HOUR, hour_of_day_source=HourSource.MODELLED,
        n_years=7, median_hours_exceeded=257.0, pct_of_month=35,
        cross_up_hhmm="10:11", cross_down_hhmm="18:29", threshold_c=35.0,
    )
    assert F.exceedance_sentence(s) == (
        "This work face exceeded the 35 C concrete discharge limit for a median of "
        "257 hours across seven Augusts — 35% of the month. Modelled crossing at "
        "10:11, closing at 18:29."
    )


def test_modelled_caveat_present_on_hero_sentence():
    """The modelled-timing caveat is carried, never stripped."""
    got = F.compliant_window_sentence(trade_word="concrete", pct_mornings=64,
                                      open_hhmm="00:00", close_hhmm="10:11", n_years=7)
    assert F.MODELLED_CAVEAT in got
