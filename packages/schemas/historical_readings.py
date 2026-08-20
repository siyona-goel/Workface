"""
WORKFACE — the `historical_readings` contract.

    packages/schemas/historical_readings.py   (this file, Pydantic v2)
    packages/schemas/historical_readings.ts    (Zod — keep field-for-field identical)

Handoff #3 in WORKFACE_SCHEDULE.md: T2 -> T3 (raw sweep Day 4 -> priors Day 5).
The raw 7-year historical heatmap sweep T2 dumps to disk, which T3 aggregates
into per-tile / per-trade / per-hour window priors (the `climatology_prior`
table and Tier-0 "Plan" loop, WORKFACE_PROJECT_PLAN.md §1.4).

The sweep, precisely (WORKFACE_SCHEDULE.md Day 4, TECH_SPEC §3.3):
  - ONE August window per year, 2019 -> 2025 (`filter_type: 4`, which caps at
    one month per request — build the loop, do not discover the cap on Day 10).
  - `granularity: 100` m for the coarse planning sweep.
  - For each year: `exceedance` AND `persistence`, run BOTH directions
    ('above' the trade ceiling, 'below' the trade floor). This is the two-sided
    trick — in-band hours = window_hours − exceedance(T_max, above)
    − exceedance(T_min, below).
  - Optionally the per-hour `tcm` array so T3 can build the opening-hour
    distribution ("opens at a median of 06:40").
  - Cached FOREVER: a 2019-2025 August climatology for a tile never changes.

Thresholds come from T3's registry, not from T2. T2 sweeps the threshold set
T3 requests (`requested_thresholds_c`); the readings themselves are raw °C /
hours and trade-agnostic. T3 maps them onto trades afterwards.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------

Changing a field here is a PR that tags T2 and T3. Never rename silently.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"

Iso8601 = Annotated[
    datetime,
    Field(description="ISO-8601 with offset. Site-local (America/Phoenix, UTC-07:00, no DST)."),
]


# --------------------------------------------------------------------------- #
# Enums — mirror the FortyGuard heatmap parameters exactly
# --------------------------------------------------------------------------- #

class AnalyticType(str, Enum):
    """FortyGuard `heatmap.analytic_type`. Units differ — see `units`."""
    TCM = "tcm"                          # temperature snapshot, °C per tile
    TIME_OF_MEASURE = "time_of_measure"  # hour of day (0-23 UTC) of the peak, per tile
    EXCEEDANCE = "exceedance"            # count of hours past the threshold
    PERSISTENCE = "persistence"          # longest continuous run past the threshold


class Direction(str, Enum):
    """FortyGuard `heatmap.direction` for exceedance / persistence.

    'below' is the parameter almost nobody uses. A trade window is two-sided:
    'above' counts hours over the ceiling, 'below' counts hours under the floor.
    """
    ABOVE = "above"
    BELOW = "below"


class ReadingUnit(str, Enum):
    CELSIUS = "C"     # tcm
    HOUR = "hour"     # time_of_measure, exceedance, persistence (stats_data.units="hour")


# --------------------------------------------------------------------------- #
# Leaf models
# --------------------------------------------------------------------------- #

class TileReading(BaseModel):
    """One tile's value for one analytic in one historical window.

    Derived from the heatmap `map_data` FeatureCollection: one feature per 60/100 m
    tile. T2 reduces each feature to its centroid + value so the sweep fixtures
    stay small; the full GeoJSON is cached separately and referenced by fg_activity_id.
    """
    model_config = ConfigDict(extra="forbid")

    tile_id: str = Field(..., description="Stable tile key within the AOI (e.g. H3 cell or 'AOI1-r03c07').")
    centroid_lon: float
    centroid_lat: float
    value: float | None = Field(
        None,
        description="The analytic value. °C for tcm; hours for exceedance/persistence; "
                    "hour-of-day 0-23 for time_of_measure. null if the tile had no data.",
    )
    hourly_tcm_c: list[float | None] | None = Field(
        None,
        description="OPTIONAL per-hour temperatures for this tile across the window, when T2 also "
                    "captured tcm. Lets T3 build the opening-hour distribution. Length = window hours.",
    )


class TemperatureStats(BaseModel):
    """`stats_data.Temperature_stats` roll-up for the window. Convenience, not the source of truth."""
    model_config = ConfigDict(extra="forbid")

    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    standard_deviation: float | None = None


class SweepWindow(BaseModel):
    """One FortyGuard heatmap call: one year, one analytic, one threshold+direction."""
    model_config = ConfigDict(extra="forbid")

    year: int = Field(..., ge=2019, description="FortyGuard supports 2019-01-01 onward.")
    start_date: str = Field(..., description="YYYY-MM-DD. The August window's first day.")
    end_date: str = Field(..., description="YYYY-MM-DD. <= 1 month after start_date (filter_type 4 cap).")
    filter_type: Literal[4] = Field(4, description="Range of days. The climatology loop always uses 4.")
    granularity_m: Literal[60, 80, 100] = Field(100, description="100 m for the coarse planning sweep.")

    analytic_type: AnalyticType
    threshold_c: float | None = Field(
        None, description="Only for exceedance / persistence. Ignored by tcm and time_of_measure.",
    )
    direction: Direction | None = Field(
        None, description="Only for exceedance / persistence. Run the sweep BOTH ways.",
    )
    units: ReadingUnit

    tiles: list[TileReading]
    stats: TemperatureStats | None = None

    fg_activity_id: str = Field(
        ..., description="The FortyGuard job handle for THIS call. Provenance + re-derivation.",
    )

    @model_validator(mode="after")
    def _threshold_pairing(self) -> SweepWindow:
        needs_threshold = self.analytic_type in (AnalyticType.EXCEEDANCE, AnalyticType.PERSISTENCE)
        if needs_threshold and (self.threshold_c is None or self.direction is None):
            raise ValueError(f"{self.analytic_type.value} requires both threshold_c and direction")
        if not needs_threshold and (self.threshold_c is not None or self.direction is not None):
            raise ValueError(f"{self.analytic_type.value} ignores threshold_c/direction; leave them null")
        return self


class TileSweep(BaseModel):
    """All historical windows for one AOI / tile-cluster. What T2 dumps to disk per cluster."""
    model_config = ConfigDict(extra="forbid")

    tile_cluster_id: str
    aoi_geojson: dict = Field(..., description="GeoJSON Polygon of the AOI this sweep covers.")
    month: int = Field(8, ge=1, le=12, description="The climatology month. 8 = the August demo window.")
    years: list[int] = Field(..., description="e.g. [2019, 2020, 2021, 2022, 2023, 2024, 2025].")
    requested_thresholds_c: list[float] = Field(
        default_factory=list,
        description="The distinct thresholds T3 asked T2 to sweep, from the registry's t_min/t_max "
                    "across all trades. Recorded so T3 can confirm coverage.",
    )
    windows: list[SweepWindow]


class HistoricalSweepBundle(BaseModel):
    """The whole 7-year sweep for the site. Tier-0 input; cached forever."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    generated_at: Iso8601 = Field(..., description="When the sweep was fetched.")
    site_id: str
    tz: str = "America/Phoenix"
    tier: Literal["plan"] = "plan"
    sweeps: list[TileSweep]
    cached_forever: bool = Field(
        True, description="A 2019-2025 August climatology never changes. TTL = infinity.",
    )
    replay: bool = Field(True, description="True when served from fixtures. REPLAY_MODE default is true.")


__all__ = [
    "SCHEMA_VERSION", "AnalyticType", "Direction", "ReadingUnit",
    "TileReading", "TemperatureStats", "SweepWindow", "TileSweep", "HistoricalSweepBundle",
]
