import type { ComponentPropsWithoutRef, ReactNode } from "react";

import type { RecordVerdict } from "@/lib/record-data";
import {
  GATE_DECISION_LABEL,
  type ConflictOutcome,
  type GateDecision,
  type GateVerdict,
} from "@/lib/trace-data";
import { cn } from "@/lib/utils";

export const GATE_RAIL: Record<GateDecision, string> = {
  approve: "bg-emerald-500",
  modify: "bg-amber-500",
  deny: "bg-red-500",
};

export const GATE_TEXT: Record<GateDecision, string> = {
  approve: "text-emerald-400",
  modify: "text-amber-400",
  deny: "text-red-400",
};

export const CONFLICT_RAIL: Record<ConflictOutcome, string> = {
  resolved: "bg-emerald-500",
  escalated: "bg-red-500",
  open: "bg-amber-500",
};

export const CONFLICT_TEXT: Record<ConflictOutcome, string> = {
  resolved: "text-emerald-400",
  escalated: "text-red-400",
  open: "text-amber-400",
};

export const RECORD_VERDICT_RAIL: Record<RecordVerdict, string> = {
  compliant: "bg-emerald-500",
  at_risk: "bg-amber-500",
  non_compliant: "bg-red-500",
  insufficient_window: "bg-orange-500",
  no_data: "bg-muted-foreground/35",
};

export const RECORD_VERDICT_TEXT: Record<RecordVerdict, string> = {
  compliant: "text-emerald-400",
  at_risk: "text-amber-400",
  non_compliant: "text-red-400",
  insufficient_window: "text-orange-400",
  no_data: "text-muted-foreground",
};

export const NEUTRAL_RAIL = "bg-muted-foreground/35";

type RailCardProps = {
  railClass: string;
  children: ReactNode;
  className?: string;
  innerClassName?: string;
};

export function StatusRailCard({
  railClass,
  children,
  className,
  innerClassName,
}: RailCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border/70 bg-card/25",
        className,
      )}
    >
      <div
        aria-hidden
        className={cn("absolute inset-y-0 left-0 w-[3px]", railClass)}
      />
      <div className={cn("py-3 pr-3 pl-4", innerClassName)}>{children}</div>
    </div>
  );
}

type StatusRailShellProps = RailCardProps & ComponentPropsWithoutRef<"div">;

export function StatusRailShell({
  railClass,
  children,
  className,
  innerClassName,
  ...props
}: StatusRailShellProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-lg border border-border/70 bg-card/25 text-left",
        className,
      )}
      {...props}
    >
      <div
        aria-hidden
        className={cn("absolute inset-y-0 left-0 w-[3px]", railClass)}
      />
      <div className={cn("py-3 pr-3 pl-4", innerClassName)}>{children}</div>
    </div>
  );
}

type StatusRailButtonProps = RailCardProps &
  ComponentPropsWithoutRef<"button">;

export function StatusRailButton({
  railClass,
  children,
  className,
  innerClassName,
  type = "button",
  ...props
}: StatusRailButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "relative w-full overflow-hidden rounded-lg border border-border/70 bg-card/25 text-left",
        className,
      )}
      {...props}
    >
      <div
        aria-hidden
        className={cn("absolute inset-y-0 left-0 w-[3px]", railClass)}
      />
      <div className={cn("py-3 pr-3 pl-4", innerClassName)}>{children}</div>
    </button>
  );
}

export function GateStatusLabel({
  decision,
  className,
}: {
  decision: GateDecision;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "text-[10px] font-semibold tracking-[0.14em] uppercase",
        GATE_TEXT[decision],
        className,
      )}
    >
      {GATE_DECISION_LABEL[decision]}
    </span>
  );
}

export function ConflictStatusLabel({
  outcome,
  label,
  className,
}: {
  outcome: ConflictOutcome;
  label: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "text-[10px] font-semibold tracking-[0.14em] uppercase",
        CONFLICT_TEXT[outcome],
        className,
      )}
    >
      {label}
    </span>
  );
}

export function RecordVerdictLabel({
  verdict,
  className,
}: {
  verdict: RecordVerdict;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "text-[10px] font-semibold tracking-[0.14em] uppercase",
        RECORD_VERDICT_TEXT[verdict],
        className,
      )}
    >
      {verdict.replace("_", " ")}
    </span>
  );
}

export function GateVerdictPanel({ gate }: { gate: GateVerdict }) {
  const tinted = gate.decision === "deny" || gate.escalated;
  return (
    <div
      className={cn(
        "mt-3 rounded-md border px-3 py-3",
        tinted
          ? "border-red-950/30 bg-red-950/12"
          : "border-border/60 bg-background/30",
      )}
    >
      <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
        Gate verdict
      </p>
      <div className="mt-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <GateStatusLabel decision={gate.decision} />
        <span className="font-mono text-[11px] text-muted-foreground">
          rule_id: {gate.rule_id}
        </span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-foreground/90">
        {gate.reason}
      </p>
    </div>
  );
}
