import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { CalendarPayload, EnsoBlock } from "../api/types";
import { divergingColor, sequentialColor } from "../charts/scales";
import { format } from "../i18n";
import { statusView } from "../state/monthStatus";
import { usePrefs, useT } from "../state/prefs";
import { cellAt, ensoAt, ensoIndex, neighbour, ymKey, type CalendarCell, type CalendarGrid as Grid } from "./calendarModel";
import "./Calendar.css";

export type CalendarMode = "count" | "anomaly";

interface Props {
  grid: Grid;
  mode: CalendarMode;
  meta: CalendarPayload["meta"];
  /** Scale of the payload ("viirs_eq" | "modis_eq"): MODIS drift is only noted where MODIS counts are part of the figure. */
  scale: string;
  /** ENSO block of the payload; null hides the phase strip. */
  enso: EnsoBlock | null;
  /** Chosen month "YYYY-MM" (already defaulted to the latest with data). */
  selected: string | null;
  onSelect: (ym: string) => void;
}

interface Tip {
  ym: string;
  x: number;
  y: number;
  /** Cell too close to the top of the card: draw the tooltip under it instead. */
  below: boolean;
}

/** Year columns narrower than this get a label only every {@link LABEL_EVERY} years (plus the last one). */
const MIN_LABEL_WIDTH = 28;
const LABEL_EVERY = 5;

/** Month name for a "YYYY-MM"; `style` "long" for sentences and tooltips, "narrow" for column heads. */
export function monthName(lang: string, month: number, style: "long" | "narrow" | "short" = "long"): string {
  return new Intl.DateTimeFormat(lang, { month: style, timeZone: "UTC" }).format(new Date(Date.UTC(2001, month - 1, 1)));
}

export function CalendarGrid({ grid, mode, meta, scale, enso, selected, onSelect }: Props) {
  const t = useT();
  const { theme, lang } = usePrefs();
  const wrap = useRef<HTMLDivElement>(null);
  const [focusYm, setFocusYm] = useState<string | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [sparse, setSparse] = useState(false);
  const nYears = grid.years.length;
  const ensoByYm = useMemo(() => ensoIndex(enso), [enso]);

  // Thin the year labels when the columns are too narrow for them (full year stays in aria-label).
  useEffect(() => {
    const el = wrap.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const colWidth = (entry.contentRect.width - 28) / Math.max(1, nYears);
      setSparse(colWidth < MIN_LABEL_WIDTH);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [nYears]);

  const num = (v: number) => v.toLocaleString(lang, { maximumFractionDigits: 1 });
  const label = (c: CalendarCell) => `${monthName(lang, c.month)} ${c.year}`;
  const roving = focusYm && grid.cells.has(focusYm) ? focusYm : selected ?? ymKey(grid.years[0], 1);

  const colorOf = (c: CalendarCell) =>
    mode === "count" ? sequentialColor(c.value, grid.max, theme) : divergingColor(c.ratio, theme);

  const show = (el: HTMLElement, ym: string) => {
    const w = wrap.current?.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    if (!w) return;
    const x = Math.min(Math.max(r.left - w.left + r.width / 2, 100), Math.max(100, w.width - 100));
    const below = r.top - w.top < 110;
    setTip({ ym, x, y: below ? r.bottom - w.top : r.top - w.top, below });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>, c: CalendarCell) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (c.value !== null) onSelect(c.ym);
      return;
    }
    const next = neighbour(grid, c.ym, e.key);
    if (!next) return;
    e.preventDefault();
    wrap.current?.querySelector<HTMLElement>(`[data-ym="${next}"]`)?.focus();
  };

  const tipCell = tip ? cellAt(grid, tip.ym) : null;
  const tipStatus = tipCell && tipCell.value !== null ? statusView(tipCell.statusInfo, scale, t) : null;
  const tipRatio = tipCell?.ratio ?? null;

  return (
    <div className="cal-wrap" ref={wrap} onMouseLeave={() => setTip(null)}>
      <div
        className="cal-grid"
        role="grid"
        aria-label={t.calendar.gridLabel}
        data-testid="calendar-grid"
        data-mode={mode}
        data-sparse={sparse}
        style={{ "--years": nYears } as CSSProperties}
      >
        <div className="cal-row" role="row">
          <span className="cal-corner" role="columnheader" aria-hidden="true" />
          {grid.years.map((year, i) => (
            <span
              key={year}
              className="cal-colhead num"
              role="columnheader"
              aria-label={String(year)}
              data-labelled={i % LABEL_EVERY === 0 || i === nYears - 1}
            >
              {year}
            </span>
          ))}
        </div>
        {Array.from({ length: 12 }, (_, mi) => (
          <div className="cal-row" role="row" key={mi}>
            <span className="cal-rowhead" role="rowheader" aria-label={monthName(lang, mi + 1)}>
              {monthName(lang, mi + 1, "short")}
            </span>
            {grid.years.map((year) => {
              const c = cellAt(grid, ymKey(year, mi + 1));
              const color = colorOf(c);
              const isSel = c.ym === selected;
              const prov = c.value !== null && c.statusInfo.provisional === true;
              const style: CSSProperties | undefined = color ? { backgroundColor: color } : undefined;
              return (
                <div
                  key={c.ym}
                  role="gridcell"
                  className={`cal-cell${color ? "" : " nodata"}${isSel ? " chosen" : ""}${prov ? " provisional" : ""}`}
                  style={style}
                  tabIndex={c.ym === roving ? 0 : -1}
                  aria-selected={isSel}
                  aria-label={
                    c.value === null
                      ? format(t.calendar.cellLabelNone, { month: label(c) })
                      : format(t.calendar.cellLabel, { month: label(c), count: num(c.value) }) +
                        (prov ? `, ${t.status.cellProvisional}` : "")
                  }
                  aria-describedby={tip?.ym === c.ym ? "cal-tip" : undefined}
                  data-ym={c.ym}
                  data-value={c.value ?? ""}
                  data-ratio={c.ratio ?? ""}
                  data-color={color ?? ""}
                  data-status={c.status}
                  data-provisional={prov}
                  onClick={() => c.value !== null && onSelect(c.ym)}
                  onKeyDown={(e) => onKeyDown(e, c)}
                  onMouseEnter={(e) => show(e.currentTarget, c.ym)}
                  onFocus={(e) => {
                    setFocusYm(c.ym);
                    show(e.currentTarget, c.ym);
                  }}
                  onBlur={() => setTip(null)}
                />
              );
            })}
          </div>
        ))}
      </div>

      {enso && (
        <div
          className="enso-strip"
          role="group"
          aria-label={format(t.calendar.enso.strip, { source: enso.source })}
          data-testid="enso-strip"
          style={{ "--years": nYears } as CSSProperties}
        >
          <span className="enso-title" aria-hidden="true">
            {t.calendar.enso.title}
          </span>
          {grid.years.map((year) => (
            <div className="enso-year" key={year} data-year={year}>
              {Array.from({ length: 12 }, (_, mi) => {
                const ym = ymKey(year, mi + 1);
                const m = ensoAt(ensoByYm, ym);
                const base = { month: label({ year, month: mi + 1 } as CalendarCell), source: enso.source, start: enso.period.start, end: enso.period.end };
                const text =
                  m.oni === null || m.phase === null
                    ? format(t.calendar.enso.segNone, base)
                    : format(t.calendar.enso.seg, { ...base, oni: m.oni.toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 2 }), phase: t.calendar.enso[m.phase] });
                return <span key={ym} className="enso-seg" role="img" aria-label={text} title={text} data-enso-ym={ym} data-phase={m.phase ?? "none"} />;
              })}
            </div>
          ))}
        </div>
      )}

      {tip && tipCell && (
        <div className={`cal-tip${tip.below ? " below" : ""}`} id="cal-tip" role="tooltip" data-testid="calendar-tooltip" style={{ left: tip.x, top: tip.y }}>
          <strong>{label(tipCell)}</strong>
          {tipCell.value === null ? (
            <span>{t.calendar.noData}</span>
          ) : (
            <>
              <span>
                {t.calendar.count}: <span className="num" data-testid="tip-count">{num(tipCell.value)}</span>
                {tipCell.status === "estimated" && <em data-testid="tip-estimated"> ({t.calendar.estimated})</em>}
              </span>
              {mode === "anomaly" && (
                <span>
                  {t.calendar.vsMedian}:{" "}
                  {tipRatio === null || tipCell.median === null ? (
                    t.calendar.noData
                  ) : (
                    <span className="num" data-testid="tip-anomaly">
                      {`${tipRatio > 0 ? "+" : ""}${(tipRatio * 100).toLocaleString(lang, { maximumFractionDigits: 0 })} % (${t.calendar.median}: ${num(tipCell.median)})`}
                    </span>
                  )}
                </span>
              )}
            </>
          )}
          {tipStatus?.provisional && (
            <span data-testid="tip-provisional">
              {t.status.provisionalTip}
              {tipStatus.sourceText && (
                <>
                  {" · "}
                  {t.status.sourceLevel}: <span data-testid="tip-source-level">{tipStatus.sourceText}</span>
                </>
              )}
            </span>
          )}
          {tipStatus?.drift && <span data-testid="tip-drift">{t.status.drift}</span>}
          <span className="muted">
            {t.calendar.source}: {meta.source} · {t.calendar.period}: <span className="num">{meta.period}</span>
          </span>
        </div>
      )}
    </div>
  );
}
