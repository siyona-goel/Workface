import chainJson from "@/data/record-chain.json";
import metaJson from "@/data/record-meta.json";
import { ribbonData } from "@/lib/ribbon-data";
import type { Verdict } from "@/lib/console-data";

export type RecordAction =
  | "evaluate"
  | "shift"
  | "split"
  | "resequence"
  | "mitigate"
  | "rfi"
  | "notify"
  | "escalate"
  | "no_action";

export type RecordVerdict = Verdict;

export type UsdExposure = {
  at_risk_usd: number;
  protected_usd: number;
  basis: string;
};

export type RecordPayload = {
  run_id: string;
  ts: string;
  activity_id: string;
  activity_name: string;
  trade_id: string;
  trade_display_name: string;
  work_face_id: string;
  work_face_name: string;
  tier: string;
  verdict: RecordVerdict;
  binding_constraint_id: string | null;
  clause_cited: string;
  standard_ref: string;
  compliant_hours: number | null;
  action: RecordAction;
  proposal_summary: string | null;
  gate_decision: "approve" | "modify" | "deny" | null;
  gate_rule_id: string | null;
  gate_reason: string | null;
  approver: string | null;
  fg_activity_ids: string[];
  series_digest: string | null;
  registry_version: string | null;
  usd_exposure: UsdExposure | null;
  advisory_notice: string;
};

export type RecordEntry = {
  seq: number;
  prev_hash: string;
  hash: string;
  algo: string;
  payload: RecordPayload;
};

export type RecordChain = {
  schema_version: string;
  site_id: string;
  generated_at: string;
  entries: RecordEntry[];
  head_hash: string | null;
};

export type WorkPackage = {
  activity_id: string;
  activity_name: string;
  work_face_id: string;
  work_face_name: string;
  trade_display_name: string;
  latest_verdict: RecordVerdict;
  latest_action: RecordAction;
  at_risk_usd: number;
  protected_usd: number;
  entries: RecordEntry[];
  latest_ts: string;
};

export const recordChain = chainJson as unknown as RecordChain;

export const recordMeta = metaJson as unknown as {
  schema_version: string;
  heat_intelligence: {
    pdf_url: string;
    title: string;
    work_face_id: string;
    work_face_name: string;
    activity_id: string;
    activity_name: string;
    fg_activity_id: string;
    source_date: string;
    temperature_c: number;
    temperature_source: string;
    note: string;
  };
  exposure_totals: {
    at_risk_usd: number;
    protected_usd: number;
    basis: string;
  };
};

export const ACTION_LABEL: Record<RecordAction, string> = {
  evaluate: "Evaluated",
  shift: "Shifted",
  split: "Split",
  resequence: "Resequenced",
  mitigate: "Mitigation requested",
  rfi: "RFI raised",
  notify: "Crew notified",
  escalate: "Escalated",
  no_action: "No action",
};

export const VERDICT_TONE: Record<RecordVerdict, string> = {
  compliant: "border-emerald-400/35 bg-emerald-400/8 text-emerald-100",
  at_risk: "border-amber-400/40 bg-amber-400/10 text-amber-100",
  non_compliant: "border-red-400/45 bg-red-400/10 text-red-100",
  insufficient_window: "border-orange-400/40 bg-orange-400/10 text-orange-100",
  no_data: "border-border/70 bg-muted/20 text-muted-foreground",
};

export function workPackagesFromChain(chain: RecordChain = recordChain): WorkPackage[] {
  const byActivity = new Map<string, RecordEntry[]>();
  for (const entry of chain.entries) {
    const list = byActivity.get(entry.payload.activity_id) ?? [];
    list.push(entry);
    byActivity.set(entry.payload.activity_id, list);
  }

  return [...byActivity.entries()]
    .map(([activity_id, entries]) => {
      const sorted = [...entries].sort((a, b) => a.seq - b.seq);
      const latest = sorted[sorted.length - 1]!.payload;
      const at_risk = Math.max(
        ...sorted.map((e) => e.payload.usd_exposure?.at_risk_usd ?? 0),
      );
      const protectedUsd = Math.max(
        ...sorted.map((e) => e.payload.usd_exposure?.protected_usd ?? 0),
      );
      return {
        activity_id,
        activity_name: latest.activity_name,
        work_face_id: latest.work_face_id,
        work_face_name: latest.work_face_name,
        trade_display_name: latest.trade_display_name,
        latest_verdict: latest.verdict,
        latest_action: latest.action,
        at_risk_usd: at_risk,
        protected_usd: protectedUsd,
        entries: sorted,
        latest_ts: latest.ts,
      };
    })
    .sort((a, b) => {
      if (a.at_risk_usd !== b.at_risk_usd) return b.at_risk_usd - a.at_risk_usd;
      return a.activity_name.localeCompare(b.activity_name);
    });
}

export function exposureTotals() {
  const fromRibbon = ribbonData.totals;
  return {
    at_risk_usd: recordMeta.exposure_totals.at_risk_usd ?? fromRibbon.at_risk_usd,
    protected_usd:
      recordMeta.exposure_totals.protected_usd ?? fromRibbon.protected_usd,
    basis: recordMeta.exposure_totals.basis ?? fromRibbon.basis,
    chain_at_risk_usd: recordChain.entries.reduce(
      (sum, e) => sum + (e.payload.usd_exposure?.at_risk_usd ?? 0),
      0,
    ),
    entry_count: recordChain.entries.length,
  };
}

const phoenixWhen = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/Phoenix",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatRecordWhen(iso: string) {
  return phoenixWhen.format(new Date(iso)).replace(",", "");
}

export function truncateHash(hash: string, chars = 8) {
  return `${hash.slice(0, chars)}…${hash.slice(-chars)}`;
}

export function clauseExcerpt(clause: string, max = 220) {
  if (clause.length <= max) return clause;
  return `${clause.slice(0, max).trim()}…`;
}

export function isHeroPackage(activityId: string) {
  return activityId === recordMeta.heat_intelligence.activity_id;
}

function sortDeep(value: unknown): unknown {
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
}

function canonicalPayloadJson(payload: RecordPayload): string {
  return JSON.stringify(sortDeep(payload));
}

async function computeEntryHash(payload: RecordPayload, prevHash: string) {
  const material = canonicalPayloadJson(payload) + prevHash;
  const bytes = new TextEncoder().encode(material);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyRecordChain(chain: RecordChain = recordChain) {
  for (const entry of chain.entries) {
    const ok = entry.hash === (await computeEntryHash(entry.payload, entry.prev_hash));
    if (!ok) return false;
  }
  return true;
}
