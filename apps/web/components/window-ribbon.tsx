"use client";

import { useMemo, useState, type MouseEvent } from "react";

import { WindowChip } from "@/components/window-chip";
import {
  HORIZON_HOURS,
  HOUR_STATE_FILL,
  HOUR_STATE_FILL_DIM,
  HOUR_STATE_LABEL,
  contendedLabel,
  evalMatchesFilters,
  formatTick,
  formatTickHour,
  heroRole,
  isHeroLane,
  laneFromActivity,
  laneFromEval,
  mergeBands,
  ribbonData,
  sortLanes,
  type HourState,
  type RibbonHour,
  type RibbonLane,
} from "@/lib/ribbon-data";
import {
  consoleData,
  formatUsd,
  type Activity,
  type ConsoleFilters,
} from "@/lib/console-data";
import { cn } from "@/lib/utils";

const LANE_H = 34;
const BAND_Y = 8;
const BAND_H = 18;
const BAR_H = 7;
const AXIS_H = 28;

type Props = {
  activities: Activity[];
  filters: ConsoleFilters;
  selectedId: string | null;
  onSelectLane: (activityId: string) => void;
  evalsOnly: boolean;
  onEvalsOnlyChange: (value: boolean) => void;
  heroOnly: boolean;
  onHeroOnlyChange: (value: boolean) => void;
};

type Hover = {
  laneId: string;
  x: number;
  y: number;
  hour: RibbonHour;
};

export function WindowRibbon({
  activities,
  filters,
  selectedId,
  onSelectLane,
  evalsOnly,
  onEvalsOnlyChange,
  heroOnly,
  onHeroOnlyChange,
}: Props) {
  const [hover, setHover] = useState<Hover | null>(null);

  const t0 = Date.parse(ribbonData.horizon.start);
  const t1 = Date.parse(ribbonData.horizon.end);
  const span = t1 - t0;
  const stepMs = ribbonData.horizon.step_minutes * 60_000;

  const lanes = useMemo(() => {
    const fromEvals = ribbonData.evaluations
      .filter((ev) => evalMatchesFilters(ev, filters))
      .filter((ev) => !heroOnly || isHeroLane(ev.activity_id))
      .map(laneFromEval);
    if (evalsOnly) return sortLanes(fromEvals);
    const seen = new Set(fromEvals.map((l) => l.activity_id));
    const extras = activities
      .filter((a) => !seen.has(a.id))
      .filter((a) => !heroOnly || isHeroLane(a.id))
      .map(laneFromActivity);
    return sortLanes([...fromEvals, ...extras]);
  }, [activities, evalsOnly, filters, heroOnly]);

  const contention = contendedLabel(ribbonData.contended_hours);
  const heroVisible = lanes.filter((l) => isHeroLane(l.activity_id)).length;

  const ticks = useMemo(() => {
    const out: { t: number; label: string; major: boolean }[] = [];
    for (let t = t0; t <= t1; t += 6 * 60 * 60 * 1000) {
      const iso = new Date(t).toISOString();
      const hour = formatTickHour(iso);
      out.push({
        t,
        label: hour === "00:00" ? formatTick(iso) : hour,
        major: hour === "00:00",
      });
    }
    return out;
  }, [t0, t1]);

  function onLaneMove(
    event: MouseEvent<SVGSVGElement>,
    lane: RibbonLane,
  ) {
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const width = rect.width;
    const t = t0 + (x / width) * span;
    let best = lane.hours[0];
    let bestDist = Infinity;
    for (const hour of lane.hours) {
      const dist = Math.abs(Date.parse(hour.ts) - t);
      if (dist < bestDist) {
        bestDist = dist;
        best = hour;
      }
    }
    setHover({
      laneId: lane.activity_id,
      x: event.clientX,
      y: event.clientY,
      hour: best,
    });
  }

  return (
    <section className="flex min-h-0 flex-col border-t border-border/70 bg-card/15">
      <div className="flex flex-col gap-2 px-3 py-2 sm:px-4 lg:flex-row lg:items-start lg:justify-between lg:gap-3">
        <div className="min-w-0">
          <h2 className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
            Window ribbon
          </h2>
          <p className="hidden text-[11px] text-muted-foreground sm:block">
            {HORIZON_HOURS} h · {ribbonData.horizon.tz} · scheduled bar on the
            bands. If the bar is not on green, that is the problem.
          </p>
          {heroVisible >= 2 ? (
            <p className="mt-0.5 hidden text-[11px] text-cyan-200/90 md:block">
              Hero pair pinned at top — same coating,{" "}
              {consoleData.hero_pair.separation_m} m apart,{" "}
              {consoleData.hero_pair.level}. Shaded stays open at 04:00; bare
              goes marginal.
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground sm:gap-3">
          <button
            type="button"
            aria-pressed={evalsOnly}
            onClick={() => onEvalsOnlyChange(!evalsOnly)}
            className={cn(
              "h-6 rounded-md border px-2 text-[11px] font-medium",
              evalsOnly
                ? "border-primary/40 bg-primary/15 text-foreground"
                : "border-border text-muted-foreground",
            )}
          >
            Evals only
          </button>
          <button
            type="button"
            aria-pressed={heroOnly}
            onClick={() => onHeroOnlyChange(!heroOnly)}
            className={cn(
              "h-6 rounded-md border px-2 text-[11px] font-medium",
              heroOnly
                ? "border-cyan-400/40 bg-cyan-400/15 text-cyan-100"
                : "border-border text-muted-foreground",
            )}
          >
            Hero pair
          </button>
          {contention ? (
            <span className="rounded-sm border border-violet-300/30 bg-violet-300/10 px-1.5 py-0.5 text-violet-200">
              contention {contention}
            </span>
          ) : null}
          <span className="hidden items-center gap-2 sm:contents">
            <LegendSwatch state="open" />
            <LegendSwatch state="marginal" />
            <LegendSwatch state="closed" />
            <LegendSwatch state="no_data" />
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-5 rounded-sm bg-slate-100" />
              Scheduled
            </span>
          </span>
          <span className="font-mono tabular-nums">
            {formatUsd(ribbonData.totals.at_risk_usd)} at risk
          </span>
        </div>
      </div>

      {lanes.length === 0 ? (
        <div className="px-4 py-8 text-center text-sm text-muted-foreground">
          No ribbon fixtures match the current filters. Clear a filter or turn
          off “Evals only”.
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <div className="min-w-[540px] sm:min-w-[720px]">
            <div className="sticky top-0 z-10 flex bg-background/95 backdrop-blur">
              <div className="w-36 shrink-0 px-3 py-1 text-[10px] tracking-wider text-muted-foreground uppercase sm:w-56">
                Activity
              </div>
              <div className="relative min-w-0 flex-1 pr-3">
                <svg
                  width="100%"
                  height={AXIS_H}
                  className="block"
                  aria-hidden
                >
                  <AxisTicks
                    ticks={ticks}
                    t0={t0}
                    span={span}
                    contended={ribbonData.contended_hours}
                  />
                </svg>
              </div>
            </div>

            {lanes.map((lane) => {
              const selected = selectedId === lane.activity_id;
              const hero = isHeroLane(lane.activity_id)
                ? heroRole(lane.work_face_id)
                : null;
              return (
                <button
                  key={lane.activity_id}
                  type="button"
                  onClick={() => onSelectLane(lane.activity_id)}
                  className={cn(
                    "flex w-full items-stretch text-left transition-colors",
                    selected ? "bg-primary/15" : "hover:bg-muted/25",
                    hero && "border-l-2 border-cyan-300/70",
                  )}
                >
                  <div className="flex w-36 shrink-0 flex-col justify-center px-3 py-1 sm:w-56">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {lane.activity_id}
                      </span>
                      <WindowChip verdict={lane.verdict} static />
                      {hero ? (
                        <span className="rounded-sm bg-cyan-400/15 px-1 font-mono text-[9px] tracking-wide text-cyan-200 uppercase">
                          {hero}
                        </span>
                      ) : null}
                    </div>
                    <div className="truncate text-[11px] font-medium">
                      {lane.activity_name}
                    </div>
                    <div className="truncate font-mono text-[10px] text-muted-foreground">
                      {lane.work_face_name}
                    </div>
                  </div>
                  <div className="min-w-0 flex-1 pr-3">
                    <LaneSvg
                      lane={lane}
                      t0={t0}
                      t1={t1}
                      span={span}
                      stepMs={stepMs}
                      hoverHour={
                        hover?.laneId === lane.activity_id ? hover.hour : null
                      }
                      onMove={(e) => onLaneMove(e, lane)}
                      onLeave={() => setHover(null)}
                    />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {hover ? (
        <div
          className="pointer-events-none fixed z-50 max-w-sm rounded-md border border-border bg-background px-2.5 py-2 text-xs shadow-lg"
          style={{
            left: Math.min(hover.x + 14, window.innerWidth - 240),
            top: Math.min(hover.y + 14, window.innerHeight - 120),
          }}
        >
          <div className="flex items-center gap-2">
            <span
              className="size-2 rounded-full"
              style={{ background: HOUR_STATE_FILL[hover.hour.state] }}
            />
            <span className="font-medium">
              {HOUR_STATE_LABEL[hover.hour.state]}
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">
              {formatTick(hover.hour.ts)}
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
            {hover.hour.reason ?? "No reason on this hour."}
          </p>
          {hover.hour.margin != null ? (
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              margin {hover.hour.margin > 0 ? "+" : ""}
              {hover.hour.margin} {hover.hour.margin_unit ?? ""}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function LegendSwatch({ state }: { state: HourState }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="size-2.5 rounded-sm"
        style={{ background: HOUR_STATE_FILL[state] }}
      />
      {HOUR_STATE_LABEL[state]}
    </span>
  );
}

function AxisTicks({
  ticks,
  t0,
  span,
  contended,
}: {
  ticks: { t: number; label: string; major: boolean }[];
  t0: number;
  span: number;
  contended: string[];
}) {
  return (
    <>
      {contended.map((iso) => {
        const x = ((Date.parse(iso) - t0) / span) * 100;
        return (
          <rect
            key={iso}
            x={`${x}%`}
            y={0}
            width={`${(60 * 60 * 1000) / span * 100}%`}
            height={AXIS_H}
            fill="rgba(196,181,253,0.12)"
          />
        );
      })}
      {ticks.map((tick) => {
        const x = ((tick.t - t0) / span) * 100;
        return (
          <g key={tick.t}>
            <line
              x1={`${x}%`}
              x2={`${x}%`}
              y1={tick.major ? 4 : 12}
              y2={AXIS_H}
              stroke="currentColor"
              className="text-border"
              strokeWidth={1}
            />
            <text
              x={`${x}%`}
              y={10}
              className="fill-muted-foreground"
              fontSize={9}
              fontFamily="ui-monospace, monospace"
            >
              {tick.label}
            </text>
          </g>
        );
      })}
    </>
  );
}

function LaneSvg({
  lane,
  t0,
  t1,
  span,
  stepMs,
  hoverHour,
  onMove,
  onLeave,
}: {
  lane: RibbonLane;
  t0: number;
  t1: number;
  span: number;
  stepMs: number;
  hoverHour: RibbonHour | null;
  onMove: (event: MouseEvent<SVGSVGElement>) => void;
  onLeave: () => void;
}) {
  const bands = useMemo(
    () => mergeBands(lane.hours, stepMs),
    [lane.hours, stepMs],
  );

  return (
    <svg
      width="100%"
      height={LANE_H}
      className="block"
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      {ribbonData.contended_hours.map((iso) => (
        <rect
          key={iso}
          x={`${((Date.parse(iso) - t0) / span) * 100}%`}
          y={0}
          width={`${((60 * 60 * 1000) / span) * 100}%`}
          height={LANE_H}
          fill="rgba(196,181,253,0.07)"
        />
      ))}
      {bands.map((band, i) => (
        <rect
          key={`${band.startMs}-${i}`}
          x={`${((band.startMs - t0) / span) * 100}%`}
          y={BAND_Y}
          width={`${((band.endMs - band.startMs) / span) * 100}%`}
          height={BAND_H}
          rx={2}
          fill={
            hoverHour &&
            Date.parse(hoverHour.ts) >= band.startMs &&
            Date.parse(hoverHour.ts) < band.endMs
              ? HOUR_STATE_FILL[band.state]
              : HOUR_STATE_FILL_DIM[band.state]
          }
        />
      ))}
      <ScheduledBar t0={t0} t1={t1} span={span} start={lane.scheduled.start} finish={lane.scheduled.finish} />
      {hoverHour ? (
        <rect
          x={`${((Date.parse(hoverHour.ts) - t0) / span) * 100}%`}
          y={BAND_Y - 1}
          width={`${(stepMs / span) * 100}%`}
          height={BAND_H + 2}
          fill="none"
          stroke="rgba(248,250,252,0.7)"
          strokeWidth={1}
        />
      ) : null}
    </svg>
  );
}

function ScheduledBar({
  t0,
  t1,
  span,
  start,
  finish,
}: {
  t0: number;
  t1: number;
  span: number;
  start: string;
  finish: string;
}) {
  const a = Math.max(t0, Date.parse(start));
  const b = Math.min(t1, Date.parse(finish));
  if (b <= a) return null;
  return (
    <rect
      x={`${((a - t0) / span) * 100}%`}
      y={BAND_Y + (BAND_H - BAR_H) / 2}
      width={`${((b - a) / span) * 100}%`}
      height={BAR_H}
      rx={2}
      fill="#f8fafc"
      stroke="#94a3b8"
      strokeWidth={0.75}
      opacity={0.92}
    />
  );
}
