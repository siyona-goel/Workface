"""
WORKFACE — the `twin_segmentation` contract.

    packages/schemas/twin_segmentation.py   (this file, Pydantic v2)
    packages/schemas/twin_segmentation.ts    (Zod — keep field-for-field identical)

Handoff #4 in WORKFACE_SCHEDULE.md: T2 -> T3 (raw capture Day 5 -> surface Day 6).
The raw FortyGuard `satellite` + `streetview` segmentation T2 captures per work
face, from which T3 derives the Work Face Thermal Twin (WORKFACE_TECH_SPEC.md §6):

    satellite  segmentation -> land-cover fractions -> solar absorptivity alpha,
                               thermal-inertia class
    streetview segmentation -> vertical obstruction  -> sky view factor psi,
                               facade orientation for elevated faces
    -> T_surf(t) via a first-order surface energy balance, with a graceful
       confidence downgrade when a face lacks segmentation.

Both endpoints are captured ONCE per work face and cached FOREVER (neither the
land cover nor the built obstruction changes over a 12-day sprint). Neither
takes a `temperature`; only lat/lon (+ view angles for streetview).

Images are large. This contract carries each image as an `ImageRef`: T2 stores
the decoded PNG under data/fixtures/ and puts the PATH in `ref`; `base64` is the
raw FortyGuard payload and is optional (omit it in committed fixtures to keep the
repo small). At least one of the two must be present.

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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"

Iso8601 = Annotated[
    datetime,
    Field(description="ISO-8601 with offset. Site-local (America/Phoenix, UTC-07:00, no DST)."),
]


class Confidence(str, Enum):
    """Same ladder as window_eval / thermal_series. T3 sets it from what it got."""
    HIGH = "high"       # satellite + streetview both present
    MEDIUM = "medium"   # land-cover-only alpha; psi assumed
    LOW = "low"         # no segmentation; psi = 1.0


# --------------------------------------------------------------------------- #
# Leaf models
# --------------------------------------------------------------------------- #

class ImageRef(BaseModel):
    """One image, stored as a repo path and/or raw Base64. At least one required.

    FortyGuard returns raw Base64 (no data: prefix). To render, prepend
    'data:image/png;base64,'. In committed fixtures prefer `ref` (a path) and
    leave `base64` null so the repo stays small.
    """
    model_config = ConfigDict(extra="forbid")

    ref: str | None = Field(
        None, description="Repo-relative path to the decoded image, e.g. 'data/fixtures/twin/WF-FAB2-01_sat.png'.",
    )
    base64: str | None = Field(None, description="Raw Base64 as FortyGuard returned it (no data: prefix).")
    media_type: str = Field("image/png", description="MIME type for the data: URL prefix.")

    @model_validator(mode="after")
    def _one_present(self) -> ImageRef:
        if not self.ref and not self.base64:
            raise ValueError("ImageRef needs at least one of `ref` or `base64`")
        return self


class Coordinates(BaseModel):
    """FortyGuard returns lat/lon as STRINGS. T2 parses to float on ingest."""
    model_config = ConfigDict(extra="forbid")

    latitude: float
    longitude: float


class ImageDimensions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    height: int = Field(..., gt=0)
    width: int = Field(..., gt=0)


class Segmentation(BaseModel):
    """The shared shape both endpoints return: class coverage + legend + mask.

    `segments` is class-name -> coverage percent (0-100). `legend` is class-name
    -> [R, G, B]. These are free-form (the model's own class taxonomy); T3 maps
    the class names it recognises to absorptivity / thermal-inertia and ignores
    the rest, degrading confidence when its key classes are absent.
    """
    model_config = ConfigDict(extra="forbid")

    segments: dict[str, float] = Field(..., description="class -> coverage %, 0-100.")
    legend: dict[str, list[int]] = Field(
        default_factory=dict, description="class -> [R,G,B], 0-255. For rendering the mask.",
    )
    mask_image: ImageRef | None = Field(
        None, description="satellite: `image_content`. streetview: `segmented_image`. The mask.",
    )
    dimensions: ImageDimensions | None = None
    processing_time_seconds: float | None = None
    request_id: str | None = Field(None, description="FortyGuard's internal trace id. Not the fg_activity_id.")


class SatelliteCapture(BaseModel):
    """FortyGuard `satellite` result for one work face. Overhead land cover -> alpha."""
    model_config = ConfigDict(extra="forbid")

    coordinates: Coordinates
    image_year: int | None = Field(None, description="Year of the satellite imagery used.")
    original_image: ImageRef | None = None
    segmentation: Segmentation
    mode: str = Field("sat", description="FortyGuard processing mode.")
    fg_activity_id: str


class StreetViewSide(BaseModel):
    """One camera side (front or back) of a `streetview` capture. Obstruction -> psi."""
    model_config = ConfigDict(extra="forbid")

    original_image: ImageRef | None = None
    segmentation: Segmentation
    image_date: str | None = Field(None, description="YYYY-MM-DD the Street View image was captured.")


class StreetViewCapture(BaseModel):
    """FortyGuard `streetview` result for one work face, plus the request angles."""
    model_config = ConfigDict(extra="forbid")

    coordinates: Coordinates
    vertical_angle: float = Field(..., description="Requested tilt up/down, degrees.")
    horizontal_angle: float = Field(..., ge=0, le=360, description="Requested pan left/right, degrees.")
    back_view_requested: bool = Field(..., description="Whether the opposite direction was captured.")
    front: StreetViewSide
    back: StreetViewSide | None = None
    fg_activity_id: str


class WorkFaceTwinCapture(BaseModel):
    """Everything captured for one work face's twin. Cached forever, built once."""
    model_config = ConfigDict(extra="forbid")

    work_face_id: str = Field(..., description="e.g. 'WF-FAB2-01'.")
    centroid_lon: float
    centroid_lat: float
    satellite: SatelliteCapture | None = Field(
        None, description="null on a greenfield tile with no coverage -> T3 downgrades confidence.",
    )
    streetview: StreetViewCapture | None = Field(
        None, description="null when no ground imagery -> T3 sets psi=1.0, confidence=low.",
    )
    capture_confidence: Confidence = Field(
        Confidence.MEDIUM, description="T2's honest read of coverage. T3 refines it after deriving the twin.",
    )
    notes: str | None = None

    @model_validator(mode="after")
    def _at_least_one_source(self) -> WorkFaceTwinCapture:
        if self.satellite is None and self.streetview is None:
            raise ValueError(
                "a twin capture with neither satellite nor streetview carries no signal; "
                "omit the face or record the gap in notes with confidence=low"
            )
        return self


class TwinCaptureBundle(BaseModel):
    """Every work-face twin capture from one worker run. What T2 writes / T3 reads."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    run_id: str
    generated_at: Iso8601 = Field(..., description="When the captures were fetched.")
    site_id: str
    captures: list[WorkFaceTwinCapture]
    cached_forever: bool = Field(True, description="Land cover and obstruction do not change over the sprint.")
    replay: bool = Field(True, description="True when served from fixtures. REPLAY_MODE default is true.")


__all__ = [
    "SCHEMA_VERSION", "Confidence", "ImageRef", "Coordinates", "ImageDimensions",
    "Segmentation", "SatelliteCapture", "StreetViewSide", "StreetViewCapture",
    "WorkFaceTwinCapture", "TwinCaptureBundle",
]
