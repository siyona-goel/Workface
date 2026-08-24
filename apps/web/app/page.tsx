import { Suspense } from "react";

import { SiteConsole } from "@/components/site-console";

export default function Home() {
  return (
    <Suspense>
      <SiteConsole />
    </Suspense>
  );
}
