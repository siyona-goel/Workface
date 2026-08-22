"use client";

import { GeoJsonLayer } from "@deck.gl/layers";
import { useEffect, useMemo, useRef, useState } from "react";
import Map, { type MapRef } from "react-map-gl/mapbox";
import "mapbox-gl/dist/mapbox-gl.css";

import { DeckGLOverlay } from "@/components/deck-gl-overlay";
import phoenixSite from "@/data/phoenix-site.json";
import workFacesJson from "@/data/work-faces.json";
import { consoleData, VERDICT_LABEL, type Verdict } from "@/lib/console-data";
import { VERDICT_FILL } from "@/lib/verdicts";
import type { FeatureCollection } from "@/lib/site-map-data";

export type WorkFaceFeatureProps = {
  id: string;
  name: string;
  structure_id: string;
  exposure_class: string;
};

export type SiteMapProps = {
  selectedWorkFaceId: string | null;
  onSelectWorkFace: (id: string | null) => void;
  faceVerdict: Record<string, Verdict>;
};

const CAMPUS_VIEW = {
  longitude: -112.1582,
  latitude: 33.7855,
  zoom: 13.85,
} as const;

type HoverInfo = {
  x: number;
  y: number;
  name: string;
  id: string;
  verdict: Verdict;
};

export default function SiteMap({
  selectedWorkFaceId,
  onSelectWorkFace,
  faceVerdict,
}: SiteMapProps) {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const mapRef = useRef<MapRef>(null);

  useEffect(() => {
    if (!selectedWorkFaceId) return;
    const face = consoleData.work_faces.find((f) => f.id === selectedWorkFaceId);
    if (!face) return;
    mapRef.current?.flyTo({
      center: [face.centroid_lon, face.centroid_lat],
      zoom: 15.4,
      duration: 700,
    });
  }, [selectedWorkFaceId]);

  const layers = useMemo(
    () => [
      new GeoJsonLayer({
        id: "site-boundary",
        data: phoenixSite as FeatureCollection<Record<string, unknown>>,
        filled: false,
        stroked: true,
        getLineColor: [226, 232, 240, 200],
        getLineWidth: 2,
        lineWidthMinPixels: 1.5,
        pickable: false,
      }),
      new GeoJsonLayer<WorkFaceFeatureProps>({
        id: "work-faces",
        data: workFacesJson as FeatureCollection<WorkFaceFeatureProps>,
        filled: true,
        stroked: true,
        getFillColor: (f) => {
          const id = f.properties?.id;
          const verdict = (id && faceVerdict[id]) || "no_data";
          const fill = VERDICT_FILL[verdict];
          if (id && id === selectedWorkFaceId) {
            return [fill[0], fill[1], fill[2], 230];
          }
          return fill;
        },
        getLineColor: (f) => {
          const id = f.properties?.id;
          if (id === selectedWorkFaceId) return [255, 255, 255, 255];
          if (
            id === consoleData.hero_pair.bare ||
            id === consoleData.hero_pair.shaded
          ) {
            return [165, 243, 252, 220];
          }
          return [255, 255, 255, 70];
        },
        getLineWidth: (f) => {
          const id = f.properties?.id;
          if (id === selectedWorkFaceId) return 3;
          if (
            id === consoleData.hero_pair.bare ||
            id === consoleData.hero_pair.shaded
          ) {
            return 2;
          }
          return 1;
        },
        lineWidthMinPixels: 1,
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 50],
        updateTriggers: {
          getFillColor: [selectedWorkFaceId, faceVerdict],
          getLineColor: [selectedWorkFaceId],
          getLineWidth: [selectedWorkFaceId],
        },
        onHover: (info) => {
          if (!info.object || info.x == null || info.y == null) {
            setHover(null);
            return;
          }
          const p = info.object.properties;
          setHover({
            x: info.x,
            y: info.y,
            name: p.name,
            id: p.id,
            verdict: faceVerdict[p.id] ?? "no_data",
          });
        },
        onClick: (info) => {
          const id = info.object?.properties?.id;
          if (!id) return;
          onSelectWorkFace(id === selectedWorkFaceId ? null : id);
        },
      }),
    ],
    [faceVerdict, onSelectWorkFace, selectedWorkFaceId],
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
          ). Create one at account.mapbox.com → Tokens.
        </p>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <Map
        ref={mapRef}
        mapboxAccessToken={token}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        initialViewState={CAMPUS_VIEW}
        style={{ width: "100%", height: "100%" }}
        attributionControl
        cursor={hover ? "pointer" : "grab"}
      >
        <DeckGLOverlay layers={layers} />
      </Map>

      <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-border/60 bg-background/85 px-2.5 py-1.5 text-[10px] text-muted-foreground backdrop-blur">
        40 work faces · North Phoenix campus · hero pair outlined
      </div>

      {hover ? (
        <div
          className="pointer-events-none absolute z-10 max-w-xs rounded-md border border-border bg-background px-2 py-1.5 text-xs shadow-md"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium">{hover.name}</div>
          <div className="font-mono text-[10px] text-muted-foreground">
            {hover.id} · {VERDICT_LABEL[hover.verdict]}
          </div>
        </div>
      ) : null}
    </div>
  );
}
