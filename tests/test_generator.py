"""Generator invariants + TASK 1 acceptance.

The appendix's Half-A verification is turned into a test here (as the brief asks)
so the TASK 1 tuning cannot silently break the DAG, the CPM float, or the
registry cross-references. Regenerates into a temp dir — never touches the
committed data/project_demo/.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from apps.api.schedule import generator as g

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("gen")
    g.emit(d)
    return d


@pytest.fixture(scope="module")
def schedule(out: Path) -> dict:
    return json.loads((out / "activities.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def stats(out: Path) -> dict:
    return json.loads((out / "stats.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Structural invariants (appendix — must survive TASK 1 tuning)
# --------------------------------------------------------------------------- #

def test_counts(schedule: dict) -> None:
    assert len(schedule["work_faces"]) == 40
    assert len(schedule["activities"]) == 328
    assert len(schedule["precedences"]) == 313


def test_precedence_graph_is_a_dag(schedule: dict) -> None:
    acts = {a["id"] for a in schedule["activities"]}
    succ: dict[str, list[str]] = {a: [] for a in acts}
    indeg = {a: 0 for a in acts}
    for p in schedule["precedences"]:
        if p["pred_id"] in acts and p["activity_id"] in acts:
            succ[p["pred_id"]].append(p["activity_id"])
            indeg[p["activity_id"]] += 1
    queue = [a for a, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        n = queue.pop()
        seen += 1
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    assert seen == len(acts), "precedence graph has a cycle"


def test_fs_links_respected_and_float_non_negative(schedule: dict) -> None:
    by_id = {a["id"]: a for a in schedule["activities"]}
    for p in schedule["precedences"]:
        if p["link_type"] != "FS":
            continue
        a, pred = by_id[p["activity_id"]], by_id.get(p["pred_id"])
        if pred is None:
            continue
        assert datetime.fromisoformat(a["early_start"]) >= datetime.fromisoformat(pred["early_finish"]), \
            f"FS violated: {a['id']} starts before {pred['id']} finishes"
    for a in schedule["activities"]:
        assert a["total_float_d"] >= -0.01, f"negative float on {a['id']}"


def test_critical_activities_have_zero_float(schedule: dict) -> None:
    crit = [a for a in schedule["activities"] if a["is_critical"]]
    assert crit, "expected at least one critical activity"
    for a in crit:
        assert a["total_float_d"] <= 0.01


def test_every_trade_id_resolves_in_registry(schedule: dict) -> None:
    reg = json.loads((REPO / "data" / "trade_windows.json").read_text(encoding="utf-8"))
    known = {t["trade_id"] for t in reg["trades"]}
    used = {a["trade_id"] for a in schedule["activities"] if a["trade_id"]}
    assert used <= known, f"unknown trade_ids: {used - known}"


# --------------------------------------------------------------------------- #
# TASK 1 acceptance
# --------------------------------------------------------------------------- #

def test_1a_cold_weather_swapped(stats: dict) -> None:
    assert stats["cold_weather_swapped"] >= 4
    whole = stats["by_trade_whole_project"]
    assert whole.get("concrete_cip_cold_weather", 0) >= 1
    assert whole.get("masonry_cmu_cold_weather", 0) >= 1
    # fixing cold weather must not starve the demo window
    assert stats["in_demo_window"]["activities"] >= 35


def test_1b_thermal_sensitive_in_window(stats: dict) -> None:
    iw = stats["in_demo_window"]
    assert 30 <= iw["thermal_sensitive"] <= 45, iw["thermal_sensitive"]
    assert len(iw["by_trade"]) >= 5, iw["by_trade"]


def test_1c_hero_pair(stats: dict) -> None:
    hp = stats["hero_pair"]
    assert hp is not None
    assert hp["sky_view_factor"]["bare"] > hp["sky_view_factor"]["shaded"]
    assert hp["bare"].startswith("WF-FAB2") and hp["shaded"].startswith("WF-FAB2")
    assert hp["separation_m"] > 0
    # the recorded separation must be the truth, not the plan's ~300 m prose
    assert "300" not in str(hp["separation_m"])


def test_committed_demo_data_matches_generator(schedule: dict) -> None:
    """The committed data/project_demo/activities.json is the generator's output."""
    committed = json.loads((REPO / "data" / "project_demo" / "activities.json").read_text(encoding="utf-8"))
    assert len(committed["activities"]) == len(schedule["activities"])
    assert len(committed["precedences"]) == len(schedule["precedences"])
