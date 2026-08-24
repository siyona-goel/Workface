"use client";

import {
  ACTION_LABEL,
  clauseExcerpt,
  formatRecordWhen,
  truncateHash,
  type RecordEntry,
  type RecordVerdict,
  type WorkPackage,
} from "@/lib/record-data";
import { formatUsd } from "@/lib/console-data";
import {
  GATE_RAIL,
  GateVerdictPanel,
  RECORD_VERDICT_RAIL,
  RECORD_VERDICT_TEXT,
  RecordVerdictLabel,
  StatusRailCard,
  StatusRailShell,
} from "@/components/status-rail";
import { cn } from "@/lib/utils";

type Props = {
  packages: WorkPackage[];
  selectedId: string;
  onSelect: (activityId: string) => void;
};

export function RecordPackageList({ packages, selectedId, onSelect }: Props) {
  return (
    <div className="flex min-h-0 flex-col">
      <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
        Work packages
      </h2>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {packages.length} packages in the hash chain
      </p>
      <ul className="mt-3 flex max-h-[min(480px,52dvh)] flex-col gap-1 overflow-y-auto">
        {packages.map((pkg) => (
          <li key={pkg.activity_id}>
            <button
              type="button"
              onClick={() => onSelect(pkg.activity_id)}
              className={cn(
                "relative w-full overflow-hidden rounded-lg border text-left transition-colors",
                selectedId === pkg.activity_id
                  ? "border-border bg-muted/20"
                  : "border-border/70 bg-card/25 hover:bg-muted/15",
              )}
            >
              <div
                aria-hidden
                className={cn(
                  "absolute inset-y-0 left-0 w-[3px]",
                  RECORD_VERDICT_RAIL[pkg.latest_verdict],
                )}
              />
              <div className="py-2.5 pr-3 pl-4">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[12px] font-medium leading-snug text-foreground/95">
                    {pkg.activity_name}
                  </span>
                  <RecordVerdictLabel verdict={pkg.latest_verdict} />
                </div>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {pkg.activity_id} · {pkg.work_face_name}
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {ACTION_LABEL[pkg.latest_action]}
                  {pkg.at_risk_usd > 0
                    ? ` · ${formatUsd(pkg.at_risk_usd)} at risk`
                    : null}
                </p>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TimelineEntry({ entry }: { entry: RecordEntry }) {
  const p = entry.payload;
  const showGatePanel =
    p.gate_decision != null && p.gate_rule_id != null && p.gate_reason != null;

  return (
    <li className="relative pl-6 pb-5 last:pb-0">
      <span
        aria-hidden
        className="absolute top-1.5 left-[7px] h-2 w-2 rounded-full bg-muted-foreground/70 ring-4 ring-background"
      />
      <span
        aria-hidden
        className="absolute top-4 left-[10px] h-[calc(100%-8px)] w-px bg-border/70 last:hidden"
      />

      <StatusRailCard
        railClass={RECORD_VERDICT_RAIL[p.verdict as RecordVerdict]}
        innerClassName="py-3"
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-[12px] font-semibold text-foreground/95">
            {ACTION_LABEL[p.action]}
            {p.gate_decision ? ` · gate ${p.gate_decision}` : null}
          </p>
          <time className="font-mono text-[10px] text-muted-foreground">
            {formatRecordWhen(p.ts)}
          </time>
        </div>

        <RecordVerdictLabel verdict={p.verdict as RecordVerdict} className="mt-2" />

        {p.proposal_summary ? (
          <p className="mt-2 text-[12px] leading-relaxed text-foreground/90">
            {p.proposal_summary}
          </p>
        ) : null}

        {showGatePanel && p.gate_decision && p.gate_rule_id && p.gate_reason ? (
          <GateVerdictPanel
            gate={{
              decision: p.gate_decision,
              rule_id: p.gate_rule_id,
              reason: p.gate_reason,
              escalated: p.action === "escalate",
              modified_params: null,
            }}
          />
        ) : p.gate_rule_id ? (
          <p className="mt-2 font-mono text-[11px] text-muted-foreground">
            rule_id: {p.gate_rule_id}
            {p.gate_reason ? ` — ${p.gate_reason}` : null}
          </p>
        ) : null}

        <blockquote className="mt-3 border-l-2 border-border/70 pl-3 text-[11px] leading-relaxed text-muted-foreground italic">
          {clauseExcerpt(p.clause_cited, 280)}
        </blockquote>

        <p className="mt-2 text-[10px] text-muted-foreground">
          {p.standard_ref}
          {p.compliant_hours != null ? ` · ${p.compliant_hours} h open` : null}
        </p>

        {p.usd_exposure ? (
          <p className="mt-2 text-[11px]">
            {p.usd_exposure.at_risk_usd > 0 ? (
              <span className={RECORD_VERDICT_TEXT.non_compliant}>
                {formatUsd(p.usd_exposure.at_risk_usd)} at risk
              </span>
            ) : (
              <span className={RECORD_VERDICT_TEXT.compliant}>
                {formatUsd(p.usd_exposure.protected_usd)} protected
              </span>
            )}
            <span className="text-muted-foreground">
              {" "}
              · {p.usd_exposure.basis}
            </span>
          </p>
        ) : null}

        {p.fg_activity_ids.length > 0 ? (
          <p className="mt-2 font-mono text-[10px] text-muted-foreground">
            fg: {p.fg_activity_ids.join(", ")}
          </p>
        ) : null}

        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          seq {entry.seq} · hash {truncateHash(entry.hash, 6)}
        </p>
      </StatusRailCard>
    </li>
  );
}

export function RecordPackageTimeline({ pkg }: { pkg: WorkPackage | null }) {
  if (!pkg) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Select a work package to view its record timeline.
      </p>
    );
  }

  const railClass =
    pkg.entries.some((e) => e.payload.action === "escalate")
      ? GATE_RAIL.deny
      : RECORD_VERDICT_RAIL[pkg.latest_verdict];

  return (
    <div className="min-h-0">
      <StatusRailShell railClass={railClass} innerClassName="py-4 mb-4">
        <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Timeline
        </h2>
        <h3 className="mt-1 text-base font-semibold">{pkg.activity_name}</h3>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          {pkg.activity_id} · {pkg.trade_display_name} · {pkg.work_face_name}
        </p>
      </StatusRailShell>

      <ol className="relative">
        {pkg.entries.map((entry) => (
          <TimelineEntry key={entry.seq} entry={entry} />
        ))}
      </ol>

      <p className="mt-4 border-t border-border/60 pt-3 text-[10px] leading-relaxed text-muted-foreground">
        {pkg.entries[0]?.payload.advisory_notice}
      </p>
    </div>
  );
}
