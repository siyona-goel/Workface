"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { AGENT_CHANNEL, tryGetSupabase } from "@/lib/supabase";
import {
  runForSource,
  streamDelayMs,
  type AgentRun,
  type AgentSource,
  type AgentStep,
} from "@/lib/trace-data";

export type ChannelState = "off" | "connecting" | "subscribed" | "error";

export function useAgentSource(): AgentSource {
  const params = useSearchParams();
  const q = params.get("src");
  if (q === "live" || q === "fixture") return q;
  if (process.env.NEXT_PUBLIC_AGENT_SOURCE === "live") return "live";
  return "fixture";
}

export function useSetAgentSource() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  return function setSource(source: AgentSource) {
    const next = new URLSearchParams(params.toString());
    next.set("src", source);
    router.replace(`${pathname}?${next.toString()}`);
  };
}

function stepFromRow(row: Record<string, unknown>): AgentStep | null {
  const output = row.output;
  if (output && typeof output === "object" && "type" in output && "seq" in output) {
    return output as AgentStep;
  }
  const seq = typeof row.seq === "number" ? row.seq : null;
  const kind = typeof row.kind === "string" ? row.kind : null;
  if (seq == null || !kind) return null;
  return {
    seq,
    type: kind as AgentStep["type"],
    at: typeof row.created_at === "string" ? row.created_at : new Date().toISOString(),
    title: kind,
    detail: null,
    activity_ids: [],
    conflict_id: null,
    tool_calls: [],
    proposal: null,
    gate: null,
    record_seq: null,
  };
}

function upsertStep(steps: AgentStep[], incoming: AgentStep) {
  const i = steps.findIndex((s) => s.seq === incoming.seq);
  if (i === -1) return [...steps, incoming].sort((a, b) => a.seq - b.seq);
  const next = [...steps];
  next[i] = incoming;
  return next;
}

export function useAgentChannel() {
  const [channelState, setChannelState] = useState<ChannelState>("off");
  const [channelSteps, setChannelSteps] = useState<AgentStep[]>([]);

  useEffect(() => {
    const sb = tryGetSupabase();
    if (!sb) {
      setChannelState("off");
      return;
    }
    setChannelState("connecting");
    const channel = sb
      .channel(AGENT_CHANNEL)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "agent_step" },
        (payload) => {
          const step = stepFromRow(payload.new as Record<string, unknown>);
          if (step) setChannelSteps((cur) => upsertStep(cur, step));
        },
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED") setChannelState("subscribed");
        else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
          setChannelState("error");
        } else setChannelState("connecting");
      });

    return () => {
      void sb.removeChannel(channel);
    };
  }, []);

  return { channelState, channelSteps };
}

export function useAgentEvents() {
  const source = useAgentSource();
  const setSource = useSetAgentSource();
  const run: AgentRun = runForSource(source);
  const { channelState, channelSteps } = useAgentChannel();

  const [visibleCount, setVisibleCount] = useState(0);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    setVisibleCount(0);
    setGeneration((g) => g + 1);
  }, [source, run.run_id]);

  useEffect(() => {
    if (visibleCount >= run.steps.length) return;
    const prev = run.steps[visibleCount - 1];
    const next = run.steps[visibleCount];
    const id = window.setTimeout(() => {
      setVisibleCount((n) => n + 1);
    }, streamDelayMs(prev, next));
    return () => window.clearTimeout(id);
  }, [generation, run.steps, visibleCount]);

  const fileSteps = run.steps.slice(0, visibleCount);
  const steps = useMemo(() => {
    let merged = fileSteps;
    for (const step of channelSteps) merged = upsertStep(merged, step);
    return merged;
  }, [channelSteps, fileSteps]);

  const streaming = visibleCount < run.steps.length && channelSteps.length === 0;

  function replay() {
    setVisibleCount(0);
    setGeneration((g) => g + 1);
  }

  function showAll() {
    setVisibleCount(run.steps.length);
  }

  return {
    source,
    setSource,
    run,
    steps,
    visibleCount,
    streaming,
    channelState,
    channelStepCount: channelSteps.length,
    replay,
    showAll,
  };
}
