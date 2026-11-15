import { format } from "../i18n";
import { areaName } from "../state/areaName";
import {
  buildInspectorModel,
  formatCount,
  formatMonth,
  formatPercent,
  formatPeriod,
  NO_VALUE,
} from "../state/inspectorModel";
import { statusView } from "../state/monthStatus";
import { usePrefs, useT } from "../state/prefs";
import { useSelection } from "../state/SelectionContext";
import { Downloads } from "./Downloads";

/** Key figures of the selected area and month (SA3.4): `stats.key_figures`, `stats.anomaly` and `calendar.months`. */
function AreaFigures() {
  const t = useT();
  const { lang } = usePrefs();
  const { state, data } = useSelection();
  const heading = (month: string) => format(t.inspector.heading, { area: areaName(state.area, t), month });

  if (data.status !== "ready" || data.statsPending) {
    return (
      <>
        <h2 className="card-title" id="inspector-title">
          {areaName(state.area, t)}
        </h2>
        <p className={data.status === "error" ? "field-error" : "muted"} data-testid="inspector-status">
          {data.status === "error" ? t.inspector.dataError : t.inspector.dataLoading}
        </p>
      </>
    );
  }

  const { calendar, stats } = data;
  const model = buildInspectorModel(calendar, stats, state.scale);
  const { anomaly, key_figures: kf, meta } = stats;
  const note = lang === "en" ? calendar.band.note_en : calendar.band.note_es;
  const estimatedNote = lang === "en" ? meta.estimated_note_en : meta.estimated_note_es;
  const column = model.row ? model.row[state.scale === "reported" ? "viirs_eq" : state.scale] : null;
  const mostActive = kf.most_active_month;
  const status = statusView(model.row, state.scale, t);
  const provisionalNote =
    (lang === "en" ? meta.provisional_note_en : meta.provisional_note_es) || t.status.provisionalFallbackNote;

  return (
    <>
      <h2 className="card-title" id="inspector-title" data-testid="inspector-heading">
        {heading(model.ref ? formatMonth(model.ref, lang) : t.inspector.noMonth)}
      </h2>
      {status.provisional && (
        <div className="stack" data-testid="provisional-box">
          <p>
            <span className="flag status-badge" data-testid="provisional-badge">
              {t.status.provisional}
            </span>
          </p>
          <p className="muted" data-testid="provisional-note">
            {provisionalNote}
          </p>
        </div>
      )}
      <p className="muted num" data-testid="inspector-range">
        {calendar.period.start} – {calendar.period.end}
      </p>
      <dl className="rows figures" data-testid="area-figures">
        {model.harmonized ? (
          <div className="row">
            <dt>{t.inspector.monthCount}</dt>
            <dd className="num" data-testid="fig-count">
              {formatCount(anomaly.value ?? column, lang)}
              {model.estimated && <span className="flag">{t.inspector.estimatedTag}</span>}
            </dd>
          </div>
        ) : (
          <>
            <div className="row">
              <dt>{t.inspector.monthCountModis}</dt>
              <dd className="num" data-testid="fig-modis">
                {formatCount(model.reported?.modis, lang)}
              </dd>
            </div>
            <div className="row">
              <dt>{t.inspector.monthCountViirs}</dt>
              <dd className="num" data-testid="fig-viirs">
                {formatCount(model.reported?.viirs, lang)}
              </dd>
            </div>
          </>
        )}
        {model.harmonized && (
          <>
            <div className="row">
              <dt>{t.inspector.median}</dt>
              <dd className="num" data-testid="fig-median">
                {formatCount(anomaly.median, lang)}
              </dd>
            </div>
            <div className="row">
              <dt>{t.inspector.anomaly}</dt>
              <dd className="num" data-testid="fig-anomaly">
                {anomaly.percentile === null
                  ? NO_VALUE
                  : format(t.inspector.anomalyValue, {
                      pct: formatPercent(anomaly.pct_anomaly, lang),
                      p: Math.round(anomaly.percentile),
                    })}
              </dd>
            </div>
            <div className="row">
              <dt>{t.inspector.mostActive}</dt>
              <dd className="num" data-testid="fig-most-active">
                {mostActive
                  ? format(t.inspector.mostActiveValue, { month: formatMonth(mostActive, lang), n: formatCount(mostActive.value, lang) })
                  : NO_VALUE}
              </dd>
            </div>
          </>
        )}
        <div className="row">
          <dt>{t.inspector.source}</dt>
          <dd data-testid="fig-source">
            <span lang="en">{meta.source}</span>
            {lang === "es" && (
              <span className="muted" data-testid="source-lang-note">
                {" "}
                ({t.status.sourceInEnglish})
              </span>
            )}
          </dd>
        </div>
        {status.sourceText && (
          <div className="row">
            <dt>{t.status.sourceLevel}</dt>
            <dd data-testid="fig-source-level">{status.sourceText}</dd>
          </div>
        )}
        <div className="row">
          <dt>{t.inspector.dataPeriod}</dt>
          <dd className="num" data-testid="fig-period">
            {formatPeriod(meta.period)}
          </dd>
        </div>
        <div className="row">
          <dt>{t.inspector.calibration}</dt>
          <dd className="num" data-testid="fig-calibration">
            {meta.calibration_version ?? NO_VALUE}
          </dd>
        </div>
      </dl>
      {status.drift && (
        <p className="muted" data-testid="drift-note">
          {t.status.drift}
        </p>
      )}
      {!model.harmonized && (
        <p className="muted" data-testid="reported-note">
          {t.inspector.reportedNote}
        </p>
      )}
      {model.estimated && (
        <div className="stack" data-testid="estimated-note">
          <p className="muted">{estimatedNote}</p>
          {!calendar.band.verified && (
            <p className="muted" data-testid="band-note">
              {format(t.inspector.bandUnverified, { note })}
            </p>
          )}
        </div>
      )}
    </>
  );
}

export function Inspector() {
  return (
    <section className="inspector card" aria-labelledby="inspector-title" data-testid="inspector">
      <AreaFigures />
      <Downloads />
    </section>
  );
}
