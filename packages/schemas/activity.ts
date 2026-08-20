/**
 * WORKFACE — canonical project-schedule contract (Zod mirror of activity.py).
 *
 * Handoff #1: T3 -> T2 (Day 2). Also the target shape for T2's P6 XER / CSV
 * importer (Day 6), so generator and importer are interchangeable.
 *
 * NAMING RULE: activity_id = a scheduled construction task.
 *              fg_activity_id = a FortyGuard async job handle. Never blur them.
 */

import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0";

const Iso8601 = z.string().datetime({ offset: true });

export const LinkType = z.enum(["FS", "SS", "FF", "SF"]);
export type LinkType = z.infer<typeof LinkType>;

export const ExposureClass = z.enum([
  "open_deck",
  "shaded_by_steel",
  "ground_slab",
  "elevated_facade",
  "enclosed",
  "paved_corridor",
  "trench",
]);
export type ExposureClass = z.infer<typeof ExposureClass>;

export const SurfaceClass = z.enum([
  "bare_concrete",
  "aged_concrete",
  "asphalt",
  "galvanised_steel",
  "coated_steel",
  "cmu_masonry",
  "soil",
  "vegetation",
]);
export type SurfaceClass = z.infer<typeof SurfaceClass>;

export const Discipline = z.enum([
  "civil",
  "structural",
  "architectural",
  "mechanical",
  "electrical",
  "sitework",
]);
export type Discipline = z.infer<typeof Discipline>;

/** The unit of everything. Not the site, not the activity. */
export const WorkFace = z.object({
  id: z.string(),
  name: z.string(),
  structure_id: z.string(),
  level: z.string().nullable().default(null),
  /** GeoJSON Polygon, EPSG:4326, [lon, lat]. */
  geom: z.record(z.string(), z.unknown()),
  centroid_lon: z.number(),
  centroid_lat: z.number(),
  area_m2: z.number().positive(),
  elevation_m: z.number(),
  height_agl_m: z.number().min(0).default(0),
  exposure_class: ExposureClass,
  surface_class: SurfaceClass,
  /** psi. 1.0 = unobstructed. Placeholder until T2's streetview capture. */
  sky_view_factor: z.number().min(0).max(1).default(1),
  orientation_deg: z.number().min(0).lt(360).nullable().default(null),
  /** Written by T2 on Day 3. Leave null. */
  tile_cluster_id: z.string().nullable().default(null),
  notes: z.string().nullable().default(null),
});
export type WorkFace = z.infer<typeof WorkFace>;

export const Activity = z.object({
  id: z.string(),
  wbs: z.string(),
  name: z.string(),
  work_face_id: z.string(),
  structure_id: z.string(),

  /** Key into data/trade_windows.json. NULL = no published thermal window. */
  trade_id: z.string().nullable().default(null),
  thermal_sensitive: z.boolean(),
  discipline: Discipline,

  planned_start: Iso8601,
  planned_finish: Iso8601,
  duration_h: z.number().positive(),
  duration_d: z.number().positive(),
  calendar_id: z.string().default("CAL-6x10"),

  crew_size: z.number().int().min(1),
  quantity: z.number().nullable().default(null),
  quantity_unit: z.string().nullable().default(null),

  early_start: Iso8601.nullable().default(null),
  early_finish: Iso8601.nullable().default(null),
  late_start: Iso8601.nullable().default(null),
  late_finish: Iso8601.nullable().default(null),
  total_float_d: z.number(),
  free_float_d: z.number().default(0),
  is_critical: z.boolean().default(false),
  is_near_critical: z.boolean().default(false),

  /** The policy gate NEVER lets the agent move past this. */
  milestone_date: Iso8601.nullable().default(null),
  milestone_name: z.string().nullable().default(null),
  /** Inspection hold. Blocks auto-move; escalate. */
  hold_point: z.string().nullable().default(null),
  /** Installation Work Package (AWP vocabulary). */
  iwp_id: z.string().nullable().default(null),
});
export type Activity = z.infer<typeof Activity>;

export const Precedence = z
  .object({
    activity_id: z.string(),
    pred_id: z.string(),
    link_type: LinkType.default("FS"),
    lag_h: z.number().default(0),
  })
  .refine((v) => v.activity_id !== v.pred_id, {
    message: "an activity cannot precede itself",
  });
export type Precedence = z.infer<typeof Precedence>;

export const WorkingCalendar = z.object({
  id: z.string(),
  name: z.string(),
  /** ISO weekday numbers, 1=Mon .. 7=Sun. */
  workdays: z.array(z.number().int().min(1).max(7)),
  shift_start_h: z.number().min(0).lt(24),
  shift_end_h: z.number().positive().max(24),
  hours_per_day: z.number().positive(),
  holidays: z.array(z.string()).default([]),
});
export type WorkingCalendar = z.infer<typeof WorkingCalendar>;

export const ProjectSchedule = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  project_id: z.string(),
  project_name: z.string(),
  /** P6 data date — the "as of" for the CPM run. */
  data_date: Iso8601,
  tz: z.string().default("America/Phoenix"),
  utc_offset_hours: z.number().default(-7),
  site_geojson_ref: z.string().default("data/project_demo/site.geojson"),
  work_faces_geojson_ref: z.string().default("data/project_demo/work_faces.geojson"),
  provenance: z.string(),
  calendars: z.array(WorkingCalendar),
  work_faces: z.array(WorkFace),
  activities: z.array(Activity),
  precedences: z.array(Precedence),
});
export type ProjectSchedule = z.infer<typeof ProjectSchedule>;
