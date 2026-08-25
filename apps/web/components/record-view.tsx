"use client";

import { useEffect, useMemo, useState } from "react";

import { AppNav } from "@/components/app-nav";
import { HeatIntelligenceEmbed } from "@/components/heat-intelligence-embed";
import { RecordCounters } from "@/components/record-counters";
import {
  RecordPackageList,
  RecordPackageTimeline,
} from "@/components/record-package-panel";
import {
  formatRecordWhen,
  isHeroPackage,
  recordChain,
  verifyRecordChain,
  workPackagesFromChain,
} from "@/lib/record-data";

export function RecordView() {
  const packages = useMemo(() => workPackagesFromChain(), []);
  const [selectedId, setSelectedId] = useState(
    () =>
      packages.find((p) => p.activity_id === "A-1205")?.activity_id ??
      packages[0]?.activity_id ??
      "",
  );
  const [chainVerified, setChainVerified] = useState<boolean | null>(null);

  const selected = packages.find((p) => p.activity_id === selectedId) ?? null;

  useEffect(() => {
    let cancelled = false;
    async function verify() {
      const ok = await verifyRecordChain();
      if (!cancelled) setChainVerified(ok);
    }
    void verify();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            The Record
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-sm border border-border/70 bg-card/30 px-1.5 py-0.5 font-medium tracking-wider uppercase">
            <span className="text-cyan-400">Tier 2</span>
          </span>
          <span className="hidden md:inline">
            {recordChain.site_id} · generated{" "}
            {formatRecordWhen(recordChain.generated_at)}
          </span>
        </div>
        <div className="ml-auto">
          <AppNav current="record" />
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-3 py-5 sm:px-4">
        <div>
          <h1 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            As-built thermal record
          </h1>
          <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
            Append-only hash chain per work package. When the warranty adjuster
            comes back in year three, this is what the contractor hands them.
          </p>
        </div>

        <RecordCounters chainVerified={chainVerified} />

        <div className="grid gap-6 lg:grid-cols-[minmax(240px,280px)_minmax(0,1fr)] lg:items-start">
          <aside className="rounded-xl border border-border/70 bg-background/40 p-3 sm:p-4 lg:sticky lg:top-4 lg:self-start">
            <RecordPackageList
              packages={packages}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </aside>

          <div className="flex min-w-0 flex-col gap-6">
            <section className="rounded-xl border border-border/70 bg-background/40 p-4 sm:p-5">
              <RecordPackageTimeline pkg={selected} />
              {selected && isHeroPackage(selected.activity_id) ? (
                <p className="mt-4 text-[11px] text-muted-foreground">
                  Hero work face — heat intelligence PDF below.
                </p>
              ) : null}
            </section>

            <HeatIntelligenceEmbed />
          </div>
        </div>
      </div>
    </div>
  );
}
