import { Suspense } from "react";

import { ConflictView } from "@/components/conflict-view";

export const metadata = {
  title: "WORKFACE — Conflicts",
  description: "Work-face and shift contention queue.",
};

export default function ConflictsPage() {
  return (
    <Suspense>
      <ConflictView />
    </Suspense>
  );
}
