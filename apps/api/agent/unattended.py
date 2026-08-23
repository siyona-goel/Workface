"""
WORKFACE — the unattended run: full loop -> AgentRun + RecordChain + summary.
T3, Day 8, Task H (§8.4).

    from apps.api.agent.unattended import run_unattended
    result = run_unattended()      # -> UnattendedResult(run, chain, summary)

This is the SINGLE entry point T2's GitHub Actions cron calls tomorrow. It runs
the whole loop end to end (SCAN -> ... -> ACT/ESCALATE), then builds the
append-only, hash-linked RecordChain from the same evaluation — one record entry
per flagged activity, carrying the clause, the series digest and the fg handles
(§8.4). `verify_chain(result.chain)` is True by construction; the Day-8 gate is
that this completes with zero manual steps and the chain verifies.

    python -m apps.api.agent.unattended            # write run + chain + summary
    python -m apps.api.agent.unattended --llm       # use the configured model for PROPOSE

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from apps.api.agent.loop import ANCHOR, SITE_ID, _FLAGGED, run_agent
from apps.api.agent.record import build_chain, payload_from_eval, verify_chain
from packages.schemas.agent_trace import AgentRun
from packages.schemas.record import RecordAction, RecordChain

_REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = _REPO_ROOT / "data" / "fixtures"
RUN_PATH = FIXTURES / "agent_run_live.json"
CHAIN_PATH = FIXTURES / "record_chain_live.json"
SUMMARY_PATH = FIXTURES / "agent_run_summary.json"


@dataclass
class UnattendedResult:
    run: AgentRun
    chain: RecordChain
    summary: dict


def run_unattended(*, use_llm: bool = False) -> UnattendedResult:
    """Run the loop and build the verified record chain from the same evaluation."""
    run, evals, outcomes = run_agent(use_llm=use_llm, return_evals=True)

    # One entry per flagged activity, deterministically ordered by id. A targeted
    # activity carries the action the agent took + the gate verdict; the rest are
    # observe-only EVALUATE entries. The chain is append-only (hard rule 5).
    flagged_ids = sorted(aid for aid, ev in evals.items() if ev.verdict in _FLAGGED)
    payloads = []
    for i, aid in enumerate(flagged_ids):
        ev = evals[aid]
        oc = outcomes.get(aid)
        ts = ANCHOR + timedelta(seconds=i)
        if oc:
            payloads.append(payload_from_eval(
                ev, run_id=run.run_id, ts=ts, action=oc["action"],
                gate_decision=oc["gate_decision"], gate_rule_id=oc["gate_rule_id"],
                gate_reason=oc["gate_reason"], proposal_summary=oc["proposal_summary"],
                approver=oc["approver"]))
        else:
            payloads.append(payload_from_eval(
                ev, run_id=run.run_id, ts=ts, action=RecordAction.EVALUATE))

    chain = build_chain(SITE_ID, payloads, generated_at=run.finished_at)
    assert verify_chain(chain), "record chain failed to verify — this must never ship"

    summary = {
        "run_id": run.run_id,
        "site_id": run.site_id,
        "model_name": run.model_name,
        "scanned_count": run.scanned_count,
        "flagged_count": run.flagged_count,
        "conflicts_count": run.conflicts_count,
        "resolved_count": run.resolved_count,
        "escalated_count": run.escalated_count,
        "record_entries": len(chain.entries),
        "chain_verified": True,
        "head_hash": chain.head_hash,
        "steps": len(run.steps),
    }
    return UnattendedResult(run=run, chain=chain, summary=summary)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="WORKFACE unattended agent run (T3, Day 8)")
    ap.add_argument("--llm", action="store_true",
                    help="use the configured model for PROPOSE (default: deterministic)")
    args = ap.parse_args(argv)

    result = run_unattended(use_llm=args.llm)
    RUN_PATH.write_text(result.run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    CHAIN_PATH.write_text(result.chain.model_dump_json(indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(result.summary, indent=2) + "\n", encoding="utf-8")

    s = result.summary
    print(f"[ok] unattended run {s['run_id']}")
    print(f"     scanned {s['scanned_count']}, flagged {s['flagged_count']}, "
          f"conflicts {s['conflicts_count']}, resolved {s['resolved_count']}, escalated {s['escalated_count']}")
    print(f"     record: {s['record_entries']} entries, chain_verified={s['chain_verified']}, head={s['head_hash'][:16]}…")
    print(f"     wrote {RUN_PATH.name}, {CHAIN_PATH.name}, {SUMMARY_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
