"use client";

import { AppNav } from "@/components/app-nav";
import { BriefPhone } from "@/components/brief-phone";
import { NotificationTemplatesPanel } from "@/components/notification-templates-panel";
import { briefProvenance, briefStatsLine, morningBrief } from "@/lib/morning-brief";
import { formatUsd } from "@/lib/console-data";

export function MorningBriefView() {
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            Morning brief
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-sm border border-violet-400/35 bg-violet-400/10 px-1.5 py-0.5 font-medium tracking-wider text-violet-200 uppercase">
            Phone
          </span>
          <span className="hidden md:inline">{briefStatsLine()}</span>
        </div>
        <div className="ml-auto">
          <AppNav current="brief" />
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-3 py-5 sm:px-4 lg:grid lg:grid-cols-[minmax(280px,390px)_minmax(0,1fr)] lg:items-start lg:gap-10">
        <div className="flex flex-col gap-4">
          <div>
            <h1 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Foreman view
            </h1>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {morningBrief.project_name}
            </p>
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              {briefProvenance()}
            </p>
          </div>
          <div className="relative rounded-2xl border border-border/40 bg-gradient-to-b from-muted/25 to-muted/5 px-2 py-4 sm:px-4">
            <BriefPhone />
          </div>
          <dl className="grid grid-cols-2 gap-2 text-[11px] md:hidden">
            <div className="rounded-lg border border-border/70 px-2.5 py-2">
              <dt className="text-muted-foreground">At risk</dt>
              <dd className="font-semibold">
                {formatUsd(morningBrief.stats.at_risk_usd)}
              </dd>
            </div>
            <div className="rounded-lg border border-border/70 px-2.5 py-2">
              <dt className="text-muted-foreground">Protected</dt>
              <dd className="font-semibold">
                {formatUsd(morningBrief.stats.protected_usd)}
              </dd>
            </div>
          </dl>
        </div>

        <NotificationTemplatesPanel />
      </div>
    </div>
  );
}
