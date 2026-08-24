import type { AgentSource } from "@/lib/trace-data";
import type { ChannelState } from "@/lib/use-agent-events";
import { cn } from "@/lib/utils";

type Props = {
  source?: AgentSource;
  channelState?: ChannelState;
};

export function ModeBadge({ source = "fixture", channelState = "off" }: Props) {
  if (channelState === "subscribed") {
    return (
      <span className="rounded-sm border border-sky-400/40 bg-sky-400/10 px-1.5 py-0.5 font-medium tracking-wider text-sky-200 uppercase">
        Realtime
      </span>
    );
  }
  if (source === "live") {
    return (
      <span className="rounded-sm border border-cyan-400/40 bg-cyan-400/10 px-1.5 py-0.5 font-medium tracking-wider text-cyan-200 uppercase">
        Live file
      </span>
    );
  }
  return (
    <span className="rounded-sm border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-medium tracking-wider text-emerald-200 uppercase">
      Replay
    </span>
  );
}

export function channelHint(state: ChannelState) {
  return cn(
    "rounded-sm border px-1.5 py-0.5 text-[10px] font-medium tracking-wider uppercase",
    state === "subscribed"
      ? "border-sky-400/40 bg-sky-400/10 text-sky-200"
      : state === "error"
        ? "border-red-400/40 bg-red-400/10 text-red-200"
        : "border-border/70 text-muted-foreground",
  );
}
