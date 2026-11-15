import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useT } from "../state/prefs";

const STORAGE_KEY = "fire-calendar:calendar-height";
export const MIN_HEIGHT = 120;
/** Space the map and the top bar keep when the strip is at its tallest. */
const RESERVED = 280;
const STEP = 24;
const BIG_STEP = 96;

const maxHeight = () => Math.max(MIN_HEIGHT, window.innerHeight - RESERVED);
const clamp = (h: number) => Math.round(Math.min(maxHeight(), Math.max(MIN_HEIGHT, h)));

function readStored(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const n = raw === null ? NaN : Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function store(h: number) {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(h));
  } catch {
    // Storage can be unavailable (private mode); the height still applies in memory.
  }
}

/** Default height: 30% of the viewport, but tall enough for all 12 month rows on short screens. */
const DEFAULT_MIN = 240;

/** Initial height: the stored one, else the default; always clamped. */
export const initialHeight = () => clamp(readStored() ?? Math.max(DEFAULT_MIN, window.innerHeight * 0.3));

/** Height state for the calendar strip: clamped, persisted under its own key, re-clamped on window resize. */
export function useStripHeight() {
  const [height, setHeightState] = useState(initialHeight);
  const setHeight = useCallback((h: number) => {
    const next = clamp(h);
    setHeightState(next);
    store(next);
  }, []);
  useEffect(() => {
    const onResize = () => setHeightState((h) => clamp(h));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return { height, setHeight };
}

interface Props {
  height: number;
  onChange: (height: number) => void;
}

/** Horizontal splitter above the calendar strip: drag, keyboard, double-click to collapse / restore. */
export function StripResizer({ height, onChange }: Props) {
  const t = useT();
  const drag = useRef<{ startY: number; startH: number } | null>(null);
  const lastOpen = useRef(Math.max(height, MIN_HEIGHT + BIG_STEP));
  const [dragging, setDragging] = useState(false);
  if (height > MIN_HEIGHT) lastOpen.current = height;

  const toggle = () => onChange(height <= MIN_HEIGHT ? lastOpen.current : MIN_HEIGHT);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { startY: e.clientY, startH: height };
    setDragging(true);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current) onChange(drag.current.startH + (drag.current.startY - e.clientY));
  };
  const end = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    drag.current = null;
    setDragging(false);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const next: Record<string, number | undefined> = {
      ArrowUp: height + STEP,
      ArrowDown: height - STEP,
      PageUp: height + BIG_STEP,
      PageDown: height - BIG_STEP,
      Home: MIN_HEIGHT,
      End: maxHeight(),
    };
    if (e.key === "Enter") {
      e.preventDefault();
      toggle();
    } else if (next[e.key] !== undefined) {
      e.preventDefault();
      onChange(next[e.key]!);
    }
  };

  return (
    <div
      className={dragging ? "strip-resizer dragging" : "strip-resizer"}
      role="separator"
      aria-orientation="horizontal"
      aria-label={t.calendar.resize}
      aria-valuemin={MIN_HEIGHT}
      aria-valuemax={maxHeight()}
      aria-valuenow={height}
      tabIndex={0}
      data-testid="strip-resizer"
      data-compact={height <= MIN_HEIGHT}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onDoubleClick={toggle}
      onKeyDown={onKeyDown}
    >
      <span className="strip-grip" aria-hidden="true" />
    </div>
  );
}
