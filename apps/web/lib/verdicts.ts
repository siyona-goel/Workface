import type { Verdict } from "@/lib/console-data";

/**
 * One colour family for every surface that names a verdict: these chips, the
 * ribbon bands (`HOUR_STATE_FILL` in `lib/ribbon-data.ts`) and the deck.gl
 * work-face fills below. Fills use the -500 shades so they survive a 1 h cell
 * width and video compression; row *text* stays on -400, which is legible on
 * the dark background where -500 is not.
 */
export const VERDICT_DOT: Record<Verdict, string> = {
  compliant: "bg-emerald-300",
  at_risk: "bg-amber-500",
  non_compliant: "bg-red-500",
  insufficient_window: "bg-orange-500",
  no_data: "bg-zinc-400",
};

export const VERDICT_CHIP: Record<Verdict, string> = {
  compliant:
    "border-emerald-300/55 bg-emerald-300/25 text-emerald-200 data-[on=true]:border-emerald-300/80 data-[on=true]:bg-emerald-300/40",
  at_risk:
    "border-amber-500/55 bg-amber-500/25 text-amber-100 data-[on=true]:border-amber-500/80 data-[on=true]:bg-amber-500/40",
  non_compliant:
    "border-red-500/55 bg-red-500/25 text-red-100 data-[on=true]:border-red-500/80 data-[on=true]:bg-red-500/40",
  insufficient_window:
    "border-orange-500/55 bg-orange-500/25 text-orange-100 data-[on=true]:border-orange-500/80 data-[on=true]:bg-orange-500/40",
  no_data:
    "border-zinc-400/50 bg-zinc-300/20 text-zinc-200 data-[on=true]:border-zinc-300/70 data-[on=true]:bg-zinc-300/35",
};

export const VERDICT_ROW: Record<Verdict, string> = {
  compliant: "text-emerald-300",
  at_risk: "text-amber-400",
  non_compliant: "text-red-400",
  insufficient_window: "text-orange-400",
  no_data: "text-zinc-400",
};

/** deck.gl RGBA for work-face fill by worst verdict on that face. */
export const VERDICT_FILL: Record<Verdict, [number, number, number, number]> = {
  compliant: [16, 185, 129, 150],
  at_risk: [245, 158, 11, 160],
  non_compliant: [239, 68, 68, 170],
  insufficient_window: [249, 115, 22, 160],
  no_data: [113, 113, 122, 70],
};
