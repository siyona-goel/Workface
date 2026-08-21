"""TASK 6 — schema contract for 001_init.sql (no live database required).

We cannot spin up Postgres+PostGIS in CI here, so instead we assert the migration
TEXT enforces the two non-negotiables and the required indexes. A live-DB
integration test is T2/infra's to add once a Postgres service exists in CI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SQL = (REPO / "apps" / "api" / "db" / "migrations" / "001_init.sql").read_text(encoding="utf-8")
SQL_LOWER = SQL.lower()


def test_postgis_extension() -> None:
    assert "create extension if not exists postgis" in SQL_LOWER


def test_record_entry_is_append_only() -> None:
    # The columns the brief specifies…
    assert re.search(r"record_entry\s*\(", SQL_LOWER)
    for col in ("seq", "prev_hash", "hash", "payload", "created_at"):
        assert col in SQL_LOWER, col
    assert "hash       text not null" in SQL_LOWER or "hash text not null" in SQL_LOWER
    # …and a trigger that blocks mutation.
    assert re.search(r"before\s+update\s+or\s+delete\s+on\s+record_entry", SQL_LOWER)
    assert "raise exception" in SQL_LOWER


def test_trade_window_columns_are_not_null() -> None:
    block = SQL_LOWER.split("create table if not exists trade_window", 1)[1].split(");", 1)[0]
    for col in ("citation", "standard_ref", "source_url", "verify_status"):
        assert re.search(col + r"[^\n,]*not null", block), f"{col} must be NOT NULL"
    assert "verify_status in ('primary', 'secondary', 'partial')" in block


def test_required_indexes_present() -> None:
    for needle in (
        "on activity (planned_start)",
        "on activity (trade_id) where thermal_sensitive",
        "on activity (work_face_id)",
        "on thermal_series (ts)",
        "on window_eval (run_id)",
        "using gist (geom)",
    ):
        assert needle in SQL_LOWER, needle


def test_t2_stub_tables_are_owned_and_present() -> None:
    for table in ("tile_cluster", "fg_activity", "fg_cache"):
        assert f"create table if not exists {table}" in SQL_LOWER, table
    assert SQL.count("OWNER: T2") >= 3


def test_all_t3_tables_present() -> None:
    for table in ("work_face", "activity", "activity_pred", "trade_window",
                  "thermal_series", "window_eval", "climatology_prior",
                  "agent_run", "agent_step", "record_entry"):
        assert f"create table if not exists {table}" in SQL_LOWER, table


def test_seed_module_imports_and_columns_match_data() -> None:
    """seed.py imports without the driver, and the activity columns it upserts
    all exist in the generated schedule."""
    from apps.api.db import seed
    assert callable(seed.seed)
    schedule = json.loads((REPO / "data" / "project_demo" / "activities.json").read_text(encoding="utf-8"))
    sample = schedule["activities"][0]
    for col in ("id", "trade_id", "work_face_id", "thermal_sensitive", "planned_start"):
        assert col in sample, col
