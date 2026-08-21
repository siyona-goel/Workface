"""
WORKFACE — the `trade_window` registry contract.

    packages/schemas/trade_window.py   (this file, Pydantic v2)
    packages/schemas/trade_window.ts    (Zod mirror — keep field-for-field identical)

Typed model of every row in `data/trade_windows.json`. T3's window engine loads
it through apps/api/windows/registry.py; T2 reads it for the AOI clustering and
T1's detail drawer renders `citation_fragment` inline. The seven constraint
shapes are a DISCRIMINATED UNION on `constraints[].type`, one variant per value
of ConstraintType in window_eval.py.

The registry is the long pole of the whole project. Every row MUST carry a real
`citation` (> 20 chars), `standard_ref`, `source_url` and `verify_status`; those
are validated here so an uncited row fails to load, not just fails a test.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------

Changing a field here is a PR that tags T1 and T2. Never rename silently.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .window_eval import ConstraintType, GoverningTemp

SCHEMA_VERSION = "1.0.0"

VerifyStatus = Literal["primary", "secondary", "partial"]


# --------------------------------------------------------------------------- #
# Small typed nested models the physics actually reads (TASK 4 / TASK 5).
# --------------------------------------------------------------------------- #

class Q10Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_lo_c: float
    t_hi_c: float
    q10: float


class CalibrationPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_c: float
    t_f: float | None = None
    hours: float


class RecoatPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t_c: float
    hours: float


class WbgtBand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wbgt_c_lo: float
    wbgt_c_hi: float
    work_fraction: float
    label: str | None = None


# --------------------------------------------------------------------------- #
# The seven constraint variants. `type` is the discriminator.
# Every field observed in data/trade_windows.json is enumerated; extra=forbid
# so a typo or a drifted field fails the load rather than passing silently.
# --------------------------------------------------------------------------- #

class _ConstraintBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    constraint_id: str
    label: str
    citation_fragment: str = Field(..., min_length=1)


class BandSpec(_ConstraintBase):
    type: Literal["band"] = "band"
    on: str | None = None
    t_min_c: float | None = None
    t_max_c: float | None = None
    t_min_f: float | None = None
    t_max_f: float | None = None
    marginal_delta_c: float | None = None
    rh_max_pct: float | None = None
    marginal_delta_pct: float | None = None
    rising_required: bool | None = None
    hard_floor_c: float | None = None
    hard_floor_f: float | None = None
    trigger_only: bool | None = None
    mitigation_not_stop: bool | None = None
    thickness_dependent: bool | None = None
    lookup: list[dict[str, Any]] | None = None
    air_changes_per_hour_min: float | None = None
    advisory_only: bool | None = None
    direction_note: str | None = None


class OffsetSpec(_ConstraintBase):
    type: Literal["offset"] = "offset"
    on: str | None = None
    above: str | None = None
    delta_c: float
    delta_f: float | None = None
    marginal_delta_c: float | None = None
    requires_dry: bool | None = None


class ContinuitySpec(_ConstraintBase):
    type: Literal["continuity"] = "continuity"
    on: str | None = None
    also_on: str | None = None
    t_min_c: float | None = None
    t_min_f: float | None = None
    run_hours: float
    grouted_run_hours: float | None = None
    lead_hours: float | None = None
    starts_at: str | None = None
    marginal_delta_c: float | None = None


class CureClockSpec(_ConstraintBase):
    type: Literal["cure_clock"] = "cure_clock"
    on: str | None = None
    milestone: str | None = None
    ref_c: float
    hours_at_ref: float
    model: str | None = None
    q10_segments: list[Q10Segment] = Field(default_factory=list)
    calibration_points: list[CalibrationPoint] = Field(default_factory=list)
    recoat_min_hours: list[RecoatPoint] = Field(default_factory=list)
    recoat_max_hours: float | None = None


class CompositeRateSpec(_ConstraintBase):
    type: Literal["composite_rate"] = "composite_rate"
    formula: str
    expression: str | None = None
    units: dict[str, str] | None = None
    limit_lb_ft2_hr: float | None = None
    marginal_lb_ft2_hr: float | None = None
    low_bleed_limit_lb_ft2_hr: float | None = None


class DecayClockSpec(_ConstraintBase):
    type: Literal["decay_clock"] = "decay_clock"
    on: str | None = None
    quantity: str | None = None
    lookup: list[dict[str, Any]] = Field(default_factory=list)
    requires: str | None = None
    interpolation: str | None = None
    wet_hole_cure_multiplier: float | None = None


class HumanSpec(_ConstraintBase):
    type: Literal["human"] = "human"
    metric: str | None = None
    threshold: float | None = None
    mandatory_break_minutes: float | None = None
    mandatory_break_interval_h: float | None = None
    implied_rest_ratio: float | None = None
    model: str | None = None
    wbgt_formula_outdoor: str | None = None
    wbgt_method: str | None = None
    productive_fraction_by_band: list[WbgtBand] = Field(default_factory=list)


ConstraintSpec = Annotated[
    Union[
        BandSpec, OffsetSpec, ContinuitySpec, CureClockSpec,
        CompositeRateSpec, DecayClockSpec, HumanSpec,
    ],
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# The trade row and the registry file.
# --------------------------------------------------------------------------- #

class TradeWindow(BaseModel):
    """One trade: its constraints plus the provenance that makes them checkable."""
    model_config = ConfigDict(extra="forbid")

    trade_id: str
    display_name: str
    discipline: str
    constraint_types: list[ConstraintType]
    governing_temp: GoverningTemp
    constraints: list[ConstraintSpec]

    mitigations: list[str] = Field(default_factory=list)
    wind_sensitive: bool = False
    duration_h_typical: float | None = None
    crew_size_typical: int | None = None
    unit_cost_usd: float | None = None
    unit: str | None = None
    typical_quantity: float | None = None
    rework_multiplier: float | None = None
    warranty_conditioned: bool = False
    applies_to_all_trades: bool = False

    # --- provenance — the definition of done for a registry row --------------
    citation: str = Field(..., description="Verbatim-enough clause a human can check.")
    standard_ref: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1)
    source_secondary_urls: list[str] = Field(default_factory=list)
    source_date: str | None = None
    verify_status: VerifyStatus
    verify_note: str | None = None

    @field_validator("citation")
    @classmethod
    def _citation_is_real(cls, v: str) -> str:
        if len(v.strip()) <= 20:
            raise ValueError("citation must be a real clause (> 20 chars) — WORKFACE_REPO_GUIDE definition of done")
        return v

    @field_validator("constraints")
    @classmethod
    def _constraint_ids_unique(cls, v: list[ConstraintSpec]) -> list[ConstraintSpec]:
        ids = [c.constraint_id for c in v]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate constraint_id(s) within a trade: {sorted(dupes)}")
        return v

    def constraint(self, constraint_id: str) -> ConstraintSpec | None:
        return next((c for c in self.constraints if c.constraint_id == constraint_id), None)


class TradeWindowRegistry(BaseModel):
    """The whole `data/trade_windows.json` file."""
    model_config = ConfigDict(extra="ignore")   # tolerate metadata (legends, notes)

    schema_version: str = SCHEMA_VERSION
    registry_version: str
    trades: list[TradeWindow]

    @field_validator("trades")
    @classmethod
    def _trade_ids_unique(cls, v: list[TradeWindow]) -> list[TradeWindow]:
        ids = [t.trade_id for t in v]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate trade_id(s): {sorted(dupes)}")
        return v


__all__ = [
    "SCHEMA_VERSION", "VerifyStatus",
    "Q10Segment", "CalibrationPoint", "RecoatPoint", "WbgtBand",
    "BandSpec", "OffsetSpec", "ContinuitySpec", "CureClockSpec",
    "CompositeRateSpec", "DecayClockSpec", "HumanSpec", "ConstraintSpec",
    "TradeWindow", "TradeWindowRegistry",
]
