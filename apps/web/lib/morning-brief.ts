import briefJson from "@/data/morning-brief.json";
import { consoleData, formatDay, formatUsd } from "@/lib/console-data";
import {
  formatTickHour,
  mergeBands,
  ribbonEvalFor,
  type HourState,
} from "@/lib/ribbon-data";

export type BriefItemKind =
  | "window"
  | "shift"
  | "hold"
  | "escalation"
  | "weather";

export type BriefPriority = "high" | "normal" | "info";

export type BriefItem = {
  id: string;
  kind: BriefItemKind;
  priority: BriefPriority;
  activity_id: string;
  location: string;
  title: string;
  body: string;
  window?: { opens: string; closes: string; date: string };
  scheduled_start?: string;
  previous_start?: string;
  new_start?: string;
  hold_until?: string;
  status: string;
};

export type BriefNotificationQueue = {
  id: string;
  template_id: string;
  activity_id: string;
  channel: string;
  crew: string;
  status: "queued" | "sent" | "failed";
  vars: Record<string, string>;
};

export type MorningBrief = {
  brief_id: string;
  generated_at: string;
  for_date: string;
  tz: string;
  site_id: string;
  project_name: string;
  recipient: { role: string; name: string };
  headline: string;
  weather_line: string;
  items: BriefItem[];
  stats: {
    at_risk_usd: number;
    protected_usd: number;
    activities_today: number;
    notifications_queued: number;
  };
  notification_queue: BriefNotificationQueue[];
};

export const morningBrief = briefJson as unknown as MorningBrief;

const OPEN_STATES = new Set<HourState>(["open", "marginal"]);

const briefDay = new Intl.DateTimeFormat("en-GB", {
  timeZone: morningBrief.tz,
  weekday: "long",
  day: "numeric",
  month: "long",
});

const briefTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: morningBrief.tz,
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatBriefDate(iso: string) {
  return briefDay.format(new Date(iso));
}

export function formatBriefTime(iso: string) {
  return briefTime.format(new Date(iso));
}

export function openWindowForDay(activityId: string, dayIso: string) {
  const ev = ribbonEvalFor(activityId);
  if (!ev) return null;
  const day = dayIso.slice(0, 10);
  const hours = ev.hours.filter((h) => h.ts.startsWith(day));
  if (hours.length === 0) return null;
  const bands = mergeBands(hours, 60 * 60 * 1000).filter((b) =>
    OPEN_STATES.has(b.state as HourState),
  );
  if (bands.length === 0) return null;
  const first = bands[0]!;
  const last = bands[bands.length - 1]!;
  return {
    opens: formatTickHour(new Date(first.startMs).toISOString()),
    closes: formatTickHour(new Date(last.endMs).toISOString()),
  };
}

export const ITEM_KIND_LABEL: Record<BriefItemKind, string> = {
  window: "Window",
  shift: "Moved",
  hold: "Hold",
  escalation: "Escalation",
  weather: "Weather",
};

export const ITEM_STATUS_LABEL: Record<string, string> = {
  ready: "Ready",
  confirmed: "Confirmed",
  hold: "On hold",
  watch: "Watch",
  escalated: "Escalated",
};

export const PRIORITY_ORDER: Record<BriefPriority, number> = {
  high: 0,
  normal: 1,
  info: 2,
};

export function briefStatsLine() {
  const { stats } = morningBrief;
  return `${formatUsd(stats.at_risk_usd)} at risk · ${formatUsd(stats.protected_usd)} protected · ${stats.activities_today} activities today`;
}

export function briefProvenance() {
  return `${consoleData.project_id} · data date ${formatDay(consoleData.data_date)} · ${morningBrief.brief_id}`;
}
