import { useMemo, useState } from "react";
import { parseMonthKey } from "../../charts/dashboard-scales";
import { format } from "../../i18n";
import { usePrefs, useT } from "../../state/prefs";
import { useSelection } from "../../state/SelectionContext";
import { useNumberFormat } from "./Axes";
import { AnomalyChart } from "./AnomalyChart";
import { LinkContext, type Hover, type MonthLink } from "./link";
import { MonthlyChart } from "./MonthlyChart";
import { SeasonChart } from "./SeasonChart";
import { YearlyChart } from "./YearlyChart";
import "./dashboard.css";

/**
 * Dashboard tab (SA4.8): charts of the selected area built only from the /calendar and /stats payloads.
 * Not shown because no payload provides them yet: day/night split and FRP distribution, ENSO phase.
 */
export function Dashboard() {
  const t = useT();
  const { lang } = usePrefs();
  const fmt = useNumberFormat();
  const { state, dispatch, data } = useSelection();
  const [hover, setHover] = useState<Hover | null>(null);

  const link = useMemo<MonthLink>(
    () => ({
      hover,
      setHover,
      selected: state.month ? parseMonthKey(state.month) : null,
      select: (key) => dispatch({ type: "setMonth", month: key }),
    }),
    [hover, state.month, dispatch],
  );

  if (data.status === "loading") return <p className="muted">{t.dashboard.loading}</p>;
  if (data.status === "error") return <p role="alert">{t.dashboard.error}</p>;

  const { calendar: cal, stats, statsPending } = data;
  const d = t.dashboard;
  const source = `${d.source}: ${cal.meta.source} · ${d.period}: ${cal.meta.period.replace("/", " – ")} · ${d.series}: ${d.seriesNames[cal.scale]}`;
  const kf = stats.key_figures;

  return (
    <LinkContext.Provider value={link}>
      <div className="dashboard-body" aria-label={d.label} data-testid="dashboard">
        <div className="dash-summary">
          <p className="dash-total-label muted">{d.total}</p>
          <p className="dash-total num" data-testid="dashboard-total">
            {fmt(kf.total)}
          </p>
          <p className="muted num">
            {format(d.totalDetail, { cells: cal.n_cells, start: cal.period.start, end: cal.period.end })}
          </p>
          {kf.includes_estimated && (
            <p className="muted" data-testid="dashboard-estimated">
              {format(d.estimatedIncluded, { n: kf.estimated_months })} {lang === "es" ? cal.meta.estimated_note_es : cal.meta.estimated_note_en}
            </p>
          )}
        </div>
        <div className="dash-grid">
          <MonthlyChart cal={cal} source={source} />
          <YearlyChart cal={cal} source={source} />
          <SeasonChart cal={cal} stats={stats} source={source} pending={statsPending} />
          <AnomalyChart cal={cal} stats={stats} source={source} pending={statsPending} />
        </div>
      </div>
    </LinkContext.Provider>
  );
}
