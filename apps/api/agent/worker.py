"""T2 Day 8 — cron / Actions entrypoint.

Runs the T3 unattended loop, always writes fixtures, optionally pushes to Supabase.

    # Local / CI (fixtures only)
    REPLAY_MODE=true python -m apps.api.agent.worker

    # With Supabase (needs SUPABASE_URL + SUPABASE_SERVICE_KEY)
    python -m apps.api.agent.worker --push-supabase

GitHub Actions should set REPLAY_MODE=true so the worker never bills FortyGuard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root on path when run as module
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv

load_dotenv(_REPO / ".env")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WORKFACE agent worker (cron entrypoint)")
    parser.add_argument(
        "--push-supabase",
        action="store_true",
        help="Upsert agent_run / agent_step / record_entry to Supabase",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM propose step (requires LLM_* env)",
    )
    parser.add_argument(
        "--require-supabase",
        action="store_true",
        help="Exit non-zero if --push-supabase is set but env is missing",
    )
    args = parser.parse_args(argv)

    # Default safe for Actions
    os.environ.setdefault("REPLAY_MODE", "true")

    from apps.api.agent.unattended import run_unattended, RUN_PATH, CHAIN_PATH, SUMMARY_PATH

    print(f"REPLAY_MODE={os.environ.get('REPLAY_MODE')}")
    print("running unattended agent…")
    result = run_unattended(use_llm=args.llm)

    # unattended.main writes files; mirror here for worker ownership
    RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUN_PATH.write_text(result.run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    CHAIN_PATH.write_text(result.chain.model_dump_json(indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(result.summary, indent=2, default=str) + "\n", encoding="utf-8")

    s = result.summary
    print(
        f"ok run_id={s.get('run_id')} scanned={s.get('scanned_count')} "
        f"flagged={s.get('flagged_count')} conflicts={s.get('conflicts_count')} "
        f"resolved={s.get('resolved_count')} escalated={s.get('escalated_count')}"
    )
    print(
        f"record entries={s.get('record_entries')} verified={s.get('chain_verified')} "
        f"head={(s.get('head_hash') or '')[:16]}…"
    )
    print(f"wrote {RUN_PATH.name}, {CHAIN_PATH.name}, {SUMMARY_PATH.name}")

    if args.push_supabase:
        from apps.api.db.supabase_client import env_ready
        from apps.api.db.push_run import push_unattended_result

        if not env_ready():
            msg = "SUPABASE_URL / SUPABASE_SERVICE_KEY not set"
            if args.require_supabase:
                print(f"error: {msg}", file=sys.stderr)
                return 1
            print(f"skip push: {msg}")
            return 0
        info = push_unattended_result(result)
        print(f"supabase push: {json.dumps(info)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
