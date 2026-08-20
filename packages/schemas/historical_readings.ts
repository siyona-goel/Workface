/**
 * WORKFACE — the `historical_readings` contract (Zod mirror of historical_readings.py).
 *
 * Handoff #3 in WORKFACE_SCHEDULE.md: T2 -> T3. The raw 7-year historical
 * heatmap sweep (one August window per year, 2019->2025, exceedance +
 * persistence, BOTH directions, cached forever) that T3 aggregates into
 * per-tile/per-trade/per-hour window priors (the Tier-0 "Plan" loop).
 *
 * Keep this field-for-field identical to packages/schemas/historical_readings.py.
 * Any change is a PR that tags T2 and T3. Never rename a field silently.
 *
 * ---------------------------------------------------------------------------
 * WORKFACE NAMING RULE — do not violate.
 *   activityId / activity_id    = a scheduled construction task
 *   fgActivityId / fg_activity_id = a FortyGuard async job handle
 * ---------------------------------------------------------------------------
 *
 * Wire format is snake_case. Parse as-is.
 */

import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0";

/* -------------------------------------------------------------------------- */
/* Enums — mirror the FortyGuard heatmap parameters exactly                   */
/* -------------------------------------------------------------------------- */

/** FortyGuard heatmap.analytic_type. Units differ — see `units`. */
export const AnalyticType = z.enum(["tcm", "time_of_measure", "exceedance", "persistence"]);
export type AnalyticType = z.infer<typeof AnalyticType>;

/** heatmap.direction. 'below' is the two-sided parameter almost nobody uses. */
export const Direction = z.enum(["above", "below"]);
export type Direction = z.infer<typeof Direction>;

export const ReadingUnit = z.enum(["C", "hour"]);
export type ReadingUnit = z.infer<typeof ReadingUnit>;

/* -------------------------------------------------------------------------- */
/* Leaf models                                                                */
/* -------------------------------------------------------------------------- */

/** One tile's value for one analytic in one historical window. */
export const TileReading = z.object({
  tile_id: z.string(),
  centroid_lon: z.number(),
  centroid_lat: z.number(),
  /** °C for tcm; hours for exceedance/persistence; hour-of-day 0-23 for time_of_measure. */
  value: z.number().nullable().default(null),
  /** OPTIONAL per-hour temperatures across the window. Length = window hours. */
  hourly_tcm_c: z.array(z.number().nullable()).nullable().default(null),
});
export type TileReading = z.infer<typeof TileReading>;

/** stats_data.Temperature_stats roll-up. Convenience, not the source of truth. */
export const TemperatureStats = z.object({
  minimum: z.number().nullable().default(null),
  maximum: z.number().nullable().default(null),
  mean: z.number().nullable().default(null),
  standard_deviation: z.number().nullable().default(null),
});
export type TemperatureStats = z.infer<typeof TemperatureStats>;

/** One FortyGuard heatmap call: one year, one analytic, one threshold+direction. */
export const SweepWindow = z
  .object({
    year: z.number().int().min(2019),
    /** YYYY-MM-DD. The August window's first day. */
    start_date: z.string(),
    /** YYYY-MM-DD. <= 1 month after start_date (filter_type 4 cap). */
    end_date: z.string(),
    filter_type: z.literal(4).default(4),
    granularity_m: z.union([z.literal(60), z.literal(80), z.literal(100)]).default(100),

    analytic_type: AnalyticType,
    /** Only for exceedance / persistence. Ignored by tcm and time_of_measure. */
    threshold_c: z.number().nullable().default(null),
    /** Only for exceedance / persistence. Run the sweep BOTH ways. */
    direction: Direction.nullable().default(null),
    units: ReadingUnit,

    tiles: z.array(TileReading),
    stats: TemperatureStats.nullable().default(null),

    /** The FortyGuard job handle for THIS call. Provenance + re-derivation. */
    fg_activity_id: z.string(),
  })
  .superRefine((v, ctx) => {
    const needsThreshold = v.analytic_type === "exceedance" || v.analytic_type === "persistence";
    if (needsThreshold && (v.threshold_c === null || v.direction === null)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `${v.analytic_type} requires both threshold_c and direction`,
        path: ["threshold_c"],
      });
    }
    if (!needsThreshold && (v.threshold_c !== null || v.direction !== null)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `${v.analytic_type} ignores threshold_c/direction; leave them null`,
        path: ["threshold_c"],
      });
    }
  });
export type SweepWindow = z.infer<typeof SweepWindow>;

/** All historical windows for one AOI / tile-cluster. What T2 dumps to disk per cluster. */
export const TileSweep = z.object({
  tile_cluster_id: z.string(),
  /** GeoJSON Polygon of the AOI this sweep covers. */
  aoi_geojson: z.record(z.string(), z.unknown()),
  /** The climatology month. 8 = the August demo window. */
  month: z.number().int().min(1).max(12).default(8),
  years: z.array(z.number().int()),
  /** Distinct thresholds T3 asked T2 to sweep, from the registry t_min/t_max. */
  requested_thresholds_c: z.array(z.number()).default([]),
  windows: z.array(SweepWindow),
});
export type TileSweep = z.infer<typeof TileSweep>;

/** The whole 7-year sweep for the site. Tier-0 input; cached forever. */
export const HistoricalSweepBundle = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  run_id: z.string(),
  /** ISO-8601 with offset. When the sweep was fetched. */
  generated_at: z.string().datetime({ offset: true }),
  site_id: z.string(),
  tz: z.string().default("America/Phoenix"),
  tier: z.literal("plan").default("plan"),
  sweeps: z.array(TileSweep),
  /** A 2019-2025 August climatology never changes. TTL = infinity. */
  cached_forever: z.boolean().default(true),
  replay: z.boolean().default(true),
});
export type HistoricalSweepBundle = z.infer<typeof HistoricalSweepBundle>;
