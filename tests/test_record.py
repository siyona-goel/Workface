"""
WORKFACE — Day-8 record chain tests.  T3, Task G (§8.4).

The chain is the whole product, so it is tested like one:
  * build_chain over real evals verifies;
  * canonical JSON is deterministic across a re-serialisation (round-trip);
  * integral floats fold to ints (the compliant_hours: 3.0 bug the scheme fixes);
  * genesis prev_hash is 64 zeros;
  * TAMPERING is caught — break an entry and verify_chain returns False;
  * the record is append-only — building with one more payload is a NEW chain.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.api.agent.record import build_chain, payload_from_eval, verify_chain
from apps.api.windows.evaluate import evaluate_window
from apps.api.windows.registry import load_registry
from packages.schemas.record import (
    GENESIS_PREV_HASH,
    RecordAction,
    RecordPayload,
    canonical_payload_json,
    compute_entry_hash,
)

TZ = timezone(timedelta(hours=-7))


def _real_evals(ids=("A-1237", "A-1205", "A-1088")):
    from apps.api.agent.loop import _horizon, _load_activities, _load_faces, _load_thermal
    from scripts.make_ribbon_fixture import _bar, _series_for_face
    reg, faces, thermal = load_registry(), _load_faces(), _load_thermal()
    byid = {a["id"]: a for a in _load_activities()}
    out = []
    for aid in ids:
        a = byid[aid]
        wf = a["work_face_id"]
        series, ts = _series_for_face(thermal[wf], faces[wf]["surface_class"])
        out.append(evaluate_window(
            trade_id=a["trade_id"], series=series, ts=ts, scheduled=_bar(a),
            activity_id=aid, activity_name=a["name"], work_face_id=wf,
            work_face_name=faces[wf]["name"], run_id="rec-test", horizon=_horizon(), registry=reg))
    return out


def _chain_of(evals):
    payloads = [payload_from_eval(ev, run_id="rec-test", ts=datetime(2026, 8, 24, 8, i, tzinfo=TZ),
                                  action=RecordAction.EVALUATE) for i, ev in enumerate(evals)]
    return build_chain("NPX-FAB-P2", payloads)


def test_build_chain_verifies_and_links():
    chain = _chain_of(_real_evals())
    assert verify_chain(chain)
    assert chain.entries[0].seq == 0
    assert chain.entries[0].prev_hash == GENESIS_PREV_HASH
    for a, b in zip(chain.entries, chain.entries[1:]):
        assert b.prev_hash == a.hash                    # each links to the one before
    assert chain.head_hash == chain.entries[-1].hash


def test_canonical_json_is_deterministic_across_reserialisation():
    """The chain only verifies if canonicalisation is stable. Round-trip a payload
    through JSON and confirm the canonical form — and thus the hash — is identical."""
    ev = _real_evals(("A-1237",))[0]
    payload = payload_from_eval(ev, run_id="rec-test", ts=datetime(2026, 8, 24, 8, 0, tzinfo=TZ),
                                action=RecordAction.SHIFT)
    c1 = canonical_payload_json(payload)
    reser = RecordPayload.model_validate_json(payload.model_dump_json())
    c2 = canonical_payload_json(reser)
    assert c1 == c2
    assert compute_entry_hash(payload, GENESIS_PREV_HASH) == compute_entry_hash(reser, GENESIS_PREV_HASH)


def test_integral_floats_fold_to_ints():
    """compliant_hours: 3.0 must canonicalise to `3`, not `3.0`, or the Python
    worker and the JS browser hash differently (the bug the scheme fixes)."""
    ev = _real_evals(("A-1237",))[0]
    payload = payload_from_eval(ev, run_id="rec-test", ts=datetime(2026, 8, 24, 8, 0, tzinfo=TZ),
                                action=RecordAction.EVALUATE)
    obj = payload.model_copy(update={"compliant_hours": 3.0})
    canon = canonical_payload_json(obj)
    assert '"compliant_hours":3' in canon
    assert '"compliant_hours":3.0' not in canon


def test_genesis_prev_hash_is_64_zeros():
    chain = _chain_of(_real_evals(("A-1237",)))
    assert chain.entries[0].prev_hash == "0" * 64


def test_tampering_is_caught():
    """Break an entry's payload after the fact; the recomputed hash no longer
    matches, so verify_chain returns False. A chain nobody has seen fail is untested."""
    chain = _chain_of(_real_evals())
    assert verify_chain(chain)
    chain.entries[1].payload.activity_name = "TAMPERED — never happened"
    assert verify_chain(chain) is False


def test_tampering_with_the_hash_itself_is_caught():
    chain = _chain_of(_real_evals())
    chain.entries[0].hash = "0" * 64                     # forge the genesis hash
    assert verify_chain(chain) is False


def test_record_is_append_only_a_new_payload_is_a_new_chain():
    """Appending is building a NEW chain over one more payload — there is no update
    path (hard rule 5). The old chain's head is unchanged; the new one extends it."""
    evals = _real_evals()
    c1 = _chain_of(evals)
    c2 = _chain_of(evals + evals[:1])
    assert len(c2.entries) == len(c1.entries) + 1
    # every original entry hashes identically — the chain is deterministic, not mutated.
    for a, b in zip(c1.entries, c2.entries):
        assert a.hash == b.hash


def test_provenance_carried_through_untouched():
    """clause_cited (>=20), standard_ref, series_digest and fg handles reach the
    entry — the sentence you say on stage only works if the ids are real."""
    ev = _real_evals(("A-1237",))[0]
    p = payload_from_eval(ev, run_id="rec-test", ts=datetime(2026, 8, 24, 8, 0, tzinfo=TZ),
                          action=RecordAction.EVALUATE)
    assert len(p.clause_cited) >= 20
    assert p.standard_ref
    assert p.series_digest == ev.provenance.series_digest      # reused, not recomputed
    assert p.registry_version == ev.provenance.registry_version
