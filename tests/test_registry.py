"""TASK 3 acceptance — the trade-window registry loads, validates and is fully cited.

WORKFACE_REPO_GUIDE's definition of done for a registry row is enforced here in CI:
every row carries a real citation, a standard_ref, a source_url and a verify_status.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.api.windows.registry import UnknownTradeError, load_registry
from packages.schemas.window_eval import ConstraintType

REPO = Path(__file__).resolve().parents[1]
ACTIVITIES = REPO / "data" / "project_demo" / "activities.json"


@pytest.fixture(scope="module")
def reg():
    return load_registry()


def test_all_twelve_rows_load_and_validate(reg) -> None:
    assert len(reg) == 12
    assert reg.version == "2026.08.20-a"


def test_trade_ids_unique(reg) -> None:
    ids = reg.trade_ids
    assert len(ids) == len(set(ids))


def test_every_row_is_fully_cited(reg) -> None:
    for t in reg.all():
        assert len(t.citation.strip()) > 20, t.trade_id
        assert t.standard_ref.strip(), t.trade_id
        assert t.source_url.strip(), t.trade_id
        assert t.verify_status in ("primary", "secondary", "partial"), t.trade_id


def test_union_of_constraint_types_covers_all_seven(reg) -> None:
    seen: set[str] = set()
    for t in reg.all():
        for c in t.constraints:
            seen.add(c.type)
    assert seen == {ct.value for ct in ConstraintType}, seen


def test_constraint_ids_unique_within_each_trade(reg) -> None:
    for t in reg.all():
        ids = [c.constraint_id for c in t.constraints]
        assert len(ids) == len(set(ids)), t.trade_id


def test_every_scheduled_trade_id_resolves(reg) -> None:
    schedule = json.loads(ACTIVITIES.read_text(encoding="utf-8"))
    used = {a["trade_id"] for a in schedule["activities"] if a["trade_id"]}
    for trade_id in used:
        assert trade_id in reg, trade_id
        assert reg.get(trade_id).trade_id == trade_id


def test_get_raises_on_unknown_trade_never_returns_none(reg) -> None:
    with pytest.raises(UnknownTradeError):
        reg.get("no_such_trade")


def test_citation_for_returns_the_clause(reg) -> None:
    clause = reg.citation_for("coating_epoxy_structural_steel", "offset_dew_point")
    assert "dew point" in clause.lower()
    with pytest.raises(UnknownTradeError):
        reg.citation_for("coating_epoxy_structural_steel", "no_such_constraint")


def test_discriminated_union_picks_the_right_variant(reg) -> None:
    from packages.schemas.trade_window import BandSpec, CompositeRateSpec, OffsetSpec
    concrete = reg.get("concrete_cip_hot_weather")
    by_id = {c.constraint_id: c for c in concrete.constraints}
    assert isinstance(by_id["band_concrete_discharge_max"], BandSpec)
    assert isinstance(by_id["composite_evaporation_rate"], CompositeRateSpec)
    coating = reg.get("coating_epoxy_structural_steel")
    offset = coating.constraint("offset_dew_point")
    assert isinstance(offset, OffsetSpec)
    assert offset.delta_c == 2.8


def test_registry_is_cached(reg) -> None:
    assert load_registry() is reg     # same object back
