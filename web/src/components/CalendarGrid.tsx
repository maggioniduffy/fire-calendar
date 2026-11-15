import { useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { CalendarPayload } from "../api/types";
import { divergingColor, sequentialColor } from "../charts/scales";
import { format } from "../i18n";
import { usePrefs, useT } from "../state/prefs";
import { cellAt, neighbour, ymKey, type CalendarCell, type CalendarGrid as Grid } from "./calendarModel";
import "./Calendar.css";

export type CalendarMode = "count" | "anomaly";

interface Props {
  grid: Grid;
  mode: CalendarMode;
  meta: CalendarPayload["meta"];
  /** Chosen month "YYYY-MM" (already defaulted to the latest with data). */
  selected: string | null;
  onSelect: (ym: string) => void;
}

interface Tip {
  ym: string;
  x: number;
  y: number;
}

/** Month name for a "YYYY-MM"; `style` "long" for sentences and tooltips, "narrow" for column heads. */
export function monthName(lang: string, month: number, style: "long" | "narrow" | "short" = "long"): string {
  return new Intl.DateTimeFormat(lang, { month: style, timeZone: "UTC" }).format(new Date(Date.UTC(2001, month - 1, 1)));
}

export function CalendarGrid({ grid, mode, meta, selected, onSelect }: Props) {
  const t = useT();
  const { theme, lang } = usePrefs();
  const wrap = useRef<HTMLDivElement>(null);
  const [focusYm, setFocusYm] = useState<string | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);

  const num = (v: number) => v.toLocaleString(lang, { maximumFractionDigits: 1 });
  const label = (c: CalendarCell) => `${monthName(lang, c.month)} ${c.year}`;
  const roving = focusYm && grid.cells.has(focusYm) ? focusYm : selected ?? ymKey(grid.years[0], 1);

  const colorOf = (c: CalendarCell) =>
    mode === "count" ? sequentialColor(c.value, grid.max, theme) : divergingColor(c.ratio, theme);

  const show = (el: HTMLElement, ym: string) => {
    const w = wrap.current?.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    if (w) setTip({ ym, x: r.left - w.left + r.width / 2, y: r.top - w.top });
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
  const tipRatio = tipCell?.ratio ?? null;

  return (
    <div className="cal-wrap" ref={wrap} onMouseLeave={() => setTip(null)}>
      <div className="cal-grid" role="grid" aria-label={t.calendar.gridLabel} data-testid="calendar-grid" data-mode={mode}>
        <div className="cal-row" role="row">
          <span className="cal-corner" role="columnheader" aria-hidden="true" />
          {Array.from({ length: 12 }, (_, i) => (
            <span key={i} className="cal-colhead" role="columnheader" aria-label={monthName(lang, i + 1)}>
              {monthName(lang, i + 1, "narrow")}
            </span>
          ))}
        </div>
        {grid.years.map((year) => (
          <div className="cal-row" role="row" key={year}>
            <span className="cal-year num" role="rowheader">
              {year}
            </span>
            {Array.from({ length: 12 }, (_, i) => {
              const c = cellAt(grid, ymKey(year, i + 1));
              const color = colorOf(c);
              const isSel = c.ym === selected;
              const style: CSSProperties | undefined = color ? { backgroundColor: color } : undefined;
              return (
                <div
                  key={c.ym}
                  role="gridcell"
                  className={`cal-cell${color ? "" : " nodata"}${isSel ? " chosen" : ""}`}
                  style={style}
                  tabIndex={c.ym === roving ? 0 : -1}
                  aria-selected={isSel}
                  aria-label={
                    c.value === null
                      ? format(t.calendar.cellLabelNone, { month: label(c) })
                      : format(t.calendar.cellLabel, { month: label(c), count: num(c.value) })
                  }
                  aria-describedby={tip?.ym === c.ym ? "cal-tip" : undefined}
                  data-ym={c.ym}
                  data-value={c.value ?? ""}
                  data-ratio={c.ratio ?? ""}
                  data-color={color ?? ""}
                  data-status={c.status}
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

      {tip && tipCell && (
        <div className="cal-tip" id="cal-tip" role="tooltip" data-testid="calendar-tooltip" style={{ left: tip.x, top: tip.y }}>
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
          <span className="muted">
            {t.calendar.source}: {meta.source} · {t.calendar.period}: <span className="num">{meta.period}</span>
          </span>
        </div>
      )}
    </div>
  );
}
