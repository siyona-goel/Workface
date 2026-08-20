"""
WORKFACE — the `record` contract (the hash chain + the thermal certificate).

    packages/schemas/record.py   (this file, Pydantic v2)
    packages/schemas/record.ts    (Zod — keep field-for-field identical)

Two handoffs share this file because they share the payload:
  - Handoff #6 (T3 -> T1): the record entries T1 renders as The Record timeline.
  - Handoff #7 (T3 -> T2): the record payload T2 renders as the certificate PDF
    (schema shipped Day 8, PDF rendered Day 9).

Why it matters (WORKFACE_PROJECT_PLAN.md §1.5, §4.4): Tier 2 is the business.
Every run writes an append-only, hash-chained entry — the warranty defence and
the weather-delay-claim evidence in one artifact. Provenance is the point: a
claims consultant takes an `fg_activity_id` back to FortyGuard and re-derives
the number.

The hash chain (WORKFACE_TECH_SPEC.md §8.4):

    entry_n.hash = sha256( canonical_json(entry_n.payload) || entry_{n-1}.hash )

`prev_hash` of the first (genesis) entry is GENESIS_PREV_HASH (64 zeros).
`compute_entry_hash()` below is the ONE canonical implementation — T1 and T2
must both verify against it, never re-implement the ordering by hand.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------

Changing a field here is a PR that tags T1 and T2. Never rename silently.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"

GENESIS_PREV_HASH = "0" * 64
_HASH_RE = r"^[0-9a-f]{64}$"

Iso8601 = Annotated[
    datetime,
    Field(description="ISO-8601 with offset. Site-local (America/Phoenix, UTC-07:00, no DST)."),
]


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class RecordAction(str, Enum):
    """What the run did to this activity. Mirrors the gated agent tools."""
    EVALUATE = "evaluate"        # observed only; window computed, nothing moved
    SHIFT = "shift"
    SPLIT = "split"
    RESEQUENCE = "resequence"
    MITIGATE = "mitigate"
    RFI = "rfi"                  # raised to the engineer of record
    NOTIFY = "notify"
    ESCALATE = "escalate"        # routed to a human; no action taken
    NO_ACTION = "no_action"


class GateDecision(str, Enum):
    """Kept in sync with agent_trace.GateDecision (self-contained per contract)."""
    APPROVE = "approve"
    MODIFY = "modify"
    DENY = "deny"


class RecordVerdict(str, Enum):
    """The compliance finding this entry attests to. Mirrors window_eval.Verdict."""
    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    NON_COMPLIANT = "non_compliant"
    INSUFFICIENT_WINDOW = "insufficient_window"
    NO_DATA = "no_data"


# --------------------------------------------------------------------------- #
# The payload
# --------------------------------------------------------------------------- #

class UsdExposure(BaseModel):
    """Same shape as window_eval.UsdExposure. Feeds the $ at-risk / $ protected counters."""
    model_config = ConfigDict(extra="forbid")

    at_risk_usd: float = Field(0.0, ge=0)
    protected_usd: float = Field(0.0, ge=0)
    basis: str = Field(..., description="How it was computed, e.g. 'quantity 4200 m2 x $34/m2 x 3.2'.")


class RecordPayload(BaseModel):
    """The immutable content of one record entry. This is what gets hashed.

    Keep it JSON-canonicalisable: no floats that vary by platform beyond what
    round-trips, no datetime objects that serialise ambiguously. Datetimes are
    serialised to ISO strings before hashing (see compute_entry_hash).
    """
    model_config = ConfigDict(extra="forbid")

    run_id: str
    ts: Iso8601 = Field(..., description="When this decision was recorded.")

    # --- what was evaluated ------------------------------------------------
    activity_id: str = Field(..., description="SCHEDULE activity. Never a FortyGuard handle.")
    activity_name: str
    trade_id: str
    trade_display_name: str
    work_face_id: str
    work_face_name: str
    tier: str = Field("commit", description="plan / commit / record.")

    # --- the finding -------------------------------------------------------
    verdict: RecordVerdict
    binding_constraint_id: str | None = None
    clause_cited: str = Field(..., min_length=20, description="The manufacturer / standard clause, verbatim enough to check.")
    standard_ref: str = Field(..., description="e.g. 'SSPC-PA 1 (AMPP), Section 6.2'.")
    compliant_hours: float | None = Field(None, ge=0, description="In-window hours found on the horizon.")

    # --- what the agent did ------------------------------------------------
    action: RecordAction
    proposal_summary: str | None = Field(None, max_length=600, description="One line of what was proposed.")
    gate_decision: GateDecision | None = None
    gate_rule_id: str | None = None
    gate_reason: str | None = Field(None, max_length=500)
    approver: str | None = Field(
        None, description="Human who approved a gated action, or the superintendent an escalation went to. "
                          "null for observe-only / auto-approved.",
    )

    # --- provenance --------------------------------------------------------
    fg_activity_ids: list[str] = Field(
        default_factory=list,
        description="FortyGuard handles the decision rests on. A claims consultant re-derives from these.",
    )
    series_digest: str | None = Field(None, description="sha256 of the canonical-JSON thermal series evaluated.")
    registry_version: str | None = Field(None, description="e.g. '2026.08.20-a'. Which registry cut was used.")
    usd_exposure: UsdExposure | None = None

    advisory_notice: str = Field(
        "Advisory and contractual. Does not replace the field measurement the referenced standard requires.",
        description="Never remove. Prints on the certificate.",
    )


class RecordEntry(BaseModel):
    """One link in the append-only chain. `hash` binds this payload to all before it."""
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(..., ge=0, description="0 = genesis. Strictly increasing, gapless within a site's chain.")
    prev_hash: str = Field(..., pattern=_HASH_RE, description="Previous entry's hash; 64 zeros for genesis.")
    hash: str = Field(..., pattern=_HASH_RE, description="sha256(canonical_json(payload) || prev_hash). Lowercase hex.")
    algo: str = Field("sha256", description="Hash algorithm. Fixed for v1.")
    payload: RecordPayload

    @model_validator(mode="after")
    def _genesis_consistency(self) -> RecordEntry:
        if self.seq == 0 and self.prev_hash != GENESIS_PREV_HASH:
            raise ValueError("genesis entry (seq=0) must have prev_hash = 64 zeros")
        return self

    def verify(self) -> bool:
        """True iff `hash` equals the recomputed hash. Cheap integrity check."""
        return self.hash == compute_entry_hash(self.payload, self.prev_hash)


class RecordChain(BaseModel):
    """The whole chain for one site. T1 renders the timeline; verify on load."""
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    site_id: str
    generated_at: Iso8601
    entries: list[RecordEntry]
    head_hash: str | None = Field(None, description="Hash of the last entry. The chain's fingerprint.")

    @field_validator("entries")
    @classmethod
    def _linked_and_ordered(cls, v: list[RecordEntry]) -> list[RecordEntry]:
        for i, entry in enumerate(v):
            if entry.seq != i:
                raise ValueError(f"entries must be gapless from 0; got seq={entry.seq} at index {i}")
            if i > 0 and entry.prev_hash != v[i - 1].hash:
                raise ValueError(f"broken chain at seq={entry.seq}: prev_hash != previous entry's hash")
        return v


# --------------------------------------------------------------------------- #
# The thermal certificate (handoff #7 — what T2 renders to PDF)
# --------------------------------------------------------------------------- #

class CertificateHour(BaseModel):
    """One hour on the certificate's as-built series. Air / surface / dew / WBGT + pass-fail."""
    model_config = ConfigDict(extra="forbid")

    ts: Iso8601
    t_air_c: float | None = None
    t_surf_c: float | None = None
    t_dew_c: float | None = None
    wbgt_c: float | None = None
    passed: bool = Field(..., description="Did every constraint hold this hour, for this trade?")
    note: str | None = Field(None, max_length=200, description="Why it failed, if it did.")


class ThermalCertificate(BaseModel):
    """The per-work-package artifact a claims consultant buys. T2 renders it to PDF.

    'The other half of the product looks backwards' (WORKFACE_PROJECT_PLAN.md §1.5).
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    certificate_id: str
    issued_at: Iso8601
    site_id: str
    site_name: str

    # --- the work package it certifies -------------------------------------
    activity_id: str
    activity_name: str
    wbs: str | None = None
    trade_id: str
    trade_display_name: str
    work_face_id: str
    work_face_name: str
    placed_start: Iso8601 | None = Field(None, description="Actual placement start, if recorded.")
    placed_finish: Iso8601 | None = None

    # --- the finding it attests to -----------------------------------------
    verdict: RecordVerdict
    clause_cited: str = Field(..., min_length=20)
    standard_ref: str
    hours: list[CertificateHour] = Field(..., description="The as-built hourly series with pass/fail per hour.")

    # --- provenance & chain binding ----------------------------------------
    fg_activity_ids: list[str] = Field(default_factory=list)
    record_entry_hashes: list[str] = Field(
        default_factory=list,
        description="Hashes of the record entries this certificate summarises. Ties the PDF to the chain.",
    )
    registry_version: str | None = None
    heat_intelligence_pdf_ref: str | None = Field(
        None, description="Optional path to the FortyGuard heat_intelligence PDF for the hero face.",
    )
    approver: str | None = None
    advisory_notice: str = Field(
        "Advisory and contractual. Does not replace the field measurement the referenced standard requires.",
        description="Never remove. Prints on the certificate footer.",
    )

    @field_validator("hours")
    @classmethod
    def _hours_ordered(cls, v: list[CertificateHour]) -> list[CertificateHour]:
        if not v:
            raise ValueError("a certificate must carry at least one hour of series")
        for a, b in zip(v, v[1:]):
            if b.ts <= a.ts:
                raise ValueError(f"certificate hours must be strictly increasing: {a.ts} -> {b.ts}")
        return v


# --------------------------------------------------------------------------- #
# The canonical hash — ONE implementation. Do not re-derive by hand.
# --------------------------------------------------------------------------- #

def _ecmascript_numbers(o):
    """Normalise numbers so Python's JSON matches JavaScript's, cross-language.

    JavaScript has ONE number type: `JSON.stringify(3.0)` is `"3"`, but Python's
    `json.dumps(3.0)` is `"3.0"`. Left alone, the two sides hash differently
    (this bit us on `compliant_hours: 3.0`). We fold every integral float to an
    int so both emit `3`. Non-integral doubles already agree — Python's
    `repr(float)` and JS `String(n)` both emit the shortest round-tripping form.
    This is the number rule RFC 8785 (JSON Canonicalization Scheme) also mandates.
    (bool is an int subclass in Python — guard it first so True/False survive.)
    """
    if isinstance(o, bool):
        return o
    if isinstance(o, float):
        return int(o) if math.isfinite(o) and o == int(o) else o
    if isinstance(o, dict):
        return {k: _ecmascript_numbers(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_ecmascript_numbers(v) for v in o]
    return o


def canonical_payload_json(payload: RecordPayload) -> str:
    """Deterministic JSON for hashing: sorted keys, no whitespace, ISO datetimes.

    The Zod side (record.ts) documents and implements the SAME canonicalisation.
    If you touch one, touch both, or the chains will diverge across the worker
    and the browser. Two rules make this cross-language:
      - keys sorted, separators (",", ":"), UTF-8, no ASCII escaping;
      - integral floats folded to ints (see _ecmascript_numbers) so Python and
        JavaScript print the same digits.
    Datetimes are serialised by the worker (mode="json" -> ISO with offset); the
    browser verifies over the worker's stored payload, so both see one string.
    """
    obj = _ecmascript_numbers(payload.model_dump(mode="json"))  # dt -> ISO, enums -> values
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_entry_hash(payload: RecordPayload, prev_hash: str) -> str:
    """entry.hash = sha256( canonical_json(payload) || prev_hash ). Lowercase hex."""
    material = canonical_payload_json(payload) + prev_hash
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def make_entry(payload: RecordPayload, prev_hash: str, seq: int) -> RecordEntry:
    """Build a fully-linked entry. The only sanctioned way to append to the chain."""
    return RecordEntry(
        seq=seq,
        prev_hash=prev_hash,
        hash=compute_entry_hash(payload, prev_hash),
        payload=payload,
    )


__all__ = [
    "SCHEMA_VERSION", "GENESIS_PREV_HASH",
    "RecordAction", "GateDecision", "RecordVerdict",
    "UsdExposure", "RecordPayload", "RecordEntry", "RecordChain",
    "CertificateHour", "ThermalCertificate",
    "canonical_payload_json", "compute_entry_hash", "make_entry",
]
