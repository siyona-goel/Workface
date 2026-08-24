"""
WORKFACE — the record: build the append-only hash chain.  T3, Day 8, Task G (§8.4).

    from apps.api.agent.record import build_chain, verify_chain, payload_from_eval

The chain is the product: an append-only, hash-linked log where
`entry_n.hash = sha256(canonical_json(payload_n) || entry_{n-1}.hash)` and the
genesis prev_hash is 64 zeros. The ONE canonical hash lives in
`packages/schemas/record.py` (`compute_entry_hash` / `make_entry`); this module
NEVER re-derives the ordering — it assembles payloads and links them through
`make_entry`, and `verify_chain` recomputes every hash from the payloads.

Provenance is the point (§8.4): every entry carries the `fg_activity_id`s the
decision rests on, the `series_digest` (reused from `evaluate.py`, never a second
differently-canonicalised hash), the clause cited (>= 20 chars, checkable) and
the standard_ref. A claims consultant takes an fg handle back to FortyGuard and
re-derives the number.

APPEND-ONLY (hard rule 5): no update path, no delete path, not even in tests. A
test that needs a different chain builds a new one.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task
#   fg_activity_id  = a FortyGuard async job handle
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime

from packages.schemas.record import (
    GENESIS_PREV_HASH,
    RecordAction,
    RecordChain,
    RecordEntry,
    RecordPayload,
    RecordVerdict,
    UsdExposure,
    compute_entry_hash,
    make_entry,
)
from packages.schemas.window_eval import Verdict, WindowEval

# window_eval.Verdict -> record.RecordVerdict (self-contained per the contract).
_VERDICT_MAP = {
    Verdict.COMPLIANT: RecordVerdict.COMPLIANT,
    Verdict.AT_RISK: RecordVerdict.AT_RISK,
    Verdict.NON_COMPLIANT: RecordVerdict.NON_COMPLIANT,
    Verdict.INSUFFICIENT_WINDOW: RecordVerdict.INSUFFICIENT_WINDOW,
    Verdict.NO_DATA: RecordVerdict.NO_DATA,
}


def _usd(ev: WindowEval) -> UsdExposure | None:
    u = ev.usd_exposure
    if u is None:
        return None
    return UsdExposure(at_risk_usd=u.at_risk_usd, protected_usd=u.protected_usd, basis=u.basis)


def payload_from_eval(
    ev: WindowEval,
    *,
    run_id: str,
    ts: datetime,
    action: RecordAction,
    tier: str = "commit",
    gate_decision=None,
    gate_rule_id: str | None = None,
    gate_reason: str | None = None,
    proposal_summary: str | None = None,
    approver: str | None = None,
) -> RecordPayload:
    """Build one immutable record payload from a WindowEval and what the agent did.

    The clause and standard_ref come straight off the evaluated trade (the citation
    carried since Day 2). series_digest / fg_activity_ids / registry_version are
    REUSED from the eval's provenance — never recomputed here, or the browser and
    worker chains diverge."""
    binding = ev.binding_constraint.constraint_id if ev.binding_constraint else None
    return RecordPayload(
        run_id=run_id,
        ts=ts,
        activity_id=ev.activity_id,
        activity_name=ev.activity_name,
        trade_id=ev.trade_id,
        trade_display_name=ev.trade_display_name,
        work_face_id=ev.work_face_id,
        work_face_name=ev.work_face_name,
        tier=tier,
        verdict=_VERDICT_MAP[ev.verdict],
        binding_constraint_id=binding,
        clause_cited=ev.citation,               # >= 20 chars, verbatim-enough-to-check
        standard_ref=ev.standard_ref,
        compliant_hours=max((iv.duration_h for iv in ev.open_intervals), default=0.0),
        action=action,
        proposal_summary=proposal_summary,
        gate_decision=gate_decision,
        gate_rule_id=gate_rule_id,
        gate_reason=(gate_reason[:500] if gate_reason else None),
        approver=approver,
        fg_activity_ids=list(ev.provenance.fg_activity_ids),
        series_digest=ev.provenance.series_digest,       # reuse evaluate._series_digest output
        registry_version=ev.provenance.registry_version,
        usd_exposure=_usd(ev),
    )


def build_chain(site_id: str, payloads: list[RecordPayload],
                generated_at: datetime | None = None) -> RecordChain:
    """Link payloads into an append-only chain, genesis first. `make_entry` is the
    ONLY sanctioned way to append (it computes the canonical hash)."""
    entries: list[RecordEntry] = []
    prev = GENESIS_PREV_HASH
    for seq, payload in enumerate(payloads):
        entry = make_entry(payload, prev, seq)
        entries.append(entry)
        prev = entry.hash
    return RecordChain(
        site_id=site_id,
        generated_at=generated_at or (payloads[0].ts if payloads else datetime.now()),
        entries=entries,
        head_hash=entries[-1].hash if entries else None,
    )


def verify_chain(chain: RecordChain) -> bool:
    """True iff every entry's hash recomputes from its payload and prev_hash, the
    links are intact, and the genesis prev_hash is 64 zeros. Recomputes from the
    payloads — the whole-product integrity check. Break an entry and this fails."""
    prev = GENESIS_PREV_HASH
    for i, entry in enumerate(chain.entries):
        if entry.seq != i:
            return False
        if entry.prev_hash != prev:
            return False
        if entry.hash != compute_entry_hash(entry.payload, entry.prev_hash):
            return False
        prev = entry.hash
    if chain.head_hash is not None and chain.entries and chain.head_hash != chain.entries[-1].hash:
        return False
    return True


__all__ = ["payload_from_eval", "build_chain", "verify_chain"]
