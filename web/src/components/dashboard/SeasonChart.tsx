import { useMemo } from "react";
import type { CalendarPayload, StatsPayload } from "../../api/types";
import { linear, monthKey, niceMax, niceTicks, seasonality } from "../../charts/dashboard-scales";
import { format } from "../../i18n";
import { usePrefs, useT } from "../../state/prefs";
import { MARGIN, XLabel, YAxis, useNumberFormat } from "./Axes";
import { CHART_HEIGHT, ChartFrame, Legend } from "./ChartFrame";
import { bandPath, linePaths, useMonthLink } from "./link";

export function SeasonChart({ cal, stats, source }: { cal: CalendarPayload; stats: StatsPayload; source: string }) {
  const t = useT();
  const { lang } = usePrefs();
  const fmt = useNumberFormat();
  const link = useMonthLink();
  const { latestYear, points } = useMemo(() => seasonality(cal, stats), [cal, stats]);
  const d = t.dashboard.season;
  const monthName = useMemo(() => {
    const f = new Intl.DateTimeFormat(lang, { month: "short", timeZone: "UTC" });
    return (m: number) => f.format(new Date(Date.UTC(2001, m - 1, 1)));
  }, [lang]);
  const base = stats.climatology.baseline_years;
  const y0 = base.length ? Math.min(...base) : "";
  const y1 = base.length ? Math.max(...base) : "";
  const latestLabel = latestYear === null ? "" : format(d.latest, { year: latestYear });

  const csv = {
    header: ["month", "median", "p10", "p90", "n_years", "latest_year", "latest_value"],
    rows: points.map((p) => [p.month, p.median, p.p10, p.p90, p.nYears, latestYear, p.latest]),
  };
  // A month of the latest year the user hovers/selected elsewhere maps to its calendar month here.
  const focus = link.hover ? link.hover.month : (link.selected?.month ?? null);
  const shown = points.find((p) => p.month === focus);
  const readout = shown ? (
    <>
      {monthName(shown.month)} · {d.median} {fmt(shown.median)} ({d.range} {fmt(shown.p10)}–{fmt(shown.p90)})
      {shown.latest !== null ? ` · ${latestLabel} ${fmt(shown.latest)}` : ""}
    </>
  ) : undefined;

  return (
    <ChartFrame
      id="season"
      title={d.title}
      source={source}
      csv={csv}
      readout={readout}
      legend={
        <Legend
          items={[
            { label: d.range, swatch: "sw-range" },
            { label: d.median, swatch: "sw-median" },
            ...(latestYear !== null ? [{ label: latestLabel, swatch: "sw-latest" }] : []),
          ]}
        />
      }
      note={
        <p className="dash-note muted">
          {format(d.note, { y0, y1, method: stats.climatology.quantile_method })}
        </p>
      }
    >
      {(width) => {
        const H = CHART_HEIGHT;
        const x = linear([1, 12], [MARGIN.l + 12, width - MARGIN.r - 12]);
        const ymax = niceMax(Math.max(1, ...points.flatMap((p) => [p.p90, p.median, p.latest]).map((v) => v ?? 0)));
        const y = linear([0, ymax], [H - MARGIN.b, MARGIN.t]);
        const ranged = points.filter((p) => p.p10 !== null && p.p90 !== null);
        const step = (width - MARGIN.l - MARGIN.r) / 12;
        const select = (month: number) => {
          // Seasonality has no year of its own: choose that month of the latest year when it has a value.
          if (latestYear !== null && points[month - 1].latest !== null) link.select(monthKey(latestYear, month));
        };
        return (
          <svg width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={d.title} onPointerLeave={() => link.setHover(null)} data-testid="season-svg">
            <YAxis ticks={niceTicks(0, ymax, 4)} y={y} width={width} />
            {focus !== null && (
              <rect className="d-month-hover" x={x(focus) - step / 2} y={MARGIN.t} width={step} height={H - MARGIN.t - MARGIN.b} />
            )}
            <path
              className="d-band-range"
              d={bandPath(
                ranged.map((p) => ({ x: x(p.month), y: y(p.p90!) })),
                ranged.map((p) => ({ x: x(p.month), y: y(p.p10!) })),
              )}
            />
            {linePaths(points.map((p) => (p.median === null ? null : { x: x(p.month), y: y(p.median) }))).map((dd, i) => (
              <path key={`m${i}`} className="d-line d-line-median" d={dd} />
            ))}
            {linePaths(points.map((p) => (p.latest === null ? null : { x: x(p.month), y: y(p.latest) }))).map((dd, i) => (
              <g key={`l${i}`}>
                <path className="d-line-casing" d={dd} />
                <path className="d-line d-line-latest" d={dd} />
              </g>
            ))}
            {points.map((p) =>
              p.latest === null ? null : <circle key={p.month} className="d-dot-latest" cx={x(p.month)} cy={y(p.latest)} r={4} />,
            )}
            {points.map((p) => (
              <g key={p.month}>
                <XLabel x={x(p.month)} y={H - 8} text={monthName(p.month)} />
                <rect
                  className="d-hit"
                  x={x(p.month) - step / 2}
                  y={MARGIN.t}
                  width={step}
                  height={H - MARGIN.t - MARGIN.b}
                  onPointerEnter={() => link.setHover({ year: null, month: p.month })}
                  onClick={() => select(p.month)}
                  data-month={p.month}
                />
              </g>
            ))}
          </svg>
        );
      }}
    </ChartFrame>
  );
}
