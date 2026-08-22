"""T2 Day 3 — credit meter: 80% tripwire, replay ledger, no live call required."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.api.fortyguard.credits import CreditBudgetExceeded, CreditMeter


def _meter(tmp_path: Path, **kwargs) -> CreditMeter:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "remaining": 1_901_040,
                "starting_balance": 2_000_000,
                "days": {},
                "last_api_raw": {"detail": "Method Not Allowed"},
            }
        )
    )
    return CreditMeter(replay_mode=True, ledger_path=ledger, max_calls_per_day=10, **kwargs)


def test_fails_loudly_at_80_percent(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    # max 10 → fail at 8
    for _ in range(8):
        meter.record_local("heatmap")
    with pytest.raises(CreditBudgetExceeded, match="80%"):
        meter.check_budget(extra_calls=1)


def test_records_estimated_burn_from_budget(tmp_path: Path) -> None:
    meter = _meter(tmp_path)
    before = meter.remaining()
    meter.record_local("heatmap")
    assert meter.calls_today() == 1
    assert meter.remaining() == before - meter.costs["heatmap"]


def test_replay_fetch_does_not_need_the_network(tmp_path: Path) -> None:
    import asyncio

    meter = _meter(tmp_path)
    snap = asyncio.run(meter.fetch_usage())
    assert snap.source == "replay"
    assert snap.remaining == 1_901_040
    assert snap.fail_at_calls == 8
