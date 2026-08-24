"""Push an unattended agent run + record chain to Supabase.

Tables (001_init.sql):
  agent_run(id, run_id, kind, status, started_at, finished_at, summary)
  agent_step(run_id, seq, kind, input, output)
  record_entry(prev_hash, hash, payload)  — append-only
"""

from __future__ import annotations

import json
from typing import Any

from apps.api.db.supabase_client import get_supabase


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def push_unattended_result(result: Any) -> dict[str, Any]:
    """Insert agent_run, agent_steps, and record_entry rows. Returns counts."""
    client = get_supabase()
    run = result.run
    chain = result.chain
    summary = result.summary

    run_id = run.run_id
    run_row = {
        "id": run_id,
        "run_id": run_id,
        "kind": "unattended",
        "status": "completed",
        "started_at": getattr(run, "started_at", None) or summary.get("started_at"),
        "finished_at": getattr(run, "finished_at", None),
        "summary": _jsonable(summary),
    }
    # coerce datetimes to iso if needed
    for k in ("started_at", "finished_at"):
        v = run_row.get(k)
        if v is not None and hasattr(v, "isoformat"):
            run_row[k] = v.isoformat()

    client.table("agent_run").upsert(run_row, on_conflict="id").execute()

    steps = getattr(run, "steps", None) or []
    step_rows = []
    for i, step in enumerate(steps):
        dumped = _jsonable(step)
        step_rows.append(
            {
                "run_id": run_id,
                "seq": i,
                "kind": dumped.get("type") or dumped.get("kind") or "step",
                "input": dumped.get("input") or dumped,
                "output": dumped.get("output") or dumped,
            }
        )
    if step_rows:
        # delete prior steps for this run then insert (idempotent re-runs)
        client.table("agent_step").delete().eq("run_id", run_id).execute()
        client.table("agent_step").insert(step_rows).execute()

    entries = getattr(chain, "entries", None) or []
    inserted = 0
    for entry in entries:
        dumped = _jsonable(entry)
        payload = dumped.get("payload") if isinstance(dumped, dict) else None
        if payload is None and hasattr(entry, "payload"):
            payload = _jsonable(entry.payload)
        row = {
            "prev_hash": dumped.get("prev_hash") if isinstance(dumped, dict) else getattr(entry, "prev_hash", None),
            "hash": dumped.get("hash") if isinstance(dumped, dict) else getattr(entry, "hash", None),
            "payload": payload if payload is not None else dumped,
        }
        client.table("record_entry").insert(row).execute()
        inserted += 1

    return {
        "run_id": run_id,
        "steps_written": len(step_rows),
        "record_entries_written": inserted,
        "head_hash": getattr(chain, "head_hash", None) or summary.get("head_hash"),
    }
