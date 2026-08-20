"""
WORKFACE — the canonical project-schedule contract.

Handoff #1 in WORKFACE_SCHEDULE.md: T3 -> T2 (Day 2), so T2 can cluster work
faces into AOI polygons on Day 3. It is ALSO the target shape T2's P6 XER / CSV
importer must produce on Day 6 (`apps/api/schedule/importer.py`), so the
generator and the importer are interchangeable behind one type.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (this file)
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"

Iso8601 = Annotated[datetime, Field(description="ISO-8601 with offset, site-local.")]


class LinkType(str, Enum):
    """P6 relationship types. The sequencer honours all four."""
    FS = "FS"  # finish-to-start   (the common one)
    SS = "SS"  # start-to-start
    FF = "FF"  # finish-to-finish
    SF = "SF"  # start-to-finish   (rare; included for XER fidelity)


class ExposureClass(str, Enum):
    """Drives the surface model's sky view factor and absorptivity defaults."""
    OPEN_DECK = "open_deck"                # elevated steel deck, full sky
    SHADED_BY_STEEL = "shaded_by_steel"    # erected structure overhead
    GROUND_SLAB = "ground_slab"            # at grade, full sun
    ELEVATED_FACADE = "elevated_facade"    # vertical, orientation matters
    ENCLOSED = "enclosed"                  # building dried in
    PAVED_CORRIDOR = "paved_corridor"      # asphalt / haul road
    TRENCH = "trench"                      # below grade, low sky view


class SurfaceClass(str, Enum):
    """Land-cover proxy until T2's `satellite` segmentation lands on Day 5."""
    BARE_CONCRETE = "bare_concrete"
    AGED_CONCRETE = "aged_concrete"
    ASPHALT = "asphalt"
    GALVANISED_STEEL = "galvanised_steel"
    COATED_STEEL = "coated_steel"
    CMU_MASONRY = "cmu_masonry"
    SOIL = "soil"
    VEGETATION = "vegetation"


class WorkFace(BaseModel):
    """The unit of everything. Not the site, not the activity.

    Many activities map to one work face; one work face maps to one 60 m tile
    cluster. T2: cluster these into 3-5 AOI polygons, never one call per face.
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="e.g. 'WF-FAB2-L3-N'")
    name: str
    structure_id: str = Field(..., description="Parent structure, e.g. 'FAB2'.")
    level: str | None = Field(None, description="e.g. 'L3 deck', 'grade', 'roof'.")
    geom: dict = Field(..., description="GeoJSON Polygon, EPSG:4326, [lon, lat] order.")
    centroid_lon: float
    centroid_lat: float
    area_m2: float = Field(..., gt=0)
    elevation_m: float = Field(..., description="Ground elevation AMSL, metres.")
    height_agl_m: float = Field(0.0, ge=0, description="Height of the work face above grade.")
    exposure_class: ExposureClass
    surface_class: SurfaceClass
    sky_view_factor: float = Field(
        1.0, ge=0, le=1,
        description="psi. 1.0 = unobstructed. Placeholder until T2's streetview capture (Day 5).",
    )
    orientation_deg: float | None = Field(
        None, ge=0, lt=360, description="Facade azimuth, degrees from true north. None for horizontal faces."
    )
    tile_cluster_id: str | None = Field(None, description="Written by T2 on Day 3. Leave null.")
    notes: str | None = None


class Activity(BaseModel):
    """One scheduled construction task. Maps to exactly one work face."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="activity_id. e.g. 'A-1042'.")
    wbs: str = Field(..., description="Dotted WBS path, e.g. 'FAB2.STR.L3'.")
    name: str
    work_face_id: str
    structure_id: str

    trade_id: str | None = Field(
        None,
        description="Key into data/trade_windows.json. NULL means the activity has no published "
                    "thermal window — the agent scans it and skips it. Most of a real schedule is NULL.",
    )
    thermal_sensitive: bool = Field(
        ..., description="True iff trade_id is not null. Denormalised so T2 can filter without a join."
    )
    discipline: Literal["civil", "structural", "architectural", "mechanical", "electrical", "sitework"]

    planned_start: Iso8601
    planned_finish: Iso8601
    duration_h: float = Field(..., gt=0, description="Working hours, not elapsed hours.")
    duration_d: float = Field(..., gt=0, description="Working days at the calendar's hours/day.")
    calendar_id: str = Field("CAL-6x10", description="Working calendar. See ProjectSchedule.calendars.")

    crew_size: int = Field(..., ge=1)
    quantity: float | None = Field(None, description="Installed quantity in `quantity_unit`.")
    quantity_unit: str | None = Field(None, description="m2 | m3 | ea | lf | t")

    # --- CPM ---------------------------------------------------------------
    early_start: Iso8601 | None = None
    early_finish: Iso8601 | None = None
    late_start: Iso8601 | None = None
    late_finish: Iso8601 | None = None
    total_float_d: float = Field(..., description="Working days. 0 = critical.")
    free_float_d: float = Field(0.0)
    is_critical: bool = False
    is_near_critical: bool = Field(False, description="0 < total_float_d <= 3.0")

    # --- contract ----------------------------------------------------------
    milestone_date: Iso8601 | None = Field(
        None, description="Contractual date. The policy gate NEVER lets the agent move past this."
    )
    milestone_name: str | None = None
    hold_point: str | None = Field(
        None, description="Inspection hold, e.g. 'city inspector - slab pour'. Blocks auto-move; escalate."
    )
    iwp_id: str | None = Field(None, description="Installation Work Package (AWP vocabulary).")


class Precedence(BaseModel):
    """A precedence link. `pred_id` must finish/start before `activity_id` may proceed."""
    model_config = ConfigDict(extra="forbid")

    activity_id: str
    pred_id: str
    link_type: LinkType = LinkType.FS
    lag_h: float = Field(0.0, description="Positive = lag, negative = lead. Working hours.")

    @model_validator(mode="after")
    def _no_self_link(self) -> Precedence:
        if self.activity_id == self.pred_id:
            raise ValueError("an activity cannot precede itself")
        return self


class WorkingCalendar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    workdays: list[int] = Field(..., description="ISO weekday numbers, 1=Mon .. 7=Sun.")
    shift_start_h: float = Field(..., ge=0, lt=24)
    shift_end_h: float = Field(..., gt=0, le=24)
    hours_per_day: float = Field(..., gt=0)
    holidays: list[str] = Field(default_factory=list, description="ISO dates, YYYY-MM-DD.")


class ProjectSchedule(BaseModel):
    """The whole handoff, one file. `data/project_demo/activities.json`."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    project_id: str
    project_name: str
    data_date: Iso8601 = Field(..., description="P6 data date — the 'as of' for the CPM run.")
    tz: str = "America/Phoenix"
    utc_offset_hours: float = -7.0
    site_geojson_ref: str = "data/project_demo/site.geojson"
    work_faces_geojson_ref: str = "data/project_demo/work_faces.geojson"
    provenance: str = Field(
        "Synthetic schedule, real geography, real standards. Not a real contractor's programme.",
        description="Say this on the slide. Never imply the schedule is a real project's.",
    )
    calendars: list[WorkingCalendar]
    work_faces: list[WorkFace]
    activities: list[Activity]
    precedences: list[Precedence]


__all__ = [
    "SCHEMA_VERSION", "LinkType", "ExposureClass", "SurfaceClass",
    "WorkFace", "Activity", "Precedence", "WorkingCalendar", "ProjectSchedule",
]
