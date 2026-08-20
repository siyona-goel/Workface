/**
 * WORKFACE — the `record` contract (Zod mirror of record.py).
 *
 * Two handoffs share this file because they share the payload:
 *   - Handoff #6 (T3 -> T1): the record entries T1 renders as The Record timeline.
 *   - Handoff #7 (T3 -> T2): the record payload T2 renders as the certificate PDF.
 *
 * The hash chain (WORKFACE_TECH_SPEC.md §8.4):
 *   entry_n.hash = sha256( canonicalPayloadJson(entry_n.payload) || entry_{n-1}.hash )
 *
 * `computeEntryHash` below MUST stay byte-identical to record.py's
 * compute_entry_hash — sorted keys, no whitespace, ISO datetime strings — or
 * the worker's chain and the browser's verification will diverge. If you touch
 * one canonicalisation, touch both.
 *
 * Keep this field-for-field identical to packages/schemas/record.py.
 * Any change is a PR that tags T1 and T2. Never rename a field silently.
 *
 * ---------------------------------------------------------------------------
 * WORKFACE NAMING RULE — do not violate.
 *   activityId / activity_id    = a scheduled construction task
 *   fgActivityId / fg_activity_id = a FortyGuard async job handle
 * ---------------------------------------------------------------------------
 *
 * Wire format is snake_case. Parse as-is.
 */

import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0";

export const GENESIS_PREV_HASH = "0".repeat(64);
const HASH_RE = /^[0-9a-f]{64}$/;
const Hash = z.string().regex(HASH_RE, "must be lowercase 64-char hex sha256");

/** ISO-8601 with offset, site-local (America/Phoenix, UTC-07:00, no DST). */
const Iso8601 = z.string().datetime({ offset: true });

/* -------------------------------------------------------------------------- */
/* Enums                                                                      */
/* -------------------------------------------------------------------------- */

/** What the run did to this activity. Mirrors the gated agent tools. */
export const RecordAction = z.enum([
  "evaluate",
  "shift",
  "split",
  "resequence",
  "mitigate",
  "rfi",
  "notify",
  "escalate",
  "no_action",
]);
export type RecordAction = z.infer<typeof RecordAction>;

/** Kept in sync with agent_trace.GateDecision. */
export const GateDecision = z.enum(["approve", "modify", "deny"]);
export type GateDecision = z.infer<typeof GateDecision>;

/** The compliance finding this entry attests to. Mirrors window_eval.Verdict. */
export const RecordVerdict = z.enum([
  "compliant",
  "at_risk",
  "non_compliant",
  "insufficient_window",
  "no_data",
]);
export type RecordVerdict = z.infer<typeof RecordVerdict>;

/* -------------------------------------------------------------------------- */
/* The payload                                                                */
/* -------------------------------------------------------------------------- */

/** Same shape as window_eval.UsdExposure. */
export const UsdExposure = z.object({
  at_risk_usd: z.number().min(0).default(0),
  protected_usd: z.number().min(0).default(0),
  basis: z.string(),
});
export type UsdExposure = z.infer<typeof UsdExposure>;

/** The immutable content of one record entry. This is what gets hashed. */
export const RecordPayload = z.object({
  run_id: z.string(),
  ts: Iso8601,

  /* what was evaluated */
  /** SCHEDULE activity. Never a FortyGuard handle. */
  activity_id: z.string(),
  activity_name: z.string(),
  trade_id: z.string(),
  trade_display_name: z.string(),
  work_face_id: z.string(),
  work_face_name: z.string(),
  tier: z.string().default("commit"),

  /* the finding */
  verdict: RecordVerdict,
  binding_constraint_id: z.string().nullable().default(null),
  clause_cited: z.string().min(20),
  standard_ref: z.string(),
  compliant_hours: z.number().min(0).nullable().default(null),

  /* what the agent did */
  action: RecordAction,
  proposal_summary: z.string().max(600).nullable().default(null),
  gate_decision: GateDecision.nullable().default(null),
  gate_rule_id: z.string().nullable().default(null),
  gate_reason: z.string().max(500).nullable().default(null),
  /** Human who approved a gated action / escalation target. null for auto/observe-only. */
  approver: z.string().nullable().default(null),

  /* provenance */
  fg_activity_ids: z.array(z.string()).default([]),
  series_digest: z.string().nullable().default(null),
  registry_version: z.string().nullable().default(null),
  usd_exposure: UsdExposure.nullable().default(null),

  /** Never remove. Prints on the certificate. */
  advisory_notice: z
    .string()
    .default(
      "Advisory and contractual. Does not replace the field measurement the referenced standard requires.",
    ),
});
export type RecordPayload = z.infer<typeof RecordPayload>;

/** One link in the append-only chain. `hash` binds this payload to all before it. */
export const RecordEntry = z
  .object({
    seq: z.number().int().min(0),
    prev_hash: Hash,
    hash: Hash,
    algo: z.string().default("sha256"),
    payload: RecordPayload,
  })
  .superRefine((v, ctx) => {
    if (v.seq === 0 && v.prev_hash !== GENESIS_PREV_HASH) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "genesis entry (seq=0) must have prev_hash = 64 zeros",
        path: ["prev_hash"],
      });
    }
  });
export type RecordEntry = z.infer<typeof RecordEntry>;

/** The whole chain for one site. T1 renders the timeline; verify on load. */
export const RecordChain = z
  .object({
    schema_version: z.string().default(SCHEMA_VERSION),
    site_id: z.string(),
    generated_at: Iso8601,
    entries: z.array(RecordEntry),
    /** Hash of the last entry. The chain's fingerprint. */
    head_hash: Hash.nullable().default(null),
  })
  .superRefine((v, ctx) => {
    for (let i = 0; i < v.entries.length; i++) {
      const e = v.entries[i];
      if (e.seq !== i) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `entries must be gapless from 0; got seq=${e.seq} at index ${i}`,
          path: ["entries", i, "seq"],
        });
        break;
      }
      if (i > 0 && e.prev_hash !== v.entries[i - 1].hash) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `broken chain at seq=${e.seq}: prev_hash != previous entry's hash`,
          path: ["entries", i, "prev_hash"],
        });
        break;
      }
    }
  });
export type RecordChain = z.infer<typeof RecordChain>;

/* -------------------------------------------------------------------------- */
/* The thermal certificate (handoff #7 — what T2 renders to PDF)              */
/* -------------------------------------------------------------------------- */

/** One hour on the certificate's as-built series. Air / surface / dew / WBGT + pass-fail. */
export const CertificateHour = z.object({
  ts: Iso8601,
  t_air_c: z.number().nullable().default(null),
  t_surf_c: z.number().nullable().default(null),
  t_dew_c: z.number().nullable().default(null),
  wbgt_c: z.number().nullable().default(null),
  /** Did every constraint hold this hour, for this trade? */
  passed: z.boolean(),
  note: z.string().max(200).nullable().default(null),
});
export type CertificateHour = z.infer<typeof CertificateHour>;

/** The per-work-package artifact a claims consultant buys. T2 renders it to PDF. */
export const ThermalCertificate = z
  .object({
    schema_version: z.string().default(SCHEMA_VERSION),
    certificate_id: z.string(),
    issued_at: Iso8601,
    site_id: z.string(),
    site_name: z.string(),

    /* the work package it certifies */
    activity_id: z.string(),
    activity_name: z.string(),
    wbs: z.string().nullable().default(null),
    trade_id: z.string(),
    trade_display_name: z.string(),
    work_face_id: z.string(),
    work_face_name: z.string(),
    placed_start: Iso8601.nullable().default(null),
    placed_finish: Iso8601.nullable().default(null),

    /* the finding it attests to */
    verdict: RecordVerdict,
    clause_cited: z.string().min(20),
    standard_ref: z.string(),
    hours: z.array(CertificateHour).min(1),

    /* provenance & chain binding */
    fg_activity_ids: z.array(z.string()).default([]),
    /** Hashes of the record entries this certificate summarises. Ties the PDF to the chain. */
    record_entry_hashes: z.array(Hash).default([]),
    registry_version: z.string().nullable().default(null),
    heat_intelligence_pdf_ref: z.string().nullable().default(null),
    approver: z.string().nullable().default(null),
    /** Never remove. Prints on the certificate footer. */
    advisory_notice: z
      .string()
      .default(
        "Advisory and contractual. Does not replace the field measurement the referenced standard requires.",
      ),
  })
  .superRefine((v, ctx) => {
    for (let i = 1; i < v.hours.length; i++) {
      if (v.hours[i].ts <= v.hours[i - 1].ts) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `certificate hours must be strictly increasing at index ${i}`,
          path: ["hours", i, "ts"],
        });
        break;
      }
    }
  });
export type ThermalCertificate = z.infer<typeof ThermalCertificate>;

/* -------------------------------------------------------------------------- */
/* The canonical hash — ONE implementation. Keep byte-identical to record.py. */
/* -------------------------------------------------------------------------- */

/**
 * Deterministic JSON for hashing: sorted keys, no whitespace.
 * Mirrors record.py's canonical_payload_json (Python json.dumps with
 * sort_keys=True, separators=(",", ":")).
 *
 * Numbers: JavaScript's native `JSON.stringify` is the REFERENCE format —
 * `3.0` prints as `3`, shortest round-trip otherwise. record.py folds integral
 * floats to ints so its output matches this exactly (RFC 8785 number rule).
 * So JS needs no number handling here; JSON.stringify already does the right thing.
 *
 * Datetimes are already ISO strings on the wire, so no coercion is needed here —
 * but callers MUST verify over the same snake_case, ISO-stringed payload the
 * Python worker dumped (that is the object stored in the record entry).
 */
export function canonicalPayloadJson(payload: RecordPayload): string {
  const sortDeep = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(sortDeep);
    if (value && typeof value === "object") {
      return Object.keys(value as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, k) => {
          acc[k] = sortDeep((value as Record<string, unknown>)[k]);
          return acc;
        }, {});
    }
    return value;
  };
  return JSON.stringify(sortDeep(payload));
}

/**
 * entry.hash = sha256( canonicalPayloadJson(payload) || prev_hash ), lowercase hex.
 * Async because it uses the Web Crypto SubtleCrypto digest (browser + Node 18+).
 */
export async function computeEntryHash(payload: RecordPayload, prevHash: string): Promise<string> {
  const material = canonicalPayloadJson(payload) + prevHash;
  const bytes = new TextEncoder().encode(material);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** True iff `entry.hash` matches the recomputed hash. Cheap integrity check. */
export async function verifyEntry(entry: RecordEntry): Promise<boolean> {
  return entry.hash === (await computeEntryHash(entry.payload, entry.prev_hash));
}
