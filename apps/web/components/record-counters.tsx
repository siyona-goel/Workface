import { formatUsd } from "@/lib/console-data";
import { exposureTotals, recordChain, truncateHash } from "@/lib/record-data";
import { cn } from "@/lib/utils";

type Props = {
  chainVerified?: boolean | null;
};

export function RecordCounters({ chainVerified }: Props) {
  const totals = exposureTotals();

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <div className="rounded-xl border border-red-400/35 bg-red-400/8 px-4 py-3">
        <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          $ at risk
        </p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-red-100">
          {formatUsd(totals.at_risk_usd)}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          Demo-window lanes · {formatUsd(totals.chain_at_risk_usd)} in this
          chain
        </p>
      </div>

      <div className="rounded-xl border border-emerald-400/35 bg-emerald-400/8 px-4 py-3">
        <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          $ protected
        </p>
        <p className="mt-1 text-2xl font-semibold tabular-nums text-emerald-100">
          {formatUsd(totals.protected_usd)}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">{totals.basis}</p>
      </div>

      <div className="rounded-xl border border-border/70 bg-card/30 px-4 py-3">
        <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Record chain
        </p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">
          {totals.entry_count}
        </p>
        <p className="mt-1 font-mono text-[10px] text-muted-foreground">
          head {truncateHash(recordChain.head_hash ?? "—", 6)}
        </p>
      </div>

      <div className="rounded-xl border border-border/70 bg-card/30 px-4 py-3">
        <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
          Integrity
        </p>
        <p
          className={cn(
            "mt-1 text-sm font-semibold",
            chainVerified === true
              ? "text-emerald-200"
              : chainVerified === false
                ? "text-red-300"
                : "text-muted-foreground",
          )}
        >
          {chainVerified === true
            ? "Chain verified"
            : chainVerified === false
              ? "Chain broken"
              : "Verifying…"}
        </p>
        <p className="mt-1 text-[11px] text-muted-foreground">
          sha256 over canonical payload + prev_hash
        </p>
      </div>
    </div>
  );
}
