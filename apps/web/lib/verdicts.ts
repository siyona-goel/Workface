import type { Verdict } from "@/lib/console-data";

export const VERDICT_DOT: Record<Verdict, string> = {
  compliant: "bg-emerald-300",
  at_risk: "bg-amber-300",
  non_compliant: "bg-red-300",
  insufficient_window: "bg-orange-300",
  no_data: "bg-zinc-400",
};

export const VERDICT_CHIP: Record<Verdict, string> = {
  compliant:
    "border-emerald-300/55 bg-emerald-300/25 text-emerald-200 data-[on=true]:border-emerald-300/80 data-[on=true]:bg-emerald-300/40",
  at_risk:
    "border-amber-300/55 bg-amber-300/25 text-amber-200 data-[on=true]:border-amber-300/80 data-[on=true]:bg-amber-300/40",
  non_compliant:
    "border-red-300/55 bg-red-300/25 text-red-200 data-[on=true]:border-red-300/80 data-[on=true]:bg-red-300/40",
  insufficient_window:
    "border-orange-300/55 bg-orange-300/25 text-orange-200 data-[on=true]:border-orange-300/80 data-[on=true]:bg-orange-300/40",
  no_data:
    "border-zinc-400/50 bg-zinc-300/20 text-zinc-200 data-[on=true]:border-zinc-300/70 data-[on=true]:bg-zinc-300/35",
};

export const VERDICT_ROW: Record<Verdict, string> = {
  compliant: "text-emerald-300",
  at_risk: "text-amber-300",
  non_compliant: "text-red-300",
  insufficient_window: "text-orange-300",
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
