import { useMemo, useState } from "react";
import type { CalendarPayload } from "../api/types";
import { divergingGradient, sequentialGradient } from "../charts/scales";
import { format } from "../i18n";
import { modisScale } from "../state/monthStatus";
import { usePrefs, useT } from "../state/prefs";
import { useSelection } from "../state/SelectionContext";
import { CalendarGrid, monthName, type CalendarMode } from "./CalendarGrid";
import { buildGrid } from "./calendarModel";
import "./Calendar.css";

function EnsoLegend({ enso }: { enso: CalendarPayload["enso"] }) {
  const t = useT();
  const { lang } = usePrefs();
  const e = t.calendar.enso;
  if (!enso) {
    return (
      <p className="enso-missing muted" data-testid="enso-missing">
        {e.missing}
      </p>
    );
  }
  return (
    <div className="cal-legend enso-legend" data-testid="enso-legend">
      <span className="cal-legend-title">{e.legend}</span>
      <ul className="enso-swatches">
        {(["nino", "nina", "neutral"] as const).map((p) => (
          <li key={p}>
            <span className="cal-swatch enso-sw" data-phase={p} aria-hidden="true" /> {e[p]}
          </li>
        ))}
        <li>
          <span className="cal-swatch nodata" aria-hidden="true" /> {e.noOni}
        </li>
      </ul>
      <span className="muted num" data-testid="enso-source">
        {format(e.src, { source: enso.source, start: enso.period.start, end: enso.period.end })}
      </span>
      <span className="muted" data-testid="enso-note">
        {lang === "en" ? enso.note_en : enso.note_es}
      </span>
    </div>
  );
}

const modes: readonly CalendarMode[] = ["count", "anomaly"];

/** Calendar card: main finding, year × month heatmap (count or anomaly), legend. */
export function CalendarStrip() {
  const t = useT();
  const { theme, lang } = usePrefs();
  const { state, dispatch, data } = useSelection();
  const [mode, setMode] = useState<CalendarMode>("count");
  const grid = useMemo(() => (data.status === "ready" ? buildGrid(data.calendar, data.stats) : null), [data]);

  const body = () => {
    if (data.status === "loading") return <p className="muted">{t.calendar.loading}</p>;
    if (data.status === "error") return <p className="muted">{format(t.calendar.error, { message: data.message })}</p>;
    const { calendar, stats } = data;
    const best = stats.key_figures.most_active_month;
    const num = (v: number) => v.toLocaleString(lang, { maximumFractionDigits: 1 });
    // Sentence only from payload numbers: the most active month (stats.key_figures) and its count.
    const finding =
      best && best.value !== null
        ? format(t.calendar.finding, {
            month: `${monthName(lang, best.month)} ${best.year}`,
            count: num(best.value),
            scale: t.calendar.scaleLabel[calendar.scale],
          })
        : t.calendar.findingNone;
    const selected = state.month ?? grid?.latest ?? null;
    return (
      <>
        <div className="cal-side">
          <h2 className="card-title" id="calendar-title">
            {t.calendar.title}
          </h2>
        <p className="cal-finding" data-testid="calendar-finding">
          {finding}
        </p>
        <div className="segmented" role="group" aria-label={t.calendar.mode}>
          {modes.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              data-testid={`calendar-mode-${m}`}
              onClick={() => setMode(m)}
            >
              {m === "count" ? t.calendar.modeCount : t.calendar.modeAnomaly}
            </button>
          ))}
        </div>
        <div className="cal-legend" data-testid="calendar-legend" data-mode={mode}>
          <span className="cal-legend-title">{mode === "count" ? t.calendar.legendCount : t.calendar.legendAnomaly}</span>
          <span className="cal-legend-bar">
            <span className="muted">{mode === "count" ? "0" : `${t.calendar.below} −100 %`}</span>
            <span
              className="cal-ramp"
              aria-hidden="true"
              style={{ background: mode === "count" ? sequentialGradient(theme) : divergingGradient(theme) }}
            />
            <span className="muted num">{mode === "count" ? num(grid?.max ?? 0) : `${t.calendar.above} +100 %`}</span>
          </span>
          <span className="cal-legend-nodata">
            <span className="cal-swatch nodata" aria-hidden="true" /> {t.calendar.noData}
          </span>
          {grid?.hasProvisional && (
            <span className="cal-legend-nodata" data-testid="legend-provisional">
              <span className="cal-swatch provisional" aria-hidden="true" /> {t.status.legendProvisional}
            </span>
          )}
          {grid?.hasDrift && modisScale(calendar.scale) && (
            <span className="cal-legend-note muted" data-testid="legend-drift">
              {t.status.legendDrift}
            </span>
          )}
        </div>
        </div>
        <div className="cal-main">
          {grid && grid.years.length > 0 && (
            <CalendarGrid grid={grid} mode={mode} meta={calendar.meta} scale={calendar.scale} enso={calendar.enso} selected={selected} onSelect={(month) => dispatch({ type: "setMonth", month })} />
          )}
          <EnsoLegend enso={calendar.enso} />
        </div>
      </>
    );
  };

  return (
    <section className="calendar card" aria-labelledby="calendar-title" data-testid="calendar-strip">
      {data.status === "ready" ? (
        body()
      ) : (
        <div className="cal-side">
          <h2 className="card-title" id="calendar-title">
            {t.calendar.title}
          </h2>
          {body()}
        </div>
      )}
    </section>
  );
}
