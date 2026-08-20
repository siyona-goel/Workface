/**
 * WORKFACE — the `twin_segmentation` contract (Zod mirror of twin_segmentation.py).
 *
 * Handoff #4 in WORKFACE_SCHEDULE.md: T2 -> T3. The raw FortyGuard `satellite`
 * + `streetview` segmentation T2 captures per work face, from which T3 derives
 * the Work Face Thermal Twin (alpha, psi, T_surf). Captured once, cached forever.
 *
 * Keep this field-for-field identical to packages/schemas/twin_segmentation.py.
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

/** Same ladder as window_eval / thermal_series. */
export const Confidence = z.enum(["high", "medium", "low"]);
export type Confidence = z.infer<typeof Confidence>;

/* -------------------------------------------------------------------------- */
/* Leaf models                                                                */
/* -------------------------------------------------------------------------- */

/**
 * One image, stored as a repo path and/or raw Base64. At least one required.
 * FortyGuard returns raw Base64 (no data: prefix); prepend
 * 'data:image/png;base64,' to render. Prefer `ref` in committed fixtures.
 */
export const ImageRef = z
  .object({
    ref: z.string().nullable().default(null),
    base64: z.string().nullable().default(null),
    media_type: z.string().default("image/png"),
  })
  .refine((v) => Boolean(v.ref) || Boolean(v.base64), {
    message: "ImageRef needs at least one of `ref` or `base64`",
    path: ["ref"],
  });
export type ImageRef = z.infer<typeof ImageRef>;

/** FortyGuard returns lat/lon as STRINGS. T2 parses to float on ingest. */
export const Coordinates = z.object({
  latitude: z.number(),
  longitude: z.number(),
});
export type Coordinates = z.infer<typeof Coordinates>;

export const ImageDimensions = z.object({
  height: z.number().int().positive(),
  width: z.number().int().positive(),
});
export type ImageDimensions = z.infer<typeof ImageDimensions>;

/** The shared shape both endpoints return: class coverage + legend + mask. */
export const Segmentation = z.object({
  /** class -> coverage %, 0-100. */
  segments: z.record(z.string(), z.number()),
  /** class -> [R,G,B], 0-255. For rendering the mask. */
  legend: z.record(z.string(), z.array(z.number().int())).default({}),
  /** satellite: image_content. streetview: segmented_image. The mask. */
  mask_image: ImageRef.nullable().default(null),
  dimensions: ImageDimensions.nullable().default(null),
  processing_time_seconds: z.number().nullable().default(null),
  /** FortyGuard's internal trace id. Not the fg_activity_id. */
  request_id: z.string().nullable().default(null),
});
export type Segmentation = z.infer<typeof Segmentation>;

/** FortyGuard `satellite` result for one work face. Overhead land cover -> alpha. */
export const SatelliteCapture = z.object({
  coordinates: Coordinates,
  image_year: z.number().int().nullable().default(null),
  original_image: ImageRef.nullable().default(null),
  segmentation: Segmentation,
  mode: z.string().default("sat"),
  fg_activity_id: z.string(),
});
export type SatelliteCapture = z.infer<typeof SatelliteCapture>;

/** One camera side (front or back) of a `streetview` capture. Obstruction -> psi. */
export const StreetViewSide = z.object({
  original_image: ImageRef.nullable().default(null),
  segmentation: Segmentation,
  /** YYYY-MM-DD the Street View image was captured. */
  image_date: z.string().nullable().default(null),
});
export type StreetViewSide = z.infer<typeof StreetViewSide>;

/** FortyGuard `streetview` result for one work face, plus the request angles. */
export const StreetViewCapture = z.object({
  coordinates: Coordinates,
  vertical_angle: z.number(),
  horizontal_angle: z.number().min(0).max(360),
  back_view_requested: z.boolean(),
  front: StreetViewSide,
  back: StreetViewSide.nullable().default(null),
  fg_activity_id: z.string(),
});
export type StreetViewCapture = z.infer<typeof StreetViewCapture>;

/** Everything captured for one work face's twin. Cached forever, built once. */
export const WorkFaceTwinCapture = z
  .object({
    work_face_id: z.string(),
    centroid_lon: z.number(),
    centroid_lat: z.number(),
    /** null on a greenfield tile with no coverage -> T3 downgrades confidence. */
    satellite: SatelliteCapture.nullable().default(null),
    /** null when no ground imagery -> T3 sets psi=1.0, confidence=low. */
    streetview: StreetViewCapture.nullable().default(null),
    /** T2's honest read of coverage. T3 refines it after deriving the twin. */
    capture_confidence: Confidence.default("medium"),
    notes: z.string().nullable().default(null),
  })
  .refine((v) => v.satellite !== null || v.streetview !== null, {
    message:
      "a twin capture with neither satellite nor streetview carries no signal; " +
      "omit the face or record the gap in notes with confidence=low",
    path: ["satellite"],
  });
export type WorkFaceTwinCapture = z.infer<typeof WorkFaceTwinCapture>;

/** Every work-face twin capture from one worker run. What T2 writes / T3 reads. */
export const TwinCaptureBundle = z.object({
  schema_version: z.string().default(SCHEMA_VERSION),
  run_id: z.string(),
  /** ISO-8601 with offset. */
  generated_at: z.string().datetime({ offset: true }),
  site_id: z.string(),
  captures: z.array(WorkFaceTwinCapture),
  cached_forever: z.boolean().default(true),
  replay: z.boolean().default(true),
});
export type TwinCaptureBundle = z.infer<typeof TwinCaptureBundle>;
