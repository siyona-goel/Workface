/**
 * WORKFACE — the `trade_window` registry contract (Zod mirror of trade_window.py).
 *
 * Typed model of every row in data/trade_windows.json. T1's detail drawer renders
 * `citation_fragment` inline; the seven constraint shapes are a discriminated union
 * on `constraints[].type`. Keep this field-for-field identical to trade_window.py.
 * Any change is a PR that tags T1 and T2. Never rename a field silently.
 *
 * ---------------------------------------------------------------------------
 * WORKFACE NAMING RULE — do not violate.
 *   activityId    / activity_id     = a scheduled construction task
 *   fgActivityId  / fg_activity_id  = a FortyGuard async job handle
 * ---------------------------------------------------------------------------
 *
 * Wire format is snake_case (it comes straight out of the JSON registry).
 */

import { z } from "zod";
import { ConstraintType, GoverningTemp } from "./window_eval";

export const SCHEMA_VERSION = "1.0.0";

export const VerifyStatus = z.enum(["primary", "secondary", "partial"]);
export type VerifyStatus = z.infer<typeof VerifyStatus>;

/* -------------------------------------------------------------------------- */
/* Small typed nested models the physics actually reads (TASK 4 / TASK 5).    */
/* -------------------------------------------------------------------------- */

export const Q10Segment = z
  .object({ t_lo_c: z.number(), t_hi_c: z.number(), q10: z.number() })
  .strict();
export type Q10Segment = z.infer<typeof Q10Segment>;

export const CalibrationPoint = z
  .object({ t_c: z.number(), t_f: z.number().nullish(), hours: z.number() })
  .strict();
export type CalibrationPoint = z.infer<typeof CalibrationPoint>;

export const RecoatPoint = z.object({ t_c: z.number(), hours: z.number() }).strict();
export type RecoatPoint = z.infer<typeof RecoatPoint>;

export const WbgtBand = z
  .object({
    wbgt_c_lo: z.number(),
    wbgt_c_hi: z.number(),
    work_fraction: z.number(),
    label: z.string().nullish(),
  })
  .strict();
export type WbgtBand = z.infer<typeof WbgtBand>;

/* -------------------------------------------------------------------------- */
/* The seven constraint variants. `type` is the discriminator.                */
/* -------------------------------------------------------------------------- */

const base = {
  constraint_id: z.string(),
  label: z.string(),
  citation_fragment: z.string().min(1),
};

export const BandSpec = z
  .object({
    ...base,
    type: z.literal("band"),
    on: z.string().nullish(),
    t_min_c: z.number().nullish(),
    t_max_c: z.number().nullish(),
    t_min_f: z.number().nullish(),
    t_max_f: z.number().nullish(),
    marginal_delta_c: z.number().nullish(),
    rh_max_pct: z.number().nullish(),
    marginal_delta_pct: z.number().nullish(),
    rising_required: z.boolean().nullish(),
    hard_floor_c: z.number().nullish(),
    hard_floor_f: z.number().nullish(),
    trigger_only: z.boolean().nullish(),
    mitigation_not_stop: z.boolean().nullish(),
    thickness_dependent: z.boolean().nullish(),
    lookup: z.array(z.record(z.string(), z.any())).nullish(),
    air_changes_per_hour_min: z.number().nullish(),
    advisory_only: z.boolean().nullish(),
    direction_note: z.string().nullish(),
  })
  .strict();
export type BandSpec = z.infer<typeof BandSpec>;

export const OffsetSpec = z
  .object({
    ...base,
    type: z.literal("offset"),
    on: z.string().nullish(),
    above: z.string().nullish(),
    delta_c: z.number(),
    delta_f: z.number().nullish(),
    marginal_delta_c: z.number().nullish(),
    requires_dry: z.boolean().nullish(),
  })
  .strict();
export type OffsetSpec = z.infer<typeof OffsetSpec>;

export const ContinuitySpec = z
  .object({
    ...base,
    type: z.literal("continuity"),
    on: z.string().nullish(),
    also_on: z.string().nullish(),
    t_min_c: z.number().nullish(),
    t_min_f: z.number().nullish(),
    run_hours: z.number(),
    grouted_run_hours: z.number().nullish(),
    lead_hours: z.number().nullish(),
    starts_at: z.string().nullish(),
    marginal_delta_c: z.number().nullish(),
  })
  .strict();
export type ContinuitySpec = z.infer<typeof ContinuitySpec>;

export const CureClockSpec = z
  .object({
    ...base,
    type: z.literal("cure_clock"),
    on: z.string().nullish(),
    milestone: z.string().nullish(),
    ref_c: z.number(),
    hours_at_ref: z.number(),
    model: z.string().nullish(),
    q10_segments: z.array(Q10Segment).default([]),
    calibration_points: z.array(CalibrationPoint).default([]),
    recoat_min_hours: z.array(RecoatPoint).default([]),
    recoat_max_hours: z.number().nullish(),
  })
  .strict();
export type CureClockSpec = z.infer<typeof CureClockSpec>;

export const CompositeRateSpec = z
  .object({
    ...base,
    type: z.literal("composite_rate"),
    formula: z.string(),
    expression: z.string().nullish(),
    units: z.record(z.string(), z.string()).nullish(),
    limit_lb_ft2_hr: z.number().nullish(),
    marginal_lb_ft2_hr: z.number().nullish(),
    low_bleed_limit_lb_ft2_hr: z.number().nullish(),
  })
  .strict();
export type CompositeRateSpec = z.infer<typeof CompositeRateSpec>;

export const DecayClockSpec = z
  .object({
    ...base,
    type: z.literal("decay_clock"),
    on: z.string().nullish(),
    quantity: z.string().nullish(),
    lookup: z.array(z.record(z.string(), z.any())).default([]),
    requires: z.string().nullish(),
    interpolation: z.string().nullish(),
    wet_hole_cure_multiplier: z.number().nullish(),
  })
  .strict();
export type DecayClockSpec = z.infer<typeof DecayClockSpec>;

export const HumanSpec = z
  .object({
    ...base,
    type: z.literal("human"),
    metric: z.string().nullish(),
    threshold: z.number().nullish(),
    mandatory_break_minutes: z.number().nullish(),
    mandatory_break_interval_h: z.number().nullish(),
    implied_rest_ratio: z.number().nullish(),
    model: z.string().nullish(),
    wbgt_formula_outdoor: z.string().nullish(),
    wbgt_method: z.string().nullish(),
    productive_fraction_by_band: z.array(WbgtBand).default([]),
  })
  .strict();
export type HumanSpec = z.infer<typeof HumanSpec>;

export const ConstraintSpec = z.discriminatedUnion("type", [
  BandSpec,
  OffsetSpec,
  ContinuitySpec,
  CureClockSpec,
  CompositeRateSpec,
  DecayClockSpec,
  HumanSpec,
]);
export type ConstraintSpec = z.infer<typeof ConstraintSpec>;

/* -------------------------------------------------------------------------- */
/* The trade row and the registry file.                                       */
/* -------------------------------------------------------------------------- */

export const TradeWindow = z
  .object({
    trade_id: z.string(),
    display_name: z.string(),
    discipline: z.string(),
    constraint_types: z.array(ConstraintType),
    governing_temp: GoverningTemp,
    constraints: z.array(ConstraintSpec),

    mitigations: z.array(z.string()).default([]),
    wind_sensitive: z.boolean().default(false),
    duration_h_typical: z.number().nullish(),
    crew_size_typical: z.number().int().nullish(),
    unit_cost_usd: z.number().nullish(),
    unit: z.string().nullish(),
    typical_quantity: z.number().nullish(),
    rework_multiplier: z.number().nullish(),
    warranty_conditioned: z.boolean().default(false),
    applies_to_all_trades: z.boolean().default(false),

    // provenance — the definition of done for a registry row
    citation: z.string().min(21),
    standard_ref: z.string().min(1),
    source_url: z.string().min(1),
    source_secondary_urls: z.array(z.string()).default([]),
    source_date: z.string().nullish(),
    verify_status: VerifyStatus,
    verify_note: z.string().nullish(),
  })
  .strict();
export type TradeWindow = z.infer<typeof TradeWindow>;

/** The whole data/trade_windows.json file. Tolerates metadata keys (legends, notes). */
export const TradeWindowRegistry = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  registry_version: z.string(),
  trades: z.array(TradeWindow),
});
export type TradeWindowRegistry = z.infer<typeof TradeWindowRegistry>;
