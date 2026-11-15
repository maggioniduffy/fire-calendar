import { useMemo, useState } from "react";
import type { CalendarPayload, EnsoPhase, StatsPayload } from "../../api/types";
import { linear, monthKey, niceMax, niceTicks, seasonality } from "../../charts/dashboard-scales";
import { format } from "../../i18n";
import { usePrefs, useT } from "../../state/prefs";
import { MARGIN, XLabel, YAxis, useNumberFormat } from "./Axes";
import { CHART_HEIGHT, ChartFrame, Legend } from "./ChartFrame";
import { bandPath, linePaths, useMonthLink } from "./link";

const PHASES: readonly EnsoPhase[] = ["nino", "nina", "neutral"];
/** Medians from fewer years than this are drawn hollow and labelled "few years". */
const FEW_YEARS = 3;

export function SeasonChart({ cal, stats, source, pending }: { cal: CalendarPayload; stats: StatsPayload; source: string; pending: boolean }) {
  const t = useT();
  const { lang } = usePrefs();
  const fmt = useNumberFormat();
  const link = useMonthLink();
  const { latestYear, points } = useMemo(() => seasonality(cal, stats), [cal, stats]);
  const d = t.dashboard.season;
  const enso = cal.enso;
  const [byPhase, setByPhase] = useState(false);
  const phaseOn = byPhase && enso !== null;
  const phaseRows = useMemo(() => enso?.by_phase ?? [], [enso]);
  const phaseName = t.calendar.enso;
  const monthName = useMemo(() => {
    const f = new Intl.DateTimeFormat(lang, { month: "short", timeZone: "UTC" });
    return (m: number) => f.format(new Date(Date.UTC(2001, m - 1, 1)));
  }, [lang]);
  const base = stats.climatology.baseline_years;
  const y0 = base.length ? Math.min(...base) : "";
  const y1 = base.length ? Math.max(...base) : "";
  const latestLabel = latestYear === null ? "" : format(d.latest, { year: latestYear });

  const csv = phaseOn
    ? {
        header: ["month", "enso_phase", "median", "p25", "p75", "n_years"],
        rows: phaseRows.map((r) => [r.month, r.phase, r.median, r.p25, r.p75, r.n_years]),
      }
    : {
        header: ["month", "median", "p10", "p25", "p75", "p90", "n_years", "latest_year", "latest_value"],
        rows: points.map((p) => [p.month, p.median, p.p10, p.p25, p.p75, p.p90, p.nYears, latestYear, p.latest]),
      };
  // A month of the latest year the user hovers/selected elsewhere maps to its calendar month here.
  const focus = link.hover ? link.hover.month : (link.selected?.month ?? null);
  const shown = points.find((p) => p.month === focus);
  const phaseReadout = focus !== null && (
    <>
      {monthName(focus)} ·{" "}
      {PHASES.map((ph) => {
        const r = phaseRows.find((x) => x.month === focus && x.phase === ph);
        return r && r.median !== null ? `${phaseName[ph]} ${fmt(r.median)} (${r.n_years}${r.n_years < FEW_YEARS ? `, ${d.ensoFew}` : ""})` : `${phaseName[ph]} ${t.calendar.noData}`;
      }).join(" · ")}
    </>
  );
  const readout = phaseOn ? (
    focus !== null ? phaseReadout : undefined
  ) : shown ? (
    <>
      {monthName(shown.month)} · {d.median} {fmt(shown.median)} ({d.range} {fmt(shown.p10)}–{fmt(shown.p90)}; {d.normal} {fmt(shown.p25)}–{fmt(shown.p75)})
      {shown.latest !== null ? ` · ${latestLabel} ${fmt(shown.latest)}` : ""}
    </>
  ) : undefined;

  return (
    <ChartFrame
      id="season"
      title={d.title}
      source={source}
      pending={pending}
      csv={csv}
      readout={readout}
      legend={
        <>
          {enso && (
            <button type="button" className="btn dash-toggle" aria-pressed={byPhase} onClick={() => setByPhase((v) => !v)} data-testid="season-enso-toggle">
              {d.ensoToggle}
            </button>
          )}
          <Legend
            items={
              phaseOn
                ? [
                    { label: d.range, swatch: "sw-range" },
                    { label: d.normal, swatch: "sw-normal" },
                    ...PHASES.map((ph) => ({ label: phaseName[ph], swatch: `sw-enso-${ph}` })),
                    { label: d.ensoFew, swatch: "sw-few" },
                  ]
                : [
                    { label: d.range, swatch: "sw-range" },
                    { label: d.normal, swatch: "sw-normal" },
                    { label: d.median, swatch: "sw-median" },
                    ...(latestYear !== null ? [{ label: latestLabel, swatch: "sw-latest" }] : []),
                  ]
            }
          />
        </>
      }
      note={
        <p className="dash-note muted">
          {format(d.note, { y0, y1, method: stats.climatology.quantile_method })}
          {phaseOn && enso ? ` ${format(d.ensoNote, { source: `${enso.source} ${enso.period.start}–${enso.period.end}` })}` : ""}
        </p>
      }
    >
      {(width) => {
        const H = CHART_HEIGHT;
        const x = linear([1, 12], [MARGIN.l + 12, width - MARGIN.r - 12]);
        const ymax = niceMax(Math.max(1, ...points.flatMap((p) => [p.p90, p.p75, p.median, p.latest]).concat(phaseOn ? phaseRows.map((r) => r.p75) : []).map((v) => v ?? 0)));
        const y = linear([0, ymax], [H - MARGIN.b, MARGIN.t]);
        const ranged = points.filter((p) => p.p10 !== null && p.p90 !== null);
        const normal = points.filter((p) => p.p25 !== null && p.p75 !== null);
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
            <path
              className="d-band-normal"
              d={bandPath(
                normal.map((p) => ({ x: x(p.month), y: y(p.p75!) })),
                normal.map((p) => ({ x: x(p.month), y: y(p.p25!) })),
              )}
            />
            {!phaseOn &&
              linePaths(points.map((p) => (p.median === null ? null : { x: x(p.month), y: y(p.median) }))).map((dd, i) => (
                <path key={`m${i}`} className="d-line d-line-median" d={dd} />
              ))}
            {!phaseOn &&
              linePaths(points.map((p) => (p.latest === null ? null : { x: x(p.month), y: y(p.latest) }))).map((dd, i) => (
                <g key={`l${i}`}>
                  <path className="d-line-casing" d={dd} />
                  <path className="d-line d-line-latest" d={dd} />
                </g>
              ))}
            {!phaseOn &&
              points.map((p) =>
                p.latest === null ? null : <circle key={p.month} className="d-dot-latest" cx={x(p.month)} cy={y(p.latest)} r={4} />,
              )}
            {phaseOn &&
              PHASES.map((ph) => {
                const rows = phaseRows.filter((r) => r.phase === ph && r.median !== null);
                const byMonth = new Map(rows.map((r) => [r.month, r]));
                const line = linePaths(Array.from({ length: 12 }, (_, i) => byMonth.get(i + 1)).map((r) => (r ? { x: x(r.month), y: y(r.median!) } : null)));
                return (
                  <g key={ph} className={`d-phase d-phase-${ph}`} data-testid={`season-phase-${ph}`} role="img" aria-label={`${d.ensoLabel}: ${phaseName[ph]}`}>
                    {line.map((dd, i) => (
                      <path key={i} className="d-line d-phase-line" d={dd} />
                    ))}
                    {rows.map((r) => {
                      const few = r.n_years < FEW_YEARS;
                      const text = few
                        ? format(d.ensoFewPoint, { phase: phaseName[ph], month: monthName(r.month), n: r.n_years })
                        : format(d.ensoPoint, { phase: phaseName[ph], median: fmt(r.median), n: r.n_years });
                      return (
                        <circle key={r.month} className={few ? "d-phase-dot few" : "d-phase-dot"} cx={x(r.month)} cy={y(r.median!)} r={4} data-few={few} data-month={r.month}>
                          <title>{text}</title>
                        </circle>
                      );
                    })}
                  </g>
                );
              })}
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
