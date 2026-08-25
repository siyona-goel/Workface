import Link from "next/link";

import { StatusRailCard, NEUTRAL_RAIL } from "@/components/status-rail";
import {
  ITEM_KIND_LABEL,
  ITEM_STATUS_LABEL,
  PRIORITY_ORDER,
  formatBriefDate,
  formatBriefHoldUntil,
  formatBriefTime,
  morningBrief,
  type BriefItem,
  type BriefItemKind,
} from "@/lib/morning-brief";
import { cn } from "@/lib/utils";

const KIND_RAIL: Record<BriefItemKind, string> = {
  window: "bg-emerald-500",
  shift: "bg-sky-500",
  hold: "bg-amber-500",
  escalation: "bg-red-500",
  weather: NEUTRAL_RAIL,
};

const KIND_TEXT: Record<BriefItemKind, string> = {
  window: "text-emerald-400",
  shift: "text-sky-400",
  hold: "text-amber-400",
  escalation: "text-red-400",
  weather: "text-muted-foreground",
};

const STATUS_TEXT: Record<string, string> = {
  ready: "text-emerald-400",
  confirmed: "text-sky-400",
  hold: "text-amber-400",
  watch: "text-muted-foreground",
  escalated: "text-red-400",
};

function BriefItemCard({ item }: { item: BriefItem }) {
  const isEscalation = item.kind === "escalation";

  return (
    <StatusRailCard
      railClass={KIND_RAIL[item.kind]}
      innerClassName="py-3"
      className="rounded-lg"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p
            className={cn(
              "text-[10px] font-semibold tracking-[0.14em] uppercase",
              KIND_TEXT[item.kind],
            )}
          >
            {ITEM_KIND_LABEL[item.kind]}
          </p>
          <h3 className="mt-0.5 text-[15px] font-semibold leading-snug text-foreground/95">
            {item.title}
          </h3>
        </div>
        <span
          className={cn(
            "shrink-0 text-[10px] font-semibold tracking-[0.14em] uppercase",
            STATUS_TEXT[item.status] ?? "text-muted-foreground",
          )}
        >
          {ITEM_STATUS_LABEL[item.status] ?? item.status}
        </span>
      </div>

      <p
        className={cn(
          "mt-2 text-[13px] leading-relaxed",
          isEscalation
            ? "rounded-md border border-red-950/30 bg-red-950/12 px-2.5 py-2 text-foreground/90"
            : "text-foreground/90",
        )}
      >
        {item.body}
      </p>

      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
        {item.activity_id} · {item.location}
      </p>

      {item.window ? (
        <p className="mt-1.5 text-[12px] text-muted-foreground">
          Window{" "}
          <span className={KIND_TEXT.window}>
            {item.window.opens}–{item.window.closes}
          </span>
          {item.scheduled_start
            ? ` · scheduled ${item.scheduled_start}`
            : null}
        </p>
      ) : null}

      {item.new_start ? (
        <p className="mt-1.5 text-[12px] text-muted-foreground">
          {item.previous_start ? `${item.previous_start} → ` : null}
          <span className={KIND_TEXT.shift}>{item.new_start}</span>
        </p>
      ) : null}

      {item.hold_until ? (
        <p className="mt-1.5 text-[12px] text-muted-foreground">
          Earliest clear:{" "}
          <span className={KIND_TEXT.hold}>
            {formatBriefHoldUntil(item.hold_until)}
          </span>
        </p>
      ) : null}
    </StatusRailCard>
  );
}

export function BriefPhone() {
  const items = [...morningBrief.items].sort(
    (a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority],
  );

  return (
    <div className="relative mx-auto w-full max-w-[390px] px-1 py-2">
      {/* Side buttons */}
      <div
        aria-hidden
        className="absolute top-[92px] -left-0.5 z-10 h-7 w-[3px] rounded-r-sm bg-zinc-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]"
      />
      <div
        aria-hidden
        className="absolute top-[132px] -left-0.5 z-10 h-11 w-[3px] rounded-r-sm bg-zinc-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]"
      />
      <div
        aria-hidden
        className="absolute top-[188px] -left-0.5 z-10 h-11 w-[3px] rounded-r-sm bg-zinc-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]"
      />
      <div
        aria-hidden
        className="absolute top-[118px] -right-0.5 z-10 h-16 w-[3px] rounded-l-sm bg-zinc-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]"
      />

      {/* Phone chassis */}
      <div className="rounded-[2.75rem] border-2 border-zinc-600/90 bg-gradient-to-b from-zinc-600 via-zinc-800 to-zinc-900 p-[11px] shadow-[0_32px_64px_-16px_rgba(0,0,0,0.85),0_0_0_1px_rgba(255,255,255,0.06)_inset,0_1px_0_rgba(255,255,255,0.12)_inset]">
        {/* Screen bezel */}
        <div className="overflow-hidden rounded-[2.15rem] border border-black/80 bg-black shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]">
          {/* Status bar + dynamic island */}
          <div className="relative flex items-center justify-between bg-zinc-950 px-5 pt-3 pb-1">
            <span className="text-[11px] font-semibold tabular-nums text-foreground/90">
              {formatBriefTime(morningBrief.generated_at)}
            </span>
            <div
              aria-hidden
              className="absolute left-1/2 top-2.5 h-[26px] w-[92px] -translate-x-1/2 rounded-full bg-black ring-1 ring-zinc-700/80"
            />
            <div
              aria-hidden
              className="flex items-center gap-1 text-foreground/80"
            >
              <span className="h-[7px] w-[7px] rounded-full bg-foreground/70" />
              <span className="h-[7px] w-[7px] rounded-full bg-foreground/50" />
              <span className="ml-0.5 h-2.5 w-5 rounded-[2px] border border-foreground/50 px-[1px]">
                <span className="block h-full w-3/4 rounded-[1px] bg-emerald-400/90" />
              </span>
            </div>
          </div>

          <header className="border-b border-border/60 bg-zinc-950 px-4 pb-3 pt-0.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] font-semibold tracking-[0.2em]">
                WORKFACE
              </span>
              <span className="rounded-sm border border-border/70 bg-card/30 px-2 py-0.5 text-[9px] font-semibold tracking-[0.12em] text-violet-400 uppercase">
                Brief
              </span>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Morning brief · {formatBriefDate(morningBrief.for_date)}
            </p>
            <h1 className="mt-1 text-lg font-semibold leading-snug">
              {morningBrief.headline}
            </h1>
            <p className="mt-1.5 text-[12px] text-muted-foreground">
              {morningBrief.weather_line}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              For {morningBrief.recipient.name} · {morningBrief.recipient.role}
            </p>
          </header>

          <div className="max-h-[min(580px,62dvh)] space-y-2.5 overflow-y-auto bg-zinc-950 px-3 py-3">
            {items.map((item) => (
              <BriefItemCard key={item.id} item={item} />
            ))}

            <StatusRailCard
              railClass={NEUTRAL_RAIL}
              innerClassName="py-3"
              className="rounded-lg"
            >
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {morningBrief.stats.activities_today} activities today ·{" "}
                {morningBrief.notification_queue.filter((n) => n.status === "queued").length}{" "}
                crew notifications queued
              </p>
              <Link
                href="/trace"
                className="mt-2 inline-block text-[11px] text-foreground/80 underline"
              >
                Open agent trace
              </Link>
            </StatusRailCard>
          </div>

          {/* Home indicator */}
          <div className="flex justify-center bg-zinc-950 py-3">
            <div className="h-1 w-[108px] rounded-full bg-foreground/35" />
          </div>
        </div>
      </div>
    </div>
  );
}
