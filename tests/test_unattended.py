"""
WORKFACE — Day-8 gate.  T3, Task H (§8.4).

THE Day-8 gate: one entry point runs the whole loop unattended and writes a
chained record that verifies — with zero manual steps and no model. This is what
T2's cron calls. Runs deterministically (use_llm=False) so it is CI-stable.
"""

from __future__ import annotations

from apps.api.agent.record import verify_chain
from apps.api.agent.unattended import run_unattended


def test_unattended_run_completes_and_chain_verifies():
    result = run_unattended(use_llm=False)
    assert result.run.status.value == "completed"
    assert result.summary["chain_verified"] is True
    assert verify_chain(result.chain)
    # one record entry per flagged activity; the chain is gapless from genesis.
    assert len(result.chain.entries) == result.run.flagged_count
    assert result.chain.entries[0].seq == 0
    assert result.chain.head_hash == result.chain.entries[-1].hash


def test_unattended_record_carries_the_decisions_and_citations():
    result = run_unattended(use_llm=False)
    # A-1205's hold-point escalation is recorded as an escalate action.
    a1205 = next((e for e in result.chain.entries if e.payload.activity_id == "A-1205"), None)
    assert a1205 is not None and a1205.payload.action.value == "escalate"
    # every entry carries a checkable clause and a standard ref (§8.4).
    for e in result.chain.entries:
        assert len(e.payload.clause_cited) >= 20
        assert e.payload.standard_ref
