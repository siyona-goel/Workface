import heatmapJson from "@/data/heatmap.json";
import siteJson from "@/data/site.json";

export type HeatmapProperties = {
  tile_id: number;
  average_temperature: number;
  min_temperature: number;
  max_temperature: number;
};

export type SiteProperties = {
  name: string;
  note: string;
};

type PolygonGeometry = {
  type: "Polygon";
  coordinates: number[][][];
};

type Feature<P> = {
  type: "Feature";
  id?: string;
  properties: P;
  geometry: PolygonGeometry;
};

export type FeatureCollection<P> = {
  type: "FeatureCollection";
  features: Feature<P>[];
};

export const heatmapGeojson = heatmapJson as FeatureCollection<HeatmapProperties>;
export const siteGeojson = siteJson as FeatureCollection<SiteProperties>;

const temps = heatmapGeojson.features.map((f) => f.properties.average_temperature);

export const TEMP_MIN = Math.min(...temps);
export const TEMP_MAX = Math.max(...temps);
export const TILE_COUNT = heatmapGeojson.features.length;

/** T2 Day-1 sample AOI centroid (NYC docs polygon). */
export const SITE_VIEW = {
  longitude: -74.01,
  latitude: 40.7115,
  zoom: 13.6,
} as const;

export const HEATMAP_FIXTURE =
  "data/fixtures/heatmap_result_20260821_152159.json";

/** Blue → yellow → red, mapped across the fixture temperature range. */
export function temperatureFill(
  t: number,
): [number, number, number, number] {
  const span = TEMP_MAX - TEMP_MIN;
  const x = span === 0 ? 0.5 : (t - TEMP_MIN) / span;
  const clamped = Math.min(1, Math.max(0, x));
  const [r, g, b] = lerpStops(clamped, [
    [37, 99, 235],
    [34, 211, 238],
    [250, 204, 21],
    [239, 68, 68],
  ]);
  return [r, g, b, 160];
}

function lerpStops(
  t: number,
  stops: [number, number, number][],
): [number, number, number] {
  const scaled = t * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(scaled));
  const f = scaled - i;
  const a = stops[i];
  const b = stops[i + 1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

export function formatC(t: number) {
  return `${t.toFixed(2)} °C`;
}
