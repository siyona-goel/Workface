"""Content-addressed cache for FortyGuard responses.

Key = sha256 of normalised request body.
TTL by tier:
  - historical / twin  → forever
  - forecast           → 30 min
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

# Default on-disk location (also used by REPLAY_MODE)
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures"


def _canonical(obj: Any) -> str:
    """Stable JSON for hashing (sorted keys, no whitespace variance)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def request_hash(endpoint: str, body: dict) -> str:
    payload = {"endpoint": endpoint, "body": body}
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()[:24]


class FixtureCache:
    """Filesystem cache under data/fixtures/.

    In REPLAY_MODE this is the only source of truth.
    In live mode we still write every successful response here
    so the next run can replay without burning credits.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or FIXTURES_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str, ttl_seconds: float | None = None) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        if ttl_seconds is not None:
            age = time.time() - path.stat().st_mtime
            if age > ttl_seconds:
                return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, key: str, data: dict) -> Path:
        path = self._path(key)
        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    def find_by_endpoint(self, endpoint: str) -> list[Path]:
        """Helper for REPLAY: list fixture files that match an endpoint name."""
        return sorted(self.root.glob(f"{endpoint}_*.json"))
