"use client";

import { GeoJsonLayer } from "@deck.gl/layers";
import { useMemo, useState } from "react";
import Map from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

import { DeckGLOverlay } from "@/components/deck-gl-overlay";
import {
  HEATMAP_FIXTURE,
  SITE_VIEW,
  TEMP_MAX,
  TEMP_MIN,
  TILE_COUNT,
  formatC,
  heatmapGeojson,
  siteGeojson,
  temperatureFill,
  type HeatmapProperties,
} from "@/lib/site-map-data";

type HoverInfo = {
  x: number;
  y: number;
  tileId: number;
  tAvg: number;
  tMin: number;
  tMax: number;
};

export default function SiteMap() {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";
  const [hover, setHover] = useState<HoverInfo | null>(null);

  const layers = useMemo(
    () => [
      new GeoJsonLayer<HeatmapProperties>({
        id: "heatmap-tiles",
        data: heatmapGeojson,
        filled: true,
        stroked: true,
        getFillColor: (f) =>
          temperatureFill(f.properties?.average_temperature ?? TEMP_MIN),
        getLineColor: [255, 255, 255, 50],
        lineWidthMinPixels: 0.5,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 80],
        onHover: (info) => {
          if (!info.object || info.x == null || info.y == null) {
            setHover(null);
            return;
          }
          const p = info.object.properties;
          setHover({
            x: info.x,
            y: info.y,
            tileId: p.tile_id,
            tAvg: p.average_temperature,
            tMin: p.min_temperature,
            tMax: p.max_temperature,
          });
        },
      }),
      new GeoJsonLayer({
        id: "site-polygon",
        data: siteGeojson,
        filled: false,
        stroked: true,
        getLineColor: [255, 255, 255, 230],
        getLineWidth: 3,
        lineWidthMinPixels: 2,
        pickable: false,
      }),
    ],
    [],
  );

  if (!token) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-muted-foreground">
        Missing <code className="font-mono">NEXT_PUBLIC_MAPBOX_TOKEN</code>. Add
        a public Mapbox token (starts with <code className="font-mono">pk.</code>
        ) to <code className="font-mono">apps/web/.env.local</code> and restart
        the dev server.
      </div>
    );
  }

  if (token.startsWith("sk.")) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="max-w-md">
          <code className="font-mono">NEXT_PUBLIC_MAPBOX_TOKEN</code> is a secret
          token (<code className="font-mono">sk.</code>). Mapbox GL in the
          browser only accepts a public token (
          <code className="font-mono">pk.</code>
          ). Create one at account.mapbox.com → Tokens, put it in{" "}
          <code className="font-mono">.env.local</code> and Vercel, then restart.
        </p>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <Map
        mapboxAccessToken={token}
        mapStyle="mapbox://styles/mapbox/satellite-streets-v12"
        initialViewState={SITE_VIEW}
        style={{ width: "100%", height: "100%" }}
        attributionControl
        cursor={hover ? "pointer" : "grab"}
      >
        <DeckGLOverlay layers={layers} />
      </Map>

      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between gap-4 p-4">
        <div className="pointer-events-auto max-w-md rounded-md border border-border/60 bg-background/90 px-3 py-2 shadow-sm backdrop-blur">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Site Console · replay
          </p>
          <h1 className="text-sm font-semibold">
            Heatmap tiles over the site polygon
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            T2 fixture {HEATMAP_FIXTURE.split("/").pop()} · {TILE_COUNT} tiles ·
            100 m · 2024-07-15 14:00. Sample NYC polygon — not the Phoenix
            campus.
          </p>
        </div>
        <TempLegend />
      </div>

      {hover ? (
        <div
          className="pointer-events-none absolute z-10 rounded-md border border-border bg-background px-2 py-1.5 text-xs shadow-md"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium">Tile {hover.tileId}</div>
          <div className="text-muted-foreground">
            avg {formatC(hover.tAvg)} · min {formatC(hover.tMin)} · max{" "}
            {formatC(hover.tMax)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function TempLegend() {
  return (
    <div className="pointer-events-auto h-fit rounded-md border border-border/60 bg-background/90 px-3 py-2 shadow-sm backdrop-blur">
      <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
        Average air °C
      </p>
      <div
        className="mt-1.5 h-2 w-40 rounded-full"
        style={{
          background:
            "linear-gradient(90deg, rgb(37,99,235), rgb(34,211,238), rgb(250,204,21), rgb(239,68,68))",
        }}
      />
      <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
        <span>{TEMP_MIN.toFixed(2)}</span>
        <span>{TEMP_MAX.toFixed(2)}</span>
      </div>
    </div>
  );
}
