"""Day-7 mock site-systems adapter — agent action surface.

Crew calendar, ready-mix slots, lighting capacity, heated-enclosure inventory.
Deterministic, offline, REPLAY-friendly. No real ERP.

    python -m apps.api.sitefeeds.sitesystems --write-fixture
    python -m apps.api.sitefeeds.sitesystems --check night_shift --when 2026-08-25T20:00:00-07:00
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

REPO = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO / "data" / "mitigations" / "catalog.json"
FIXTURE_PATH = REPO / "data" / "fixtures" / "site_systems.json"

TZ = timezone(timedelta(hours=-7))

# Demo window (matches generator DATA_DATE / demo horizon)
DEMO_START = date(2026, 8, 24)
DEMO_END = date(2026, 8, 30)


SystemName = Literal["crew_calendar", "ready_mix", "lighting", "heated_enclosure"]


@dataclass(frozen=True)
class Availability:
    available: bool
    system: SystemName
    reason: str
    detail: dict[str, Any]


def _parse_when(when: str | datetime | None) -> datetime:
    if when is None:
        return datetime(2026, 8, 25, 14, 0, tzinfo=TZ)
    if isinstance(when, datetime):
        return when if when.tzinfo else when.replace(tzinfo=TZ)
    s = when.strip()
    if s.endswith("Z"):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


class MockSiteSystems:
    """Fixed inventory + calendars for NPX-FAB-P2 demo week."""

    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self.snapshot = snapshot or default_snapshot()

    # ------------------------------------------------------------------
    # Public queries the agent / policy will call
    # ------------------------------------------------------------------

    def crew_available(
        self,
        *,
        trade_id: str | None,
        headcount: int,
        when: str | datetime,
        hours: float = 10.0,
    ) -> Availability:
        dt = _parse_when(when)
        day = dt.date().isoformat()
        cal = self.snapshot["crew_calendar"]
        day_row = cal["days"].get(day) or {"available_heads": cal["default_heads"], "notes": "default"}
        available_heads = int(day_row["available_heads"])
        reserved = int(day_row.get("reserved") or 0)
        free = max(0, available_heads - reserved)
        ok = free >= headcount and not day_row.get("blackout")
        return Availability(
            available=ok,
            system="crew_calendar",
            reason=(
                f"{free} heads free of {available_heads} on {day} (need {headcount})"
                if ok
                else f"insufficient crew on {day}: free={free}, need={headcount}"
                + (f" — {day_row.get('notes')}" if day_row.get("notes") else "")
            ),
            detail={
                "day": day,
                "free_heads": free,
                "requested": headcount,
                "trade_id": trade_id,
                "hours": hours,
            },
        )

    def ready_mix_slot(
        self,
        *,
        when: str | datetime,
        volume_m3: float | None = None,
    ) -> Availability:
        dt = _parse_when(when)
        day = dt.date().isoformat()
        hour = dt.hour
        plant = self.snapshot["ready_mix"]
        slots = plant["slots_by_day"].get(day) or []
        # slot is open if start hour matches a free slot
        open_slots = [s for s in slots if not s.get("booked")]
        match = next((s for s in open_slots if int(s["hour"]) == hour), None)
        if match is None:
            # nearest free same day
            match = open_slots[0] if open_slots else None
            ok = False
            reason = (
                f"no ready-mix slot at {hour:02d}:00 on {day}; "
                + (f"next free {match['hour']:02d}:00" if match else "plant full / no pour day")
            )
        else:
            ok = True
            reason = f"slot open {day} {match['hour']:02d}:00 ({match.get('plant', 'plant')})"
        return Availability(
            available=ok,
            system="ready_mix",
            reason=reason,
            detail={
                "day": day,
                "requested_hour": hour,
                "volume_m3": volume_m3,
                "open_slots": [s["hour"] for s in open_slots],
                "matched_hour": match["hour"] if match else None,
            },
        )

    def lighting_available(
        self,
        *,
        when: str | datetime,
        work_face_id: str | None = None,
    ) -> Availability:
        dt = _parse_when(when)
        hour = dt.hour
        lighting = self.snapshot["lighting"]
        # night work needs lighting: 19:00–05:00
        needs = hour >= 19 or hour < 5
        towers_free = int(lighting["towers_free"])
        zones = lighting.get("zones_covered") or []
        zone_ok = work_face_id is None or any(
            work_face_id.startswith(z) or z in (work_face_id or "") for z in zones
        ) or "FAB2" in zones
        if not needs:
            return Availability(
                available=True,
                system="lighting",
                reason="daytime — temporary lighting not required",
                detail={"hour": hour, "towers_free": towers_free, "needs_lighting": False},
            )
        ok = towers_free > 0 and zone_ok
        return Availability(
            available=ok,
            system="lighting",
            reason=(
                f"night lighting available ({towers_free} towers, zones={zones})"
                if ok
                else f"night lighting unavailable (towers_free={towers_free}, zone_ok={zone_ok})"
            ),
            detail={
                "hour": hour,
                "needs_lighting": True,
                "towers_free": towers_free,
                "work_face_id": work_face_id,
                "zones_covered": zones,
            },
        )

    def heated_enclosure_available(
        self,
        *,
        when: str | datetime,
        area_m2: float | None = None,
    ) -> Availability:
        dt = _parse_when(when)
        inv = self.snapshot["heated_enclosure"]
        units_free = int(inv["units_free"])
        max_m2 = float(inv["max_coverage_m2_per_unit"])
        need_units = 1
        if area_m2 and area_m2 > 0:
            need_units = max(1, int((area_m2 + max_m2 - 1) // max_m2))
        ok = units_free >= need_units
        return Availability(
            available=ok,
            system="heated_enclosure",
            reason=(
                f"{units_free} enclosure units free (need {need_units})"
                if ok
                else f"enclosure inventory short: free={units_free}, need={need_units}"
            ),
            detail={
                "when": dt.isoformat(),
                "units_free": units_free,
                "need_units": need_units,
                "area_m2": area_m2,
                "max_coverage_m2_per_unit": max_m2,
            },
        )

    def can_request_mitigation(
        self,
        mitigation_id: str,
        *,
        when: str | datetime,
        trade_id: str | None = None,
        work_face_id: str | None = None,
        headcount: int = 5,
        area_m2: float | None = None,
        volume_m3: float | None = None,
    ) -> dict[str, Any]:
        """Combine catalog rules + site systems into one agent-facing verdict."""
        catalog = load_catalog()
        mit = next((m for m in catalog["mitigations"] if m["id"] == mitigation_id), None)
        if mit is None:
            return {
                "ok": False,
                "mitigation_id": mitigation_id,
                "reason": f"unknown mitigation_id {mitigation_id}",
                "checks": [],
            }

        applies = mit.get("applies_to_trades") or []
        if trade_id and "*" not in applies and trade_id not in applies:
            return {
                "ok": False,
                "mitigation_id": mitigation_id,
                "reason": f"{mitigation_id} does not apply to trade {trade_id}",
                "checks": [],
                "mitigation": mit,
            }

        checks: list[dict[str, Any]] = []
        req = mit.get("requires_site_system")
        ok = True
        if req == "lighting":
            a = self.lighting_available(when=when, work_face_id=work_face_id)
            checks.append(a.__dict__)
            ok = ok and a.available
        elif req == "ready_mix":
            a = self.ready_mix_slot(when=when, volume_m3=volume_m3)
            checks.append(a.__dict__)
            ok = ok and a.available
        elif req == "heated_enclosure":
            a = self.heated_enclosure_available(when=when, area_m2=area_m2)
            checks.append(a.__dict__)
            ok = ok and a.available
        elif req == "crew_calendar":
            a = self.crew_available(trade_id=trade_id, headcount=headcount, when=when)
            checks.append(a.__dict__)
            ok = ok and a.available

        return {
            "ok": ok,
            "mitigation_id": mitigation_id,
            "reason": "all site-system checks passed" if ok else "one or more site systems blocked",
            "checks": checks,
            "mitigation": {
                "id": mit["id"],
                "name": mit["name"],
                "lead_time_h": mit["lead_time_h"],
                "cost_usd_per_day": mit["cost_usd_per_day"],
            },
            "when": _parse_when(when).isoformat(),
        }

    def as_dict(self) -> dict[str, Any]:
        return self.snapshot


def default_snapshot() -> dict[str, Any]:
    """Demo-week inventory. Tuned so some mitigations succeed and some deny."""
    days = []
    d = DEMO_START
    while d <= DEMO_END:
        days.append(d)
        d += timedelta(days=1)

    crew_days: dict[str, Any] = {}
    for i, day in enumerate(days):
        key = day.isoformat()
        # Wed 26 short crew → deny case for crew_augment
        if day.weekday() == 2:  # Wednesday
            crew_days[key] = {
                "available_heads": 12,
                "reserved": 10,
                "blackout": False,
                "notes": "half the structural crew on FAB1 outage support",
            }
        elif day.weekday() == 6:  # Sunday
            crew_days[key] = {
                "available_heads": 4,
                "reserved": 0,
                "blackout": True,
                "notes": "Sunday — skeleton crew only",
            }
        else:
            crew_days[key] = {
                "available_heads": 28,
                "reserved": 8 + (i % 3),
                "blackout": False,
                "notes": None,
            }

    ready: dict[str, list] = {}
    for day in days:
        key = day.isoformat()
        if day.weekday() >= 5:  # Sat/Sun limited
            ready[key] = [
                {"hour": 6, "booked": False, "plant": "Phoenix Plant 3"},
                {"hour": 10, "booked": True, "plant": "Phoenix Plant 3"},
            ]
        else:
            ready[key] = [
                {"hour": 5, "booked": False, "plant": "Phoenix Plant 3"},
                {"hour": 6, "booked": False, "plant": "Phoenix Plant 3"},
                {"hour": 7, "booked": True, "plant": "Phoenix Plant 3"},
                {"hour": 14, "booked": False, "plant": "Phoenix Plant 3"},
                {"hour": 15, "booked": True, "plant": "Phoenix Plant 3"},
            ]

    return {
        "schema_version": "1.0.0",
        "site_id": "NPX-FAB-P2",
        "generated_for": "Day-7 mock site systems — agent action surface",
        "tz": "America/Phoenix",
        "crew_calendar": {
            "default_heads": 24,
            "days": crew_days,
        },
        "ready_mix": {
            "plant": "Phoenix Plant 3",
            "lead_time_h": 18,
            "slots_by_day": ready,
        },
        "lighting": {
            "towers_total": 6,
            "towers_free": 2,
            "zones_covered": ["FAB2", "UTIL", "SOUTH"],
            "notes": "2 light plants on rent through 30 Aug; PARK/ROAD not covered at night",
        },
        "heated_enclosure": {
            "units_total": 3,
            "units_free": 1,
            "max_coverage_m2_per_unit": 200.0,
            "notes": "One 200 m² heated tent free; two units already on FAB2 L1 cure",
        },
    }


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def write_fixture(path: Path | None = None) -> Path:
    path = path or FIXTURE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    snap = default_snapshot()
    # attach catalog summary
    cat = load_catalog()
    payload = {
        **snap,
        "mitigation_ids": [m["id"] for m in cat["mitigations"]],
        "catalog_ref": "data/mitigations/catalog.json",
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mock site systems + mitigation checks")
    parser.add_argument("--write-fixture", action="store_true")
    parser.add_argument("--check", type=str, help="mitigation_id to test")
    parser.add_argument("--when", type=str, default="2026-08-25T20:00:00-07:00")
    parser.add_argument("--trade", type=str, default="coating_epoxy_structural_steel")
    parser.add_argument("--face", type=str, default="WF-FAB2-07")
    args = parser.parse_args(argv)

    if args.write_fixture:
        if not CATALOG_PATH.exists():
            raise SystemExit(f"missing catalog {CATALOG_PATH}")
        path = write_fixture()
        print(f"wrote {path}")
        return 0

    systems = MockSiteSystems()
    if args.check:
        result = systems.can_request_mitigation(
            args.check,
            when=args.when,
            trade_id=args.trade,
            work_face_id=args.face,
        )
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
