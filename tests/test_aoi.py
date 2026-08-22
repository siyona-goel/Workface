"""T2 Day 3 — AOI clustering: 40 faces → 3–5 polygons, call budget written down."""

from __future__ import annotations

import json
from pathlib import Path

from apps.api.fortyguard.aoi import (
    REPO,
    cluster_work_faces,
    heatmap_body,
    load_work_faces,
    project_call_budget,
)

BUDGET_MAX = 5
BUDGET_MIN = 3


def test_clusters_forty_faces_into_three_to_five_polygons() -> None:
    faces = load_work_faces()
    assert len(faces) == 40
    clusters = cluster_work_faces(faces)
    assert BUDGET_MIN <= len(clusters) <= BUDGET_MAX, [c.id for c in clusters]
    assigned = {fid for c in clusters for fid in c.work_face_ids}
    assert assigned == {f["properties"]["id"] for f in faces}
    assert all(c.work_face_ids for c in clusters)


def test_fab2_stays_one_hero_cluster() -> None:
    clusters = cluster_work_faces()
    fab = [c for c in clusters if "FAB2" in c.structure_ids]
    assert len(fab) == 1
    assert fab[0].structure_ids == ["FAB2"]
    assert fab[0].granularity_commit_m == 60
    assert len(fab[0].work_face_ids) == 14


def test_call_budget_is_written_and_beats_naive() -> None:
    clusters = cluster_work_faces()
    plan = project_call_budget(clusters, n_faces=40)
    assert plan["n_aoi_polygons"] <= plan["max_aoi_polygons"] <= 5
    daily = plan["daily_commit_calls"]
    assert daily["clustered"] == plan["n_aoi_polygons"] * 3
    assert daily["clustered"] < daily["naive_per_face"]
    assert daily["clustered"] < plan["max_fg_calls_per_day"] * 0.8
    sweep = plan["climatology_sweep_calls_once"]
    assert sweep["clustered"] == 7 * 4 * plan["n_aoi_polygons"]
    assert sweep["clustered"] < sweep["naive_per_face"]


def test_heatmap_body_is_one_featurecollection_per_cluster() -> None:
    cluster = cluster_work_faces()[0]
    body = heatmap_body(cluster, start_date="2026-08-24", filter_type=2)
    assert body["granularity"] in (60, 100)
    aoi = body["polygon_aoi"]
    assert aoi["type"] == "FeatureCollection"
    assert len(aoi["features"]) == 1
    ring = aoi["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]


def test_committed_plan_matches_live_clustering() -> None:
    plan_path = REPO / "data" / "aoi" / "plan.json"
    if not plan_path.exists():
        return
    committed = json.loads(plan_path.read_text(encoding="utf-8"))
    live = project_call_budget(cluster_work_faces())
    assert committed["n_aoi_polygons"] == live["n_aoi_polygons"]
    assert committed["daily_commit_calls"]["clustered"] == live["daily_commit_calls"]["clustered"]
