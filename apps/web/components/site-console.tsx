"use client";

import { useCallback, useMemo, useRef, useState } from "react";

import { ActivityDrawer } from "@/components/activity-drawer";
import { ActivityTable } from "@/components/activity-table";
import { AppNav, WorkfaceHomeLink } from "@/components/app-nav";
import { ConsoleToolbar } from "@/components/console-toolbar";
import { RowResizeHandle } from "@/components/row-resize-handle";
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

const PANE_MIN_PX = 140;
const HANDLE_PX = 8;
const DEFAULT_PANE_SHARES = {
  map: 0.9,
  ribbon: 1.2,
  activities: 0.7,
};

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

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
  const [paneShares, setPaneShares] = useState(DEFAULT_PANE_SHARES);
  const [resizingPanes, setResizingPanes] = useState(false);
  const panesRef = useRef<HTMLDivElement>(null);

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

  const resizeMapRibbon = useCallback((clientY: number) => {
    const el = panesRef.current;
    if (!el) return;
    const ribbonEl = el.children[2] as HTMLElement | undefined;
    const activitiesEl = el.children[4] as HTMLElement | undefined;
    if (!ribbonEl || !activitiesEl) return;
    const rect = el.getBoundingClientRect();
    const content = rect.height - HANDLE_PX * 2;
    if (content <= 0) return;
    const mapPx = clamp(
      clientY - rect.top,
      PANE_MIN_PX,
      content - PANE_MIN_PX * 2,
    );
    const rest = content - mapPx;
    const ribbonH = ribbonEl.getBoundingClientRect().height;
    const activitiesH = activitiesEl.getBoundingClientRect().height;
    const restShare = ribbonH + activitiesH;
    const ribbonRatio = restShare > 0 ? ribbonH / restShare : 0.63;
    const ribbonPx = clamp(rest * ribbonRatio, PANE_MIN_PX, rest - PANE_MIN_PX);
    setPaneShares({
      map: mapPx,
      ribbon: ribbonPx,
      activities: rest - ribbonPx,
    });
  }, []);

  const resizeRibbonActivities = useCallback((clientY: number) => {
    const el = panesRef.current;
    if (!el) return;
    const mapEl = el.children[0] as HTMLElement | undefined;
    if (!mapEl) return;
    const rect = el.getBoundingClientRect();
    const content = rect.height - HANDLE_PX * 2;
    if (content <= 0) return;
    const mapPx = mapEl.getBoundingClientRect().height;
    const ribbonPx = clamp(
      clientY - mapEl.getBoundingClientRect().bottom,
      PANE_MIN_PX,
      content - mapPx - PANE_MIN_PX,
    );
    setPaneShares({
      map: mapPx,
      ribbon: ribbonPx,
      activities: content - mapPx - ribbonPx,
    });
  }, []);

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="flex shrink-0 items-center gap-x-3 border-b border-border/70 px-3 py-2 sm:px-4 sm:py-2.5">
        <div className="flex min-w-0 items-baseline gap-2.5">
          <WorkfaceHomeLink />
          <span className="truncate text-xs text-muted-foreground">
            North Phoenix · {formatDay(consoleData.demo_window.start)}–
            {formatDay(consoleData.demo_window.end)}
          </span>
        </div>
        <div className="ml-auto shrink-0">
          <AppNav current="console" />
        </div>
      </header>

      <div className="shrink-0">
        <ConsoleToolbar
          filters={filters}
          onChange={setFilters}
          verdictCounts={verdictCounts}
          resultCount={rows.length}
        />
      </div>

      <div
        ref={panesRef}
        className="grid min-h-0 flex-1"
        style={{
          gridTemplateRows: `${paneShares.map}fr ${HANDLE_PX}px ${paneShares.ribbon}fr ${HANDLE_PX}px ${paneShares.activities}fr`,
        }}
      >
        <div className="grid h-full min-h-0 grid-cols-1 overflow-hidden lg:grid-cols-[minmax(0,1fr)_280px]">
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

        <RowResizeHandle
          label="Resize map and window ribbon"
          onResize={resizeMapRibbon}
          onDragChange={setResizingPanes}
        />

        <div className="min-h-0 min-w-0 overflow-hidden">
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
        </div>

        <RowResizeHandle
          label="Resize window ribbon and activities"
          onResize={resizeRibbonActivities}
          onDragChange={setResizingPanes}
        />

        <div className="min-h-0 overflow-hidden">
          <ActivityTable
            activities={rows}
            selectedId={selectedActivityId}
            onSelect={selectActivity}
          />
        </div>
      </div>

      {resizingPanes ? (
        <div className="fixed inset-0 z-50 cursor-row-resize" />
      ) : null}

      <ActivityDrawer
        activityId={selectedActivityId}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}
