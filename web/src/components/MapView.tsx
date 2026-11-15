import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DeckGL, Layer, PathLayer, PolygonLayer, ScatterplotLayer, WebMercatorViewport, type DeckGLRef, type PickingInfo } from "deck.gl";
import { Map as BaseMap } from "react-map-gl/maplibre";
import { setWorkerUrl } from "maplibre-gl";
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import { ApiError, getCells, getDetections } from "../api/client";
import type { BBox, CellsPayload, DetectionsPayload } from "../api/types";
import { format } from "../i18n";
import { usePrefs, useT } from "../state/prefs";
import { colors, hexToRgb } from "../theme/tokens";
import { areaBounds, circleRing, toCellsRequest, type LonLat } from "../state/selection";
import { useSelection } from "../state/SelectionContext";

// MapLibre resolves its worker next to its own module, which bundling breaks; point it at the copied file.
setWorkerUrl(maplibreWorkerUrl);

/** Córdoba province, approximate bounding box [west, south, east, north]. */
export const CORDOBA_BOUNDS: [number, number, number, number] = [-65.8, -35.0, -61.7, -29.5];

// CARTO basemaps: free with attribution (shown by MapLibre), no key.
/** Raw detections replace cells from this zoom on (when the server has them). */
export const DETECTION_MIN_ZOOM = 8;
const CELL_DEG = 0.1;
const WINDOW_PAD = 0.25;

type View = { longitude: number; latitude: number; zoom: number; pitch: number; bearing: number };
type Settled = { zoom: number; bounds: BBox };
type Fetched<T> = { key: string; data: T };

const BASEMAP = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
} as const;

declare global {
  interface Window {
    /** Test hook (dev and e2e builds only): screen position of a lon/lat inside the map. */
    __firecal?: { project: (lon: number, lat: number) => [number, number] | null };
  }
}

/** View that fits `bounds` [west, south, east, north] in a box of the given size. */
function fitView(bounds: [number, number, number, number], width: number, height: number): View {
  const vp = new WebMercatorViewport({ width, height }).fitBounds(
    [
      [bounds[0], bounds[1]],
      [bounds[2], bounds[3]],
    ],
    { padding: Math.min(24, width / 8, height / 8), maxZoom: 12 },
  );
  return { longitude: vp.longitude, latitude: vp.latitude, zoom: vp.zoom, pitch: 0, bearing: 0 };
}

/** View window as [lat_min, lat_max, lon_min, lon_max], rounded to 2 decimals. */
function viewBounds(view: View, width: number, height: number): BBox {
  const [w, s, e, n] = new WebMercatorViewport({ ...view, width, height }).getBounds();
  const r = (v: number) => Math.round(v * 100) / 100;
  return [r(s), r(n), r(w), r(e)];
}

const pad = ([s, n, w, e]: BBox, f: number): BBox => {
  const dy = (n - s) * f;
  const dx = (e - w) * f;
  const r = (v: number) => Math.round(v * 100) / 100;
  return [r(s - dy), r(n + dy), r(w - dx), r(e + dx)];
};

const contains = (outer: BBox, inner: BBox) =>
  inner[0] >= outer[0] && inner[1] <= outer[1] && inner[2] >= outer[2] && inner[3] <= outer[3];

const square = (lat: number, lon: number): LonLat[] => {
  const h = CELL_DEG / 2;
  return [
    [lon - h, lat - h],
    [lon + h, lat - h],
    [lon + h, lat + h],
    [lon - h, lat + h],
  ];
};

export default function MapView() {
  const t = useT();
  const { theme, lang } = usePrefs();
  const box = useRef<HTMLDivElement>(null);
  const deck = useRef<DeckGLRef>(null);
  const { state, dispatch } = useSelection();
  const { draw } = state;
  const lastClick = useRef<{ t: number; x: number; y: number } | null>(null);
  const [initialView, setInitialView] = useState<View | null>(null);
  const [settled, setSettled] = useState<Settled | null>(null);
  /** Window the current data was requested for; only replaced when the view leaves it or the mode changes. */
  const [win, setWin] = useState<BBox | null>(null);
  const [cellsData, setCellsData] = useState<Fetched<CellsPayload | "error"> | null>(null);
  const [detData, setDetData] = useState<Fetched<DetectionsPayload> | null>(null);
  /** False once /detections answered 404: the map stays on cells. */
  const [detAvailable, setDetAvailable] = useState(true);
  const settleTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const lastView = useRef<View | null>(null);

  const detMode = detAvailable && (settled?.zoom ?? 0) >= DETECTION_MIN_ZOOM;

  /** Records the settled view and decides whether the data window must be requested again. */
  const settle = useCallback((view: View) => {
    const el = box.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width < 1 || height < 1) return;
    const bounds = viewBounds(view, width, height);
    setSettled({ zoom: view.zoom, bounds });
    setWin((cur) => {
      const raw = pad(bounds, WINDOW_PAD);
      if (!cur) return raw;
      const wide = (cur[3] - cur[2]) / Math.max(bounds[3] - bounds[2], 1e-6) > 4; // zoomed in a lot: shrink
      return contains(cur, bounds) && !wide ? cur : raw;
    });
  }, []);

  // Fit the view to the area on mount and whenever the area changes.
  const areaKey = JSON.stringify(state.area);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    const view = fitView(areaBounds(state.area, CORDOBA_BOUNDS), Math.max(width, 1), Math.max(height, 1));
    lastView.current = view;
    setInitialView(view);
    setWin(null);
    settle(view);
    // `areaKey` encodes the area.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [areaKey, settle]);

  useEffect(() => () => clearTimeout(settleTimer.current), []);

  const onViewStateChange = ({ viewState }: { viewState: Record<string, unknown> }) => {
    const v = viewState as unknown as View;
    lastView.current = v;
    clearTimeout(settleTimer.current);
    settleTimer.current = setTimeout(() => settle(v), 250);
  };

  // Cells: one request per area / month / scale / window; the previous one is aborted.
  const cellsBody = win ? toCellsRequest(state, win) : null;
  const cellsKey = cellsBody ? JSON.stringify(cellsBody) : null;
  useEffect(() => {
    if (!cellsBody || !cellsKey) return;
    const ctl = new AbortController();
    getCells(cellsBody, ctl.signal)
      .then((data) => setCellsData({ key: cellsKey, data }))
      .catch(() => {
        if (!ctl.signal.aborted) setCellsData({ key: cellsKey, data: "error" });
      });
    return () => ctl.abort();
    // `cellsKey` encodes the body.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cellsKey]);

  // Raw detections: only from DETECTION_MIN_ZOOM on and while the server has answered something but 404.
  const detKey = detMode && cellsBody && cellsKey ? `det:${cellsKey}` : null;
  useEffect(() => {
    if (!detKey || !cellsBody || !cellsBody.bbox) return;
    const ctl = new AbortController();
    getDetections({ ...cellsBody, bbox: cellsBody.bbox }, ctl.signal)
      .then((data) => setDetData({ key: detKey, data }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted && e instanceof ApiError && e.status === 404) setDetAvailable(false);
      });
    return () => ctl.abort();
    // `detKey` encodes the body.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detKey]);

  const cells = cellsData?.key === cellsKey && cellsData.data !== "error" ? cellsData.data : null;
  const cellsError = cellsData?.key === cellsKey && cellsData.data === "error";
  const lastCells = cellsData && cellsData.data !== "error" ? cellsData.data : null;
  const dets = detMode && detData?.key === detKey ? detData.data : null;
  const showDetections = dets !== null;

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

  const outline = useMemo<LonLat[][]>(() => {
    const { area } = state;
    if (area.kind === "circle") return [circleRing(area.lat, area.lon, area.radiusKm)];
    if (area.kind === "polygon") return [[...area.vertices, area.vertices[0]]];
    const ring = lastCells?.outline?.[0] as LonLat[] | undefined;
    if (ring) return [ring];
    const [w, s, e, n] = CORDOBA_BOUNDS;
    return [
      [
        [w, s],
        [e, s],
        [e, n],
        [w, n],
        [w, s],
      ],
    ];
  }, [state, lastCells]);

  // Cells of the last answer stay drawn while the next one loads (no flicker); counts use the current one only.
  const shown = cells ?? lastCells;
  const maxValue = useMemo(() => (shown ? Math.max(1, ...shown.cells.map((c) => c.value)) : 1), [shown]);

  const deckLayers = useMemo(() => {
    const c = colors[theme];
    const accent = hexToRgb(c.accent);
    const casing = hexToRgb(c.casing);
    const ctrl = hexToRgb(c.ctrl);
    const fill = (v: number): [number, number, number, number] => [
      ...accent,
      Math.round(60 + 195 * (Math.log1p(v) / Math.log1p(maxValue))),
    ];
    const cellLayer = new PolygonLayer<{ lat: number; lon: number; value: number }>({
      id: "cells",
      data: !showDetections && shown ? shown.cells.map((d) => ({ lat: d.cell_lat, lon: d.cell_lon, value: d.value })) : [],
      getPolygon: (d) => square(d.lat, d.lon),
      stroked: true,
      filled: true,
      lineWidthUnits: "pixels",
      getLineWidth: 1,
      getLineColor: [...casing, 150],
      getFillColor: (d) => fill(d.value),
      updateTriggers: { getFillColor: [maxValue, theme], getLineColor: theme },
    });
    const detLayer = new ScatterplotLayer<DetectionsPayload["points"][number]>({
      id: "detections",
      data: dets?.points ?? [],
      radiusUnits: "pixels",
      lineWidthUnits: "pixels",
      stroked: true,
      getPosition: (d) => [d.lon, d.lat],
      getRadius: 4,
      getFillColor: [...accent, 255],
      getLineColor: casing,
      getLineWidth: 1,
      updateTriggers: { getFillColor: theme, getLineColor: theme },
    });
    const areaLayer = new PolygonLayer<LonLat[]>({
      id: "area-outline",
      data: outline,
      getPolygon: (d) => d,
      filled: false,
      stroked: true,
      lineWidthUnits: "pixels",
      getLineWidth: 2,
      getLineColor: [...ctrl, 255],
      updateTriggers: { getLineColor: theme },
    });
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
    return [cellLayer, detLayer, areaLayer, ...draft];
  }, [theme, draw.active, draw.vertices, shown, dets, showDetections, outline, maxValue]);

  /** In draw mode a click adds a vertex; a second click within 350 ms and 8 px closes the polygon. */
  const onMapClick = (info: PickingInfo) => {
    if (!draw.active || !info.coordinate) return;
    const prev = lastClick.current;
    const now = Date.now();
    if (prev && now - prev.t < 350 && Math.hypot(info.x - prev.x, info.y - prev.y) < 8) {
      lastClick.current = null;
      return dispatch({ type: "drawFinish" });
    }
    lastClick.current = { t: now, x: info.x, y: info.y };
    dispatch({ type: "drawVertex", vertex: [info.coordinate[0], info.coordinate[1]] });
  };

  const nf = new Intl.NumberFormat(lang === "es" ? "es-AR" : "en-US", { maximumFractionDigits: 1 });
  const total = cells?.total;
  const countText = cellsError
    ? t.map.error
    : !cells
      ? t.map.loading
      : total === null || total === undefined
        ? t.map.noData
        : format(t.map.hotspots, { n: nf.format(total) });
  const accentCss = colors[theme].accent;
  const [ar, ag, ab] = hexToRgb(accentCss);

  return (
    <div
      className="map"
      ref={box}
      role="region"
      aria-label={t.map.label}
      data-testid="map"
      data-mode={showDetections ? "detections" : "cells"}
      data-cell-count={cells ? cells.cells.length : undefined}
      data-detection-count={dets ? dets.points.length : undefined}
    >
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
          onViewStateChange={onViewStateChange}
        >
          <BaseMap mapStyle={BASEMAP[theme]} attributionControl={{ compact: true }} />
        </DeckGL>
      )}
      <div className="map-overlay" data-testid="map-overlay">
        <div className="month num" data-testid="map-month">
          {state.month ?? "—"}
        </div>
        <p className="count" data-testid="map-count" aria-live="polite">
          {countText}
        </p>
      </div>
      <div className="map-legend" data-testid="map-legend">
        {showDetections ? (
          <>
            <p>{t.map.legendDetections}</p>
            {dets.truncated && (
              <p className="num">{format(t.map.legendTruncated, { shown: dets.points.length, total: dets.total })}</p>
            )}
          </>
        ) : (
          <>
            <p>{t.map.legendCells}</p>
            <div className="ramp num">
              1
              <i
                aria-hidden="true"
                style={{ background: `linear-gradient(to right, rgba(${ar},${ag},${ab},0.24), rgba(${ar},${ag},${ab},1))` }}
              />
              {nf.format(maxValue)}
            </div>
          </>
        )}
        {shown?.cells.some((c) => c.estimated) && !showDetections && <p>{t.map.legendEstimated}</p>}
      </div>
    </div>
  );
}
