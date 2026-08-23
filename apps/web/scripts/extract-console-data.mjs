import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../../..");
const outDir = path.resolve(here, "../data");

const sched = JSON.parse(
  fs.readFileSync(path.join(root, "data/project_demo/activities.json"), "utf8"),
);
const ribbon = JSON.parse(
  fs.readFileSync(
    path.join(root, "data/fixtures/sample_window_eval_ribbon.json"),
    "utf8",
  ),
);
const tradesFile = JSON.parse(
  fs.readFileSync(path.join(root, "data/trade_windows.json"), "utf8"),
);
const stats = JSON.parse(
  fs.readFileSync(path.join(root, "data/project_demo/stats.json"), "utf8"),
);

const DEMO = stats.demo_window;

function overlaps(start, finish, winStart, winEnd) {
  return start < winEnd && finish > winStart;
}

const activities = sched.activities.map((a) => ({
  id: a.id,
  wbs: a.wbs,
  name: a.name,
  work_face_id: a.work_face_id,
  structure_id: a.structure_id,
  trade_id: a.trade_id,
  thermal_sensitive: a.thermal_sensitive,
  discipline: a.discipline,
  planned_start: a.planned_start,
  planned_finish: a.planned_finish,
  duration_h: a.duration_h,
  duration_d: a.duration_d,
  total_float_d: a.total_float_d,
  is_critical: a.is_critical,
  is_near_critical: a.is_near_critical,
  hold_point: a.hold_point,
  crew_size: a.crew_size,
  in_demo_window: overlaps(
    a.planned_start,
    a.planned_finish,
    DEMO.start,
    DEMO.end,
  ),
}));

const work_faces = sched.work_faces.map((w) => ({
  id: w.id,
  name: w.name,
  structure_id: w.structure_id,
  level: w.level,
  centroid_lon: w.centroid_lon,
  centroid_lat: w.centroid_lat,
  exposure_class: w.exposure_class,
  surface_class: w.surface_class,
  sky_view_factor: w.sky_view_factor,
}));

function offsetDeltaC(tradeId) {
  const trade = tradesFile.trades.find((t) => t.trade_id === tradeId);
  const offset = trade?.constraints?.find((c) => c.type === "offset");
  return typeof offset?.delta_c === "number" ? offset.delta_c : null;
}

const evaluations = ribbon.evaluations.map((e) => ({
  activity_id: e.activity_id,
  verdict: e.verdict,
  verdict_summary: e.verdict_summary,
  trade_id: e.trade_id,
  trade_display_name: e.trade_display_name,
  work_face_id: e.work_face_id,
  work_face_name: e.work_face_name,
  binding_constraint: e.binding_constraint
    ? {
        type: e.binding_constraint.type,
        label: e.binding_constraint.label,
        mitigation_hint: e.binding_constraint.mitigation_hint,
      }
    : null,
  usd_exposure: e.usd_exposure,
  confidence: e.confidence,
}));

const trades = tradesFile.trades.map((t) => ({
  trade_id: t.trade_id,
  display_name: t.display_name,
  discipline: t.discipline,
}));

const payload = {
  project_id: sched.project_id,
  project_name: sched.project_name,
  data_date: sched.data_date,
  tz: sched.tz,
  provenance: sched.provenance,
  demo_window: DEMO,
  hero_pair: stats.hero_pair,
  trades,
  work_faces,
  activities,
  evaluations,
};

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(
  path.join(outDir, "console.json"),
  JSON.stringify(payload, null, 2),
);

const ribbonPayload = {
  run_id: ribbon.run_id,
  generated_at: ribbon.generated_at,
  horizon: ribbon.horizon,
  site_id: ribbon.site_id,
  contended_hours: ribbon.contended_hours,
  totals: ribbon.totals,
  evaluations: ribbon.evaluations.map((e) => ({
    activity_id: e.activity_id,
    activity_name: e.activity_name,
    wbs: e.wbs,
    trade_id: e.trade_id,
    trade_display_name: e.trade_display_name,
    work_face_id: e.work_face_id,
    work_face_name: e.work_face_name,
    verdict: e.verdict,
    verdict_summary: e.verdict_summary,
    citation: e.citation,
    standard_ref: e.standard_ref,
    advisory_notice: e.advisory_notice,
    offset_delta_c: offsetDeltaC(e.trade_id),
    constraints: (e.constraints ?? []).map((c) => ({
      constraint_id: c.constraint_id,
      type: c.type,
      label: c.label,
      citation_fragment: c.citation_fragment,
    })),
    binding_constraint: e.binding_constraint
      ? {
          type: e.binding_constraint.type,
          label: e.binding_constraint.label,
          mitigation_hint: e.binding_constraint.mitigation_hint,
        }
      : null,
    scheduled: e.scheduled,
    hours: e.hours.map((h) => ({
      ts: h.ts,
      state: h.state,
      reason: h.reason,
      binding_constraint_id: h.binding_constraint_id,
      margin: h.margin,
      margin_unit: h.margin_unit,
      t_air_c: h.values?.t_air_c ?? null,
      t_surf_c: h.values?.t_surf_c ?? null,
      t_dew_c: h.values?.t_dew_c ?? null,
    })),
  })),
};

fs.writeFileSync(
  path.join(outDir, "ribbon.json"),
  JSON.stringify(ribbonPayload),
);

fs.copyFileSync(
  path.join(root, "data/project_demo/site.geojson"),
  path.join(outDir, "phoenix-site.json"),
);
fs.copyFileSync(
  path.join(root, "data/project_demo/work_faces.geojson"),
  path.join(outDir, "work-faces.json"),
);
fs.copyFileSync(
  path.join(root, "data/fixtures/cure_fit_macropoxy646.json"),
  path.join(outDir, "cure-fit.json"),
);

console.log(
  `wrote console.json (${activities.length} activities, ${work_faces.length} faces, ${evaluations.length} evals)`,
);
console.log(
  `wrote ribbon.json (${ribbonPayload.evaluations.length} lanes, ${ribbonPayload.evaluations[0]?.hours.length ?? 0} hours)`,
);
