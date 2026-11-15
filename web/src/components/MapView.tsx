import { useEffect, useMemo, useRef, useState } from "react";
import { DeckGL, Layer, PathLayer, ScatterplotLayer, WebMercatorViewport, type DeckGLRef, type PickingInfo } from "deck.gl";
import { Map as BaseMap } from "react-map-gl/maplibre";
import { setWorkerUrl } from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Hotspot, PointLayer } from "../layers/manifest";
import { usePrefs, useT } from "../state/prefs";
import { colors, hexToRgb } from "../theme/tokens";
import type { LonLat } from "../state/selection";
import { useSelection } from "../state/SelectionContext";

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
  const { state, dispatch } = useSelection();
  const { draw } = state;
  const lastClick = useRef<{ t: number; x: number; y: number } | null>(null);
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
    const draft: Layer[] = draw.active
      ? [
          new PathLayer<LonLat[]>({
            id: "draw-path",
            data: draw.vertices.length > 1 ? [draw.vertices] : [],
            getPath: (d) => d,
            widthUnits: "pixels",
            getWidth: 2,
            getColor: [...accent, 255],
          }),
          new ScatterplotLayer<LonLat>({
            id: "draw-vertices",
            data: draw.vertices,
            radiusUnits: "pixels",
            lineWidthUnits: "pixels",
            stroked: true,
            getPosition: (d) => d,
            getRadius: 5,
            getFillColor: [...accent, 255],
            getLineColor: casing,
            getLineWidth: 2,
          }),
        ]
      : [];
    const points = layers.map(
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
    return [...points, ...draft];
  }, [layers, selected, theme, draw.active, draw.vertices]);

  /** In draw mode a click adds a vertex; a second click within 350 ms and 8 px closes the polygon. */
  const onMapClick = (info: PickingInfo<Hotspot>) => {
    if (!draw.active) return onSelect(info.object ?? null);
    if (!info.coordinate) return;
    const prev = lastClick.current;
    const now = Date.now();
    if (prev && now - prev.t < 350 && Math.hypot(info.x - prev.x, info.y - prev.y) < 8) {
      lastClick.current = null;
      return dispatch({ type: "drawFinish" });
    }
    lastClick.current = { t: now, x: info.x, y: info.y };
    dispatch({ type: "drawVertex", vertex: [info.coordinate[0], info.coordinate[1]] });
  };

  return (
    <div className="map" ref={box} role="region" aria-label={t.map.label} data-testid="map">
      {initialView && (
        <DeckGL
          ref={deck}
          initialViewState={initialView}
          controller={{ doubleClickZoom: !draw.active }}
          layers={deckLayers}
          pickingRadius={6}
          getCursor={({ isHovering, isDragging }) =>
            draw.active ? "crosshair" : isDragging ? "grabbing" : isHovering ? "pointer" : "grab"
          }
          onClick={onMapClick}
        >
          <BaseMap mapStyle={BASEMAP[theme]} attributionControl={{ compact: true }} />
        </DeckGL>
      )}
    </div>
  );
}
