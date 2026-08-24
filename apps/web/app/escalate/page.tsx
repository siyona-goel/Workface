import { Suspense } from "react";

import { EscalationView } from "@/components/escalation-view";

export const metadata = {
  title: "WORKFACE — Escalation",
  description: "Policy gate verdict and rule id.",
};

export default function EscalatePage() {
  return (
    <Suspense>
      <EscalationView />
    </Suspense>
  );
}
