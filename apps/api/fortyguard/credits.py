"""FortyGuard credit meter.

Poll `/v1/system/fetch-api-key-usage` after every batch. The Day-1 notebook
got HTTP 405 on GET — we try GET then POST, and if the endpoint is missing we
keep a local ledger (CREDITS.md numbers + estimated per-call burn).

Hard daily cap lives in config/budget.yaml. Fail loudly at 80%.

    python -m apps.api.fortyguard.credits
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .aoi import BUDGET_PATH, REPO, _load_budget

LEDGER_PATH = REPO / "data" / "fixtures" / "credit_ledger.json"
USAGE_URL = "https://api.fortyguard.com/v1/system/fetch-api-key-usage"


class CreditBudgetExceeded(RuntimeError):
    """Raised at 80% of MAX_FG_CALLS_PER_DAY (or when remaining credits collapse)."""


@dataclass
class CreditSnapshot:
    fetched_at: str
    calls_today: int
    max_calls_per_day: int
    fail_at_calls: int
    remaining: int | None
    used_estimated: int | None
    source: str  # "api" | "ledger" | "replay"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def fraction_used(self) -> float:
        if self.max_calls_per_day <= 0:
            return 1.0
        return self.calls_today / self.max_calls_per_day

    def as_dict(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at,
            "calls_today": self.calls_today,
            "max_calls_per_day": self.max_calls_per_day,
            "fail_at_calls": self.fail_at_calls,
            "remaining": self.remaining,
            "used_estimated": self.used_estimated,
            "source": self.source,
            "fraction_used": round(self.fraction_used, 4),
            "raw": self.raw,
        }


def _today() -> str:
    return date.today().isoformat()


class CreditMeter:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        replay_mode: bool | None = None,
        budget_path: Path = BUDGET_PATH,
        ledger_path: Path = LEDGER_PATH,
        max_calls_per_day: int | None = None,
    ) -> None:
        self.budget = _load_budget(budget_path)
        env_replay = os.environ.get("REPLAY_MODE", "true").lower() in ("1", "true", "yes")
        self.replay_mode = env_replay if replay_mode is None else replay_mode
        self.api_key = api_key or os.environ.get("FORTYGUARD_API_KEY", "")
        self.ledger_path = ledger_path
        self.max_calls_per_day = max_calls_per_day or int(
            os.environ.get(
                "MAX_FG_CALLS_PER_DAY",
                str(self.budget.get("max_fg_calls_per_day", 120)),
            )
        )
        self.fail_at_fraction = float(self.budget.get("fail_at_fraction", 0.8))
        self.costs: dict[str, int] = {
            str(k): int(v)
            for k, v in (self.budget.get("estimated_credits_per_call") or {}).items()
        }
        self._ledger = self._load_ledger()

    @property
    def fail_at_calls(self) -> int:
        return max(1, int(self.max_calls_per_day * self.fail_at_fraction))

    def _load_ledger(self) -> dict[str, Any]:
        if self.ledger_path.exists():
            try:
                return json.loads(self.ledger_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "remaining": int(self.budget.get("ledger_remaining", 1_901_040)),
            "starting_balance": int(self.budget.get("starting_balance", 2_000_000)),
            "days": {},
            "last_api_raw": None,
        }

    def _save_ledger(self) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(
            json.dumps(self._ledger, indent=2) + "\n", encoding="utf-8"
        )

    def calls_today(self) -> int:
        day = self._ledger.setdefault("days", {}).setdefault(
            _today(), {"calls": 0, "estimated_credits": 0, "by_endpoint": {}}
        )
        return int(day["calls"])

    def remaining(self) -> int:
        return int(self._ledger.get("remaining", 0))

    def check_budget(self, *, extra_calls: int = 1) -> None:
        """Fail closed before a live submit that would cross 80% of the daily cap."""
        projected = self.calls_today() + extra_calls
        if projected > self.fail_at_calls:
            raise CreditBudgetExceeded(
                f"FortyGuard daily cap tripwire: {projected} calls would exceed "
                f"{self.fail_at_fraction:.0%} of MAX_FG_CALLS_PER_DAY="
                f"{self.max_calls_per_day} (fail at {self.fail_at_calls}). "
                f"Stop. Do not guess."
            )

    def record_local(self, endpoint: str) -> CreditSnapshot:
        day = self._ledger.setdefault("days", {}).setdefault(
            _today(), {"calls": 0, "estimated_credits": 0, "by_endpoint": {}}
        )
        day["calls"] = int(day["calls"]) + 1
        cost = int(self.costs.get(endpoint, 0))
        day["estimated_credits"] = int(day["estimated_credits"]) + cost
        by_ep = day.setdefault("by_endpoint", {})
        by_ep[endpoint] = int(by_ep.get(endpoint, 0)) + 1
        self._ledger["remaining"] = max(0, int(self._ledger.get("remaining", 0)) - cost)
        self._save_ledger()
        return self.snapshot(source="ledger")

    def snapshot(self, *, source: str | None = None, raw: dict | None = None) -> CreditSnapshot:
        return CreditSnapshot(
            fetched_at=datetime.now(timezone.utc).isoformat(),
            calls_today=self.calls_today(),
            max_calls_per_day=self.max_calls_per_day,
            fail_at_calls=self.fail_at_calls,
            remaining=self.remaining(),
            used_estimated=int(self._ledger.get("starting_balance", 0)) - self.remaining(),
            source=source or ("replay" if self.replay_mode else "ledger"),
            raw=raw if raw is not None else (self._ledger.get("last_api_raw") or {}),
        )

    async def fetch_usage(self) -> CreditSnapshot:
        """Poll the sponsor meter. Replay → ledger. Live 405 → ledger + last raw."""
        if self.replay_mode:
            return self.snapshot(source="replay")

        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        raw: dict[str, Any] = {"tried": []}
        async with httpx.AsyncClient(timeout=30.0) as client:
            for method in ("GET", "POST"):
                try:
                    r = await client.request(method, USAGE_URL, headers=headers)
                    payload: Any
                    try:
                        payload = r.json()
                    except Exception:
                        payload = {"text": r.text, "status_code": r.status_code}
                    raw["tried"].append({"method": method, "status_code": r.status_code, "body": payload})
                    if r.status_code < 400 and isinstance(payload, dict) and "detail" not in payload:
                        remaining = _extract_remaining(payload)
                        if remaining is not None:
                            self._ledger["remaining"] = remaining
                        self._ledger["last_api_raw"] = payload
                        self._save_ledger()
                        return self.snapshot(source="api", raw=payload)
                except httpx.HTTPError as exc:
                    raw["tried"].append({"method": method, "error": str(exc)})

        self._ledger["last_api_raw"] = raw
        self._save_ledger()
        # Endpoint missing (405) — keep metering locally, don't pretend we have live remaining.
        return self.snapshot(source="ledger", raw=raw)

    async def after_call(self, endpoint: str) -> CreditSnapshot:
        self.record_local(endpoint)
        return await self.fetch_usage()

    async def after_batch(self, endpoints: list[str] | None = None) -> CreditSnapshot:
        """Call this after every FortyGuard batch. Spec §3.4 / rule 5."""
        if endpoints:
            for ep in endpoints:
                self.record_local(ep)
        snap = await self.fetch_usage()
        snap_path = self.ledger_path.parent / "credit_meter_latest.json"
        snap_path.write_text(json.dumps(snap.as_dict(), indent=2) + "\n", encoding="utf-8")
        return snap


def _extract_remaining(payload: dict) -> int | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("remaining", "credits_remaining", "balance", "credits", "remaining_credits"):
        if key in data and data[key] is not None:
            try:
                return int(data[key])
            except (TypeError, ValueError):
                continue
    return None


async def main() -> None:
    meter = CreditMeter()
    snap = await meter.fetch_usage()
    print(json.dumps(snap.as_dict(), indent=2))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
