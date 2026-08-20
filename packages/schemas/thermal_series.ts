/**
 * WORKFACE — the `thermal_series` contract (Zod mirror of thermal_series.py).
 *
 * Handoff #2 in WORKFACE_SCHEDULE.md: T2 -> T3. The hourly thermal record T2
 * assembles per work face (FortyGuard heatmap `tcm` + `env_params` for the SAME
 * date_time + external wind) and hands to T3's window engine and surface twin.
 *
 * Keep this field-for-field identical to packages/schemas/thermal_series.py.
 * Any change is a PR that tags T2 and T3. Never rename a field silently.
 *
 * ---------------------------------------------------------------------------
 * WORKFACE NAMING RULE — do not violate.
 *   activityId    / activity_id     = a scheduled construction task
 *   fgActivityId  / fg_activity_id  = a FortyGuard async job handle
 * These are different things. They will collide if you blur them.
 * ---------------------------------------------------------------------------
 *
 * Wire format is snake_case (straight out of Postgres/Pydantic). Parse as-is.
 */

import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0";

/* -------------------------------------------------------------------------- */
/* Enums                                                                      */
/* -------------------------------------------------------------------------- */

/** Which temporal loop produced this series. */
export const Tier = z.enum(["plan", "commit", "record"]);
export type Tier = z.infer<typeof Tier>;

/** Where each point came from. Drives the REPLAY/LIVE badge and confidence. */
export const SeriesSource = z.enum([
  "fortyguard_live",
  "fortyguard_historical",
  "fixture",
  "synthetic",
]);
export type SeriesSource = z.infer<typeof SeriesSource>;

/** Matches window_eval.Confidence so it can flow straight through. */
export const Confidence = z.enum(["high", "medium", "low"]);
export type Confidence = z.infer<typeof Confidence>;

/** ISO-8601 with offset, site-local (America/Phoenix, UTC-07:00, no DST). */
const Iso8601 = z.string().datetime({ offset: true });

/* -------------------------------------------------------------------------- */
/* Leaf models                                                                */
/* -------------------------------------------------------------------------- */

/** `env_params.solar_irradiance` — clear-sky components, W/m^2. */
export const SolarIrradiance = z.object({
  ghi_w_m2: z.number().nullable().default(null),
  dni_w_m2: z.number().nullable().default(null),
  dhi_w_m2: z.number().nullable().default(null),
});
export type SolarIrradiance = z.infer<typeof SolarIrradiance>;

/** `env_params` air-quality (US AQI) and gases. null means unavailable — never zero. */
export const AirQuality = z.object({
  aqi_overall: z.number().nullable().default(null),
  aqi_pm2p5: z.number().nullable().default(null),
  aqi_pm10: z.number().nullable().default(null),
  aqi_no2: z.number().nullable().default(null),
  aqi_co: z.number().nullable().default(null),
  aqi_o3: z.number().nullable().default(null),
  aqi_so2: z.number().nullable().default(null),
  methane_ppb: z.number().nullable().default(null),
  co2_ppm: z.number().nullable().default(null),
});
export type AirQuality = z.infer<typeof AirQuality>;

/** One hour at one work face. Dense: one entry per horizon step, ordered. */
export const ThermalPoint = z.object({
  ts: Iso8601,

  /* FortyGuard heatmap (tcm) */
  /** 2 m air temperature at the work-face centroid tile. The only temp FortyGuard sells. */
  t_air_c: z.number().nullable().default(null),

  /* FortyGuard env_params (SAME date_time as the heatmap) */
  rh_pct: z.number().min(0).max(100).nullable().default(null),
  wet_bulb_c: z.number().nullable().default(null),
  apparent_temp_c: z.number().nullable().default(null),
  heat_index_c: z.number().nullable().default(null),
  precipitation_mm: z.number().min(0).nullable().default(null),
  cloud_octas: z.number().min(0).max(8).nullable().default(null),
  elevation_m: z.number().nullable().default(null),
  solar: SolarIrradiance.default({}),
  air_quality: AirQuality.default({}),

  /* external feed (the field FortyGuard lacks) */
  /** Site-level scalar from Open-Meteo / NWS. NOT spatially resolved — say so. */
  wind_ms: z.number().min(0).nullable().default(null),
  wind_dir_deg: z.number().min(0).max(359.999).nullable().default(null),

  /* DERIVED — T3 fills these downstream; null on this handoff */
  /** Surface twin output. NOT FortyGuard. Left null by T2. */
  t_surf_c: z.number().nullable().default(null),
  /** Magnus-Tetens from t_air_c + rh_pct. Left null by T2. */
  t_dew_c: z.number().nullable().default(null),
  /** Liljegren (2008). Left null by T2. */
  wbgt_c: z.number().nullable().default(null),
});
export type ThermalPoint = z.infer<typeof ThermalPoint>;

/** The full hourly series for one work face, one tier. T3 consumes this directly. */
export const WorkFaceThermalSeries = z
  .object({
    work_face_id: z.string(),
    tile_cluster_id: z.string().nullable().default(null),
    centroid_lon: z.number(),
    centroid_lat: z.number(),

    tier: Tier.default("commit"),
    step_minutes: z.number().int().min(5).max(180).default(60),
    /** The FortyGuard filter_type that produced t_air_c. 2 for the 12 h commit pass. */
    heatmap_filter_type: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]).default(2),
    heatmap_granularity_m: z.union([z.literal(60), z.literal(80), z.literal(100)]).default(60),

    /** Dense, strictly time-ordered. */
    points: z.array(ThermalPoint).min(1),

    source: SeriesSource.default("fixture"),
    confidence: Confidence.default("medium"),
    /** FortyGuard heatmap + env_params job handles. NOT activity_id. */
    fg_activity_ids: z.array(z.string()).default([]),
  })
  .superRefine((v, ctx) => {
    for (let i = 1; i < v.points.length; i++) {
      if (v.points[i].ts <= v.points[i - 1].ts) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `points must be strictly increasing at index ${i}`,
          path: ["points", i, "ts"],
        });
        break;
      }
    }
  });
export type WorkFaceThermalSeries = z.infer<typeof WorkFaceThermalSeries>;

/** Every work-face series from one worker run. The unit T2 writes / T3 reads. */
export const ThermalSeriesBundle = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  run_id: z.string(),
  generated_at: Iso8601,
  site_id: z.string(),
  tz: z.string().default("America/Phoenix"),
  tier: Tier.default("commit"),
  series: z.array(WorkFaceThermalSeries),
  /** True when served from fixtures. REPLAY_MODE default is true. */
  replay: z.boolean().default(true),
});
export type ThermalSeriesBundle = z.infer<typeof ThermalSeriesBundle>;
