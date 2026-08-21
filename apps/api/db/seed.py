"""
WORKFACE — idempotent database seed.  T3, TASK 6.

    DATABASE_URL=postgresql://user:pass@host/workface  python -m apps.api.db.seed

Loads data/project_demo/activities.json (work faces, activities, precedences) and
data/trade_windows.json (the registry) into a live Postgres+PostGIS database,
idempotently (ON CONFLICT DO UPDATE), so it can be re-run after every migration or
regeneration without duplicating rows.

Run apps/api/db/migrations/001_init.sql first. psycopg (v3) is imported lazily so
this module can be imported for inspection without the driver or a database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
ACTIVITIES = _REPO / "data" / "project_demo" / "activities.json"
REGISTRY = _REPO / "data" / "trade_windows.json"
DEFAULT_DSN = os.environ.get("DATABASE_URL", "postgresql://localhost/workface")


def _upsert_trade_windows(cur, registry: dict) -> int:
    sql = """
        INSERT INTO trade_window
            (trade_id, spec, citation, standard_ref, source_url, verify_status, registry_version)
        VALUES
            (%(trade_id)s, %(spec)s, %(citation)s, %(standard_ref)s, %(source_url)s,
             %(verify_status)s, %(registry_version)s)
        ON CONFLICT (trade_id) DO UPDATE SET
            spec = EXCLUDED.spec, citation = EXCLUDED.citation,
            standard_ref = EXCLUDED.standard_ref, source_url = EXCLUDED.source_url,
            verify_status = EXCLUDED.verify_status, registry_version = EXCLUDED.registry_version;
    """
    version = registry.get("registry_version")
    for t in registry["trades"]:
        cur.execute(sql, {
            "trade_id": t["trade_id"],
            "spec": json.dumps(t),
            "citation": t["citation"],
            "standard_ref": t["standard_ref"],
            "source_url": t["source_url"],
            "verify_status": t["verify_status"],
            "registry_version": version,
        })
    return len(registry["trades"])


def _upsert_work_faces(cur, faces: list[dict]) -> int:
    sql = """
        INSERT INTO work_face
            (id, name, structure_id, level, geom, centroid, area_m2, elevation_m,
             height_agl_m, exposure_class, surface_class, sky_view_factor,
             orientation_deg, twin_json, tile_cluster_id)
        VALUES
            (%(id)s, %(name)s, %(structure_id)s, %(level)s,
             ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326),
             ST_SetSRID(ST_MakePoint(%(clon)s, %(clat)s), 4326)::geography,
             %(area_m2)s, %(elevation_m)s, %(height_agl_m)s, %(exposure_class)s,
             %(surface_class)s, %(sky_view_factor)s, %(orientation_deg)s,
             %(twin_json)s, %(tile_cluster_id)s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name, structure_id = EXCLUDED.structure_id, level = EXCLUDED.level,
            geom = EXCLUDED.geom, centroid = EXCLUDED.centroid, area_m2 = EXCLUDED.area_m2,
            elevation_m = EXCLUDED.elevation_m, height_agl_m = EXCLUDED.height_agl_m,
            exposure_class = EXCLUDED.exposure_class, surface_class = EXCLUDED.surface_class,
            sky_view_factor = EXCLUDED.sky_view_factor, orientation_deg = EXCLUDED.orientation_deg,
            twin_json = EXCLUDED.twin_json, tile_cluster_id = EXCLUDED.tile_cluster_id;
    """
    for f in faces:
        cur.execute(sql, {
            "id": f["id"], "name": f.get("name"), "structure_id": f.get("structure_id"),
            "level": f.get("level"), "geom": json.dumps(f["geom"]),
            "clon": f.get("centroid_lon"), "clat": f.get("centroid_lat"),
            "area_m2": f.get("area_m2"), "elevation_m": f.get("elevation_m"),
            "height_agl_m": f.get("height_agl_m"), "exposure_class": f.get("exposure_class"),
            "surface_class": f.get("surface_class"), "sky_view_factor": f.get("sky_view_factor"),
            "orientation_deg": f.get("orientation_deg"),
            "twin_json": json.dumps(f["twin_json"]) if f.get("twin_json") else None,
            "tile_cluster_id": f.get("tile_cluster_id"),
        })
    return len(faces)


def _upsert_activities(cur, acts: list[dict]) -> int:
    sql = """
        INSERT INTO activity
            (id, wbs, name, trade_id, work_face_id, structure_id, discipline,
             thermal_sensitive, planned_start, planned_finish, duration_h,
             total_float_d, free_float_d, is_critical, is_near_critical,
             milestone_date, milestone_name, hold_point, iwp_id, calendar_id)
        VALUES
            (%(id)s, %(wbs)s, %(name)s, %(trade_id)s, %(work_face_id)s, %(structure_id)s,
             %(discipline)s, %(thermal_sensitive)s, %(planned_start)s, %(planned_finish)s,
             %(duration_h)s, %(total_float_d)s, %(free_float_d)s, %(is_critical)s,
             %(is_near_critical)s, %(milestone_date)s, %(milestone_name)s, %(hold_point)s,
             %(iwp_id)s, %(calendar_id)s)
        ON CONFLICT (id) DO UPDATE SET
            wbs = EXCLUDED.wbs, name = EXCLUDED.name, trade_id = EXCLUDED.trade_id,
            work_face_id = EXCLUDED.work_face_id, structure_id = EXCLUDED.structure_id,
            discipline = EXCLUDED.discipline, thermal_sensitive = EXCLUDED.thermal_sensitive,
            planned_start = EXCLUDED.planned_start, planned_finish = EXCLUDED.planned_finish,
            duration_h = EXCLUDED.duration_h, total_float_d = EXCLUDED.total_float_d,
            free_float_d = EXCLUDED.free_float_d, is_critical = EXCLUDED.is_critical,
            is_near_critical = EXCLUDED.is_near_critical, milestone_date = EXCLUDED.milestone_date,
            milestone_name = EXCLUDED.milestone_name, hold_point = EXCLUDED.hold_point,
            iwp_id = EXCLUDED.iwp_id, calendar_id = EXCLUDED.calendar_id;
    """
    for a in acts:
        cur.execute(sql, {k: a.get(k) for k in (
            "id", "wbs", "name", "trade_id", "work_face_id", "structure_id", "discipline",
            "thermal_sensitive", "planned_start", "planned_finish", "duration_h",
            "total_float_d", "free_float_d", "is_critical", "is_near_critical",
            "milestone_date", "milestone_name", "hold_point", "iwp_id", "calendar_id")})
    return len(acts)


def _upsert_precedences(cur, preds: list[dict]) -> int:
    sql = """
        INSERT INTO activity_pred (activity_id, pred_id, link_type, lag_h)
        VALUES (%(activity_id)s, %(pred_id)s, %(link_type)s, %(lag_h)s)
        ON CONFLICT (activity_id, pred_id) DO UPDATE SET
            link_type = EXCLUDED.link_type, lag_h = EXCLUDED.lag_h;
    """
    for p in preds:
        cur.execute(sql, {
            "activity_id": p["activity_id"], "pred_id": p["pred_id"],
            "link_type": p.get("link_type", "FS"), "lag_h": p.get("lag_h", 0),
        })
    return len(preds)


def seed(dsn: str = DEFAULT_DSN) -> dict[str, int]:
    """Load the registry and demo schedule into `dsn`, idempotently."""
    import psycopg  # lazy — the driver is not needed to import this module

    schedule = json.loads(ACTIVITIES.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    counts: dict[str, int] = {}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Order respects the foreign keys: registry -> faces -> activities -> preds.
            counts["trade_window"] = _upsert_trade_windows(cur, registry)
            counts["work_face"] = _upsert_work_faces(cur, schedule["work_faces"])
            counts["activity"] = _upsert_activities(cur, schedule["activities"])
            counts["activity_pred"] = _upsert_precedences(cur, schedule["precedences"])
        conn.commit()
    return counts


def main() -> None:
    counts = seed()
    for table, n in counts.items():
        print(f"[ok] {table:16} {n} rows upserted")


if __name__ == "__main__":
    main()
