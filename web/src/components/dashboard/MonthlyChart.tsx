import { useMemo, type PointerEvent } from "react";
import { linear, monthlySeries, niceMax, niceTicks, type MonthPoint } from "../../charts/dashboard-scales";
import type { CalendarPayload } from "../../api/types";
import { useT, usePrefs } from "../../state/prefs";
import { MARGIN, XLabel, YAxis, useNumberFormat } from "./Axes";
import { CHART_HEIGHT, ChartFrame, Legend, type LegendItem } from "./ChartFrame";
import { bandPath, linePaths, useMonthLink } from "./link";

interface Props {
  cal: CalendarPayload;
  source: string;
}

type Pt = { x: number; y: number };

/** Runs of consecutive points with a value, split where the dashed flag changes (a run starts at the previous point). */
function runs(points: (Pt | null)[], dashed: boolean[]): { d: string; dashed: boolean }[] {
  const out: { pts: (Pt | null)[]; dashed: boolean }[] = [];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (!a || !b) continue;
    const last = out[out.length - 1];
    const prevEnd = last?.pts[last.pts.length - 1];
    if (last && last.dashed === dashed[i] && prevEnd === a) last.pts.push(b);
    else out.push({ pts: [a, b], dashed: dashed[i] });
  }
  return out.map((r) => ({ d: linePaths(r.pts)[0], dashed: r.dashed }));
}

export function MonthlyChart({ cal, source }: Props) {
  const t = useT();
  const { lang } = usePrefs();
  const fmt = useNumberFormat();
  const link = useMonthLink();
  const series = useMemo(() => monthlySeries(cal), [cal]);
  const hasModis = series.some((p) => p.modisReported !== null);
  const hasViirs = series.some((p) => p.viirsReported !== null);
  const hasBand = series.some((p) => p.lo !== null && p.hi !== null);
  const hasEstimated = series.some((p) => p.status === "estimated");
  const d = t.dashboard.monthly;
  const unverified = !cal.band.verified;

  const csv = {
    header: ["month", "harmonized", "status", "band_lo", "band_hi", "modis_reported", "viirs_reported"],
    rows: series.map((p) => [p.key, p.value, p.status, p.lo, p.hi, p.modisReported, p.viirsReported]),
  };

  const legendItems: LegendItem[] = [{ label: `${d.harmonized} (${t.dashboard.seriesNames[cal.scale]})`, swatch: "sw-harmonized" }];
  if (hasEstimated) legendItems.push({ label: d.estimated, swatch: "sw-estimated" });
  if (hasBand) legendItems.push({ label: unverified ? `${d.band} (${d.bandUnverified})` : d.band, swatch: "sw-band" });
  if (hasModis) legendItems.push({ label: d.modisReported, swatch: "sw-modis" });
  if (hasViirs) legendItems.push({ label: d.viirsReported, swatch: "sw-viirs" });

  const hovered: MonthPoint | undefined =
    link.hover?.year != null && link.hover.month !== null ? series.find((p) => p.year === link.hover!.year && p.month === link.hover!.month) : undefined;
  const sel = link.selected ? series.find((p) => p.year === link.selected!.year && p.month === link.selected!.month) : undefined;
  const shown = hovered ?? (link.hover ? undefined : sel);
  const readout = shown ? (
    <>
      {shown.key} · {d.harmonized} {fmt(shown.value)}
      {shown.lo !== null && shown.hi !== null ? ` (${fmt(shown.lo)}–${fmt(shown.hi)})` : ""}
      {shown.modisReported !== null ? ` · ${d.modisReported} ${fmt(shown.modisReported)}` : ""}
      {shown.viirsReported !== null ? ` · ${d.viirsReported} ${fmt(shown.viirsReported)}` : ""}
    </>
  ) : undefined;

  return (
    <ChartFrame
      id="monthly"
      title={d.title}
      source={source}
      csv={csv}
      legend={<Legend items={legendItems} />}
      readout={readout}
      note={
        unverified ? (
          <p className="dash-note muted" data-testid="dash-band-note">
            {lang === "es" ? cal.band.note_es : cal.band.note_en}
          </p>
        ) : undefined
      }
    >
      {(width) => {
        const H = CHART_HEIGHT;
        const idx = series.map((p) => p.index);
        const x = linear([Math.min(...idx), Math.max(...idx)], [MARGIN.l, width - MARGIN.r]);
        const top = Math.max(1, ...series.flatMap((p) => [p.value, p.hi, p.modisReported, p.viirsReported]).map((v) => v ?? 0));
        const ymax = niceMax(top);
        const y = linear([0, ymax], [H - MARGIN.b, MARGIN.t]);
        const pts = series.map((p) => (p.value === null ? null : { x: x(p.index), y: y(p.value) }));
        const dashed = series.map((p) => p.status === "estimated");
        const bandPts = series.filter((p) => p.lo !== null && p.hi !== null);
        const years = [...new Set(series.map((p) => p.year))];
        const every = Math.max(1, Math.ceil((years.length * 44) / (width - MARGIN.l - MARGIN.r)));
        const onMove = (e: PointerEvent<SVGSVGElement>) => {
          const r = e.currentTarget.getBoundingClientRect();
          const px = e.clientX - r.left;
          let best = series[0];
          for (const p of series) if (Math.abs(x(p.index) - px) < Math.abs(x(best.index) - px)) best = p;
          if (best) link.setHover({ year: best.year, month: best.month });
        };
        const marker = (p: MonthPoint | undefined, cls: string, key: string) =>
          p ? (
            <g key={key}>
              <line className="d-sel-casing" x1={x(p.index)} x2={x(p.index)} y1={MARGIN.t} y2={H - MARGIN.b} />
              <line className={cls} x1={x(p.index)} x2={x(p.index)} y1={MARGIN.t} y2={H - MARGIN.b} />
            </g>
          ) : null;
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
            data-testid="monthly-svg"
          >
            <YAxis ticks={niceTicks(0, ymax, 4)} y={y} width={width} />
            {years.map((yr, i) =>
              i % every === 0 ? (
                <XLabel key={yr} x={x(yr * 12)} y={H - 8} text={String(yr)} anchor={i === 0 ? "start" : "middle"} />
              ) : null,
            )}
            {hasBand && (
              <path
                className="d-band"
                d={bandPath(
                  bandPts.map((p) => ({ x: x(p.index), y: y(p.hi!) })),
                  bandPts.map((p) => ({ x: x(p.index), y: y(p.lo!) })),
                )}
              />
            )}
            {link.hover && link.hover.year !== null && link.hover.month === null && (
              <rect
                className="d-year-hover"
                x={x(link.hover.year * 12)}
                width={Math.max(1, x(link.hover.year * 12 + 11) - x(link.hover.year * 12))}
                y={MARGIN.t}
                height={H - MARGIN.t - MARGIN.b}
              />
            )}
            {link.hover && link.hover.year === null &&
              series
                .filter((p) => p.month === link.hover!.month)
                .map((p) => <line key={p.key} className="d-hover-tick" x1={x(p.index)} x2={x(p.index)} y1={MARGIN.t} y2={H - MARGIN.b} />)}
            {hasModis &&
              linePaths(series.map((p) => (p.modisReported === null ? null : { x: x(p.index), y: y(p.modisReported) }))).map((dd, i) => (
                <path key={`m${i}`} className="d-line d-line-modis" d={dd} />
              ))}
            {hasViirs &&
              linePaths(series.map((p) => (p.viirsReported === null ? null : { x: x(p.index), y: y(p.viirsReported) }))).map((dd, i) => (
                <path key={`v${i}`} className="d-line d-line-viirs" d={dd} />
              ))}
            {runs(pts, dashed).map((r, i) => (
              <path key={`h${i}`} className={r.dashed ? "d-line d-line-harm d-dashed" : "d-line d-line-harm"} d={r.d} />
            ))}
            {marker(sel, "d-sel", "sel")}
            {marker(hovered, "d-hover", "hov")}
          </svg>
        );
      }}
    </ChartFrame>
  );
}
