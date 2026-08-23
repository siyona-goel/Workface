"""
WORKFACE — the sequencer: a greedy interval packer.  T3, Day 7, Task A (§7.2).

    from apps.api.sequencer.pack import pack, PackActivity, YamlCrewSource

NO LLM IN THIS FILE, EVER (hard rule 1 / §7). The packer is deterministic,
testable and explicable; the model never sees an interval. The LLM's only job is
to choose WHICH strategy to attempt (loop.py PROPOSE); the arithmetic is here.

The algorithm (WORKFACE_TECH_SPEC §7.2, the committed Day-7 implementation):

  1. Topologically sort by precedence (the FS links in activities.json).
  2. Within the topo order, take tightest-float-first (ascending total_float_d).
  3. Place each activity in its EARLIEST feasible open interval, where feasible
     means: inside an OpenInterval from the window engine, precedence satisfied
     (starts no earlier than every predecessor's placed finish + lag), crew
     capacity respected, and — the part that is easy to forget — LONG ENOUGH IN
     PRODUCTIVE HOURS, not clock hours. OpenInterval.productive_h already carries
     the WBGT haircut; that is the number we pack against.
  4. Backtrack ONE level on failure (not a full search): bump the previously
     placed activity to its next-later interval once, then retry.

The result distinguishes three outcomes per activity (§7.2, §4 of the brief):
  * PLACED               — fits at its planned start, no float spent.
  * PLACED_FLOAT_SPENT   — fits, but later than planned; `float_days_consumed` says how much.
  * UNPLACEABLE          — no feasible interval; `blocked_by` NAMES the constraint.
UNPLACEABLE is not a failure — it is the input to the escalation (§7.2: provable
infeasibility is the *good* answer to give a superintendent).

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Protocol

from packages.schemas.window_eval import OpenInterval, WindowEval

_REPO_ROOT = Path(__file__).resolve().parents[3]
CREWS_YAML = _REPO_ROOT / "config" / "crews.yaml"


# --------------------------------------------------------------------------- #
# Inputs / outputs
# --------------------------------------------------------------------------- #

class PlaceStatus(str, Enum):
    PLACED = "placed"
    PLACED_FLOAT_SPENT = "placed_float_spent"
    UNPLACEABLE = "unplaceable"


class BlockingConstraint(str, Enum):
    """WHY an activity could not be placed. Named, never a bare exception (§4)."""
    NO_OPEN_INTERVAL = "no_open_interval"                    # window engine found none (incl. continuity horizon truncation)
    INSUFFICIENT_PRODUCTIVE_HOURS = "insufficient_productive_hours"  # intervals exist, none long enough after the WBGT haircut
    PRECEDENCE_BLOCKED = "precedence_blocked"               # every long-enough interval starts before a predecessor can finish
    CREW_UNAVAILABLE = "crew_unavailable"                   # every otherwise-feasible interval fails crew capacity


@dataclass(frozen=True)
class PackActivity:
    """One activity the packer must place. Built from a WindowEval (see
    `activity_from_eval`) but standalone so the sequencer suite needs no loop."""
    id: str
    trade_id: str
    work_face_id: str
    needed_productive_h: float          # duration_h — the productive crew-hours of work content
    crew_size: int
    total_float_d: float
    planned_start: datetime
    open_intervals: list[OpenInterval]  # usable intervals from evaluate_window, ascending by start
    predecessors: list[str] = field(default_factory=list)   # ids also in this pack set
    lag_h: dict[str, float] = field(default_factory=dict)    # pred_id -> FS lag hours


def activity_from_eval(
    ev: WindowEval,
    *,
    crew_size: int,
    total_float_d: float,
    predecessors: list[str] | None = None,
    lag_h: dict[str, float] | None = None,
    needed_productive_h: float | None = None,
) -> PackActivity:
    """Build a PackActivity from a WindowEval. `needed_productive_h` defaults to
    the scheduled bar's duration (its productive work content); the open intervals
    are the window engine's usable (open+marginal) intervals, exactly what the
    packer packs against. The loop calls this for every flagged activity."""
    return PackActivity(
        id=ev.activity_id,
        trade_id=ev.trade_id,
        work_face_id=ev.work_face_id,
        needed_productive_h=needed_productive_h if needed_productive_h is not None else ev.scheduled.duration_h,
        crew_size=crew_size,
        total_float_d=total_float_d,
        planned_start=ev.scheduled.start,
        open_intervals=list(ev.open_intervals),
        predecessors=predecessors or [],
        lag_h=lag_h or {},
    )


@dataclass
class Placement:
    activity_id: str
    status: PlaceStatus
    start: datetime | None = None
    finish: datetime | None = None
    float_days_consumed: float = 0.0
    interval_start: datetime | None = None
    blocked_by: BlockingConstraint | None = None
    reason: str = ""


@dataclass
class PackResult:
    placements: dict[str, Placement]
    order: list[str]                    # the processing order actually used

    @property
    def placed(self) -> list[Placement]:
        return [p for p in self.placements.values() if p.status is not PlaceStatus.UNPLACEABLE]

    @property
    def unplaceable(self) -> list[Placement]:
        return [p for p in self.placements.values() if p.status is PlaceStatus.UNPLACEABLE]

    @property
    def total_float_days_consumed(self) -> float:
        return round(sum(p.float_days_consumed for p in self.placed), 4)


# --------------------------------------------------------------------------- #
# Crew capacity — injectable (§5). Default: config/crews.yaml. Override: T2's
# MockSiteSystems, so the packer can be tested against the real committed feed.
# --------------------------------------------------------------------------- #

class CrewSource(Protocol):
    def capacity(self, trade_id: str, when: datetime) -> int:
        """Total heads of `trade_id` available on the shift containing `when`."""
        ...

    def snap_to_shift(self, when: datetime) -> datetime | None:
        """The earliest working-shift start at or after `when`, or None if no shift
        is reachable. A source with 24 h operations returns `when` unchanged."""
        ...


class YamlCrewSource:
    """The auditable on-a-slide default. Reads config/crews.yaml (§5).

    Honours the day-shift window: a placement cannot start outside [start_hour,
    end_hour) or on a skeleton-crew Sunday, so the packer never silently books a
    night crew — night work stays a human decision (policy rule no_auto_night_work),
    reached only through the night_shift mitigation (which needs a lighting plan)."""

    _WEEKDAY = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

    def __init__(self, path: Path | None = None) -> None:
        import yaml
        cfg = yaml.safe_load((path or CREWS_YAML).read_text(encoding="utf-8"))
        self._default = int(cfg.get("default_heads", 12))
        self._trades = {t: int(v["heads"]) for t, v in (cfg.get("trades") or {}).items()}
        shift = cfg.get("shift") or {}
        self._start_hour = int(shift.get("start_hour", 6))
        self._end_hour = int(shift.get("end_hour", 18))
        self._work_days = {self._WEEKDAY[d] for d in (shift.get("days") or list(self._WEEKDAY))}

    def _is_shift_day(self, when: datetime) -> bool:
        return when.weekday() in self._work_days

    def capacity(self, trade_id: str, when: datetime) -> int:
        if not self._is_shift_day(when) or not (self._start_hour <= when.hour < self._end_hour):
            return 0
        return self._trades.get(trade_id, self._default)

    def snap_to_shift(self, when: datetime) -> datetime | None:
        d = when
        for _ in range(8):                                  # scan up to a week of shifts
            if self._is_shift_day(d):
                day_start = d.replace(hour=self._start_hour, minute=0, second=0, microsecond=0)
                day_end = d.replace(hour=self._end_hour, minute=0, second=0, microsecond=0)
                if d < day_start:
                    return day_start
                if day_start <= d < day_end:
                    return d
            d = (d + timedelta(days=1)).replace(hour=self._start_hour, minute=0, second=0, microsecond=0)
        return None


class SiteSystemsCrewSource:
    """Override wrapping T2's MockSiteSystems (§5). Free heads = the committed
    snapshot's per-day availability, so the deliberate short-crew Wednesday and
    the Sunday skeleton crew flow straight into the packer."""

    def __init__(self, systems) -> None:  # MockSiteSystems, kept untyped to avoid a hard import
        self._systems = systems

    def capacity(self, trade_id: str, when: datetime) -> int:
        # crew_available with headcount=0 always reports available; we read the
        # free-head count out of its detail so the packer keeps its own booking.
        a = self._systems.crew_available(trade_id=trade_id, headcount=0, when=when)
        return int(a.detail.get("free_heads", 0))

    def snap_to_shift(self, when: datetime) -> datetime | None:
        return when                                         # the mock models 24 h availability


# --------------------------------------------------------------------------- #
# Topological order, tightest float first
# --------------------------------------------------------------------------- #

def _topo_float_order(acts: dict[str, PackActivity]) -> list[str]:
    """Kahn's algorithm restricted to the in-set predecessors, breaking ties by
    ascending total_float_d (tightest first, §7.2) then by id for determinism."""
    indeg = {aid: 0 for aid in acts}
    succ: dict[str, list[str]] = {aid: [] for aid in acts}
    for aid, a in acts.items():
        for p in a.predecessors:
            if p in acts:
                succ[p].append(aid)
                indeg[aid] += 1

    import heapq
    ready = [(acts[aid].total_float_d, aid) for aid, d in indeg.items() if d == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, aid = heapq.heappop(ready)
        order.append(aid)
        for s in succ[aid]:
            indeg[s] -= 1
            if indeg[s] == 0:
                heapq.heappush(ready, (acts[s].total_float_d, s))
    if len(order) != len(acts):        # a cycle (should not happen for FS DAG) — append the rest, tightest first
        rest = sorted((aid for aid in acts if aid not in order), key=lambda x: (acts[x].total_float_d, x))
        order.extend(rest)
    return order


# --------------------------------------------------------------------------- #
# Placement of a single activity into its earliest feasible interval
# --------------------------------------------------------------------------- #

def _earliest_allowed(a: PackActivity, placed: dict[str, Placement], anchor: datetime) -> datetime:
    """No earlier than the horizon anchor or any placed predecessor's finish + lag."""
    t = anchor
    for p in a.predecessors:
        pl = placed.get(p)
        if pl and pl.finish is not None:
            t = max(t, pl.finish + timedelta(hours=a.lag_h.get(p, 0.0)))
    return t


def _available_productive_h(iv: OpenInterval, from_ts: datetime) -> float:
    """Productive hours in `iv` from `from_ts` onward. Prorated linearly across
    the interval when the start is pushed inside it (documented approximation —
    the whole-interval productive_h already carries the exact WBGT haircut)."""
    if from_ts <= iv.start:
        return iv.productive_h
    if from_ts >= iv.end:
        return 0.0
    span = (iv.end - iv.start).total_seconds()
    remaining = (iv.end - from_ts).total_seconds()
    return round(iv.productive_h * (remaining / span), 4) if span > 0 else 0.0


def _clock_span_for(iv: OpenInterval, productive_needed: float) -> float:
    """Clock hours needed to accrue `productive_needed` productive hours, at this
    interval's productive:clock ratio."""
    if iv.productive_h <= 0:
        return productive_needed
    ratio = iv.duration_h / iv.productive_h
    return productive_needed * ratio


def _try_place(
    a: PackActivity,
    placed: dict[str, Placement],
    crew: CrewSource,
    committed: dict[tuple[str, str], int],
    anchor: datetime,
) -> Placement:
    """Find the earliest feasible interval. Returns a PLACED / PLACED_FLOAT_SPENT
    placement, or an UNPLACEABLE one naming the tightest blocking constraint."""
    if not a.open_intervals:
        return Placement(a.id, PlaceStatus.UNPLACEABLE,
                         blocked_by=BlockingConstraint.NO_OPEN_INTERVAL,
                         reason="the window engine found no usable interval on the horizon "
                                "(closed, or a continuity run extends past the horizon — fail closed)")

    earliest = _earliest_allowed(a, placed, anchor)
    saw_long_enough = False        # at least one interval had the productive hours, ignoring precedence
    saw_after_precedence = False   # at least one long-enough interval also cleared precedence
    crew_blocked = False

    for iv in sorted(a.open_intervals, key=lambda x: x.start):
        if iv.productive_h + 1e-9 < a.needed_productive_h:
            continue                                  # not long enough even ignoring everything else
        saw_long_enough = True
        # Earliest start = no earlier than precedence allows, snapped forward to a
        # working day-shift start (so the packer never books a night crew).
        raw_start = max(iv.start, earliest)
        start = crew.snap_to_shift(raw_start)
        if start is None or start >= iv.end:
            crew_blocked = True                       # no day shift reaches this window
            continue
        if _available_productive_h(iv, start) + 1e-9 < a.needed_productive_h:
            continue                                  # precedence / shift start pushed too far into this interval
        saw_after_precedence = True

        day = start.date().isoformat()
        key = (a.trade_id, day)
        used = committed.get(key, 0)
        if used + a.crew_size > crew.capacity(a.trade_id, start):
            crew_blocked = True
            continue

        finish = start + timedelta(hours=_clock_span_for(iv, a.needed_productive_h))
        float_spent = max(0.0, round((start - a.planned_start).total_seconds() / 86400.0, 4))
        committed[key] = used + a.crew_size
        status = PlaceStatus.PLACED if float_spent <= 1e-9 else PlaceStatus.PLACED_FLOAT_SPENT
        return Placement(
            a.id, status, start=start, finish=finish, float_days_consumed=float_spent,
            interval_start=iv.start,
            reason=(f"placed {start:%Y-%m-%d %H:%M}–{finish:%H:%M} in a "
                    f"{iv.productive_h:g} h productive window"
                    + (f"; {float_spent:g} d float consumed" if float_spent > 1e-9 else "; at planned start")),
        )

    # Nothing placed — report the tightest reason (most-specific first).
    if not saw_long_enough:
        blk, why = (BlockingConstraint.INSUFFICIENT_PRODUCTIVE_HOURS,
                    f"no open interval carries the {a.needed_productive_h:g} productive crew-hours "
                    f"this activity needs after the WBGT haircut")
    elif not saw_after_precedence:
        blk, why = (BlockingConstraint.PRECEDENCE_BLOCKED,
                    f"every long-enough interval starts before {earliest:%Y-%m-%d %H:%M}, "
                    f"the earliest a predecessor lets this activity begin")
    elif crew_blocked:
        blk, why = (BlockingConstraint.CREW_UNAVAILABLE,
                    f"every feasible interval is short of {a.trade_id} crew "
                    f"(need {a.crew_size} heads)")
    else:  # pragma: no cover - defensive
        blk, why = (BlockingConstraint.NO_OPEN_INTERVAL, "no feasible interval")
    return Placement(a.id, PlaceStatus.UNPLACEABLE, blocked_by=blk, reason=why)


def _uncommit(placement: Placement, a: PackActivity, committed: dict[tuple[str, str], int]) -> None:
    if placement.start is None:
        return
    key = (a.trade_id, placement.start.date().isoformat())
    if key in committed:
        committed[key] = max(0, committed[key] - a.crew_size)


# --------------------------------------------------------------------------- #
# The packer
# --------------------------------------------------------------------------- #

def pack(
    activities: list[PackActivity],
    *,
    crew: CrewSource | None = None,
    anchor: datetime | None = None,
) -> PackResult:
    """Greedy interval packer. See the module docstring. `crew` defaults to the
    YAML source (config/crews.yaml); pass SiteSystemsCrewSource to pack against
    T2's committed feed. `anchor` is the horizon start (no activity starts before
    it); defaults to the earliest planned start in the set."""
    crew = crew or YamlCrewSource()
    acts = {a.id: a for a in activities}
    if anchor is None:
        anchor = min((a.planned_start for a in activities), default=datetime.now())

    order = _topo_float_order(acts)
    placed: dict[str, Placement] = {}
    committed: dict[tuple[str, str], int] = {}

    for idx, aid in enumerate(order):
        a = acts[aid]
        res = _try_place(a, placed, crew, committed, anchor)

        # Backtrack ONE level (§7.2): if this activity is blocked by crew or
        # precedence, bump the previously placed activity to its next interval
        # once, then retry this one. Not a full search.
        if res.status is PlaceStatus.UNPLACEABLE and res.blocked_by in (
            BlockingConstraint.CREW_UNAVAILABLE, BlockingConstraint.PRECEDENCE_BLOCKED,
        ) and idx > 0:
            prev_id = order[idx - 1]
            prev = placed.get(prev_id)
            if prev and prev.status is not PlaceStatus.UNPLACEABLE:
                prev_act = acts[prev_id]
                _uncommit(prev, prev_act, committed)
                bumped = _place_after(prev_act, placed, crew, committed, anchor, after=prev.finish)
                placed[prev_id] = bumped if bumped.status is not PlaceStatus.UNPLACEABLE else prev
                if bumped.status is PlaceStatus.UNPLACEABLE:      # bump failed — restore the original commit
                    _recommit(prev, prev_act, committed)
                res = _try_place(a, placed, crew, committed, anchor)

        placed[aid] = res

    return PackResult(placements=placed, order=order)


def _recommit(placement: Placement, a: PackActivity, committed: dict[tuple[str, str], int]) -> None:
    if placement.start is None:
        return
    key = (a.trade_id, placement.start.date().isoformat())
    committed[key] = committed.get(key, 0) + a.crew_size


def _place_after(
    a: PackActivity,
    placed: dict[str, Placement],
    crew: CrewSource,
    committed: dict[tuple[str, str], int],
    anchor: datetime,
    *,
    after: datetime | None,
) -> Placement:
    """Re-place `a` into its earliest feasible interval that starts at or after
    `after` — the one-level backtrack primitive."""
    floor = max(anchor, after) if after else anchor
    shifted = PackActivity(
        id=a.id, trade_id=a.trade_id, work_face_id=a.work_face_id,
        needed_productive_h=a.needed_productive_h, crew_size=a.crew_size,
        total_float_d=a.total_float_d, planned_start=a.planned_start,
        open_intervals=[iv for iv in a.open_intervals if iv.end > floor],
        predecessors=a.predecessors, lag_h=a.lag_h,
    )
    # anchor=floor forces the re-placement to start at or after the bump point.
    return _try_place(shifted, placed, crew, committed, floor)


__all__ = [
    "PlaceStatus", "BlockingConstraint", "PackActivity", "Placement", "PackResult",
    "CrewSource", "YamlCrewSource", "SiteSystemsCrewSource", "pack", "activity_from_eval",
]
