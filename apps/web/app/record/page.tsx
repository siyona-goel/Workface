import { Suspense } from "react";

import { RecordView } from "@/components/record-view";

export const metadata = {
  title: "WORKFACE — The Record",
  description:
    "Per-work-package hash-chained thermal record, exposure counters, and heat intelligence certificate.",
};

export default function RecordPage() {
  return (
    <Suspense>
      <RecordView />
    </Suspense>
  );
}
