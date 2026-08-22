"""FortyGuard async client.

Day-2 contract:
  - submit → fg_activity_id
  - poll with exponential backoff + hard cap
  - persist fg_activity_id *before* polling
  - content-addressed cache (filesystem; Postgres later)
  - REPLAY_MODE=true → never touch the network
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Literal

import httpx

from .activity_store import ActivityStore
from .cache import FixtureCache, request_hash
from .credits import CreditMeter

Endpoint = Literal[
    "heatmap",
    "satellite",
    "streetview",
    "heat_intelligence",
    "env_params",
]

# TTL seconds by tier
TTL = {
    "historical": None,       # forever
    "twin": None,             # forever (satellite / streetview)
    "forecast": 30 * 60,      # 30 min
}


def _tier(endpoint: Endpoint, body: dict) -> str:
    if endpoint in ("satellite", "streetview"):
        return "twin"
    # crude but good enough for Day 2: filter_type 4 or pre-2025 dates → historical
    dt = body.get("date_time") or {}
    start = str(dt.get("start_date") or body.get("date") or "")
    if start and start < "2025-01-01":
        return "historical"
    if endpoint == "heatmap" and dt.get("filter_type") == 4:
        return "historical"
    return "forecast"


class FortyGuardClient:
    BASE = "https://api.fortyguard.com/v1"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        replay_mode: bool | None = None,
        fixtures_dir: Path | None = None,
        max_poll_s: float = 300.0,
        max_calls_per_day: int | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("FORTYGUARD_API_KEY", "")
        env_replay = os.environ.get("REPLAY_MODE", "true").lower() in ("1", "true", "yes")
        self.replay_mode = env_replay if replay_mode is None else replay_mode
        self.cache = FixtureCache(fixtures_dir)
        self.store = ActivityStore()
        self.max_poll_s = max_poll_s
        self.meter = CreditMeter(
            api_key=self.api_key,
            replay_mode=self.replay_mode,
            max_calls_per_day=max_calls_per_day,
        )
        self.max_calls_per_day = self.meter.max_calls_per_day
        self._calls_today = 0

        if not self.replay_mode and not self.api_key:
            raise RuntimeError(
                "FORTYGUARD_API_KEY required when REPLAY_MODE is false"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(
        self,
        endpoint: Endpoint,
        body: dict,
        *,
        force_live: bool = False,
    ) -> dict:
        """Submit + poll, or serve from cache / fixtures.

        Returns the full status response once status is Completed or Failed.
        """
        key = request_hash(endpoint, body)
        tier = _tier(endpoint, body)
        ttl = TTL[tier]

        # 1. Cache / replay hit
        if not force_live:
            cached = self.cache.get(key, ttl_seconds=ttl)
            if cached is not None:
                return cached
            if self.replay_mode:
                # Fallback: try any fixture file named after the endpoint
                replayed = self._replay_fallback(endpoint)
                if replayed is not None:
                    return replayed
                raise FileNotFoundError(
                    f"REPLAY_MODE=true but no fixture for {endpoint} "
                    f"(hash={key}). Run the Day-1 notebook once with live key."
                )

        # 2. Live path — hard daily budget (fail loudly at 80%)
        self.meter.check_budget(extra_calls=1)
        self._calls_today += 1

        fg_id = await self._submit(endpoint, body)
        # Persist *before* polling so a crash can resume
        self.store.record(
            fg_id,
            endpoint=endpoint,
            request_hash=key,
            status="Submitted",
            body=body,
        )

        result = await self._poll(fg_id, endpoint)
        status = (result.get("data") or {}).get("status", "Unknown")
        self.store.update_status(fg_id, status, result=result)

        # Cache successful (and even failed) terminal responses
        self.cache.put(key, result)

        # heat_intelligence: fetch PDF immediately, redact signed URL
        if endpoint == "heat_intelligence" and status == "Completed":
            result = await self._handle_heat_intel_pdf(result, key)

        await self.meter.after_call(endpoint)
        return result

    async def meter_after_batch(self, endpoints: list[str] | None = None):
        """Poll the credit meter after a batch. Spec rule 5."""
        return await self.meter.after_batch(endpoints)

    async def resume(self, fg_activity_id: str) -> dict:
        """Resume polling an ID that was already submitted (restart safety)."""
        row = self.store.get(fg_activity_id)
        endpoint = (row or {}).get("endpoint", "heatmap")
        result = await self._poll(fg_activity_id, endpoint)
        status = (result.get("data") or {}).get("status", "Unknown")
        self.store.update_status(fg_activity_id, status, result=result)
        if row and row.get("request_hash"):
            self.cache.put(row["request_hash"], result)
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _submit(self, endpoint: Endpoint, body: dict) -> str:
        url = f"{self.BASE}/{endpoint}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, headers=self._headers(), json=body)
            data = r.json()
            if r.status_code >= 400:
                raise RuntimeError(f"Submit {endpoint} failed: {data}")
            return data["data"]["activity_id"]

    async def _poll(
        self,
        fg_activity_id: str,
        endpoint: str,
        *,
        interval: float = 3.0,
    ) -> dict:
        url = f"{self.BASE}/status/{fg_activity_id}"
        deadline = asyncio.get_event_loop().time() + self.max_poll_s
        attempt = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                attempt += 1
                r = await client.get(url, headers=self._headers())
                data = r.json()
                status = (data.get("data") or {}).get("status") or data.get("message")

                if status in ("Completed", "Failed"):
                    return data

                now = asyncio.get_event_loop().time()
                if now >= deadline:
                    raise TimeoutError(
                        f"Timed out after {self.max_poll_s}s waiting for "
                        f"{endpoint} {fg_activity_id} (last status={status})"
                    )

                # exponential backoff, capped
                sleep = min(interval * (1.4 ** min(attempt, 8)), 30.0)
                await asyncio.sleep(sleep)

    def _replay_fallback(self, endpoint: Endpoint) -> dict | None:
        """When exact hash miss, return the newest fixture for that endpoint."""
        candidates = [
            p for p in self.cache.find_by_endpoint(endpoint)
            if "result" in p.name or "submit" not in p.name
        ]
        if not candidates:
            # also accept any *_{endpoint}_*.json style from the notebook
            candidates = sorted(
                self.cache.root.glob(f"*{endpoint}*result*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        if not candidates:
            return None
        import json
        return json.loads(candidates[0].read_text())

    async def _handle_heat_intel_pdf(self, result: dict, key: str) -> dict:
        """Download PDF immediately; never leave the signed URL in the fixture."""
        data = result.get("data") or {}
        res = data.get("result") or {}
        link = res.get("download_link")
        if not link or link.startswith("[REDACTED"):
            return result

        pdf_name = f"heat_intelligence_hero_{key[:8]}.pdf"
        pdf_path = self.cache.root / pdf_name
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                r = await client.get(link)
                if r.status_code == 200:
                    pdf_path.write_bytes(r.content)
        except Exception:
            pass  # non-fatal

        res = {
            **res,
            "download_link": f"[REDACTED — PDF saved as {pdf_name}]",
        }
        data = {**data, "result": res}
        result = {**result, "data": data}
        self.cache.put(key, result)
        return result


# Convenience sync wrapper for notebooks / scripts
def call_sync(endpoint: Endpoint, body: dict, **kwargs: Any) -> dict:
    client = FortyGuardClient(**kwargs)
    return asyncio.run(client.call(endpoint, body))
