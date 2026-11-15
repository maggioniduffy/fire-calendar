import { useMemo } from "react";
import type { CalendarPayload } from "../../api/types";
import { linear, niceMax, niceTicks, yearlyTotals } from "../../charts/dashboard-scales";
import { useT } from "../../state/prefs";
import { MARGIN, XLabel, YAxis, useNumberFormat } from "./Axes";
import { CHART_HEIGHT, ChartFrame, Legend } from "./ChartFrame";
import { useMonthLink } from "./link";

export function YearlyChart({ cal, source }: { cal: CalendarPayload; source: string }) {
  const t = useT();
  const fmt = useNumberFormat();
  const link = useMonthLink();
  const years = useMemo(() => yearlyTotals(cal), [cal]);
  const d = t.dashboard.yearly;
  const csv = {
    header: ["year", "total", "n_months", "complete", "estimated_months"],
    rows: years.map((y) => [y.year, y.value, y.nMonths, y.complete, y.estimatedMonths]),
  };
  const focus = link.hover?.year ?? (link.hover ? null : (link.selected?.year ?? null));
  const shown = years.find((y) => y.year === focus);
  const readout = shown ? (
    <>
      {shown.year} · {d.bars} {fmt(shown.value)}
      {shown.complete ? "" : ` · ${t.dashboard.partialYear} (${shown.nMonths}/12)`}
    </>
  ) : undefined;

  return (
    <ChartFrame
      id="yearly"
      title={d.title}
      source={source}
      csv={csv}
      readout={readout}
      legend={<Legend items={[{ label: d.bars, swatch: "sw-bar" }, ...(years.some((y) => !y.complete) ? [{ label: t.dashboard.partialYear, swatch: "sw-bar-partial" }] : [])]} />}
    >
      {(width) => {
        const H = CHART_HEIGHT;
        const ymax = niceMax(Math.max(1, ...years.map((y) => y.value ?? 0)));
        const y = linear([0, ymax], [H - MARGIN.b, MARGIN.t]);
        const slot = (width - MARGIN.l - MARGIN.r) / Math.max(years.length, 1);
        const bw = Math.max(2, slot - Math.min(4, slot * 0.25));
        const every = Math.max(1, Math.ceil(44 / slot));
        return (
          <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={d.title} onPointerLeave={() => link.setHover(null)} data-testid="yearly-svg">
            <YAxis ticks={niceTicks(0, ymax, 4)} y={y} width={width} />
            {years.map((yr, i) => {
              const x0 = MARGIN.l + i * slot + (slot - bw) / 2;
              const v = yr.value ?? 0;
              const active = focus === yr.year;
              return (
                <g key={yr.year}>
                  <rect
                    className={`${yr.complete ? "d-bar" : "d-bar d-bar-partial"}${active ? " d-bar-active" : ""}`}
                    x={x0}
                    y={y(v)}
                    width={bw}
                    height={Math.max(0, y(0) - y(v))}
                    rx={2}
                    data-year={yr.year}
                  />
                  {/* Wider invisible hit target. */}
                  <rect
                    className="d-hit"
                    x={MARGIN.l + i * slot}
                    y={MARGIN.t}
                    width={slot}
                    height={H - MARGIN.t - MARGIN.b}
                    onPointerEnter={() => link.setHover({ year: yr.year, month: null })}
                  />
                  {i % every === 0 && <XLabel x={x0 + bw / 2} y={H - 8} text={String(yr.year)} />}
                </g>
              );
            })}
          </svg>
        );
      }}
    </ChartFrame>
  );
}
