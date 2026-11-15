import { useMemo, type PointerEvent } from "react";
import type { CalendarPayload, StatsPayload } from "../../api/types";
import { anomalies, linear, niceTicks } from "../../charts/dashboard-scales";
import { format } from "../../i18n";
import { useT } from "../../state/prefs";
import { MARGIN, XLabel, YAxis, useNumberFormat } from "./Axes";
import { CHART_HEIGHT, ChartFrame, Legend } from "./ChartFrame";
import { useMonthLink } from "./link";

export function AnomalyChart({ cal, stats, source, pending }: { cal: CalendarPayload; stats: StatsPayload; source: string; pending: boolean }) {
  const t = useT();
  const fmt = useNumberFormat();
  const link = useMonthLink();
  const rows = useMemo(() => anomalies(cal, stats), [cal, stats]);
  const d = t.dashboard.anomaly;
  const base = stats.climatology.baseline_years;
  const csv = {
    header: ["month", "value", "median", "anomaly"],
    rows: rows.map((r) => [r.key, r.value, r.median, r.diff]),
  };
  const hovered =
    link.hover?.year != null && link.hover.month !== null
      ? rows.find((r) => r.year === link.hover!.year && r.month === link.hover!.month)
      : undefined;
  const sel = link.selected ? rows.find((r) => r.year === link.selected!.year && r.month === link.selected!.month) : undefined;
  const shown = hovered ?? (link.hover ? undefined : sel);
  const readout = shown ? (
    <>
      {shown.key} · {fmt(shown.value)} − {fmt(shown.median)} = {shown.diff > 0 ? "+" : ""}
      {fmt(shown.diff)}
    </>
  ) : undefined;

  if (!rows.length) return null;
  return (
    <ChartFrame
      id="anomaly"
      title={d.title}
      source={source}
      pending={pending}
      csv={csv}
      readout={readout}
      legend={<Legend items={[{ label: d.above, swatch: "sw-pos" }, { label: d.below, swatch: "sw-neg" }]} />}
      note={
        <p className="dash-note muted">
          {format(d.note, { y0: base.length ? Math.min(...base) : "", y1: base.length ? Math.max(...base) : "" })}
        </p>
      }
    >
      {(width) => {
        const H = CHART_HEIGHT;
        const lo = Math.min(0, ...rows.map((r) => r.diff));
        const hi = Math.max(0, ...rows.map((r) => r.diff));
        const ticks = niceTicks(lo, hi === lo ? lo + 1 : hi, 4);
        const y = linear([ticks[0], ticks[ticks.length - 1]], [H - MARGIN.b, MARGIN.t]);
        const idx = rows.map((r) => r.index);
        const x = linear([Math.min(...idx), Math.max(...idx)], [MARGIN.l + 3, width - MARGIN.r - 3]);
        const bw = Math.max(1.5, ((width - MARGIN.l - MARGIN.r) / (Math.max(...idx) - Math.min(...idx) + 1)) * 0.8);
        const years = [...new Set(rows.map((r) => r.year))];
        const every = Math.max(1, Math.ceil((years.length * 44) / (width - MARGIN.l - MARGIN.r)));
        const onMove = (e: PointerEvent<SVGSVGElement>) => {
          const px = e.clientX - e.currentTarget.getBoundingClientRect().left;
          let best = rows[0];
          for (const r of rows) if (Math.abs(x(r.index) - px) < Math.abs(x(best.index) - px)) best = r;
          link.setHover({ year: best.year, month: best.month });
        };
        const emphasis = (r: (typeof rows)[number]) =>
          (hovered && hovered.key === r.key) ||
          (sel && sel.key === r.key) ||
          (link.hover && link.hover.year === null && link.hover.month === r.month) ||
          (link.hover && link.hover.year === r.year && link.hover.month === null);
        return (
          <svg
            width={width}
            height={H}
            viewBox={`0 0 ${width} ${H}`}
            role="img"
            aria-label={d.title}
            onPointerMove={onMove}
            onPointerLeave={() => link.setHover(null)}
            onClick={() => hovered && link.select(hovered.key)}
            data-testid="anomaly-svg"
          >
            <YAxis ticks={ticks} y={y} width={width} />
            {years.map((yr, i) =>
              i % every === 0 ? <XLabel key={yr} x={x(yr * 12)} y={H - 8} text={String(yr)} anchor={i === 0 ? "start" : "middle"} /> : null,
            )}
            {rows.map((r) => {
              const y0 = y(0);
              const y1 = y(r.diff);
              return (
                <rect
                  key={r.key}
                  className={`${r.diff >= 0 ? "d-pos" : "d-neg"}${emphasis(r) ? " d-emph" : ""}`}
                  x={x(r.index) - bw / 2}
                  y={Math.min(y0, y1)}
                  width={bw}
                  height={Math.max(1, Math.abs(y1 - y0))}
                />
              );
            })}
            <line className="d-zero" x1={MARGIN.l} x2={width - MARGIN.r} y1={y(0)} y2={y(0)} />
          </svg>
        );
      }}
    </ChartFrame>
  );
}
