import ribbonJson from "@/data/ribbon.json";
import {
  consoleData,
  VERDICT_RANK,
  type Activity,
  type ConsoleFilters,
  type Verdict,
} from "@/lib/console-data";

export const HOUR_STATES = ["open", "marginal", "closed", "no_data"] as const;
export type HourState = (typeof HOUR_STATES)[number];

export type RibbonHour = {
  ts: string;
  state: HourState;
  reason: string | null;
  binding_constraint_id: string | null;
  margin: number | null;
  margin_unit: string | null;
  t_air_c?: number | null;
  t_surf_c?: number | null;
  t_dew_c?: number | null;
};

export type RibbonConstraint = {
  constraint_id: string;
  type: string;
  label: string;
  citation_fragment: string;
};

export type RibbonEval = {
  activity_id: string;
  activity_name: string;
  wbs: string | null;
  trade_id: string;
  trade_display_name: string;
  work_face_id: string;
  work_face_name: string;
  verdict: Verdict;
  verdict_summary: string;
  citation?: string;
  standard_ref?: string;
  advisory_notice?: string;
  offset_delta_c?: number | null;
  constraints?: RibbonConstraint[];
  binding_constraint: {
    type: string;
    label: string;
    mitigation_hint: string | null;
  } | null;
  scheduled: {
    start: string;
    finish: string;
    duration_h: number;
    total_float_d: number;
    is_critical: boolean;
    is_near_critical: boolean;
  };
  hours: RibbonHour[];
};

export const ribbonData = ribbonJson as {
  run_id: string;
  generated_at: string;
  horizon: {
    start: string;
    end: string;
    step_minutes: number;
    tz: string;
    tier: string;
  };
  site_id: string;
  contended_hours: string[];
  totals: {
    at_risk_usd: number;
    protected_usd: number;
    basis: string;
  };
  evaluations: RibbonEval[];
};

export const HOUR_STATE_LABEL: Record<HourState, string> = {
  open: "Open",
  marginal: "Marginal",
  closed: "Closed",
  no_data: "No data",
};

/** Pastel fills aligned with the window-state chips (emerald / amber / red / zinc 300). */
export const HOUR_STATE_FILL: Record<HourState, string> = {
  open: "#6ee7b7",
  marginal: "#fcd34d",
  closed: "#fca5a5",
  no_data: "#a1a1aa",
};

export const HOUR_STATE_FILL_DIM: Record<HourState, string> = {
  open: "#6ee7b7aa",
  marginal: "#fcd34daa",
  closed: "#fca5a5aa",
  no_data: "#a1a1aa55",
};

/** Lower is worse. `no_data` is absence of an eval, not a thermal close. */
export const HOUR_STATE_RANK: Record<HourState, number> = {
  closed: 0,
  marginal: 1,
  open: 2,
  no_data: 3,
};

export const HOUR_STATE_DOT: Record<HourState, string> = {
  open: "bg-emerald-300",
  marginal: "bg-amber-300",
  closed: "bg-red-300",
  no_data: "bg-zinc-400",
};

/** deck.gl RGBA aligned with `HOUR_STATE_FILL`. */
export const HOUR_STATE_FILL_RGBA: Record<
  HourState,
  [number, number, number, number]
> = {
  open: [110, 231, 183, 160],
  marginal: [252, 211, 77, 165],
  closed: [252, 165, 165, 175],
  no_data: [161, 161, 170, 70],
};

export function worstHourState(states: HourState[]): HourState {
  return states.reduce<HourState>(
    (worst, s) => (HOUR_STATE_RANK[s] < HOUR_STATE_RANK[worst] ? s : worst),
    "no_data",
  );
}

export function horizonHourStarts(): string[] {
  const hours = ribbonData.evaluations[0]?.hours ?? [];
  return hours.map((hour) => hour.ts);
}

export function defaultPlayheadTs(): string {
  const stamps = horizonHourStarts();
  const contended = ribbonData.contended_hours[0];
  if (contended) {
    if (stamps.includes(contended)) return contended;
    return snapToHourTs(Date.parse(contended));
  }
  return stamps[0] ?? ribbonData.horizon.start;
}

export function snapToHourTs(ms: number): string {
  const stamps = horizonHourStarts();
  if (stamps.length === 0) return ribbonData.horizon.start;
  let best = stamps[0];
  let bestDist = Infinity;
  for (const ts of stamps) {
    const dist = Math.abs(Date.parse(ts) - ms);
    if (dist < bestDist) {
      bestDist = dist;
      best = ts;
    }
  }
  return best;
}

export function shiftPlayheadTs(ts: string, deltaHours: number): string {
  const stamps = horizonHourStarts();
  if (stamps.length === 0) return ts;
  const i = stamps.indexOf(ts);
  const idx = i < 0 ? 0 : i;
  return stamps[Math.min(stamps.length - 1, Math.max(0, idx + deltaHours))];
}

export function hourStateAt(hours: RibbonHour[], ts: string): HourState {
  const exact = hours.find((hour) => hour.ts === ts);
  if (exact) return exact.state;
  const t = Date.parse(ts);
  const stepMs = ribbonData.horizon.step_minutes * 60_000;
  for (const hour of hours) {
    const start = Date.parse(hour.ts);
    if (t >= start && t < start + stepMs) return hour.state;
  }
  return "no_data";
}

/** Worst hour-state on each work face at `ts`, among evals matching toolbar filters. */
export function faceHourStatesAt(
  ts: string,
  filters: ConsoleFilters,
): Record<string, HourState> {
  const byFace = new Map<string, HourState[]>();
  for (const ev of ribbonData.evaluations) {
    if (!evalMatchesFilters(ev, filters)) continue;
    const list = byFace.get(ev.work_face_id) ?? [];
    list.push(hourStateAt(ev.hours, ts));
    byFace.set(ev.work_face_id, list);
  }
  const out: Record<string, HourState> = {};
  for (const face of consoleData.work_faces) {
    const list = byFace.get(face.id);
    out[face.id] = list ? worstHourState(list) : "no_data";
  }
  return out;
}

const activityById = new Map(consoleData.activities.map((a) => [a.id, a]));
const evalById = new Map(ribbonData.evaluations.map((e) => [e.activity_id, e]));

const HERO_FACES = new Set([
  consoleData.hero_pair.shaded,
  consoleData.hero_pair.bare,
]);

/** Coating lanes on the hero pair (shaded WF-FAB2-06, bare WF-FAB2-07). */
export const HERO_EVALS = ribbonData.evaluations.filter(
  (ev) =>
    HERO_FACES.has(ev.work_face_id) &&
    ev.trade_id === "coating_epoxy_structural_steel",
);

export const HERO_ACTIVITY_IDS = new Set(HERO_EVALS.map((e) => e.activity_id));

export const HORIZON_HOURS = Math.round(
  (Date.parse(ribbonData.horizon.end) - Date.parse(ribbonData.horizon.start)) /
    3_600_000,
);

export function isHeroLane(activityId: string) {
  return HERO_ACTIVITY_IDS.has(activityId);
}

export function heroRole(workFaceId: string): "shaded" | "bare" | null {
  if (workFaceId === consoleData.hero_pair.shaded) return "shaded";
  if (workFaceId === consoleData.hero_pair.bare) return "bare";
  return null;
}

export function ribbonEvalFor(activityId: string) {
  return evalById.get(activityId);
}

export function activityForRibbon(activityId: string) {
  return activityById.get(activityId);
}

export type RibbonLane = {
  activity_id: string;
  activity_name: string;
  trade_display_name: string;
  work_face_id: string;
  work_face_name: string;
  verdict: Verdict;
  scheduled: { start: string; finish: string };
  hours: RibbonHour[];
  hasEval: boolean;
};

export function sortLanes(lanes: RibbonLane[]) {
  return [...lanes].sort((a, b) => {
    const ha = isHeroLane(a.activity_id) ? 0 : 1;
    const hb = isHeroLane(b.activity_id) ? 0 : 1;
    if (ha !== hb) return ha - hb;
    if (ha === 0) {
      const ra = heroRole(a.work_face_id) === "shaded" ? 0 : 1;
      const rb = heroRole(b.work_face_id) === "shaded" ? 0 : 1;
      return ra - rb;
    }
    const va = VERDICT_RANK[a.verdict];
    const vb = VERDICT_RANK[b.verdict];
    if (va !== vb) return va - vb;
    return a.scheduled.start.localeCompare(b.scheduled.start);
  });
}

export function buildPlaceholderHours(): RibbonHour[] {
  const template = ribbonData.evaluations[0]?.hours ?? [];
  return template.map((hour) => ({
    ts: hour.ts,
    state: "no_data",
    reason: "No window_eval fixture for this activity yet.",
    binding_constraint_id: null,
    margin: null,
    margin_unit: null,
    t_air_c: null,
    t_surf_c: null,
    t_dew_c: null,
  }));
}

const PLACEHOLDER_HOURS = buildPlaceholderHours();

export function evalMatchesFilters(ev: RibbonEval, filters: ConsoleFilters) {
  if (filters.tradeId && ev.trade_id !== filters.tradeId) return false;
  if (filters.workFaceId && ev.work_face_id !== filters.workFaceId) return false;
  if (filters.verdicts.size > 0 && !filters.verdicts.has(ev.verdict)) {
    return false;
  }
  return true;
}

export function laneFromEval(ev: RibbonEval): RibbonLane {
  return {
    activity_id: ev.activity_id,
    activity_name: ev.activity_name,
    trade_display_name: ev.trade_display_name,
    work_face_id: ev.work_face_id,
    work_face_name: ev.work_face_name,
    verdict: ev.verdict,
    scheduled: { start: ev.scheduled.start, finish: ev.scheduled.finish },
    hours: ev.hours,
    hasEval: true,
  };
}

export function laneFromActivity(activity: Activity): RibbonLane {
  const ev = evalById.get(activity.id);
  if (ev) {
    return {
      activity_id: ev.activity_id,
      activity_name: ev.activity_name,
      trade_display_name: ev.trade_display_name,
      work_face_id: ev.work_face_id,
      work_face_name: ev.work_face_name,
      verdict: ev.verdict,
      scheduled: { start: ev.scheduled.start, finish: ev.scheduled.finish },
      hours: ev.hours,
      hasEval: true,
    };
  }
  return {
    activity_id: activity.id,
    activity_name: activity.name,
    trade_display_name: activity.trade_id ?? "—",
    work_face_id: activity.work_face_id,
    work_face_name:
      consoleData.work_faces.find((f) => f.id === activity.work_face_id)
        ?.name ?? activity.work_face_id,
    verdict: "no_data",
    scheduled: {
      start: activity.planned_start,
      finish: activity.planned_finish,
    },
    hours: PLACEHOLDER_HOURS,
    hasEval: false,
  };
}

export type Band = {
  state: HourState;
  startMs: number;
  endMs: number;
};

export function mergeBands(hours: RibbonHour[], stepMs: number): Band[] {
  const bands: Band[] = [];
  for (const hour of hours) {
    const startMs = Date.parse(hour.ts);
    const endMs = startMs + stepMs;
    const last = bands[bands.length - 1];
    if (last && last.state === hour.state && last.endMs === startMs) {
      last.endMs = endMs;
    } else {
      bands.push({ state: hour.state, startMs, endMs });
    }
  }
  return bands;
}

const phoenixTick = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/Phoenix",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatTick(iso: string) {
  return phoenixTick.format(new Date(iso)).replace(",", "");
}

export function formatTickHour(iso: string) {
  const d = new Date(iso);
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "America/Phoenix",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
  return parts;
}

