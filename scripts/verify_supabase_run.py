"""Day 10: verify prod Supabase received an agent run.

Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY) in env.

    python -m scripts.verify_supabase_run
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")


def main() -> int:
    sys.path.insert(0, str(REPO))
    from apps.api.db.supabase_client import env_ready, get_supabase

    if not env_ready():
        print("missing SUPABASE_URL / service key in env", file=sys.stderr)
        return 1

    client = get_supabase()
    runs = (
        client.table("agent_run")
        .select("id,status,started_at,finished_at,summary")
        .order("started_at", desc=True)
        .limit(5)
        .execute()
    )
    entries = client.table("record_entry").select("seq", count="exact").limit(1).execute()

    rows = runs.data or []
    print(f"agent_run latest {len(rows)} row(s):")
    for r in rows:
        summary = r.get("summary") or {}
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except json.JSONDecodeError:
                summary = {}
        print(
            f"  {r.get('id')} status={r.get('status')} "
            f"flagged={summary.get('flagged_count')} "
            f"started={r.get('started_at')}"
        )
    count = getattr(entries, "count", None)
    print(f"record_entry count≈ {count}")
    if not rows:
        print("no agent_run rows — cron/worker has not pushed yet", file=sys.stderr)
        return 2
    print("ok — production has agent data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
