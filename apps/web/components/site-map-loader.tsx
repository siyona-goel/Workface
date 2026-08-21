"use client";

import dynamic from "next/dynamic";

const SiteMap = dynamic(() => import("@/components/site-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      Loading map…
    </div>
  ),
});

export function SiteMapLoader() {
  return <SiteMap />;
}
