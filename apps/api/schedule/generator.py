"""
WORKFACE — synthetic project generator.  T3, Day 2.  Handoff #1: T3 -> T2.

    python -m apps.api.schedule.generator --out data/project_demo

Produces, deterministically (seeded):
    data/project_demo/site.geojson         one site polygon, real N. Phoenix geography
    data/project_demo/work_faces.geojson   40 work faces as polygons
    data/project_demo/activities.json      the full ProjectSchedule (activities + precedences)
    data/project_demo/stats.json           counts the demo narrative depends on

Label it exactly this way, everywhere:
    "Synthetic schedule, real geography, real standards."

Design notes
------------
* The unit of everything is the WORK FACE, not the site and not the activity.
  Many activities map to one work face; one work face maps to one 60 m tile
  cluster (T2 builds the clusters on Day 3 from this file).
* Most of a real schedule has no published thermal window. Roughly 40 % of these
  activities carry a `trade_id`; the rest are formwork, erection, MEP rough-in
  and fit-out. That is the point — the agent scans ~300 and flags a sane subset.
* CPM is done in integer WORKING HOURS since project start, then mapped to wall
  clock through the calendar. Float is exact, testable, and independent of DST
  (Arizona does not observe it, which is why the site tz is fixed at UTC-07:00).
* Cold-weather trades (concrete_cip_cold_weather, masonry_cmu_cold_weather) only
  appear on activities that land in Dec-Feb. That gives the January
  `direction: below` slide a real activity behind it instead of a hypothetical.

No third-party dependencies. Pure stdlib so CI stays fast.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Site — real geography. TSMC-adjacent North Phoenix industrial corridor,
# between I-17 and the SR-303, Dove Valley area. Wikipedia gives the fab campus
# at 33.78 N, 112.16 W. We anchor a 1,100-acre parcel there and draw our own
# structures on it. The GEOGRAPHY is real; the project on it is invented.
# --------------------------------------------------------------------------- #

SITE_ANCHOR_LAT = 33.7772          # SW corner of the parcel
SITE_ANCHOR_LON = -112.1712
SITE_W_M = 2400.0                  # east-west
SITE_H_M = 1855.0                  # north-south  -> 4.452 km2 = 1,100.2 acres
BASE_ELEV_M = 462.0                # ~1,516 ft AMSL; N. Phoenix rises to the north
ELEV_GRADIENT_M_PER_M = 0.006

TZ_NAME = "America/Phoenix"
UTC_OFFSET_H = -7.0                # Arizona: no DST, ever. This never changes.
TZ = timezone(timedelta(hours=UTC_OFFSET_H))

PROJECT_ID = "NPX-FAB-P2"
PROJECT_NAME = "North Phoenix Advanced Packaging Facility — Phase 2"
PROJECT_START = date(2026, 6, 1)
DATA_DATE = datetime(2026, 8, 20, 6, 0, tzinfo=TZ)   # P6 "as of"
DEMO_WINDOW_START = datetime(2026, 8, 24, 0, 0, tzinfo=TZ)   # Mon
DEMO_WINDOW_END = datetime(2026, 8, 27, 0, 0, tzinfo=TZ)     # Thu 00:00 -> 72 h

NEAR_CRITICAL_FLOAT_D = 3.0

SEED = 20260820


# --------------------------------------------------------------------------- #
# Calendars
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Calendar:
    id: str
    name: str
    workdays: tuple[int, ...]      # ISO weekday, 1=Mon
    shift_start_h: float
    shift_end_h: float
    holidays: tuple[str, ...] = ()

    @property
    def hours_per_day(self) -> float:
        return self.shift_end_h - self.shift_start_h

    def is_workday(self, d: date) -> bool:
        return d.isoweekday() in self.workdays and d.isoformat() not in self.holidays

    def datetime_at(self, working_hours: float) -> datetime:
        """Map working-hours-since-PROJECT_START to a wall-clock datetime."""
        whole_days, rem_h = divmod(working_hours, self.hours_per_day)
        d = PROJECT_START
        remaining = int(whole_days)
        # advance `remaining` working days
        while True:
            if self.is_workday(d):
                if remaining == 0:
                    break
                remaining -= 1
            d += timedelta(days=1)
        while not self.is_workday(d):
            d += timedelta(days=1)
        h = self.shift_start_h + rem_h
        return datetime(d.year, d.month, d.day, tzinfo=TZ) + timedelta(hours=h)


CAL_6x10 = Calendar(
    id="CAL-6x10", name="Field 6x10 (Mon-Sat 06:00-16:00)",
    workdays=(1, 2, 3, 4, 5, 6), shift_start_h=6.0, shift_end_h=16.0,
    holidays=("2026-07-03", "2026-09-07", "2026-11-26", "2026-11-27",
              "2026-12-24", "2026-12-25", "2027-01-01"),
)
CAL_5x8 = Calendar(
    id="CAL-5x8", name="Fit-out 5x8 (Mon-Fri 07:00-15:00)",
    workdays=(1, 2, 3, 4, 5), shift_start_h=7.0, shift_end_h=15.0,
    holidays=CAL_6x10.holidays,
)
CALENDARS = {c.id: c for c in (CAL_6x10, CAL_5x8)}


# --------------------------------------------------------------------------- #
# Geometry helpers — local ENU metres -> WGS84. Equirectangular is accurate to
# well under a metre over a 2.4 km parcel; that is far finer than a 60 m tile.
# --------------------------------------------------------------------------- #

_M_PER_DEG_LAT = 111_320.0
_M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(SITE_ANCHOR_LAT))


def enu_to_lonlat(x_m: float, y_m: float) -> tuple[float, float]:
    return (
        round(SITE_ANCHOR_LON + x_m / _M_PER_DEG_LON, 7),
        round(SITE_ANCHOR_LAT + y_m / _M_PER_DEG_LAT, 7),
    )


def rect_polygon(x0: float, y0: float, x1: float, y1: float) -> dict:
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return {"type": "Polygon", "coordinates": [[list(enu_to_lonlat(x, y)) for x, y in pts]]}


def elevation_at(y_m: float) -> float:
    return round(BASE_ELEV_M + y_m * ELEV_GRADIENT_M_PER_M, 1)


# --------------------------------------------------------------------------- #
# Structures — the campus layout, in local ENU metres.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Structure:
    id: str
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    template: str
    n_faces: int


STRUCTURES: tuple[Structure, ...] = (
    Structure("FAB2",  "Fab 2 — process module & clean room shell", 300, 900, 1050, 1350, "fab_structural", 14),
    Structure("CUB",   "Central utility building",                  1110, 950, 1340, 1130, "yard_mechanical", 5),
    Structure("WHSE",  "Warehouse & receiving",                      600, 400,  880,  560, "warehouse", 4),
    Structure("CT",    "Cooling tower yard",                        1110, 1250, 1350, 1400, "yard_mechanical", 3),
    Structure("SUB",   "Electrical substation & switchyard",        1420, 900, 1660, 1080, "yard_electrical", 3),
    Structure("BULK",  "Bulk gas & specialty chemical yard",        1110,  700, 1310,  840, "cmu_enclosure", 3),
    Structure("CHEM",  "Chemical waste treatment building",          320,  620,  500,  760, "cmu_enclosure", 3),
    Structure("ADMIN", "Administration & site support building",     250,  200,  430,  300, "cmu_enclosure", 2),
    Structure("PARK",  "Employee parking structure",                1750,  300, 2000,  520, "warehouse", 2),
    Structure("ROAD",  "Perimeter haul road & marshalling paving",   250, 1500, 2050, 1620, "paving", 1),
)
assert sum(s.n_faces for s in STRUCTURES) == 40


# --------------------------------------------------------------------------- #
# Trade sequence templates — realistic Installation Work Package chains.
#
#   (short_name, trade_id | None, discipline, duration_h, crew, qty, unit,
#    link_type_to_previous, lag_h)
# --------------------------------------------------------------------------- #

TradeStep = tuple[str, str | None, str, float, int, float | None, str | None, str, float]

TEMPLATES: dict[str, list[TradeStep]] = {
    # ---- FAB2: slab bays and elevated steel decks -------------------------- #
    "fab_structural": [
        ("Layout & survey control",              None,                             "civil",       10,  3, None, None, "FS", 0),
        ("Formwork & rebar placement",           None,                             "structural",  30,  9, None, None, "FS", 0),
        ("Slab pour",                            "concrete_cip_hot_weather",       "structural",   8, 12,  340, "m3", "FS", 0),
        ("Slab finish & curing compound",        None,                             "structural",  10,  6, None, None, "FS", 0),
        ("Structural steel erection",            None,                             "structural",  40, 10, None, None, "FS", 48),
        ("Deck weld & shear stud installation",  "structural_welding_preheat",     "structural",   8,  4,  180, "ea", "FS", 0),
        ("Adhesive anchor installation",         "adhesive_anchor_epoxy",          "structural",   5,  3,  420, "ea", "FS", 0),
        ("Spray-applied fireproofing",           "sfrm_spray_applied_fireproofing","structural",  10,  6, 3100, "m2", "FS", 8),
        ("Structural steel high-build coating",  "coating_epoxy_structural_steel", "structural",   6,  5, 4200, "m2", "FS", 24),
        ("MEP hanger & rough-in",                None,                             "mechanical",  30,  8, None, None, "FS", 0),
    ],
    # ---- CUB / CT / SUB yards --------------------------------------------- #
    "yard_mechanical": [
        ("Excavation & subgrade prep",           None,                             "sitework",    20,  5, None, None, "FS", 0),
        ("Equipment pad pour",                   "concrete_cip_hot_weather",       "structural",   8, 10,  120, "m3", "FS", 0),
        ("Anchor bolt & adhesive anchor set",    "adhesive_anchor_epoxy",          "structural",   5,  3,  160, "ea", "FS", 24),
        ("Equipment set & alignment",            None,                             "mechanical",  30,  6, None, None, "FS", 0),
        ("Pipe rack erection",                   None,                             "mechanical",  20,  6, None, None, "FS", 0),
        ("Pipe rack & equipment coating",        "coating_epoxy_structural_steel", "mechanical",   6,  4, 1400, "m2", "FS", 0),
        ("Conduit, grounding & terminations",    None,                             "electrical",  30,  6, None, None, "SS", 16),
    ],
    "yard_electrical": [
        ("Excavation & duct bank",               None,                             "sitework",    25,  6, None, None, "FS", 0),
        ("Duct bank encasement pour",            "concrete_cip_hot_weather",       "electrical",   8,  8,   95, "m3", "FS", 0),
        ("Transformer pad pour",                 "concrete_cip_hot_weather",       "structural",   8, 10,  140, "m3", "FS", 24),
        ("Anchor & baseplate grout",             "adhesive_anchor_epoxy",          "structural",   5,  3,  110, "ea", "FS", 24),
        ("Switchgear set",                       None,                             "electrical",  20,  5, None, None, "FS", 0),
        ("Steel structure coating touch-up",     "coating_epoxy_structural_steel", "structural",   6,  4,  900, "m2", "FS", 0),
        ("Cable pull & termination",             None,                             "electrical",  40,  6, None, None, "FS", 0),
    ],
    # ---- CMU-framed support buildings -------------------------------------- #
    "cmu_enclosure": [
        ("Footing excavation",                   None,                             "sitework",    15,  4, None, None, "FS", 0),
        ("Foundation pour",                      "concrete_cip_hot_weather",       "structural",   8, 10,  180, "m3", "FS", 0),
        ("CMU wall construction",                "masonry_cmu_hot_weather",        "architectural",9,  8,  950, "m2", "FS", 48),
        ("Bond beam & cell grouting",            "concrete_cip_hot_weather",       "structural",   8,  6,   45, "m3", "FS", 0),
        ("Steel lintel & joist weld",            "structural_welding_preheat",     "structural",   8,  4,   60, "ea", "FS", 0),
        ("Roof deck & waterproofing",            None,                             "architectural",25, 6, None, None, "FS", 0),
        ("Perimeter joint sealant",              "sealant_silicone_weatherseal",   "architectural", 7, 4, 2300, "lf", "FS", 24),
        ("Interior fit-out",                     None,                             "architectural",40, 6, None, None, "FS", 0),
    ],
    # ---- Warehouse / parking structure ------------------------------------- #
    "warehouse": [
        ("Subgrade & vapour barrier",            None,                             "sitework",    18,  5, None, None, "FS", 0),
        ("Slab on grade pour",                   "concrete_cip_hot_weather",       "structural",   8, 12,  420, "m3", "FS", 0),
        ("Precast panel erection",               None,                             "structural",  30,  8, None, None, "FS", 72),
        ("Connection weld",                      "structural_welding_preheat",     "structural",   8,  4,  140, "ea", "FS", 0),
        ("Panel joint sealant",                  "sealant_silicone_weatherseal",   "architectural", 7, 4, 1800, "lf", "FS", 0),
        ("Spray-applied fireproofing",           "sfrm_spray_applied_fireproofing","structural",  10,  6, 2400, "m2", "FS", 0),
        ("Interior floor marking",               "pavement_marking_waterborne",    "architectural", 5, 4, 3200, "lf", "FS", 24),
    ],
    # ---- Site paving -------------------------------------------------------- #
    "paving": [
        ("Subgrade preparation",                 None,                             "sitework",    25,  6, None, None, "FS", 0),
        ("Aggregate base course",                None,                             "sitework",    20,  6, None, None, "FS", 0),
        ("HMA base course",                      "hma_paving_surface_course",      "sitework",     9, 10, 8600, "m2", "FS", 0),
        ("HMA surface course",                   "hma_paving_surface_course",      "sitework",     9, 10, 8600, "m2", "FS", 24),
        ("Pavement marking & striping",          "pavement_marking_waterborne",    "sitework",     5,  4,11000, "lf", "FS", 48),
    ],
}

# Trades whose spec is written for the cold half of the year. If an activity's
# planned start lands in Dec-Feb we swap the hot-weather row for the cold one.
COLD_SWAP = {
    "concrete_cip_hot_weather": "concrete_cip_cold_weather",
    "masonry_cmu_hot_weather": "masonry_cmu_cold_weather",
}

# Exposure / surface classes by template and face index.
EXPOSURE_BY_TEMPLATE = {
    "fab_structural": [
        ("ground_slab", "bare_concrete", 0.88, 0.0),
        ("open_deck", "galvanised_steel", 0.97, 9.0),
        ("shaded_by_steel", "galvanised_steel", 0.45, 9.0),
        ("elevated_facade", "coated_steel", 0.58, 14.0),
    ],
    "yard_mechanical": [("ground_slab", "bare_concrete", 0.92, 0.0), ("open_deck", "galvanised_steel", 0.95, 6.0)],
    "yard_electrical": [("ground_slab", "bare_concrete", 0.95, 0.0), ("open_deck", "galvanised_steel", 0.98, 4.0)],
    "cmu_enclosure": [("ground_slab", "bare_concrete", 0.86, 0.0), ("elevated_facade", "cmu_masonry", 0.62, 4.0)],
    "warehouse": [("ground_slab", "bare_concrete", 0.9, 0.0), ("elevated_facade", "bare_concrete", 0.6, 8.0)],
    "paving": [("paved_corridor", "asphalt", 1.0, 0.0)],
}


# --------------------------------------------------------------------------- #
# Model objects
# --------------------------------------------------------------------------- #

@dataclass
class Act:
    id: str
    wbs: str
    name: str
    work_face_id: str
    structure_id: str
    trade_id: str | None
    discipline: str
    duration_h: float
    crew_size: int
    quantity: float | None
    quantity_unit: str | None
    calendar_id: str
    iwp_id: str
    es: float = 0.0                       # working hours since PROJECT_START
    ef: float = 0.0
    ls: float = 0.0
    lf: float = 0.0
    total_float_h: float = 0.0
    free_float_h: float = 0.0
    milestone_h: float | None = None
    milestone_name: str | None = None
    hold_point: str | None = None
    preds: list[tuple[str, str, float]] = field(default_factory=list)  # (pred_id, link_type, lag_h)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def build_work_faces() -> list[dict]:
    faces: list[dict] = []
    for s in STRUCTURES:
        cols = math.ceil(math.sqrt(s.n_faces))
        rows = math.ceil(s.n_faces / cols)
        w = (s.x1 - s.x0) / cols
        h = (s.y1 - s.y0) / rows
        palette = EXPOSURE_BY_TEMPLATE[s.template]
        for i in range(s.n_faces):
            r, c = divmod(i, cols)
            x0 = s.x0 + c * w + 4.0
            x1 = s.x0 + (c + 1) * w - 4.0
            y0 = s.y0 + r * h + 4.0
            y1 = s.y0 + (r + 1) * h - 4.0
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

            if s.template == "fab_structural":
                # Row 0 = L1 slab bays, rows 1-2 = elevated decks (alternating
                # shaded / bare so the hero pair sits on the same level), last
                # row = perimeter facade zones.
                if r == 0:
                    exp = palette[0]
                    level = "L1 slab"
                elif r < rows - 1:
                    exp = palette[1] if c % 2 == 0 else palette[2]
                    level = f"L{r + 1} deck"
                else:
                    exp = palette[3]
                    level = "Perimeter facade"
            else:
                exp = palette[min(r, len(palette) - 1)]
                level = {"paving": "grade", "warehouse": "grade"}.get(s.template, "grade" if r == 0 else f"L{r + 1}")

            exposure_class, surface_class, psi, height = exp
            fid = f"WF-{s.id}-{i + 1:02d}"
            faces.append({
                "id": fid,
                "name": f"{s.id} {level} — bay {chr(65 + c)}{r + 1}",
                "structure_id": s.id,
                "level": level,
                "geom": rect_polygon(x0, y0, x1, y1),
                "centroid_lon": enu_to_lonlat(cx, cy)[0],
                "centroid_lat": enu_to_lonlat(cx, cy)[1],
                "area_m2": round((x1 - x0) * (y1 - y0), 1),
                "elevation_m": elevation_at(cy),
                "height_agl_m": height,
                "exposure_class": exposure_class,
                "surface_class": surface_class,
                "sky_view_factor": psi,
                "orientation_deg": (180.0 if r == 0 else 0.0) if exposure_class == "elevated_facade" else None,
                "tile_cluster_id": None,
                "notes": None,
                "_enu": (x0, y0, x1, y1),
                "_template": s.template,
            })
    return faces


# Working hours after PROJECT_START that each template's chains begin. Tuned so
# the busiest wave of thermally sensitive work lands on the demo window
# (24-26 Aug 2026 ~ working hour 720 on CAL-6x10). Structural work leads; paving
# and marking trail into the autumn.
MOBILISATION_BASE_H: dict[str, int] = {
    "fab_structural": 370,
    "yard_mechanical": 600,
    "yard_electrical": 500,
    "cmu_enclosure": 550,
    "warehouse": 500,
    "paving": 1620,
}
MOBILISATION_SPREAD_H = 3

# The ADMIN building is deliberately a WINTER package: its cmu_enclosure chain is
# pushed into Dec-Feb so the January `direction: below` slide has real cold-weather
# concrete AND masonry activities behind it (see apply_cold_weather_trades). ADMIN
# is not referenced by any cross-work-face link, so pushing it late is safe.
WINTER_PACKAGE_STRUCTURES = {"ADMIN"}
WINTER_OFFSET_H = 780


def _mobilisation_offset_h(idx: int, template: str, structure_id: str, rng: random.Random) -> float:
    """Working hours after PROJECT_START that this work face's chain may begin.

    Tuned so the campus builds out in waves and the busiest wave lands on the
    demo window (24-26 Aug 2026). The ADMIN winter package is offset deep into
    the year so the cold-weather registry rows have a real activity behind them.
    """
    base = MOBILISATION_BASE_H[template]
    if structure_id in WINTER_PACKAGE_STRUCTURES:
        base += WINTER_OFFSET_H
    return base + idx * MOBILISATION_SPREAD_H + rng.randint(-14, 14)


def build_activities(faces: list[dict], rng: random.Random) -> list[Act]:
    acts: list[Act] = []
    seq = 1000
    prev_face_last: dict[str, str] = {}

    for f_idx, face in enumerate(faces):
        template = face["_template"]
        steps = TEMPLATES[template]
        cal = CAL_5x8 if template == "cmu_enclosure" and face["structure_id"] == "ADMIN" else CAL_6x10
        iwp = f"IWP-{face['id'].replace('WF-', '')}"
        offset = _mobilisation_offset_h(f_idx, template, face["structure_id"], rng)
        prev_id: str | None = None

        for s_idx, (name, trade, disc, dur, crew, qty, unit, link, lag) in enumerate(steps):
            seq += 1
            aid = f"A-{seq}"
            jitter = rng.uniform(0.85, 1.2)
            act = Act(
                id=aid,
                wbs=f"{face['structure_id']}.{template.split('_')[0].upper()}.{face['id'].split('-')[-1]}",
                name=f"{name} — {face['name']}",
                work_face_id=face["id"],
                structure_id=face["structure_id"],
                trade_id=trade,
                discipline=disc,
                duration_h=round(dur * jitter, 1),
                crew_size=crew,
                quantity=round(qty * jitter, 1) if qty is not None else None,
                quantity_unit=unit,
                calendar_id=cal.id,
                iwp_id=iwp,
            )
            if prev_id is None:
                # First activity of the chain: seed its ES via a dummy offset.
                act.es = float(offset)
            else:
                act.preds.append((prev_id, link, float(lag)))
            acts.append(act)
            prev_id = aid

        prev_face_last[face["id"]] = prev_id  # type: ignore[assignment]

    # ---- cross-work-face links -------------------------------------------- #
    # 1. Every FAB2 elevated deck face waits on the L1 slab bay below it.
    fab_l1 = [f["id"] for f in faces if f["structure_id"] == "FAB2" and f["level"] == "L1 slab"]
    fab_upper = [f["id"] for f in faces if f["structure_id"] == "FAB2" and f["level"] != "L1 slab"]
    by_face_first: dict[str, Act] = {}
    for a in acts:
        by_face_first.setdefault(a.work_face_id, a)

    for i, up in enumerate(fab_upper):
        if fab_l1:
            below = fab_l1[i % len(fab_l1)]
            # first activity of the upper face waits on the slab pour below
            pour = next((a for a in acts if a.work_face_id == below and a.trade_id == "concrete_cip_hot_weather"), None)
            if pour:
                by_face_first[up].preds.append((pour.id, "FS", 72.0))

    # 2. Paving waits on the last structural activity of the warehouse and CUB.
    paving_face = next(f["id"] for f in faces if f["_template"] == "paving")
    for struct in ("WHSE", "CUB"):
        donor = next((f["id"] for f in faces if f["structure_id"] == struct), None)
        if donor and prev_face_last.get(donor):
            by_face_first[paving_face].preds.append((prev_face_last[donor], "FS", 0.0))

    # 3. A handful of realistic SS links between neighbouring FAB2 decks so the
    #    schedule is not a forest of independent chains.
    fab_faces = [f["id"] for f in faces if f["structure_id"] == "FAB2"]
    for a_id, b_id in zip(fab_faces, fab_faces[1:]):
        a_sfrm = next((a for a in acts if a.work_face_id == a_id and a.trade_id == "sfrm_spray_applied_fireproofing"), None)
        b_sfrm = next((a for a in acts if a.work_face_id == b_id and a.trade_id == "sfrm_spray_applied_fireproofing"), None)
        if a_sfrm and b_sfrm:
            b_sfrm.preds.append((a_sfrm.id, "SS", 10.0))  # one fireproofing crew, staggered

    return acts


# --------------------------------------------------------------------------- #
# CPM — forward and backward pass in working hours
# --------------------------------------------------------------------------- #

def topo_order(acts: list[Act]) -> list[Act]:
    by_id = {a.id: a for a in acts}
    indeg = {a.id: 0 for a in acts}
    succ: dict[str, list[str]] = {a.id: [] for a in acts}
    for a in acts:
        for p, _, _ in a.preds:
            if p in by_id:
                indeg[a.id] += 1
                succ[p].append(a.id)
    queue = [aid for aid, d in indeg.items() if d == 0]
    out: list[Act] = []
    while queue:
        aid = queue.pop(0)
        out.append(by_id[aid])
        for s in succ[aid]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(out) != len(acts):
        raise ValueError("precedence graph contains a cycle — a schedule must be a DAG")
    return out


def forward_pass(acts: list[Act]) -> float:
    by_id = {a.id: a for a in acts}
    for a in topo_order(acts):
        for pid, link, lag in a.preds:
            p = by_id[pid]
            if link == "FS":
                a.es = max(a.es, p.ef + lag)
            elif link == "SS":
                a.es = max(a.es, p.es + lag)
            elif link == "FF":
                a.es = max(a.es, p.ef + lag - a.duration_h)
            elif link == "SF":
                a.es = max(a.es, p.es + lag - a.duration_h)
        a.ef = a.es + a.duration_h
    return max(a.ef for a in acts)


def backward_pass(acts: list[Act], project_finish_h: float) -> None:
    by_id = {a.id: a for a in acts}
    succ: dict[str, list[tuple[Act, str, float]]] = {a.id: [] for a in acts}
    for a in acts:
        for pid, link, lag in a.preds:
            if pid in by_id:
                succ[pid].append((a, link, lag))

    for a in reversed(topo_order(acts)):
        if a.milestone_h is not None:
            a.lf = a.milestone_h
        elif not succ[a.id]:
            a.lf = project_finish_h
        else:
            a.lf = math.inf
        for s, link, lag in succ[a.id]:
            if link == "FS":
                a.lf = min(a.lf, s.ls - lag)
            elif link == "SS":
                a.lf = min(a.lf, s.ls - lag + a.duration_h)
            elif link == "FF":
                a.lf = min(a.lf, s.lf - lag)
            elif link == "SF":
                a.lf = min(a.lf, s.lf - lag + a.duration_h)
        if a.milestone_h is not None:
            a.lf = min(a.lf, a.milestone_h)
        a.ls = a.lf - a.duration_h
        a.total_float_h = a.ls - a.es

    for a in acts:
        if succ[a.id]:
            a.free_float_h = min(
                (s.es - a.ef - lag) if link == "FS" else (s.es - a.es - lag)
                for s, link, lag in succ[a.id]
            )
        else:
            a.free_float_h = a.total_float_h


def apply_milestones(acts: list[Act], project_finish_h: float, rng: random.Random) -> list[dict]:
    """Contractual milestones and inspection hold points.

    The policy gate must NEVER let the agent move an activity past a milestone
    date, and must escalate rather than auto-move anything with a hold point.
    Both cases need to exist in the demo data or the deny case has nothing
    to fire on.
    """
    milestones = []

    # 1. Clean room shell dry-in: the last FAB2 facade activity, tight.
    fab_facade = [a for a in acts if a.structure_id == "FAB2" and "facade" in a.name.lower()]
    if fab_facade:
        target = max(fab_facade, key=lambda a: a.ef)
        target.milestone_h = target.ef + 12.0          # 12 working hours of slack. Tight on purpose.
        target.milestone_name = "MS-210 Clean room shell dry-in"
        milestones.append({"activity_id": target.id, "name": target.milestone_name})

    # 2. Substation energisation — utility-coordinated, immovable.
    sub_last = [a for a in acts if a.structure_id == "SUB"]
    if sub_last:
        target = max(sub_last, key=lambda a: a.ef)
        target.milestone_h = target.ef + 6.0
        target.milestone_name = "MS-340 Substation energisation (utility coordinated)"
        milestones.append({"activity_id": target.id, "name": target.milestone_name})

    # 3. Inspection hold points on slab pours — a city inspector must attend.
    pours = [a for a in acts if a.trade_id in ("concrete_cip_hot_weather", "concrete_cip_cold_weather")]
    for a in rng.sample(pours, k=min(6, len(pours))):
        a.hold_point = "City of Phoenix inspector — reinforcing & embed inspection prior to pour"

    # 4. Fireproofing hold — special inspector density/thickness testing.
    sfrm = [a for a in acts if a.trade_id == "sfrm_spray_applied_fireproofing"]
    for a in rng.sample(sfrm, k=min(3, len(sfrm))):
        a.hold_point = "Special inspector — SFRM thickness & density verification"

    return milestones


def apply_cold_weather_trades(acts: list[Act], cal_by_id: dict[str, Calendar]) -> int:
    """Swap hot-weather registry rows for cold-weather rows on winter activities."""
    n = 0
    for a in acts:
        if a.trade_id in COLD_SWAP:
            start = cal_by_id[a.calendar_id].datetime_at(a.es)
            if start.month in (12, 1, 2):
                a.trade_id = COLD_SWAP[a.trade_id]
                a.name = a.name.replace("pour", "pour (cold weather protection)")
                n += 1
    return n


# --------------------------------------------------------------------------- #
# Emit
# --------------------------------------------------------------------------- #

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _separation_m(f1: dict, f2: dict) -> float:
    """Planar distance between two work-face centroids, metres (equirectangular)."""
    dlat = (f2["centroid_lat"] - f1["centroid_lat"]) * _M_PER_DEG_LAT
    dlon = (f2["centroid_lon"] - f1["centroid_lon"]) * _M_PER_DEG_LON
    return round(math.hypot(dlat, dlon), 1)


def _hero_pair(faces: list[dict], act_json: list[dict]) -> dict | None:
    """The §2.2 hero pair: two FAB2 deck faces on the same slab, one bare
    (open_deck, psi 0.97) and one shaded by erected steel (psi 0.45), both
    carrying a `coating_epoxy_structural_steel` activity — so T1 can hard-link
    them and show the same trade diverge purely on exposure.

    The FAB2 deck is a 187.5 m grid pitch, so a same-level bare/shaded pair sits
    ~188 m apart, not the ~300 m the plan's prose quotes. We record the ACTUAL
    separation here (appendix note: never let the slide say 300 m while the data
    says otherwise). Among candidate pairs we pick the one whose coating days are
    closest together, since the demo shows the two ribbons for the same day.
    """
    coating_day: dict[str, str] = {}
    for a in act_json:
        if a["trade_id"] == "coating_epoxy_structural_steel" and a["structure_id"] == "FAB2":
            coating_day.setdefault(a["work_face_id"], a["planned_start"][:10])

    by_id = {f["id"]: f for f in faces}
    deck = [f for f in faces if f["structure_id"] == "FAB2" and "deck" in f["level"]
            and f["id"] in coating_day]
    best: tuple | None = None
    for bare in (f for f in deck if f["exposure_class"] == "open_deck"):
        for shaded in (f for f in deck if f["exposure_class"] == "shaded_by_steel"):
            if bare["level"] != shaded["level"]:
                continue                                # "same slab" = same level
            sep = _separation_m(bare, shaded)
            gap = abs(date.fromisoformat(coating_day[bare["id"]])
                      - date.fromisoformat(coating_day[shaded["id"]])).days
            key = (gap, abs(sep - 300.0))               # prefer same day, then nearest 300 m
            if best is None or key < best[0]:
                best = (key, bare["id"], shaded["id"], sep)
    if best is None:
        return None
    (gap, _), bare_id, shaded_id, sep = best
    return {
        "bare": bare_id,
        "shaded": shaded_id,
        "separation_m": sep,
        "level": by_id[bare_id]["level"],
        "bare_coating_day": coating_day[bare_id],
        "shaded_coating_day": coating_day[shaded_id],
        "sky_view_factor": {"bare": by_id[bare_id]["sky_view_factor"],
                            "shaded": by_id[shaded_id]["sky_view_factor"]},
        "coating_day_gap_d": gap,
        "note": f"Same {by_id[bare_id]['level']} slab, coating on both ({gap} day apart). "
                f"Separation is the {sep:g} m FAB2 deck grid pitch — quote this number, "
                f"not the plan's ~300 m prose.",
    }


def emit(out_dir: Path) -> dict:
    rng = random.Random(SEED)
    faces = build_work_faces()
    acts = build_activities(faces, rng)

    finish = forward_pass(acts)
    backward_pass(acts, finish)
    apply_milestones(acts, finish, rng)
    forward_pass(acts)                      # milestones do not move ES, but re-run for safety
    backward_pass(acts, finish)
    n_cold = apply_cold_weather_trades(acts, CALENDARS)

    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- site.geojson ------------------------------------------------------ #
    site_ring = [(0, 0), (SITE_W_M, 0), (SITE_W_M, SITE_H_M - 260),
                 (SITE_W_M - 320, SITE_H_M), (0, SITE_H_M), (0, 0)]
    site = {
        "type": "FeatureCollection",
        "name": "workface_site",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "site_id": PROJECT_ID,
                "site_name": PROJECT_NAME,
                "locality": "North Phoenix, Maricopa County, Arizona, USA",
                "area_acres": round(SITE_W_M * SITE_H_M / 4046.856, 1),
                "area_km2": round(SITE_W_M * SITE_H_M / 1e6, 3),
                "tz": TZ_NAME,
                "utc_offset_hours": UTC_OFFSET_H,
                "dst": False,
                "base_elevation_m": BASE_ELEV_M,
                "geography_note": "Real North Phoenix industrial-corridor geography (I-17 / SR-303, Dove Valley). Structures and schedule are synthetic.",
                "provenance": "Synthetic schedule, real geography, real standards.",
            },
            "geometry": {"type": "Polygon",
                         "coordinates": [[list(enu_to_lonlat(x, y)) for x, y in site_ring]]},
        }],
    }
    (out_dir / "site.geojson").write_text(json.dumps(site, indent=2) + "\n")

    # ---- work_faces.geojson ------------------------------------------------ #
    wf_features = []
    for f in faces:
        props = {k: v for k, v in f.items() if not k.startswith("_") and k != "geom"}
        wf_features.append({"type": "Feature", "properties": props, "geometry": f["geom"]})
    (out_dir / "work_faces.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "name": "workface_work_faces",
         "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
         "features": wf_features}, indent=2) + "\n")

    # ---- activities.json (the ProjectSchedule handoff) ---------------------- #
    hpd = {cid: c.hours_per_day for cid, c in CALENDARS.items()}
    act_json, prec_json = [], []
    for a in acts:
        cal = CALENDARS[a.calendar_id]
        tf_d = round(a.total_float_h / hpd[a.calendar_id], 2)
        ff_d = round(a.free_float_h / hpd[a.calendar_id], 2)
        act_json.append({
            "id": a.id, "wbs": a.wbs, "name": a.name,
            "work_face_id": a.work_face_id, "structure_id": a.structure_id,
            "trade_id": a.trade_id, "thermal_sensitive": a.trade_id is not None,
            "discipline": a.discipline,
            "planned_start": _iso(cal.datetime_at(a.es)),
            "planned_finish": _iso(cal.datetime_at(a.ef)),
            "duration_h": a.duration_h,
            "duration_d": round(a.duration_h / hpd[a.calendar_id], 2),
            "calendar_id": a.calendar_id,
            "crew_size": a.crew_size, "quantity": a.quantity, "quantity_unit": a.quantity_unit,
            "early_start": _iso(cal.datetime_at(a.es)),
            "early_finish": _iso(cal.datetime_at(a.ef)),
            "late_start": _iso(cal.datetime_at(a.ls)),
            "late_finish": _iso(cal.datetime_at(a.lf)),
            "total_float_d": tf_d, "free_float_d": ff_d,
            "is_critical": tf_d <= 0.01,
            "is_near_critical": 0.01 < tf_d <= NEAR_CRITICAL_FLOAT_D,
            "milestone_date": _iso(cal.datetime_at(a.milestone_h)) if a.milestone_h is not None else None,
            "milestone_name": a.milestone_name,
            "hold_point": a.hold_point,
            "iwp_id": a.iwp_id,
        })
        for pid, link, lag in a.preds:
            prec_json.append({"activity_id": a.id, "pred_id": pid, "link_type": link, "lag_h": lag})

    schedule = {
        "schema_version": "1.0.0",
        "project_id": PROJECT_ID,
        "project_name": PROJECT_NAME,
        "data_date": _iso(DATA_DATE),
        "tz": TZ_NAME,
        "utc_offset_hours": UTC_OFFSET_H,
        "site_geojson_ref": "data/project_demo/site.geojson",
        "work_faces_geojson_ref": "data/project_demo/work_faces.geojson",
        "provenance": "Synthetic schedule, real geography, real standards. Not a real contractor's programme.",
        "calendars": [{
            "id": c.id, "name": c.name, "workdays": list(c.workdays),
            "shift_start_h": c.shift_start_h, "shift_end_h": c.shift_end_h,
            "hours_per_day": c.hours_per_day, "holidays": list(c.holidays),
        } for c in CALENDARS.values()],
        "work_faces": [{k: v for k, v in f.items() if not k.startswith("_")} for f in faces],
        "activities": act_json,
        "precedences": prec_json,
    }
    (out_dir / "activities.json").write_text(json.dumps(schedule, indent=2) + "\n")

    # ---- stats.json -------------------------------------------------------- #
    in_window = [
        a for a in act_json
        if datetime.fromisoformat(a["planned_start"]) < DEMO_WINDOW_END
        and datetime.fromisoformat(a["planned_finish"]) > DEMO_WINDOW_START
    ]
    trade_counts: dict[str, int] = {}
    for a in act_json:
        if a["trade_id"]:
            trade_counts[a["trade_id"]] = trade_counts.get(a["trade_id"], 0) + 1

    hero_pair = _hero_pair(faces, act_json)

    stats = {
        "generated_at": _iso(datetime.now(TZ)),
        "seed": SEED,
        "work_faces": len(faces),
        "activities": len(act_json),
        "precedences": len(prec_json),
        "thermal_sensitive": sum(1 for a in act_json if a["thermal_sensitive"]),
        "critical": sum(1 for a in act_json if a["is_critical"]),
        "near_critical": sum(1 for a in act_json if a["is_near_critical"]),
        "milestones": sum(1 for a in act_json if a["milestone_date"]),
        "hold_points": sum(1 for a in act_json if a["hold_point"]),
        "cold_weather_swapped": n_cold,
        "project_start": _iso(CAL_6x10.datetime_at(0)),
        "project_finish": _iso(CAL_6x10.datetime_at(finish)),
        "demo_window": {"start": _iso(DEMO_WINDOW_START), "end": _iso(DEMO_WINDOW_END)},
        "in_demo_window": {
            "activities": len(in_window),
            "thermal_sensitive": sum(1 for a in in_window if a["thermal_sensitive"]),
            "work_faces_touched": len({a["work_face_id"] for a in in_window}),
            "by_trade": {t: sum(1 for a in in_window if a["trade_id"] == t)
                         for t in sorted({a["trade_id"] for a in in_window if a["trade_id"]})},
        },
        "by_trade_whole_project": dict(sorted(trade_counts.items())),
        "hero_pair": hero_pair,
    }
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="WORKFACE synthetic project generator (T3, Day 2)")
    ap.add_argument("--out", default="data/project_demo", type=Path)
    args = ap.parse_args()
    stats = emit(args.out)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
