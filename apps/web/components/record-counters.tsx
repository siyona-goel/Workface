import { formatUsd } from "@/lib/console-data";
import { exposureTotals, recordChain, truncateHash } from "@/lib/record-data";
import { GATE_TEXT, RECORD_VERDICT_TEXT } from "@/components/status-rail";
import { cn } from "@/lib/utils";

type Props = {
  chainVerified?: boolean | null;
};

function CounterCard({
  label,
  value,
  detail,
  valueClassName,
}: {
  label: string;
  value: string;
  detail: string;
  valueClassName?: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-border/70 bg-card/25 px-4 py-3">
      <div
        aria-hidden
        className={cn(
          "absolute inset-y-0 left-0 w-[3px]",
          valueClassName?.includes("red")
            ? "bg-red-500"
            : valueClassName?.includes("emerald")
              ? "bg-emerald-500"
              : "bg-muted-foreground/35",
        )}
      />
      <p className="pl-1 text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 pl-1 text-2xl font-semibold tabular-nums",
          valueClassName,
        )}
      >
        {value}
      </p>
      <p className="mt-1 pl-1 text-[11px] text-muted-foreground">{detail}</p>
    </div>
  );
}

export function RecordCounters({ chainVerified }: Props) {
  const totals = exposureTotals();

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <CounterCard
        label="$ at risk"
        value={formatUsd(totals.at_risk_usd)}
        detail={`Demo-window lanes · ${formatUsd(totals.chain_at_risk_usd)} in this chain`}
        valueClassName="text-red-400"
      />

      <CounterCard
        label="$ protected"
        value={formatUsd(totals.protected_usd)}
        detail={totals.basis}
        valueClassName="text-emerald-400"
      />

      <CounterCard
        label="Record chain"
        value={String(totals.entry_count)}
        detail={`head ${truncateHash(recordChain.head_hash ?? "—", 6)}`}
      />

      <div className="relative overflow-hidden rounded-lg border border-border/70 bg-card/25 px-4 py-3">
        <div
          aria-hidden
          className={cn(
            "absolute inset-y-0 left-0 w-[3px]",
            chainVerified === true
              ? "bg-emerald-500"
              : chainVerified === false
                ? "bg-red-500"
                : "bg-muted-foreground/35",
          )}
        />
        <p className="pl-1 text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Integrity
        </p>
        <p
          className={cn(
            "mt-1 pl-1 text-sm font-semibold tracking-[0.08em] uppercase",
            chainVerified === true
              ? RECORD_VERDICT_TEXT.compliant
              : chainVerified === false
                ? GATE_TEXT.deny
                : "text-muted-foreground",
          )}
        >
          {chainVerified === true
            ? "Chain verified"
            : chainVerified === false
              ? "Chain broken"
              : "Verifying…"}
        </p>
        <p className="mt-1 pl-1 text-[11px] text-muted-foreground">
          sha256 over canonical payload + prev_hash
        </p>
      </div>
    </div>
  );
}
