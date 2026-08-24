"use client";

import {
  ACTION_LABEL,
  VERDICT_TONE,
  clauseExcerpt,
  formatRecordWhen,
  truncateHash,
  type RecordEntry,
  type WorkPackage,
} from "@/lib/record-data";
import { formatUsd } from "@/lib/console-data";
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
                "w-full rounded-lg border px-3 py-2.5 text-left transition-colors",
                selectedId === pkg.activity_id
                  ? "border-border bg-muted/50"
                  : "border-transparent hover:border-border/60 hover:bg-muted/20",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-[12px] font-medium leading-snug">
                  {pkg.activity_name}
                </span>
                <span
                  className={cn(
                    "shrink-0 rounded-sm border px-1.5 py-0.5 text-[9px] font-medium tracking-wide uppercase",
                    VERDICT_TONE[pkg.latest_verdict],
                  )}
                >
                  {pkg.latest_verdict.replace("_", " ")}
                </span>
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
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TimelineEntry({ entry }: { entry: RecordEntry }) {
  const p = entry.payload;
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

      <div className="rounded-xl border border-border/70 bg-card/30 px-3 py-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="text-[12px] font-semibold">
            {ACTION_LABEL[p.action]}
            {p.gate_decision ? ` · gate ${p.gate_decision}` : null}
          </p>
          <time className="font-mono text-[10px] text-muted-foreground">
            {formatRecordWhen(p.ts)}
          </time>
        </div>

        <p
          className={cn(
            "mt-2 inline-flex rounded-sm border px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase",
            VERDICT_TONE[p.verdict],
          )}
        >
          {p.verdict.replace("_", " ")}
        </p>

        {p.proposal_summary ? (
          <p className="mt-2 text-[12px] leading-relaxed">{p.proposal_summary}</p>
        ) : null}

        {p.gate_rule_id ? (
          <p className="mt-2 font-mono text-[11px] text-red-200">
            rule_id: {p.gate_rule_id}
            {p.gate_reason ? ` — ${p.gate_reason}` : null}
          </p>
        ) : null}

        <blockquote className="mt-3 border-l-2 border-border/80 pl-3 text-[11px] leading-relaxed text-muted-foreground italic">
          {clauseExcerpt(p.clause_cited, 280)}
        </blockquote>

        <p className="mt-2 text-[10px] text-muted-foreground">
          {p.standard_ref}
          {p.compliant_hours != null ? ` · ${p.compliant_hours} h open` : null}
        </p>

        {p.usd_exposure ? (
          <p className="mt-2 text-[11px]">
            {p.usd_exposure.at_risk_usd > 0 ? (
              <span className="text-red-200">
                {formatUsd(p.usd_exposure.at_risk_usd)} at risk
              </span>
            ) : (
              <span className="text-emerald-200">
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
      </div>
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

  return (
    <div className="min-h-0">
      <div className="mb-4">
        <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Timeline
        </h2>
        <h3 className="mt-1 text-base font-semibold">{pkg.activity_name}</h3>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
          {pkg.activity_id} · {pkg.trade_display_name} · {pkg.work_face_name}
        </p>
      </div>

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
