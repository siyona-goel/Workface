"""Day-6 schedule import → canonical ProjectSchedule shape.

    # Guaranteed path
    python -m apps.api.schedule.importer --csv data/project_demo/schedule_export.csv --write

    # Stretch (needs xerparser or PyP6Xer)
    python -m apps.api.schedule.importer --xer path/to/programme.xer --write

    # Round-trip check against T3 generator output
    python -m apps.api.schedule.importer --from-json data/project_demo/activities.json --export-csv data/project_demo/schedule_export.csv

Output matches packages/schemas/activity.py (ProjectSchedule).
CSV is documented as the fallback when XER is unavailable or fails.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO / "data" / "project_demo" / "activities_imported.json"
DEMO_JSON = REPO / "data" / "project_demo" / "activities.json"
SAMPLE_CSV = REPO / "data" / "project_demo" / "schedule_export.csv"
SAMPLE_PRED_CSV = REPO / "data" / "project_demo" / "schedule_predecessors.csv"

TZ = timezone(timedelta(hours=-7))
SCHEMA_VERSION = "1.0.0"

DISCIPLINES = {
    "civil",
    "structural",
    "architectural",
    "mechanical",
    "electrical",
    "sitework",
}

LINK_TYPES = {"FS", "SS", "FF", "SF"}

# CSV column map (header → Activity field). Extra columns ignored.
CSV_ACTIVITY_COLUMNS = [
    "id",
    "wbs",
    "name",
    "work_face_id",
    "structure_id",
    "trade_id",
    "thermal_sensitive",
    "discipline",
    "planned_start",
    "planned_finish",
    "duration_h",
    "duration_d",
    "calendar_id",
    "crew_size",
    "quantity",
    "quantity_unit",
    "early_start",
    "early_finish",
    "late_start",
    "late_finish",
    "total_float_d",
    "free_float_d",
    "is_critical",
    "is_near_critical",
    "milestone_date",
    "milestone_name",
    "hold_point",
    "iwp_id",
]

CSV_PRED_COLUMNS = ["activity_id", "pred_id", "link_type", "lag_h"]


def _parse_bool(val: Any, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "y", "t"):
        return True
    if s in ("0", "false", "no", "n", "f"):
        return False
    return default


def _parse_float(val: Any, default: float | None = None) -> float | None:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _parse_int(val: Any, default: int | None = None) -> int | None:
    if val is None or val == "":
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _parse_dt(val: Any) -> str | None:
    """Return ISO-8601 string with offset, or None."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=TZ)
        return val.isoformat()
    s = str(val).strip()
    if not s:
        return None
    # already ISO-ish
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.isoformat()
    except ValueError:
        pass
    # common P6 / Excel forms
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%d-%b-%Y %H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=TZ)
            return dt.isoformat()
        except ValueError:
            continue
    raise ValueError(f"unparseable datetime: {val!r}")


def _default_calendars() -> list[dict[str, Any]]:
    holidays = [
        "2026-07-03",
        "2026-09-07",
        "2026-11-26",
        "2026-11-27",
        "2026-12-24",
        "2026-12-25",
        "2027-01-01",
    ]
    return [
        {
            "id": "CAL-6x10",
            "name": "Field 6x10 (Mon-Sat 06:00-16:00)",
            "workdays": [1, 2, 3, 4, 5, 6],
            "shift_start_h": 6.0,
            "shift_end_h": 16.0,
            "hours_per_day": 10.0,
            "holidays": holidays,
        },
        {
            "id": "CAL-5x8",
            "name": "Fit-out 5x8 (Mon-Fri 07:00-15:00)",
            "workdays": [1, 2, 3, 4, 5],
            "shift_start_h": 7.0,
            "shift_end_h": 15.0,
            "hours_per_day": 8.0,
            "holidays": holidays,
        },
    ]


def _row_to_activity(row: dict[str, str]) -> dict[str, Any]:
    trade_id = (row.get("trade_id") or "").strip() or None
    thermal = _parse_bool(row.get("thermal_sensitive"), default=bool(trade_id))
    if trade_id:
        thermal = True
    else:
        thermal = False

    discipline = (row.get("discipline") or "civil").strip().lower()
    if discipline not in DISCIPLINES:
        discipline = "civil"

    duration_h = _parse_float(row.get("duration_h"))
    duration_d = _parse_float(row.get("duration_d"))
    if duration_h is None or duration_h <= 0:
        duration_h = 8.0
    if duration_d is None or duration_d <= 0:
        duration_d = duration_h / 10.0

    planned_start = _parse_dt(row.get("planned_start"))
    planned_finish = _parse_dt(row.get("planned_finish"))
    if not planned_start:
        planned_start = datetime(2026, 8, 24, 7, 0, tzinfo=TZ).isoformat()
    if not planned_finish:
        # naive: start + duration hours on clock (good enough for import)
        start_dt = datetime.fromisoformat(planned_start)
        planned_finish = (start_dt + timedelta(hours=duration_h)).isoformat()

    total_float = _parse_float(row.get("total_float_d"), 0.0) or 0.0
    is_critical = _parse_bool(row.get("is_critical"), default=total_float <= 0)
    is_near = _parse_bool(
        row.get("is_near_critical"),
        default=(0 < total_float <= 3.0),
    )

    act = {
        "id": (row.get("id") or "").strip(),
        "wbs": (row.get("wbs") or "").strip() or "IMPORTED",
        "name": (row.get("name") or "").strip() or "Unnamed activity",
        "work_face_id": (row.get("work_face_id") or "").strip() or "WF-UNKNOWN",
        "structure_id": (row.get("structure_id") or "").strip() or "UNKNOWN",
        "trade_id": trade_id,
        "thermal_sensitive": thermal,
        "discipline": discipline,
        "planned_start": planned_start,
        "planned_finish": planned_finish,
        "duration_h": duration_h,
        "duration_d": duration_d,
        "calendar_id": (row.get("calendar_id") or "CAL-6x10").strip(),
        "crew_size": _parse_int(row.get("crew_size"), 1) or 1,
        "quantity": _parse_float(row.get("quantity")),
        "quantity_unit": (row.get("quantity_unit") or "").strip() or None,
        "early_start": _parse_dt(row.get("early_start")),
        "early_finish": _parse_dt(row.get("early_finish")),
        "late_start": _parse_dt(row.get("late_start")),
        "late_finish": _parse_dt(row.get("late_finish")),
        "total_float_d": total_float,
        "free_float_d": _parse_float(row.get("free_float_d"), 0.0) or 0.0,
        "is_critical": is_critical,
        "is_near_critical": is_near,
        "milestone_date": _parse_dt(row.get("milestone_date")),
        "milestone_name": (row.get("milestone_name") or "").strip() or None,
        "hold_point": (row.get("hold_point") or "").strip() or None,
        "iwp_id": (row.get("iwp_id") or "").strip() or None,
    }
    if not act["id"]:
        raise ValueError(f"activity row missing id: {row}")
    return act


def _row_to_precedence(row: dict[str, str]) -> dict[str, Any]:
    link = (row.get("link_type") or "FS").strip().upper()
    if link not in LINK_TYPES:
        link = "FS"
    return {
        "activity_id": (row.get("activity_id") or "").strip(),
        "pred_id": (row.get("pred_id") or "").strip(),
        "link_type": link,
        "lag_h": _parse_float(row.get("lag_h"), 0.0) or 0.0,
    }


def import_csv(
    activities_path: Path,
    predecessors_path: Path | None = None,
    *,
    work_faces: list[dict] | None = None,
    project_id: str = "IMPORTED",
    project_name: str = "Imported schedule",
) -> dict[str, Any]:
    """Parse activities CSV (+ optional predecessors CSV) → ProjectSchedule dict."""
    with activities_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        activities = [_row_to_activity(row) for row in reader]

    precedences: list[dict[str, Any]] = []
    pred_path = predecessors_path
    if pred_path is None:
        # convention: schedule_predecessors.csv next to schedule_export.csv
        candidate = activities_path.with_name(
            activities_path.stem.replace("export", "predecessors")
            if "export" in activities_path.stem
            else activities_path.stem + "_predecessors"
        ).with_suffix(".csv")
        # also try schedule_predecessors.csv in same dir
        alt = activities_path.parent / "schedule_predecessors.csv"
        if candidate.exists():
            pred_path = candidate
        elif alt.exists():
            pred_path = alt

    if pred_path and pred_path.exists():
        with pred_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p = _row_to_precedence(row)
                if p["activity_id"] and p["pred_id"] and p["activity_id"] != p["pred_id"]:
                    precedences.append(p)

    if work_faces is None and DEMO_JSON.exists():
        demo = json.loads(DEMO_JSON.read_text())
        work_faces = demo.get("work_faces") or []
        calendars = demo.get("calendars") or _default_calendars()
        data_date = demo.get("data_date") or datetime(2026, 8, 20, 6, 0, tzinfo=TZ).isoformat()
        site_ref = demo.get("site_geojson_ref") or "data/project_demo/site.geojson"
        wf_ref = demo.get("work_faces_geojson_ref") or "data/project_demo/work_faces.geojson"
        if project_id == "IMPORTED":
            project_id = demo.get("project_id") or project_id
            project_name = demo.get("project_name") or project_name
    else:
        calendars = _default_calendars()
        data_date = datetime(2026, 8, 20, 6, 0, tzinfo=TZ).isoformat()
        site_ref = "data/project_demo/site.geojson"
        wf_ref = "data/project_demo/work_faces.geojson"
        work_faces = work_faces or []

    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "project_name": project_name,
        "data_date": data_date,
        "tz": "America/Phoenix",
        "utc_offset_hours": -7.0,
        "site_geojson_ref": site_ref,
        "work_faces_geojson_ref": wf_ref,
        "provenance": (
            f"Imported from CSV ({activities_path.name}"
            + (f" + {pred_path.name}" if pred_path and pred_path.exists() else "")
            + "). CSV is the guaranteed schedule path; XER is optional."
        ),
        "calendars": calendars,
        "work_faces": work_faces,
        "activities": activities,
        "precedences": precedences,
    }


def import_xer(path: Path) -> dict[str, Any]:
    """Stretch path: parse a P6 XER if xerparser (or similar) is installed.

    Falls back with a clear error — callers should use CSV.
    """
    try:
        import xerparser  # type: ignore
    except ImportError:
        try:
            from xerparser.reader import Reader  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "XER import requires the optional 'xerparser' package. "
                "Install with: pip install xerparser\n"
                "CSV is the guaranteed fallback: "
                "python -m apps.api.schedule.importer --csv data/project_demo/schedule_export.csv --write"
            ) from e

    # xerparser API varies by version; keep a minimal, documented attempt
    try:
        from xerparser.reader import Reader  # type: ignore

        reader = Reader(str(path))
        activities_out: list[dict[str, Any]] = []
        for task in getattr(reader, "tasks", []) or getattr(reader, "activities", []) or []:
            tid = str(getattr(task, "task_code", None) or getattr(task, "id", "") or "")
            name = str(getattr(task, "task_name", None) or getattr(task, "name", "") or "")
            if not tid:
                continue
            dur = float(getattr(task, "duration", None) or getattr(task, "target_drtn_hr_cnt", 8) or 8)
            activities_out.append(
                {
                    "id": tid,
                    "wbs": str(getattr(task, "wbs_id", None) or "XER"),
                    "name": name or tid,
                    "work_face_id": "WF-UNKNOWN",
                    "structure_id": "UNKNOWN",
                    "trade_id": None,
                    "thermal_sensitive": False,
                    "discipline": "civil",
                    "planned_start": _parse_dt(
                        getattr(task, "target_start_date", None)
                        or getattr(task, "start", None)
                    )
                    or datetime(2026, 8, 24, 7, 0, tzinfo=TZ).isoformat(),
                    "planned_finish": _parse_dt(
                        getattr(task, "target_end_date", None)
                        or getattr(task, "end", None)
                    )
                    or datetime(2026, 8, 25, 7, 0, tzinfo=TZ).isoformat(),
                    "duration_h": dur if dur > 0 else 8.0,
                    "duration_d": (dur if dur > 0 else 8.0) / 10.0,
                    "calendar_id": "CAL-6x10",
                    "crew_size": 1,
                    "quantity": None,
                    "quantity_unit": None,
                    "early_start": None,
                    "early_finish": None,
                    "late_start": None,
                    "late_finish": None,
                    "total_float_d": float(getattr(task, "total_float_hr_cnt", 0) or 0) / 10.0,
                    "free_float_d": 0.0,
                    "is_critical": False,
                    "is_near_critical": False,
                    "milestone_date": None,
                    "milestone_name": None,
                    "hold_point": None,
                    "iwp_id": None,
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": path.stem.upper()[:32],
            "project_name": f"Imported XER ({path.name})",
            "data_date": datetime.now(TZ).isoformat(),
            "tz": "America/Phoenix",
            "utc_offset_hours": -7.0,
            "site_geojson_ref": "data/project_demo/site.geojson",
            "work_faces_geojson_ref": "data/project_demo/work_faces.geojson",
            "provenance": (
                f"Imported from P6 XER ({path.name}) via xerparser. "
                "work_face_id is WF-UNKNOWN until mapped — CSV path allows explicit mapping."
            ),
            "calendars": _default_calendars(),
            "work_faces": [],
            "activities": activities_out,
            "precedences": [],
        }
    except Exception as e:
        raise RuntimeError(
            f"XER parse failed ({e}). Use the CSV fallback:\n"
            "  python -m apps.api.schedule.importer --csv data/project_demo/schedule_export.csv --write"
        ) from e


def import_schedule(
    path: Path,
    *,
    predecessors_path: Path | None = None,
) -> dict[str, Any]:
    """Auto-detect CSV vs XER by suffix."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return import_csv(path, predecessors_path)
    if suffix == ".xer":
        return import_xer(path)
    raise ValueError(f"unsupported schedule format: {suffix} (use .csv or .xer)")


def export_csv_from_json(schedule_path: Path, activities_csv: Path, pred_csv: Path) -> None:
    """Write sample CSVs from activities.json so the importer can be demoed."""
    data = json.loads(schedule_path.read_text())
    acts = data.get("activities") or []
    preds = data.get("precedences") or []

    activities_csv.parent.mkdir(parents=True, exist_ok=True)
    with activities_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_ACTIVITY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for a in acts:
            row = {k: a.get(k) if a.get(k) is not None else "" for k in CSV_ACTIVITY_COLUMNS}
            # bools as true/false
            for bk in ("thermal_sensitive", "is_critical", "is_near_critical"):
                row[bk] = "true" if a.get(bk) else "false"
            writer.writerow(row)

    with pred_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_PRED_COLUMNS)
        writer.writeheader()
        for p in preds:
            writer.writerow(
                {
                    "activity_id": p.get("activity_id", ""),
                    "pred_id": p.get("pred_id", ""),
                    "link_type": p.get("link_type", "FS"),
                    "lag_h": p.get("lag_h", 0),
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Day-6 schedule import (CSV guaranteed, XER stretch)")
    parser.add_argument("--csv", type=Path, help="Activities CSV path")
    parser.add_argument("--predecessors", type=Path, help="Predecessors CSV (optional)")
    parser.add_argument("--xer", type=Path, help="P6 XER path (optional dependency)")
    parser.add_argument(
        "--from-json",
        type=Path,
        help="Export sample CSVs from a ProjectSchedule JSON (e.g. activities.json)",
    )
    parser.add_argument(
        "--export-csv",
        type=Path,
        default=SAMPLE_CSV,
        help="Target activities CSV when using --from-json",
    )
    parser.add_argument(
        "--export-pred-csv",
        type=Path,
        default=SAMPLE_PRED_CSV,
        help="Target predecessors CSV when using --from-json",
    )
    parser.add_argument("--write", action="store_true", help="Write activities_imported.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if args.from_json:
        src = args.from_json
        if not src.exists():
            raise SystemExit(f"missing {src}")
        export_csv_from_json(src, args.export_csv, args.export_pred_csv)
        print(f"wrote {args.export_csv} ({sum(1 for _ in args.export_csv.open()) - 1} activities)")
        print(f"wrote {args.export_pred_csv}")
        return 0

    if args.xer:
        schedule = import_xer(args.xer)
    elif args.csv:
        schedule = import_csv(args.csv, args.predecessors)
    else:
        # default demo: export from generator JSON if CSV missing, then import
        if not SAMPLE_CSV.exists() and DEMO_JSON.exists():
            export_csv_from_json(DEMO_JSON, SAMPLE_CSV, SAMPLE_PRED_CSV)
            print(f"seeded sample CSV from {DEMO_JSON.name}")
        if SAMPLE_CSV.exists():
            schedule = import_csv(SAMPLE_CSV, SAMPLE_PRED_CSV)
        else:
            parser.print_help()
            print(
                "\nCSV is the guaranteed path. Example:\n"
                "  python -m apps.api.schedule.importer --from-json data/project_demo/activities.json\n"
                "  python -m apps.api.schedule.importer --csv data/project_demo/schedule_export.csv --write"
            )
            return 1

    n_act = len(schedule["activities"])
    n_pred = len(schedule["precedences"])
    print(f"imported activities={n_act} precedences={n_pred}")
    print(f"provenance: {schedule['provenance']}")

    if args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(schedule, indent=2, default=str))
        print(f"wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
