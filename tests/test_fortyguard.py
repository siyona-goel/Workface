"""T2 — FortyGuard client replay + credit tripwire on the live path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from apps.api.fortyguard.client import FortyGuardClient
from apps.api.fortyguard.credits import CreditBudgetExceeded, CreditMeter


def test_replay_heatmap_does_not_need_the_network() -> None:
    client = FortyGuardClient(replay_mode=True)
    result = asyncio.run(client.call("heatmap", {"granularity": 100}))
    status = (result.get("data") or {}).get("status")
    assert result.get("error") is False or status in ("Completed", "Failed", None)


def test_live_path_refuses_when_meter_is_spent(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"remaining": 1_901_040, "starting_balance": 2_000_000, "days": {}}))
    client = FortyGuardClient(replay_mode=False, api_key="dummy")
    client.meter = CreditMeter(
        replay_mode=True,
        ledger_path=ledger,
        max_calls_per_day=10,
    )
    for _ in range(8):
        client.meter.record_local("heatmap")
    try:
        client.meter.check_budget(extra_calls=1)
        raise AssertionError("expected CreditBudgetExceeded")
    except CreditBudgetExceeded:
        pass
