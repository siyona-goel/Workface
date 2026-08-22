"use client";

import { useMemo, useState } from "react";

import { ActivityTable } from "@/components/activity-table";
import { ConsoleToolbar } from "@/components/console-toolbar";
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
    setFilters((f) => ({ ...f, workFaceId: id }));
  }

  function selectActivity(activity: Activity) {
    setSelectedActivityId(activity.id);
    setFilters((f) => ({ ...f, workFaceId: activity.work_face_id }));
  }

  function selectLane(activityId: string) {
    setSelectedActivityId(activityId);
  }

  return (
    <div className="flex h-dvh min-h-0 flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-4 border-b border-border/70 px-4 py-2.5">
        <div className="flex items-baseline gap-3">
          <span className="text-sm font-semibold tracking-[0.22em]">
            WORKFACE
          </span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            {consoleData.project_name}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-sm border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-medium tracking-wider text-emerald-200 uppercase">
            Replay
          </span>
          <span className="font-mono">{consoleData.project_id}</span>
          <span>data date {formatDay(consoleData.data_date)}</span>
          <span>
            lookahead {formatDay(consoleData.demo_window.start)}–
            {formatDay(consoleData.demo_window.end)}
          </span>
        </div>
        <p className="ml-auto hidden max-w-sm truncate text-[11px] text-muted-foreground lg:block">
          {consoleData.provenance}
        </p>
      </header>

      <ConsoleToolbar
        filters={filters}
        onChange={setFilters}
        verdictCounts={verdictCounts}
        resultCount={rows.length}
      />

      <div className="grid min-h-0 flex-[0.9] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_280px]">
        <SiteMapLoader
          selectedWorkFaceId={filters.workFaceId}
          onSelectWorkFace={selectWorkFace}
          faceVerdict={faceVerdict}
        />
        <div className="hidden min-h-0 lg:block">
          <WorkFaceList
            selectedId={filters.workFaceId}
            onSelect={selectWorkFace}
            counts={faceCounts}
            faceVerdict={faceVerdict}
          />
        </div>
      </div>

      <section className="flex min-h-[220px] min-w-0 flex-[1.2] flex-col">
        <WindowRibbon
          activities={rows}
          filters={filters}
          selectedId={selectedActivityId}
          onSelectLane={selectLane}
          evalsOnly={evalsOnly}
          onEvalsOnlyChange={setEvalsOnly}
        />
      </section>

      <section className="min-h-0 flex-[0.7]">
        <ActivityTable
          activities={rows}
          selectedId={selectedActivityId}
          onSelect={selectActivity}
        />
      </section>
    </div>
  );
}
