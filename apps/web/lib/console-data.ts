import consoleJson from "@/data/console.json";

export const VERDICTS = [
  "compliant",
  "at_risk",
  "non_compliant",
  "insufficient_window",
  "no_data",
] as const;

export type Verdict = (typeof VERDICTS)[number];

export type Trade = {
  trade_id: string;
  display_name: string;
  discipline: string;
};

export type WorkFace = {
  id: string;
  name: string;
  structure_id: string;
  level: string | null;
  centroid_lon: number;
  centroid_lat: number;
  exposure_class: string;
  surface_class: string;
  sky_view_factor: number;
};

export type Activity = {
  id: string;
  wbs: string;
  name: string;
  work_face_id: string;
  structure_id: string;
  trade_id: string | null;
  thermal_sensitive: boolean;
  discipline: string;
  planned_start: string;
  planned_finish: string;
  duration_h: number;
  duration_d: number;
  total_float_d: number;
  is_critical: boolean;
  is_near_critical: boolean;
  hold_point: string | null;
  crew_size: number;
  in_demo_window: boolean;
};

export type WindowEvalSummary = {
  activity_id: string;
  verdict: Verdict;
  verdict_summary: string;
  trade_id: string;
  trade_display_name: string;
  work_face_id: string;
  work_face_name: string;
  binding_constraint: {
    type: string;
    label: string;
    mitigation_hint: string | null;
  } | null;
  usd_exposure: {
    at_risk_usd: number;
    protected_usd: number;
    basis: string;
  };
  confidence: "high" | "medium" | "low";
};

export const consoleData = consoleJson as {
  project_id: string;
  project_name: string;
  data_date: string;
  tz: string;
  provenance: string;
  demo_window: { start: string; end: string };
  hero_pair: {
    bare: string;
    shaded: string;
    separation_m: number;
    level: string;
  };
  trades: Trade[];
  work_faces: WorkFace[];
  activities: Activity[];
  evaluations: WindowEvalSummary[];
};

export const VERDICT_LABEL: Record<Verdict, string> = {
  compliant: "In window",
  at_risk: "At risk",
  non_compliant: "Outside",
  insufficient_window: "Too short",
  no_data: "No eval",
};

export const VERDICT_RANK: Record<Verdict, number> = {
  non_compliant: 0,
  insufficient_window: 1,
  at_risk: 2,
  compliant: 3,
  no_data: 4,
};

const evalByActivity = new Map(
  consoleData.evaluations.map((e) => [e.activity_id, e]),
);

const tradeById = new Map(consoleData.trades.map((t) => [t.trade_id, t]));
const faceById = new Map(consoleData.work_faces.map((f) => [f.id, f]));

export function evalFor(activityId: string) {
  return evalByActivity.get(activityId);
}

export function tradeName(tradeId: string | null) {
  if (!tradeId) return "—";
  return tradeById.get(tradeId)?.display_name ?? tradeId;
}

export function tradeShort(tradeId: string | null) {
  const full = tradeName(tradeId);
  if (full === "—") return full;
  return full.split("—")[0]?.trim() ?? full;
}

export function faceName(faceId: string) {
  return faceById.get(faceId)?.name ?? faceId;
}

export function verdictOf(activity: Activity): Verdict {
  return evalByActivity.get(activity.id)?.verdict ?? "no_data";
}

export function worstVerdict(verdicts: Verdict[]): Verdict {
  return verdicts.reduce<Verdict>(
    (worst, v) => (VERDICT_RANK[v] < VERDICT_RANK[worst] ? v : worst),
    "no_data",
  );
}

export type ConsoleFilters = {
  tradeId: string | null;
  workFaceId: string | null;
  verdicts: Set<Verdict>;
  lookaheadOnly: boolean;
  thermalOnly: boolean;
};

export function filterActivities(
  activities: Activity[],
  filters: ConsoleFilters,
) {
  return activities.filter((a) => {
    if (filters.lookaheadOnly && !a.in_demo_window) return false;
    if (filters.thermalOnly && !a.thermal_sensitive) return false;
    if (filters.tradeId && a.trade_id !== filters.tradeId) return false;
    if (filters.workFaceId && a.work_face_id !== filters.workFaceId) {
      return false;
    }
    if (filters.verdicts.size > 0 && !filters.verdicts.has(verdictOf(a))) {
      return false;
    }
    return true;
  });
}

export function sortActivities(activities: Activity[]) {
  return [...activities].sort((a, b) => {
    const va = VERDICT_RANK[verdictOf(a)];
    const vb = VERDICT_RANK[verdictOf(b)];
    if (va !== vb) return va - vb;
    if (a.is_critical !== b.is_critical) return a.is_critical ? -1 : 1;
    if (a.is_near_critical !== b.is_near_critical) {
      return a.is_near_critical ? -1 : 1;
    }
    return a.planned_start.localeCompare(b.planned_start);
  });
}

const phoenixWhen = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/Phoenix",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const phoenixDay = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/Phoenix",
  day: "2-digit",
  month: "short",
});

export function formatWhen(iso: string) {
  return phoenixWhen.format(new Date(iso)).replace(",", "");
}

export function formatDay(iso: string) {
  return phoenixDay.format(new Date(iso));
}

export function formatUsd(n: number) {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}k`;
  if (n <= 0) return "—";
  return `$${Math.round(n)}`;
}

export function formatHours(h: number) {
  return `${h % 1 === 0 ? h.toFixed(0) : h.toFixed(1)} h`;
}

export function formatFloat(d: number) {
  if (d === 0) return "0";
  return d % 1 === 0 ? d.toFixed(0) : d.toFixed(1);
}
