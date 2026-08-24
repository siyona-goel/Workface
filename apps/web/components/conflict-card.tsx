import {
  conflictHeadline,
  conflictOutcome,
  formatCompeting,
  formatShiftDate,
  type AgentRun,
  type Conflict,
  type ConflictOutcome,
} from "@/lib/trace-data";
import { cn } from "@/lib/utils";

export const OUTCOME_LABEL: Record<ConflictOutcome, string> = {
  resolved: "Resolved",
  escalated: "Escalated",
  open: "Open",
};

type Props = {
  conflict: Conflict;
  run: AgentRun;
  pressed?: boolean;
  onToggle?: () => void;
};

export function ConflictCard({ conflict, run, pressed, onToggle }: Props) {
  const outcome = conflictOutcome(conflict, run);

  const className = cn(
    "w-full rounded-xl border px-3 py-2.5 text-left transition-colors",
    outcome === "escalated"
      ? "border-red-300/45 bg-red-300/8"
      : outcome === "open"
        ? "border-amber-300/45 bg-amber-300/8"
        : "border-emerald-300/35 bg-emerald-300/8",
    pressed && "ring-1 ring-foreground/20",
    onToggle && "cursor-pointer",
  );

  const inner = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] text-muted-foreground">
          {conflict.id} · {formatShiftDate(conflict.shift_date)}
        </span>
        <span
          className={cn(
            "text-[10px] font-medium tracking-wide uppercase",
            outcome === "escalated"
              ? "text-red-200"
              : outcome === "open"
                ? "text-amber-200"
                : "text-emerald-200",
          )}
        >
          {OUTCOME_LABEL[outcome]}
        </span>
      </div>
      <p className="mt-1 text-[12px] font-medium leading-snug">
        {formatCompeting(conflict.competing_activity_ids)}
      </p>
      <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
        {conflict.demanded_hours} h demanded · {conflict.compliant_hours} h open
      </p>
      <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
        {conflictHeadline(conflict)}
      </p>
    </>
  );

  if (!onToggle) {
    return <div className={className}>{inner}</div>;
  }

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={pressed}
      className={className}
    >
      {inner}
    </button>
  );
}
