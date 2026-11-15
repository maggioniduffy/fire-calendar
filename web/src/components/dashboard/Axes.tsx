import { usePrefs } from "../../state/prefs";

/** Locale-aware number formatter for chart labels (null = no value). */
export function useNumberFormat(): (v: number | null | undefined, digits?: number) => string {
  const { lang } = usePrefs();
  return (v, digits = 1) =>
    v === null || v === undefined ? "–" : v.toLocaleString(lang, { maximumFractionDigits: digits });
}

export const MARGIN = { l: 48, r: 12, t: 12, b: 26 } as const;

/** Horizontal grid lines and value labels on the left. */
export function YAxis({ ticks, y, width }: { ticks: number[]; y: (v: number) => number; width: number }) {
  const fmt = useNumberFormat();
  return (
    <g>
      {ticks.map((v) => (
        <g key={v}>
          <line className="d-grid" x1={MARGIN.l} x2={width - MARGIN.r} y1={y(v)} y2={y(v)} />
          <text className="d-tick" x={MARGIN.l - 6} y={y(v)} textAnchor="end" dominantBaseline="middle">
            {fmt(v, 0)}
          </text>
        </g>
      ))}
    </g>
  );
}

/** Label under the plot at `x`. */
export function XLabel({ x, y, text, anchor = "middle" }: { x: number; y: number; text: string; anchor?: "start" | "middle" | "end" }) {
  return (
    <text className="d-tick" x={x} y={y} textAnchor={anchor}>
      {text}
    </text>
  );
}
