"use client";

import { useSearchParams } from "next/navigation";

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
  const params = useSearchParams();
  // Reveal Realtime / subscribed in the header with ?debug=1
  const debug = params.get("debug") === "1";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        data-testid="channel-state"
        data-channel-state={channelState}
        className="hidden"
      >
        Channel {channelState}
      </span>
      {debug ? (
        <>
          <ModeBadge source={source} channelState={channelState} />
          <span className={channelHint(channelState)}>
            {CHANNEL_LABEL[channelState]}
          </span>
        </>
      ) : null}
      <div
        className="flex items-center gap-2"
        role="group"
        aria-label="Trace data source"
      >
        <span className="hidden text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase sm:inline">
          Source
        </span>
        <div className="flex items-center rounded-md bg-muted/55 p-0.5">
          {(
            [
              ["fixture", "Fixtures", "Day-5 product fixtures"],
              ["live", "Live run", "T3 gated loop replay"],
            ] as const
          ).map(([id, label, title]) => (
            <button
              key={id}
              type="button"
              title={title}
              aria-pressed={source === id}
              onClick={() => setSource(id)}
              className={cn(
                "rounded-sm px-2 py-0.5 text-[11px] font-medium tracking-wide",
                source === id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <span aria-hidden className="hidden h-4 w-px shrink-0 bg-border sm:block" />
    </div>
  );
}
