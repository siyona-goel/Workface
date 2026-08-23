# Handoff #7 — the record payload shape (T3 → T2)

**For:** T2, building the thermal-certificate PDF on the record chain (Day 9).
**Committed example:** [`data/fixtures/record_chain_live.json`](../data/fixtures/record_chain_live.json)
— a real, verified 22-entry chain from the unattended run. Load it, verify it, render it.
**Schema (authority):** [`packages/schemas/record.py`](../packages/schemas/record.py)
(Pydantic) and `record.ts` (Zod, field-for-field identical).
**Builder:** [`apps/api/agent/record.py`](../apps/api/agent/record.py) —
`build_chain`, `payload_from_eval`, `verify_chain`.

You do **not** need to read T3 source to render the PDF. Everything is below.

---

## The chain

```
RecordChain
├─ schema_version   "1.0.0"
├─ site_id          "NPX-FAB-P2"
├─ generated_at     ISO-8601 with offset (site-local, America/Phoenix, UTC-07:00, no DST)
├─ entries          RecordEntry[]   — gapless from seq 0, each linked to the one before
└─ head_hash        hash of the last entry — the chain's fingerprint (print it on the cert)
```

```
RecordEntry
├─ seq        0 = genesis, strictly increasing, gapless
├─ prev_hash  previous entry's hash; 64 zeros ("0"*64) for genesis
├─ hash       sha256( canonical_json(payload) || prev_hash ), lowercase hex
├─ algo       "sha256" (fixed for v1)
└─ payload    RecordPayload   — the immutable, hashed content
```

**Verifying (do this on load, and cite it on the PDF):**
`entry.hash == sha256(canonical_json(payload) + prev_hash)`. Use `verify_chain` on
the Python side or `compute_entry_hash` on the Zod side — **never re-implement the
ordering by hand**, or the browser and worker chains diverge. Canonicalisation is:
sorted keys, separators `(",", ":")`, UTF-8 (no ASCII escaping), and **integral
floats folded to ints** (`compliant_hours: 3.0` serialises as `3`, not `3.0` — the
one cross-language gotcha; the scheme in `record.py` handles it).

---

## RecordPayload — field by field

| Field | Type | Meaning / what to print |
|---|---|---|
| `run_id` | str | The agent run that wrote this entry, e.g. `agent-2026-08-24-0000-commit-live`. |
| `ts` | ISO-8601 | When the decision was recorded. |
| `activity_id` | str | The **schedule** activity (P6). **Never** a FortyGuard handle. |
| `activity_name` | str | Human name, e.g. "Equipment pad pour — CT grade — bay A1". |
| `trade_id` / `trade_display_name` | str | Registry trade id and its display name (the cert header). |
| `work_face_id` / `work_face_name` | str | The face this attests to. |
| `tier` | str | `plan` / `commit` / `record`. Demo entries are `commit`. |
| `verdict` | enum | `compliant` / `at_risk` / `non_compliant` / `insufficient_window` / `no_data`. Drives the pass/fail badge. |
| `binding_constraint_id` | str? | The constraint that governs (e.g. `offset_dew_point`, `composite_evaporation_rate`). |
| `clause_cited` | str (≥20 chars) | **The manufacturer/standard clause, verbatim enough to check.** This is the body of the certificate's "basis" section — print it in full. |
| `standard_ref` | str | Short citation, e.g. `SSPC-PA 1 (AMPP) §6.1–6.3`, `ACI 301-20; ACI 305.1-14 §3.2–3.3`. The footnote. |
| `compliant_hours` | float? | Longest open (compliant) window found on the horizon, in hours. |
| `action` | enum | What the agent did: `evaluate` / `shift` / `split` / `resequence` / `mitigate` / `rfi` / `notify` / `escalate` / `no_action`. |
| `proposal_summary` | str? | One line of what was proposed/decided (the escalation note or the shift rationale). |
| `gate_decision` | enum? | `approve` / `modify` / `deny` — the policy gate's verdict, when a gated action was involved. |
| `gate_rule_id` | str? | Which rule fired, e.g. `no_move_inspection_hold_point`, `split_within_float_ok`. |
| `gate_reason` | str? | One human sentence naming the rule's basis. Print this next to the decision. |
| `approver` | str? | Human who approved a gated action, or the superintendent an escalation went to. **null** for observe-only / auto-approved (all demo entries are null in REPLAY). |
| `fg_activity_ids` | str[] | **FortyGuard handles the decision rests on.** A claims consultant takes one of these back to FortyGuard and re-derives the number. **This is the provenance line to print.** May be empty for a face whose series carried no handle (see note). |
| `series_digest` | str? | sha256 of the canonical thermal series evaluated — ties the entry to exact data. |
| `registry_version` | str? | Which registry cut, e.g. `2026.08.20-a`. |
| `usd_exposure` | object? | See below. |
| `advisory_notice` | str | **Never remove — prints on the certificate.** "Advisory and contractual. Does not replace the field measurement the referenced standard requires." |

### `usd_exposure`

```
UsdExposure
├─ at_risk_usd    float   — exposure if the window is missed (non-compliant path)
├─ protected_usd  float   — exposure avoided if compliant (compliant path)
└─ basis          str     — HOW it was computed, verbatim. e.g.
                            "quantity 4200 m2 x $34/m2 x rework multiplier 3.2"
```

`basis` is the arithmetic string, not a code — print it so the number is auditable.
Exactly one of `at_risk_usd` / `protected_usd` is non-zero (which one follows `verdict`).

---

## The ThermalCertificate (what you render to PDF)

`record.py` also defines `ThermalCertificate` (the per-work-package artifact). It
reuses the same `clause_cited` / `standard_ref` / `verdict` / `fg_activity_ids`, plus
an hourly `hours: CertificateHour[]` series (air/surface/dew/WBGT + `passed` per hour)
and `record_entry_hashes` — **the hashes of the record entries this cert summarises,
tying the PDF back to the chain.** Pull those from the entries you render.

---

## Notes for the build

- **`fg_activity_ids` can be empty** on a face whose thermal series carried no handle
  in the current bundle (e.g. WF-SUB-02 / A-1237 in the committed example). The field
  is always present; render "—" when empty, and note that provenance re-derivation
  needs the handle. This is a data-coverage gap to flag, not a schema issue.
- **Do not mutate an entry.** The chain is append-only (hard rule 5). To add, build a
  new chain over one more payload — the existing hashes are stable.
- **`gate_*` fields are null for observe-only (evaluate) entries** — only decisions
  that ran the gate carry them.

Questions → T3. The schema is frozen for v1; a field change is a PR that tags T1 and T2.
