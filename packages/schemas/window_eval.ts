/**
 * WORKFACE — the `window_eval` contract (Zod mirror of window_eval.py).
 *
 * Handoff #5 in WORKFACE_SCHEDULE.md: T3 -> T1, the ribbon contract.
 * Keep this field-for-field identical to packages/schemas/window_eval.py.
 * Any change is a PR that tags T1 and T2. Never rename a field silently.
 *
 * ---------------------------------------------------------------------------
 * WORKFACE NAMING RULE — do not violate.
 *   activityId    / activity_id     = a scheduled construction task
 *   fgActivityId  / fg_activity_id  = a FortyGuard async job handle
 * These are different things. They will collide if you blur them.
 * ---------------------------------------------------------------------------
 *
 * Wire format is snake_case (it comes straight out of Postgres/Pydantic).
 * These schemas parse the wire format as-is — do not camelCase on the way in.
 */

import { z } from "zod";

export const SCHEMA_VERSION = "1.0.0";

/* -------------------------------------------------------------------------- */
/* Enums                                                                      */
/* -------------------------------------------------------------------------- */

/** Per-hour ribbon cell. This is the green/amber/red. */
export const HourState = z.enum(["open", "marginal", "closed", "no_data"]);
export type HourState = z.infer<typeof HourState>;

/** Activity-level roll-up, evaluated against the scheduled bar. */
export const Verdict = z.enum([
  "compliant",
  "at_risk",
  "non_compliant",
  "insufficient_window",
  "no_data",
]);
export type Verdict = z.infer<typeof Verdict>;

/** Degrades when the thermal twin is missing inputs. Show it in the UI. */
export const Confidence = z.enum(["high", "medium", "low"]);
export type Confidence = z.infer<typeof Confidence>;

/** The seven shapes. WORKFACE_PROJECT_PLAN.md section 1.3. */
export const ConstraintType = z.enum([
  "band",
  "offset",
  "continuity",
  "cure_clock",
  "composite_rate",
  "decay_clock",
  "human",
]);
export type ConstraintType = z.infer<typeof ConstraintType>;

export const GoverningTemp = z.enum(["air", "surface", "base_material", "concrete"]);
export type GoverningTemp = z.infer<typeof GoverningTemp>;

export const MarginUnit = z.enum(["C", "pct", "lb_ft2_hr", "min", "h", "ratio"]);
export type MarginUnit = z.infer<typeof MarginUnit>;

export const Tier = z.enum(["plan", "commit", "record"]);
export type Tier = z.infer<typeof Tier>;

/** ISO-8601 with offset, site-local (America/Phoenix, UTC-07:00, no DST). */
const Iso8601 = z.string().datetime({ offset: true });

/* -------------------------------------------------------------------------- */
/* Leaf models                                                                */
/* -------------------------------------------------------------------------- */

export const Horizon = z.object({
  start: Iso8601,
  end: Iso8601,
  step_minutes: z.number().int().min(5).max(180).default(60),
  tz: z.string().default("America/Phoenix"),
  /** plan = 7-year climatological prior (a probability, NOT a forecast). */
  tier: Tier.default("commit"),
});
export type Horizon = z.infer<typeof Horizon>;

export const ScheduledBar = z.object({
  start: Iso8601,
  finish: Iso8601,
  duration_h: z.number().positive(),
  /** CPM total float, working days. 0 = critical. */
  total_float_d: z.number(),
  is_critical: z.boolean().default(false),
  is_near_critical: z.boolean().default(false),
  milestone_date: Iso8601.nullable().default(null),
  hold_point: z.string().nullable().default(null),
  crew_size: z.number().int().nullable().default(null),
});
export type ScheduledBar = z.infer<typeof ScheduledBar>;

export const SeriesPoint = z.object({
  t_air_c: z.number().nullable().default(null),
  /** From the Work Face Thermal Twin, NOT from FortyGuard. */
  t_surf_c: z.number().nullable().default(null),
  t_dew_c: z.number().nullable().default(null),
  t_base_material_c: z.number().nullable().default(null),
  rh_pct: z.number().min(0).max(100).nullable().default(null),
  wbgt_c: z.number().nullable().default(null),
  /** Site-level scalar from an external feed. Not spatially resolved. */
  wind_ms: z.number().nullable().default(null),
  ghi_w_m2: z.number().nullable().default(null),
  cloud_octas: z.number().min(0).max(8).nullable().default(null),
  evap_rate_lb_ft2_hr: z.number().nullable().default(null),
});
export type SeriesPoint = z.infer<typeof SeriesPoint>;

export const HourCell = z.object({
  ts: Iso8601,
  state: HourState,
  binding_constraint_id: z.string().nullable().default(null),
  /** Signed distance to the nearest bound. Negative = violated. */
  margin: z.number().nullable().default(null),
  margin_unit: MarginUnit.nullable().default(null),
  /** One sentence, plain English. Hover text. */
  reason: z.string().max(240).nullable().default(null),
  /** WBGT work/rest haircut. 0.75 = 25% rest ratio. */
  productive_fraction: z.number().min(0).max(1).default(1),
  values: SeriesPoint.default({}),
});
export type HourCell = z.infer<typeof HourCell>;

export const OpenInterval = z
  .object({
    start: Iso8601,
    end: Iso8601,
    duration_h: z.number().positive(),
    /** duration_h after the WBGT haircut. This is what the sequencer packs against. */
    productive_h: z.number().min(0),
    includes_marginal: z.boolean().default(false),
    min_margin: z.number().nullable().default(null),
    confidence: Confidence.default("medium"),
  })
  .refine((v) => v.productive_h <= v.duration_h + 1e-6, {
    message: "productive_h cannot exceed duration_h",
    path: ["productive_h"],
  });
export type OpenInterval = z.infer<typeof OpenInterval>;

export const ConstraintResult = z.object({
  constraint_id: z.string(),
  type: ConstraintType,
  label: z.string(),
  governing_temp: GoverningTemp,
  satisfied_hours: z.number().int().min(0),
  closed_hours: z.number().int().min(0),
  first_open: Iso8601.nullable().default(null),
  last_open: Iso8601.nullable().default(null),
  worst_margin: z.number().nullable().default(null),
  margin_unit: MarginUnit.nullable().default(null),
  /** The specific clause text this constraint encodes. Quoted inline in the drawer. */
  citation_fragment: z.string(),
});
export type ConstraintResult = z.infer<typeof ConstraintResult>;

/** The single field that makes the UI feel intelligent: *what is stopping me*. */
export const BindingConstraint = z.object({
  constraint_id: z.string(),
  type: ConstraintType,
  label: z.string(),
  hours_lost: z.number().min(0),
  would_extend_window_by_h: z.number().min(0),
  mitigation_hint: z.string().nullable().default(null),
});
export type BindingConstraint = z.infer<typeof BindingConstraint>;

export const Margin = z.object({
  value: z.number(),
  unit: MarginUnit,
  at: Iso8601.nullable().default(null),
});
export type Margin = z.infer<typeof Margin>;

export const UsdExposure = z.object({
  at_risk_usd: z.number().min(0).default(0),
  protected_usd: z.number().min(0).default(0),
  basis: z.string(),
});
export type UsdExposure = z.infer<typeof UsdExposure>;

export const Provenance = z.object({
  /** FortyGuard async job handles. NOT activity_id. See the naming rule. */
  fg_activity_ids: z.array(z.string()).default([]),
  series_digest: z.string().nullable().default(null),
  registry_version: z.string().nullable().default(null),
  twin_confidence: Confidence.default("medium"),
  /** True when served from data/fixtures/. REPLAY_MODE default is true. */
  replay: z.boolean().default(true),
});
export type Provenance = z.infer<typeof Provenance>;

/* -------------------------------------------------------------------------- */
/* The contract                                                               */
/* -------------------------------------------------------------------------- */

export const WindowEval = z
  .object({
    schema_version: z.string().default(SCHEMA_VERSION),
    run_id: z.string(),
    generated_at: Iso8601,

    /* identity */
    /** SCHEDULE activity. Never a FortyGuard handle. */
    activity_id: z.string(),
    activity_name: z.string(),
    wbs: z.string().nullable().default(null),
    trade_id: z.string(),
    trade_display_name: z.string(),
    work_face_id: z.string(),
    work_face_name: z.string(),

    /* evaluation */
    horizon: Horizon,
    scheduled: ScheduledBar,
    /** Dense and ordered. One entry per horizon step. */
    hours: z.array(HourCell).min(1),
    open_intervals: z.array(OpenInterval).default([]),
    constraints: z.array(ConstraintResult).default([]),
    binding_constraint: BindingConstraint.nullable().default(null),
    margin: Margin.nullable().default(null),

    /* the answer */
    verdict: Verdict,
    verdict_summary: z.string().max(400),
    citation: z.string().min(20),
    standard_ref: z.string(),
    usd_exposure: UsdExposure,
    confidence: Confidence,
    confidence_reasons: z.array(z.string()).default([]),
    /** Never remove. Renders as a footer in the drawer and on the certificate. */
    advisory_notice: z
      .string()
      .default(
        "Advisory and contractual. Does not replace the field measurement the referenced standard requires.",
      ),
    provenance: Provenance.default({}),
  })
  .superRefine((v, ctx) => {
    for (let i = 1; i < v.hours.length; i++) {
      if (v.hours[i].ts <= v.hours[i - 1].ts) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `hours must be strictly increasing at index ${i}`,
          path: ["hours", i, "ts"],
        });
        break;
      }
    }
    if (v.binding_constraint && v.constraints.length > 0) {
      const ids = new Set(v.constraints.map((c) => c.constraint_id));
      if (!ids.has(v.binding_constraint.constraint_id)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `binding_constraint "${v.binding_constraint.constraint_id}" is not in constraints[]`,
          path: ["binding_constraint", "constraint_id"],
        });
      }
    }
  });
export type WindowEval = z.infer<typeof WindowEval>;

/** What the ribbon actually fetches: every lane for one run. */
export const WindowEvalBundle = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  run_id: z.string(),
  generated_at: Iso8601,
  horizon: Horizon,
  site_id: z.string(),
  evaluations: z.array(WindowEval),
  /** Hours where more activities want the window than crews/space allow. */
  contended_hours: z.array(Iso8601).default([]),
  totals: UsdExposure.nullable().default(null),
});
export type WindowEvalBundle = z.infer<typeof WindowEvalBundle>;

/* -------------------------------------------------------------------------- */
/* UI helpers — T1, feel free to move these into the web app.                  */
/* -------------------------------------------------------------------------- */

export const HOUR_STATE_ORDER: readonly HourState[] = ["open", "marginal", "closed", "no_data"];

export const VERDICT_LABEL: Record<Verdict, string> = {
  compliant: "In window",
  at_risk: "At risk",
  non_compliant: "Outside window",
  insufficient_window: "No window long enough",
  no_data: "No data",
};

export const CONSTRAINT_TYPE_LABEL: Record<ConstraintType, string> = {
  band: "Temperature band",
  offset: "Dew-point offset",
  continuity: "Continuous run",
  cure_clock: "Cure clock",
  composite_rate: "Evaporation rate",
  decay_clock: "Compaction window",
  human: "Heat stress",
};
