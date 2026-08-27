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

/**
 * Fills for the ribbon bands, aligned with VERDICT_FILL in `lib/verdicts.ts` so
 * the ribbon, the verdict chips and the deck.gl work-face polygons all paint the
 * same amber/red family.
 *
 * These were emerald/amber/red-300 pastels. At a 1 h cell width the amber-300
 * pastel sat at a 1.06:1 luminance ratio against the open mint — identical
 * brightness, so a marginal hour read as green after video compression and was
 * invisible to a deuteranopic viewer. amber-500 / red-500 carry the difference.
 */
export const HOUR_STATE_FILL: Record<HourState, string> = {
  open: "#6ee7b7",
  marginal: "#f59e0b",
  closed: "#ef4444",
  no_data: "#a1a1aa",
};

export const HOUR_STATE_FILL_DIM: Record<HourState, string> = {
  open: "#6ee7b7aa",
  marginal: "#f59e0baa",
  closed: "#ef4444aa",
  no_data: "#a1a1aa55",
};

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

export function contendedLabel(hours: string[]) {
  if (hours.length === 0) return null;
  const first = formatTickHour(hours[0]);
  const lastMs = Date.parse(hours[hours.length - 1]) + 60 * 60 * 1000;
  const last = formatTickHour(new Date(lastMs).toISOString());
  const day = formatTick(hours[0]).replace(/\s+\d{2}:\d{2}$/, "");
  return `${day} ${first}–${last}`;
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

