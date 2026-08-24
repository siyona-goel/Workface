import { Suspense } from "react";

import { MorningBriefView } from "@/components/morning-brief-view";

export const metadata = {
  title: "WORKFACE — Morning Brief",
  description:
    "Foreman phone view and gated crew notification templates for today's shift.",
};

export default function BriefPage() {
  return (
    <Suspense>
      <MorningBriefView />
    </Suspense>
  );
}
