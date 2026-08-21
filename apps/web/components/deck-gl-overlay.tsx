"use client";

import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import { useControl } from "react-map-gl/mapbox";

/** deck.gl as a Mapbox custom overlay (vis.gl / react-map-gl v8 pattern). */
export function DeckGLOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}
