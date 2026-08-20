"""
WORKFACE — the `thermal_series` contract.

    packages/schemas/thermal_series.py   (this file, Pydantic v2)
    packages/schemas/thermal_series.ts    (Zod — keep field-for-field identical)

Handoff #2 in WORKFACE_SCHEDULE.md: T2 -> T3.
The hourly thermal record T2 assembles per work face and hands to T3's window
engine and surface twin. It is the FortyGuard `heatmap` (tcm) tile temperature
at the work-face centroid, joined to the `env_params` fields for the SAME
`date_time` (RH, wet bulb, solar irradiance, cloud, elevation), plus the one
field FortyGuard does not provide: site wind, from an external feed.

Endpoint chaining T2 must respect (WORKFACE_TECH_SPEC.md §3.2):

    heatmap(AOI, window)  ->  tile temperature at the work-face centroid
            |
            +--> env_params(lat, lon, temperature, SAME date_time)
                 # `temperature` and `date_time` MUST equal the heatmap you
                 # generated for that location. Never invent a temperature.

What T2 fills vs. what T3 fills
    T2 (this handoff): t_air_c, rh_pct, wet_bulb_c, solar, cloud_octas,
        elevation_m, wind_ms — everything FortyGuard + the wind feed give you.
    T3 (downstream, NOT this handoff): t_surf_c (surface twin), t_dew_c
        (Magnus-Tetens), wbgt_c (Liljegren). Those are left null here and are
        populated when T3 enriches the series into the `thermal_series` table.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# These are different things. They will collide if you blur them.
# ---------------------------------------------------------------------------

Changing a field here is a PR that tags T2 and T3. Never rename silently.
Bump SCHEMA_VERSION on any breaking change.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"

Iso8601 = Annotated[
    datetime,
    Field(description="ISO-8601 with offset. Site-local (America/Phoenix, UTC-07:00, no DST)."),
]


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class Tier(str, Enum):
    """Which temporal loop produced this series (WORKFACE_PROJECT_PLAN.md §1.4)."""
    PLAN = "plan"       # 7-year climatological prior — a probability, NOT a forecast
    COMMIT = "commit"   # <=12 h live forecast — the go/no-go window
    RECORD = "record"   # retrospective, re-queried after placement — the as-built


class SeriesSource(str, Enum):
    """Where each point came from. Drives the REPLAY/LIVE badge and confidence."""
    FORTYGUARD_LIVE = "fortyguard_live"              # commit-tier forecast heatmap
    FORTYGUARD_HISTORICAL = "fortyguard_historical"  # record/plan-tier historical heatmap
    FIXTURE = "fixture"                              # replayed from data/fixtures/ (default)
    SYNTHETIC = "synthetic"                          # hand-written placeholder, pre-integration


class Confidence(str, Enum):
    """Matches window_eval.Confidence so it can flow straight through."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --------------------------------------------------------------------------- #
# Leaf models
# --------------------------------------------------------------------------- #

class SolarIrradiance(BaseModel):
    """`env_params.solar_irradiance` — clear-sky components, W/m^2.

    Feeds the surface twin (alpha * GHI * psi) and the Liljegren WBGT. This is
    the field that makes our WBGT better-conditioned than OSHA's free
    calculator, which has to *estimate* irradiance (WORKFACE_TECH_SPEC.md §5.7).
    """
    model_config = ConfigDict(extra="forbid")

    ghi_w_m2: float | None = Field(None, description="Global horizontal irradiance.")
    dni_w_m2: float | None = Field(None, description="Direct normal irradiance.")
    dhi_w_m2: float | None = Field(None, description="Diffuse horizontal irradiance.")


class AirQuality(BaseModel):
    """`env_params` air-quality (US AQI) and gases. All optional — Premium returns all.

    null means the upstream provider had no value. NEVER read null as zero.
    Legacy stored responses may carry -999; T2 must map -999 -> None on ingest
    (WORKFACE brief: "Missing values must not be interpreted as zero").
    """
    model_config = ConfigDict(extra="forbid")

    aqi_overall: float | None = Field(None, description="air_quality:idx — overall US AQI.")
    aqi_pm2p5: float | None = Field(None, description="air_quality_pm2p5:idx")
    aqi_pm10: float | None = Field(None, description="air_quality_pm10:idx")
    aqi_no2: float | None = Field(None, description="air_quality_no2:idx")
    aqi_co: float | None = Field(None, description="aqi_us_co")
    aqi_o3: float | None = Field(None, description="air_quality_o3:idx")
    aqi_so2: float | None = Field(None, description="air_quality_so2:idx")
    methane_ppb: float | None = Field(None, description="methane_ppb")
    co2_ppm: float | None = Field(None, description="co2_ppm")


class ThermalPoint(BaseModel):
    """One hour at one work face. Dense: one entry per horizon step, ordered."""
    model_config = ConfigDict(extra="forbid")

    ts: Iso8601

    # --- FortyGuard heatmap (tcm) ------------------------------------------
    t_air_c: float | None = Field(
        None,
        description="2 m air temperature at the work-face centroid tile. FortyGuard `heatmap` "
                    "analytic_type='tcm'. This is the ONLY temperature FortyGuard sells; the "
                    "specifications are mostly written against t_surf_c, which T3 derives.",
    )

    # --- FortyGuard env_params (SAME date_time as the heatmap above) --------
    rh_pct: float | None = Field(None, ge=0, le=100, description="relative_humidity_percent.")
    wet_bulb_c: float | None = Field(None, description="wet_bulb_temperature_celsius.")
    apparent_temp_c: float | None = Field(None, description="apparent_temperature_celsius.")
    heat_index_c: float | None = Field(None, description="heat_index_celsius — feeds the OSHA HI triggers.")
    precipitation_mm: float | None = Field(None, ge=0)
    cloud_octas: float | None = Field(None, ge=0, le=8, description="cloud_cover_octas. Scales the night longwave term.")
    elevation_m: float | None = Field(None, description="Ground elevation AMSL, metres.")
    solar: SolarIrradiance = Field(default_factory=SolarIrradiance)
    air_quality: AirQuality = Field(default_factory=AirQuality)

    # --- external feed (the field FortyGuard lacks) ------------------------
    wind_ms: float | None = Field(
        None, ge=0,
        description="Site-level scalar from Open-Meteo / NWS. NOT spatially resolved — say so. "
                    "Enters the evaporation rate, WBGT, the convective term, and the masonry trigger.",
    )
    wind_dir_deg: float | None = Field(None, ge=0, lt=360, description="Optional. From the same feed.")

    # --- DERIVED — T3 fills these downstream; null on this handoff ----------
    t_surf_c: float | None = Field(
        None, description="Surface twin output. NOT FortyGuard. Left null by T2; T3 populates it.",
    )
    t_dew_c: float | None = Field(
        None, description="Magnus-Tetens from t_air_c + rh_pct. Left null by T2; T3 populates it.",
    )
    wbgt_c: float | None = Field(
        None, description="Liljegren (2008). Left null by T2; T3 populates it.",
    )


class WorkFaceThermalSeries(BaseModel):
    """The full hourly series for one work face, one tier. T3 consumes this directly."""
    model_config = ConfigDict(extra="forbid")

    work_face_id: str = Field(..., description="e.g. 'WF-FAB2-01'. Joins to the ProjectSchedule work face.")
    tile_cluster_id: str | None = Field(
        None, description="Which AOI polygon served this face. Many faces share one cluster's heatmap.",
    )
    centroid_lon: float
    centroid_lat: float

    tier: Tier = Tier.COMMIT
    step_minutes: int = Field(60, ge=5, le=180, description="Must match the horizon T3 evaluates against.")
    heatmap_filter_type: Literal[1, 2, 3, 4] = Field(
        2, description="The FortyGuard filter_type that produced t_air_c. 2 for the 12 h commit pass.",
    )
    heatmap_granularity_m: Literal[60, 80, 100] = Field(60, description="60 m for commit, 100 m for the planning sweep.")

    points: list[ThermalPoint] = Field(..., description="Dense, strictly time-ordered.")

    source: SeriesSource = SeriesSource.FIXTURE
    confidence: Confidence = Confidence.MEDIUM
    fg_activity_ids: list[str] = Field(
        default_factory=list,
        description="The FortyGuard heatmap + env_params job handles this series rests on. "
                    "NOT activity_id. A claims consultant re-derives the numbers from these.",
    )

    @field_validator("points")
    @classmethod
    def _points_ordered(cls, v: list[ThermalPoint]) -> list[ThermalPoint]:
        if not v:
            raise ValueError("points must not be empty")
        for a, b in zip(v, v[1:]):
            if b.ts <= a.ts:
                raise ValueError(f"points must be strictly increasing: {a.ts} -> {b.ts}")
        return v


class ThermalSeriesBundle(BaseModel):
    """Every work-face series from one worker run. The unit T2 writes / T3 reads."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str = Field(..., description="Groups every series from one worker run.")
    generated_at: Iso8601
    site_id: str
    tz: str = "America/Phoenix"
    tier: Tier = Tier.COMMIT
    series: list[WorkFaceThermalSeries]
    replay: bool = Field(True, description="True when served from fixtures. REPLAY_MODE default is true.")


__all__ = [
    "SCHEMA_VERSION", "Tier", "SeriesSource", "Confidence",
    "SolarIrradiance", "AirQuality", "ThermalPoint",
    "WorkFaceThermalSeries", "ThermalSeriesBundle",
]
