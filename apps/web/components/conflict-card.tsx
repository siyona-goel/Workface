import {
  conflictHeadline,
  conflictOutcome,
  formatCompeting,
  formatShiftDate,
  type AgentRun,
  type Conflict,
  type ConflictOutcome,
} from "@/lib/trace-data";
import {
  CONFLICT_RAIL,
  ConflictStatusLabel,
  StatusRailButton,
  StatusRailShell,
} from "@/components/status-rail";
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

  const inner = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] text-muted-foreground">
          {conflict.id} · {formatShiftDate(conflict.shift_date)}
        </span>
        <ConflictStatusLabel outcome={outcome} label={OUTCOME_LABEL[outcome]} />
      </div>
      <p className="mt-1 text-[12px] font-medium leading-snug text-foreground/95">
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

  const shellClass = cn(
    pressed && "ring-1 ring-foreground/15 bg-muted/20",
    onToggle && "cursor-pointer hover:bg-muted/15",
  );

  if (!onToggle) {
    return (
      <StatusRailShell railClass={CONFLICT_RAIL[outcome]} innerClassName="py-2.5">
        {inner}
      </StatusRailShell>
    );
  }

  return (
    <StatusRailButton
      onClick={onToggle}
      aria-pressed={pressed}
      railClass={CONFLICT_RAIL[outcome]}
      innerClassName="py-2.5"
      className={shellClass}
    >
      {inner}
    </StatusRailButton>
  );
}
