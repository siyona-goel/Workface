import { Suspense } from "react";

import { AgentTrace } from "@/components/agent-trace";

export const metadata = {
  title: "WORKFACE — Agent Trace",
  description:
    "Replayable agent decision log. Built against T3 Day-5 fixtures.",
};

export default function TracePage() {
  return (
    <Suspense>
      <AgentTrace />
    </Suspense>
  );
}
