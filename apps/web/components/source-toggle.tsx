"use client";

import { ModeBadge, channelHint } from "@/components/mode-badge";
import { useSetAgentSource, type ChannelState } from "@/lib/use-agent-events";
import { type AgentSource } from "@/lib/trace-data";
import { cn } from "@/lib/utils";

const CHANNEL_LABEL: Record<ChannelState, string> = {
  off: "channel off",
  connecting: "connecting",
  subscribed: "subscribed",
  error: "channel error",
};

type Props = {
  source: AgentSource;
  channelState: ChannelState;
};

export function SourceToggle({ source, channelState }: Props) {
  const setSource = useSetAgentSource();

  return (
    <div className="flex flex-wrap items-center gap-2">
      <ModeBadge source={source} channelState={channelState} />
      <div className="flex items-center gap-0.5 rounded-md border border-border/70 p-0.5">
        {(
          [
            ["fixture", "Fixtures"],
            ["live", "Live run"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSource(id)}
            className={cn(
              "rounded-sm px-2 py-0.5 text-[11px] font-medium tracking-wide",
              source === id
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <span className={channelHint(channelState)}>
        {CHANNEL_LABEL[channelState]}
      </span>
    </div>
  );
}
