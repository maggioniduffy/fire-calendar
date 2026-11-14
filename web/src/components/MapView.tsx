import { useEffect, useMemo, useRef, useState } from "react";
import { DeckGL, ScatterplotLayer, WebMercatorViewport, type DeckGLRef, type PickingInfo } from "deck.gl";
import { Map as BaseMap } from "react-map-gl/maplibre";
import { setWorkerUrl } from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Hotspot, PointLayer } from "../layers/manifest";
import { usePrefs, useT } from "../state/prefs";
import { colors, hexToRgb } from "../theme/tokens";

// MapLibre resolves its worker next to its own module, which bundling breaks; point it at the copied file.
setWorkerUrl(maplibreWorkerUrl);

/** Córdoba province, approximate bounding box [west, south, east, north]. */
export const CORDOBA_BOUNDS: [number, number, number, number] = [-65.8, -35.0, -61.7, -29.5];

// CARTO basemaps: free with attribution (shown by MapLibre), no key.
const BASEMAP = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
} as const;

interface Props {
  layers: PointLayer[];
  selected: Hotspot | null;
  onSelect: (h: Hotspot | null) => void;
}

declare global {
  interface Window {
    /** Test hook (dev and e2e builds only): screen position of a lon/lat inside the map. */
    __firecal?: { project: (lon: number, lat: number) => [number, number] | null };
  }
}

function fitCordoba(width: number, height: number) {
  const vp = new WebMercatorViewport({ width, height }).fitBounds(
    [
      [CORDOBA_BOUNDS[0], CORDOBA_BOUNDS[1]],
      [CORDOBA_BOUNDS[2], CORDOBA_BOUNDS[3]],
    ],
    { padding: Math.min(24, width / 8, height / 8) },
  );
  return { longitude: vp.longitude, latitude: vp.latitude, zoom: vp.zoom, pitch: 0, bearing: 0 };
}

export default function MapView({ layers, selected, onSelect }: Props) {
  const t = useT();
  const { theme } = usePrefs();
  const box = useRef<HTMLDivElement>(null);
  const deck = useRef<DeckGLRef>(null);
  const [initialView, setInitialView] = useState<ReturnType<typeof fitCordoba> | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || initialView) return;
    const { width, height } = el.getBoundingClientRect();
    setInitialView(fitCordoba(Math.max(width, 1), Math.max(height, 1)));
  }, [initialView]);

  useEffect(() => {
    if (!(import.meta.env.DEV || import.meta.env.MODE === "e2e")) return;
    window.__firecal = {
      project(lon, lat) {
        try {
          const vp = deck.current?.deck?.getViewports()[0];
          if (!vp) return null;
          const [x, y] = vp.project([lon, lat]);
          return [x, y];
        } catch {
          return null; // deck.gl not initialised yet
        }
      },
    };
    return () => {
      delete window.__firecal;
    };
  }, []);

  const deckLayers = useMemo(() => {
    const c = colors[theme];
    const base = [...hexToRgb(c.text), 220] as [number, number, number, number];
    const ring = hexToRgb(c.surface);
    const accent = hexToRgb(c.accent);
    const casing = hexToRgb(c.casing);
    return layers.map(
      (layer) =>
        new ScatterplotLayer<Hotspot>({
          id: layer.manifest.id,
          data: layer.points,
          pickable: true,
          stroked: true,
          radiusUnits: "pixels",
          lineWidthUnits: "pixels",
          getPosition: (d) => [d.lon, d.lat],
          getRadius: (d) => (d.id === selected?.id ? 9 : 6),
          getFillColor: (d) => (d.id === selected?.id ? accent : base),
          getLineColor: (d) => (d.id === selected?.id ? casing : ring),
          getLineWidth: (d) => (d.id === selected?.id ? 2 : 1),
          updateTriggers: {
            getRadius: selected?.id,
            getFillColor: [selected?.id, theme],
            getLineColor: [selected?.id, theme],
            getLineWidth: selected?.id,
          },
        }),
    );
  }, [layers, selected, theme]);

  return (
    <div className="map" ref={box} role="region" aria-label={t.map.label} data-testid="map">
      {initialView && (
        <DeckGL
          ref={deck}
          initialViewState={initialView}
          controller
          layers={deckLayers}
          pickingRadius={6}
          getCursor={({ isHovering, isDragging }) => (isDragging ? "grabbing" : isHovering ? "pointer" : "grab")}
          onClick={(info: PickingInfo<Hotspot>) => onSelect(info.object ?? null)}
        >
          <BaseMap mapStyle={BASEMAP[theme]} attributionControl={{ compact: true }} />
        </DeckGL>
      )}
    </div>
  );
}
