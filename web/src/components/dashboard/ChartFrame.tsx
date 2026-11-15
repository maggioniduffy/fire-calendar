import { useEffect, useRef, useState, type ReactNode } from "react";
import { downloadCsv, downloadPng } from "../../charts/dashboard-export";
import { toCsv } from "../../charts/dashboard-scales";
import { format } from "../../i18n";
import { useT } from "../../state/prefs";

export const CHART_HEIGHT = 240;

interface Props {
  /** Stable id: test ids and file names. */
  id: string;
  title: string;
  /** "Source: … · Period: … · Series: …" */
  source: string;
  /** Rows exactly as plotted; header names are data names, not translated. */
  csv: { header: string[]; rows: unknown[][] };
  legend?: ReactNode;
  note?: ReactNode;
  readout?: ReactNode;
  /** The stats answer for the chosen month is still loading: the chart shows the previous one, dimmed. */
  pending?: boolean;
  /** Receives the measured width of the chart area. */
  children: (width: number) => ReactNode;
}

/** Card around one chart: title, source line, legend, the SVG, notes and the PNG / CSV buttons. */
export function ChartFrame({ id, title, source, csv, legend, note, readout, pending, children }: Props) {
  const t = useT();
  const area = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = area.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const exportCsv = () => downloadCsv(toCsv(csv.header, csv.rows), `firecal-${id}.csv`);
  const exportPng = () => {
    const svg = area.current?.querySelector("svg");
    if (!svg) return;
    setFailed(false);
    downloadPng(svg, title, source, `firecal-${id}.png`).catch(() => setFailed(true));
  };

  return (
    <section className={pending ? "dash-chart is-pending" : "dash-chart"} aria-busy={pending || undefined} aria-labelledby={`dash-${id}-title`} data-testid={`chart-${id}`}>
      <header className="dash-chart-head">
        <h3 id={`dash-${id}-title`} className="dash-chart-title">
          {title}
        </h3>
        <div className="dash-export">
          <button
            type="button"
            className="btn"
            onClick={exportCsv}
            aria-label={format(t.dashboard.downloadCsv, { chart: title })}
            data-testid={`chart-${id}-csv`}
          >
            {t.dashboard.csv}
          </button>
          <button
            type="button"
            className="btn"
            onClick={exportPng}
            aria-label={format(t.dashboard.downloadPng, { chart: title })}
            data-testid={`chart-${id}-png`}
          >
            {t.dashboard.png}
          </button>
        </div>
      </header>
      <p className="dash-source muted num" data-testid={`chart-${id}-source`}>
        {source}
      </p>
      {legend}
      <div ref={area} className="dash-area">
        {children(width)}
      </div>
      <p className="dash-readout num" aria-live="off">
        {readout ?? t.dashboard.readoutHint}
      </p>
      {note}
      {failed && (
        <p className="dash-error" role="alert">
          {t.dashboard.exportFailed}
        </p>
      )}
    </section>
  );
}

export interface LegendItem {
  label: string;
  /** CSS class of the swatch (see dashboard.css). */
  swatch: string;
}

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="dash-legend">
      {items.map((it) => (
        <li key={it.swatch}>
          <svg width="22" height="10" aria-hidden="true">
            <rect x="0" y="0" width="22" height="10" rx="2" className={it.swatch} />
          </svg>
          <span>{it.label}</span>
        </li>
      ))}
    </ul>
  );
}
