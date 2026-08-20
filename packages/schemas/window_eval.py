"""
WORKFACE — the `window_eval` contract.

    packages/schemas/window_eval.py   (this file, Pydantic v2)
    packages/schemas/window_eval.ts   (Zod — keep field-for-field identical)

This is handoff #5 in WORKFACE_SCHEDULE.md: T3 -> T1, the ribbon contract.
It is the *only* thing T1 needs in order to build the window ribbon. It is
published on Day 1 with hand-written fixtures so the ribbon can be built on
Day 4 before any maths exists.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# These are different things. They will collide if you blur them.
# ---------------------------------------------------------------------------

Changing a field here is a PR that tags T1 and T2. Never rename silently.
Bump SCHEMA_VERSION on any breaking change.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# Enums — T1 renders directly off these. Do not add a value without telling T1.
# --------------------------------------------------------------------------- #

class HourState(str, Enum):
    """Per-hour ribbon cell. This is the green/amber/red."""
    OPEN = "open"           # green  — every constraint satisfied with margin
    MARGINAL = "marginal"   # amber  — satisfied, but at least one within tolerance
    CLOSED = "closed"       # red    — at least one constraint violated
    NO_DATA = "no_data"     # grey   — outside forecast horizon or fetch failed


class Verdict(str, Enum):
    """Activity-level roll-up, evaluated against the *scheduled* bar."""
    COMPLIANT = "compliant"                    # scheduled bar sits inside an open interval
    AT_RISK = "at_risk"                        # bar partly outside, or margin thin
    NON_COMPLIANT = "non_compliant"            # bar sits on closed hours
    INSUFFICIENT_WINDOW = "insufficient_window"  # no open interval long enough for duration_h
    NO_DATA = "no_data"                        # fail closed — never guess


class Confidence(str, Enum):
    """Degrades when the thermal twin is missing inputs. Show it in the UI."""
    HIGH = "high"       # satellite + streetview segmentation both present
    MEDIUM = "medium"   # land-cover-only absorptivity, sky view factor assumed
    LOW = "low"         # no segmentation; psi = 1.0; climatology-backed only


class ConstraintType(str, Enum):
    """The seven shapes. WORKFACE_PROJECT_PLAN.md section 1.3."""
    BAND = "band"                    # T_min <= T_gov(t) <= T_max
    OFFSET = "offset"                # T_surface(t) >= T_dew(t) + delta
    CONTINUITY = "continuity"        # unbroken compliant run >= N hours
    CURE_CLOCK = "cure_clock"        # integral of rate(T) dt >= 1
    COMPOSITE_RATE = "composite_rate"  # derived rate <= limit (ACI 305 evaporation)
    DECAY_CLOCK = "decay_clock"      # available minutes = f(base temperature)
    HUMAN = "human"                  # WBGT -> work/rest -> effective crew hours


class GoverningTemp(str, Enum):
    AIR = "air"
    SURFACE = "surface"
    BASE_MATERIAL = "base_material"
    CONCRETE = "concrete"


# --------------------------------------------------------------------------- #
# Leaf models
# --------------------------------------------------------------------------- #

Iso8601 = Annotated[datetime, Field(description="ISO-8601 with offset. Site-local (America/Phoenix, UTC-07:00, no DST).")]


class Horizon(BaseModel):
    """The evaluated span. `hours` has exactly (end-start)/step_minutes entries."""
    model_config = ConfigDict(extra="forbid")

    start: Iso8601
    end: Iso8601
    step_minutes: int = Field(60, ge=5, le=180)
    tz: str = Field("America/Phoenix", description="IANA zone the site is planned in.")
    tier: Literal["plan", "commit", "record"] = Field(
        "commit",
        description="plan = 7-year climatological prior (a probability, NOT a forecast). "
                    "commit = <=12 h live forecast. record = retrospective as-built.",
    )


class ScheduledBar(BaseModel):
    """What the schedule says. Drawn on top of the ribbon."""
    model_config = ConfigDict(extra="forbid")

    start: Iso8601
    finish: Iso8601
    duration_h: float = Field(..., gt=0)
    total_float_d: float = Field(..., description="CPM total float, working days. 0 = critical.")
    is_critical: bool = False
    is_near_critical: bool = Field(False, description="total_float_d <= near_critical_threshold_d")
    milestone_date: Iso8601 | None = Field(None, description="Contractual date the agent may never move past.")
    hold_point: str | None = Field(None, description="e.g. 'city inspector — slab pour'. Blocks auto-move.")
    crew_size: int | None = None


class SeriesPoint(BaseModel):
    """The four series a constraint is evaluated against, plus their drivers."""
    model_config = ConfigDict(extra="forbid")

    t_air_c: float | None = None
    t_surf_c: float | None = Field(None, description="From the Work Face Thermal Twin, NOT from FortyGuard.")
    t_dew_c: float | None = Field(None, description="Magnus-Tetens from t_air_c and rh_pct.")
    t_base_material_c: float | None = None
    rh_pct: float | None = Field(None, ge=0, le=100)
    wbgt_c: float | None = None
    wind_ms: float | None = Field(None, description="Site-level scalar from an external feed. Not spatially resolved.")
    ghi_w_m2: float | None = None
    cloud_octas: float | None = Field(None, ge=0, le=8)
    evap_rate_lb_ft2_hr: float | None = None


class HourCell(BaseModel):
    """One ribbon cell. T1 renders this directly; `reason` is the hover text."""
    model_config = ConfigDict(extra="forbid")

    ts: Iso8601
    state: HourState
    binding_constraint_id: str | None = Field(
        None, description="Which constraint set this cell's state. None when state=open."
    )
    margin: float | None = Field(
        None, description="Signed distance to the nearest bound in `margin_unit`. Negative = violated."
    )
    margin_unit: Literal["C", "pct", "lb_ft2_hr", "min", "h", "ratio"] | None = None
    reason: str | None = Field(
        None, max_length=240,
        description="One sentence, plain English, quoting the number and the requirement. Hover text.",
    )
    productive_fraction: float = Field(
        1.0, ge=0, le=1,
        description="WBGT work/rest haircut. 0.75 = 25%% rest ratio. Multiplies into productive_h.",
    )
    values: SeriesPoint = Field(default_factory=SeriesPoint)


class OpenInterval(BaseModel):
    """A contiguous run of open (or open+marginal) hours."""
    model_config = ConfigDict(extra="forbid")

    start: Iso8601
    end: Iso8601
    duration_h: float = Field(..., gt=0)
    productive_h: float = Field(
        ..., ge=0,
        description="duration_h after the WBGT work/rest haircut. THIS is what the sequencer packs against.",
    )
    includes_marginal: bool = False
    min_margin: float | None = None
    confidence: Confidence = Confidence.MEDIUM

    @model_validator(mode="after")
    def _productive_le_duration(self) -> OpenInterval:
        if self.productive_h > self.duration_h + 1e-6:
            raise ValueError("productive_h cannot exceed duration_h")
        return self


class ConstraintResult(BaseModel):
    """Per-constraint breakdown. Drives the stacked bands under the ribbon lane."""
    model_config = ConfigDict(extra="forbid")

    constraint_id: str = Field(..., description="Stable within a trade, e.g. 'offset_dew_point'.")
    type: ConstraintType
    label: str = Field(..., description="Human label, e.g. 'Surface >= dew point + 2.8 C'.")
    governing_temp: GoverningTemp
    satisfied_hours: int = Field(..., ge=0)
    closed_hours: int = Field(..., ge=0)
    first_open: Iso8601 | None = None
    last_open: Iso8601 | None = None
    worst_margin: float | None = None
    margin_unit: Literal["C", "pct", "lb_ft2_hr", "min", "h", "ratio"] | None = None
    citation_fragment: str = Field(
        ..., description="The specific clause text this constraint encodes. Quoted inline in the drawer."
    )


class BindingConstraint(BaseModel):
    """The single field that makes the UI feel intelligent: *what is stopping me*.

    Definition: the constraint whose removal would most extend the usable window.
    """
    model_config = ConfigDict(extra="forbid")

    constraint_id: str
    type: ConstraintType
    label: str
    hours_lost: float = Field(..., ge=0, description="Hours this constraint alone closes.")
    would_extend_window_by_h: float = Field(
        ..., ge=0, description="Hours the longest open interval would gain if this constraint were relaxed.",
    )
    mitigation_hint: str | None = Field(
        None, description="e.g. 'dehumidified enclosure', 'evaporative retarder', 'preheat to 50 C'. Advisory."
    )


class Margin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    unit: Literal["C", "pct", "lb_ft2_hr", "min", "h", "ratio"]
    at: Iso8601 | None = Field(None, description="When the worst margin occurs inside the scheduled bar.")


class UsdExposure(BaseModel):
    """Money is the language of impact. Feeds the $ at risk / $ protected counters."""
    model_config = ConfigDict(extra="forbid")

    at_risk_usd: float = Field(0.0, ge=0)
    protected_usd: float = Field(0.0, ge=0)
    basis: str = Field(
        ..., description="How it was computed, e.g. 'quantity 4200 m2 x $34/m2 x rework multiplier 3.2'.",
    )


class Provenance(BaseModel):
    """A claims consultant must be able to re-derive the number from FortyGuard."""
    model_config = ConfigDict(extra="forbid")

    fg_activity_ids: list[str] = Field(
        default_factory=list,
        description="FortyGuard async job handles the series rests on. NOT activity_id. See naming rule.",
    )
    series_digest: str | None = Field(None, description="sha256 of the canonical-JSON series this was evaluated on.")
    registry_version: str | None = None
    twin_confidence: Confidence = Confidence.MEDIUM
    replay: bool = Field(True, description="True when served from data/fixtures/. REPLAY_MODE default is true.")


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #

class WindowEval(BaseModel):
    """One activity, one horizon, one verdict. The unit T1 renders as a ribbon lane."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str = Field(..., description="Groups every evaluation from one worker run.")
    generated_at: Iso8601

    # --- identity -----------------------------------------------------------
    activity_id: str = Field(..., description="SCHEDULE activity. Never a FortyGuard handle.")
    activity_name: str
    wbs: str | None = None
    trade_id: str = Field(..., description="Key into data/trade_windows.json.")
    trade_display_name: str
    work_face_id: str
    work_face_name: str

    # --- evaluation ---------------------------------------------------------
    horizon: Horizon
    scheduled: ScheduledBar
    hours: list[HourCell] = Field(..., description="Dense and ordered. One entry per horizon step.")
    open_intervals: list[OpenInterval] = Field(default_factory=list)
    constraints: list[ConstraintResult] = Field(default_factory=list)
    binding_constraint: BindingConstraint | None = None
    margin: Margin | None = None

    # --- the answer ---------------------------------------------------------
    verdict: Verdict
    verdict_summary: str = Field(
        ..., max_length=400,
        description="One or two sentences a superintendent reads. Names the clause and the hours.",
    )
    citation: str = Field(
        ..., min_length=20,
        description="The manufacturer / standard clause, verbatim enough that a human can go and check it.",
    )
    standard_ref: str = Field(..., description="e.g. 'SSPC-PA 1 (AMPP), Section 6.2'.")
    usd_exposure: UsdExposure
    confidence: Confidence
    confidence_reasons: list[str] = Field(default_factory=list)
    advisory_notice: str = Field(
        "Advisory and contractual. Does not replace the field measurement the referenced standard requires.",
        description="Never remove. Renders as a footer in the drawer and on the certificate.",
    )
    provenance: Provenance = Field(default_factory=Provenance)

    @field_validator("hours")
    @classmethod
    def _hours_ordered(cls, v: list[HourCell]) -> list[HourCell]:
        if not v:
            raise ValueError("hours must not be empty; use verdict=no_data with a full no_data ribbon instead")
        for a, b in zip(v, v[1:]):
            if b.ts <= a.ts:
                raise ValueError(f"hours must be strictly increasing: {a.ts} -> {b.ts}")
        return v

    @model_validator(mode="after")
    def _binding_is_a_declared_constraint(self) -> WindowEval:
        if self.binding_constraint and self.constraints:
            ids = {c.constraint_id for c in self.constraints}
            if self.binding_constraint.constraint_id not in ids:
                raise ValueError(
                    f"binding_constraint {self.binding_constraint.constraint_id!r} is not in constraints[]"
                )
        return self


class WindowEvalBundle(BaseModel):
    """What the ribbon actually fetches: every lane for one work face / one run.

    T1: this is the payload for `GET /api/window-evals?run_id=...`.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    generated_at: Iso8601
    horizon: Horizon
    site_id: str
    evaluations: list[WindowEval]
    contended_hours: list[Iso8601] = Field(
        default_factory=list,
        description="Hours where more activities want the window than crews/space allow. The collision the demo shows.",
    )
    totals: UsdExposure | None = None


__all__ = [
    "SCHEMA_VERSION", "HourState", "Verdict", "Confidence", "ConstraintType", "GoverningTemp",
    "Horizon", "ScheduledBar", "SeriesPoint", "HourCell", "OpenInterval", "ConstraintResult",
    "BindingConstraint", "Margin", "UsdExposure", "Provenance", "WindowEval", "WindowEvalBundle",
]
