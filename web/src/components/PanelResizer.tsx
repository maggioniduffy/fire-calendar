import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useT } from "../state/prefs";

const STORAGE_KEY = "fire-calendar:left-width";
export const MIN_WIDTH = 240;
export const DEFAULT_WIDTH = 260;
const MAX_ABSOLUTE = 560;
const MAX_FRACTION = 0.4;
const STEP = 16;
const BIG_STEP = 64;

/** Widest the left panel may be: 40% of the viewport, capped at 560 px, never below the minimum. */
export const maxWidthFor = (viewport: number) => Math.max(MIN_WIDTH, Math.min(MAX_ABSOLUTE, Math.floor(viewport * MAX_FRACTION)));
export const clampWidth = (w: number, viewport: number) =>
  Math.round(Math.min(maxWidthFor(viewport), Math.max(MIN_WIDTH, w)));

/** Width after a key press, or null when the key does nothing. */
export function widthAfterKey(key: string, width: number, viewport: number): number | null {
  const next: Record<string, number | undefined> = {
    ArrowRight: width + STEP,
    ArrowLeft: width - STEP,
    PageUp: width + BIG_STEP,
    PageDown: width - BIG_STEP,
    Home: MIN_WIDTH,
    End: maxWidthFor(viewport),
  };
  const value = next[key];
  return value === undefined ? null : clampWidth(value, viewport);
}

function readStored(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const n = raw === null ? NaN : Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function store(w: number) {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(w));
  } catch {
    // Storage can be unavailable (private mode); the width still applies in memory.
  }
}

/** Width state for the left panel: clamped, persisted under its own key, re-clamped on window resize. */
export function usePanelWidth() {
  const [width, setWidthState] = useState(() => clampWidth(readStored() ?? DEFAULT_WIDTH, window.innerWidth));
  const setWidth = useCallback((w: number) => {
    const next = clampWidth(w, window.innerWidth);
    setWidthState(next);
    store(next);
  }, []);
  useEffect(() => {
    const onResize = () => setWidthState((w) => clampWidth(w, window.innerWidth));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { width, setWidth };
}

/** Vertical splitter on the right edge of the left panel: drag, keyboard, double-click to reset. */
export function PanelResizer({ width, onChange }: { width: number; onChange: (width: number) => void }) {
  const t = useT();
  const drag = useRef<{ startX: number; startW: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { startX: e.clientX, startW: width };
    setDragging(true);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current) onChange(drag.current.startW + (e.clientX - drag.current.startX));
  };
  const end = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    drag.current = null;
    setDragging(false);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const next = widthAfterKey(e.key, width, window.innerWidth);
    if (next === null) return;
    e.preventDefault();
    onChange(next);
  };

  return (
    <div
      className={dragging ? "panel-resizer dragging" : "panel-resizer"}
      role="separator"
      aria-orientation="vertical"
      aria-label={t.panel.resize}
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={maxWidthFor(window.innerWidth)}
      aria-valuenow={width}
      tabIndex={0}
      data-testid="panel-resizer"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onDoubleClick={() => onChange(DEFAULT_WIDTH)}
      onKeyDown={onKeyDown}
    >
      <span className="panel-grip" aria-hidden="true" />
    </div>
  );
}
