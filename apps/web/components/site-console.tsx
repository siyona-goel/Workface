"use client";

import { useMemo, useState } from "react";

import { ActivityDrawer } from "@/components/activity-drawer";
import { ActivityTable } from "@/components/activity-table";
import { AppNav } from "@/components/app-nav";
import { ConsoleToolbar } from "@/components/console-toolbar";
import { ModeBadge, channelHint } from "@/components/mode-badge";
import { SiteMapLoader } from "@/components/site-map-loader";
import { WindowRibbon } from "@/components/window-ribbon";
import { WorkFaceList } from "@/components/work-face-list";
import {
  VERDICTS,
  consoleData,
  filterActivities,
  formatDay,
  sortActivities,
  verdictOf,
  worstVerdict,
  type Activity,
  type ConsoleFilters,
  type Verdict,
} from "@/lib/console-data";
import { useAgentChannel, useAgentSource } from "@/lib/use-agent-events";

export function SiteConsole() {
  const [filters, setFilters] = useState<ConsoleFilters>({
    tradeId: null,
    workFaceId: null,
    verdicts: new Set(),
    lookaheadOnly: true,
    thermalOnly: false,
  });
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(
    null,
  );
  const [evalsOnly, setEvalsOnly] = useState(true);
  const [heroOnly, setHeroOnly] = useState(false);
  const [focusedFaceId, setFocusedFaceId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const preVerdict = useMemo(
    () =>
      filterActivities(consoleData.activities, {
        ...filters,
        verdicts: new Set(),
      }),
    [filters],
  );

  const rows = useMemo(
    () => sortActivities(filterActivities(consoleData.activities, filters)),
    [filters],
  );

  const verdictCounts = useMemo(() => {
    const counts = Object.fromEntries(VERDICTS.map((v) => [v, 0])) as Record<
      Verdict,
      number
    >;
    for (const a of preVerdict) counts[verdictOf(a)] += 1;
    return counts;
  }, [preVerdict]);

  const faceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of rows) {
      counts[a.work_face_id] = (counts[a.work_face_id] ?? 0) + 1;
    }
    return counts;
  }, [rows]);

  const faceVerdict = useMemo(() => {
    const byFace = new Map<string, Verdict[]>();
    for (const a of preVerdict) {
      const list = byFace.get(a.work_face_id) ?? [];
      list.push(verdictOf(a));
      byFace.set(a.work_face_id, list);
    }
    const out: Record<string, Verdict> = {};
    for (const [id, list] of byFace) out[id] = worstVerdict(list);
    return out;
  }, [preVerdict]);

  function selectWorkFace(id: string | null) {
    setFocusedFaceId(id);
    setFilters((f) => ({ ...f, workFaceId: id }));
  }

  function selectActivity(activity: Activity) {
    setSelectedActivityId(activity.id);
    setFocusedFaceId(activity.work_face_id);
    setFilters((f) => ({ ...f, workFaceId: activity.work_face_id }));
    setDrawerOpen(true);
  }

  function selectLane(activityId: string) {
    setSelectedActivityId(activityId);
    const activity = consoleData.activities.find((a) => a.id === activityId);
    const ev = consoleData.evaluations.find((e) => e.activity_id === activityId);
    setFocusedFaceId(activity?.work_face_id ?? ev?.work_face_id ?? null);
    setDrawerOpen(true);
  }

  const mapFaceId = filters.workFaceId ?? focusedFaceId;
  const source = useAgentSource();
  const { channelState } = useAgentChannel();

  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground lg:h-dvh lg:min-h-0 lg:overflow-hidden">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex min-w-0 items-baseline gap-3">
          <span className="shrink-0 text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden truncate text-xs text-muted-foreground md:inline">
            {consoleData.project_name}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <ModeBadge source={source} channelState={channelState} />
          <span className={channelHint(channelState)}>
            {channelState === "subscribed"
              ? "subscribed"
              : channelState === "connecting"
                ? "connecting"
                : channelState === "error"
                  ? "channel error"
                  : "channel off"}
          </span>
          <span className="hidden font-mono sm:inline">
            {consoleData.project_id}
          </span>
          <span className="hidden md:inline">
            data date {formatDay(consoleData.data_date)}
          </span>
          <span className="hidden lg:inline">
            lookahead {formatDay(consoleData.demo_window.start)}–
            {formatDay(consoleData.demo_window.end)}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <p className="hidden max-w-xs truncate text-[11px] text-muted-foreground xl:block">
            {consoleData.provenance}
          </p>
          <AppNav current="console" />
        </div>
      </header>

      <ConsoleToolbar
        filters={filters}
        onChange={setFilters}
        verdictCounts={verdictCounts}
        resultCount={rows.length}
      />

      <div className="grid h-[42vw] min-h-[200px] max-h-[320px] shrink-0 grid-cols-1 lg:h-auto lg:max-h-none lg:min-h-0 lg:flex-[0.9] lg:grid-cols-[minmax(0,1fr)_280px]">
        <SiteMapLoader
          selectedWorkFaceId={mapFaceId}
          onSelectWorkFace={selectWorkFace}
          faceVerdict={faceVerdict}
        />
        <div className="hidden min-h-0 lg:block">
          <WorkFaceList
            selectedId={mapFaceId}
            onSelect={selectWorkFace}
            counts={faceCounts}
            faceVerdict={faceVerdict}
          />
        </div>
      </div>

      <section className="flex h-[360px] min-h-[280px] min-w-0 flex-col lg:h-auto lg:min-h-0 lg:flex-[1.2]">
        <WindowRibbon
          activities={rows}
          filters={filters}
          selectedId={selectedActivityId}
          onSelectLane={selectLane}
          evalsOnly={evalsOnly}
          onEvalsOnlyChange={setEvalsOnly}
          heroOnly={heroOnly}
          onHeroOnlyChange={setHeroOnly}
        />
      </section>

      <section className="flex h-[300px] min-h-[240px] flex-col lg:h-auto lg:min-h-0 lg:flex-[0.7]">
        <ActivityTable
          activities={rows}
          selectedId={selectedActivityId}
          onSelect={selectActivity}
        />
      </section>

      <ActivityDrawer
        activityId={selectedActivityId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
