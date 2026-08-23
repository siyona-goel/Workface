"""
WORKFACE — run the live agent loop and write its AgentRun.  T3, Day 6, Task E.

    python -m scripts.make_agent_run_live            # write agent_run_live.json
    python -m scripts.make_agent_run_live --diff      # + diff vs the hand fixture

Runs apps/api/agent/loop.run_agent (SCAN -> EVALUATE -> CONFLICT) and serialises
the real AgentRun to a NEW path — data/fixtures/agent_run_live.json.

    IT NEVER OVERWRITES data/fixtures/sample_agent_run.json. T1 is building the
    Trace view against that hand-written fixture today; having it change under
    them mid-day is the one thing that would cost them the day (brief §7 / §9).
    The --diff reports every field the live loop populates differently so T1 can
    adopt the live run deliberately, not by surprise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps.api.agent.loop import run_agent
from packages.schemas.agent_trace import AgentRun

_REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = _REPO_ROOT / "data" / "fixtures"
LIVE = FIXTURES / "agent_run_live.json"
HAND = FIXTURES / "sample_agent_run.json"


def _counters(run: AgentRun) -> dict:
    return {
        "scanned_count": run.scanned_count, "flagged_count": run.flagged_count,
        "conflicts_count": run.conflicts_count, "resolved_count": run.resolved_count,
        "escalated_count": run.escalated_count,
        "step_types": [s.type.value for s in run.steps],
        "model_name": run.model_name, "lookahead_h": run.lookahead_h,
    }


def print_diff(live: AgentRun) -> None:
    hand = AgentRun.model_validate_json(HAND.read_text(encoding="utf-8"))
    lc, hc = _counters(live), _counters(hand)
    print("\n=== agent run: live loop vs hand-written fixture ===")
    print(f"{'field':<18}{'hand (sample)':<40}{'live loop':<40}")
    for k in lc:
        same = "" if lc[k] == hc[k] else "  <-- differs"
        print(f"{k:<18}{str(hc[k]):<40}{str(lc[k])!s:<40}{same}")
    print("\nExpected differences (by design, not drift):")
    print(" * the hand fixture runs the FULL loop (propose/gate/act/escalate); the Day-6")
    print("   live loop is SCAN/EVALUATE/CONFLICT only, so resolved/escalated are 0 and")
    print("   there are no propose/gate/act/record steps yet (those are Day 7+).")
    print(" * model_name is 'none' — the Day-6 gate is pure Python, no LLM.")
    print(" * scanned_count 62 (overlap at the 2026-08-24 horizon) vs the fixture's 328")
    print("   (whole schedule); flagged/conflict counts are the real evaluator's output.")


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE live agent loop (T3, Day 6/7)")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--llm", action="store_true",
                    help="use the configured model for PROPOSE (default: deterministic, so the "
                         "committed fixture is reproducible and CI-stable)")
    args = ap.parse_args()

    run = run_agent(use_llm=args.llm)
    text = run.model_dump_json(indent=2)
    AgentRun.model_validate_json(text)                 # must not raise
    LIVE.write_text(text + "\n", encoding="utf-8")
    print(f"[ok] {LIVE.name}: scanned {run.scanned_count}, flagged {run.flagged_count}, "
          f"conflicts {run.conflicts_count}, {len(run.steps)} steps "
          f"({' -> '.join(s.type.value for s in run.steps)})")
    assert HAND.exists() and "sample_agent_run.json" not in str(LIVE), "must not overwrite the hand fixture"

    if args.diff:
        print_diff(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
