"""Persistent store for fg_activity_id.

Write the ID *before* polling so a process restart can resume
instead of re-submitting (and re-billing).

Day-2 implementation: local JSON file.
Later: swap the backend for a Postgres/Supabase table (fg_activity).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

STORE_PATH = Path(__file__).resolve().parents[3] / "data" / "fg_activity_store.json"


class ActivityStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or STORE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}")

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2, default=str))

    def record(
        self,
        fg_activity_id: str,
        *,
        endpoint: str,
        request_hash: str,
        status: str = "Submitted",
        body: dict | None = None,
    ) -> None:
        data = self._load()
        data[fg_activity_id] = {
            "fg_activity_id": fg_activity_id,
            "endpoint": endpoint,
            "request_hash": request_hash,
            "status": status,
            "submitted_at": time.time(),
            "body": body,
        }
        self._save(data)

    def update_status(self, fg_activity_id: str, status: str, result: dict | None = None) -> None:
        data = self._load()
        if fg_activity_id not in data:
            return
        data[fg_activity_id]["status"] = status
        data[fg_activity_id]["updated_at"] = time.time()
        if result is not None:
            data[fg_activity_id]["result_ref"] = True  # full result lives in cache
        self._save(data)

    def get(self, fg_activity_id: str) -> dict | None:
        return self._load().get(fg_activity_id)

    def pending(self) -> list[dict]:
        """IDs still in Submitted/Processing — useful on restart."""
        return [
            row
            for row in self._load().values()
            if row.get("status") in ("Submitted", "Processing")
        ]
