import { splitPeriod, type Hotspot, type PointLayer } from "../layers/manifest";
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
import { usePrefs, useT } from "../state/prefs";
import { useSelection } from "../state/SelectionContext";
import { Downloads } from "./Downloads";

interface Props {
  layer: PointLayer | null;
  status: "loading" | "ready" | "error";
  selected: Hotspot | null;
  onClear: () => void;
}

const coord = (v: number) => v.toFixed(2);

/** Key figures of the selected area and month (SA3.4): `stats.key_figures`, `stats.anomaly` and `calendar.months`. */
function AreaFigures() {
  const t = useT();
  const { lang } = usePrefs();
  const { state, data } = useSelection();
  const heading = (month: string) => format(t.inspector.heading, { area: areaName(state.area, t), month });

  if (data.status !== "ready") {
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

  return (
    <>
      <h2 className="card-title" id="inspector-title" data-testid="inspector-heading">
        {heading(model.ref ? formatMonth(model.ref, lang) : t.inspector.noMonth)}
      </h2>
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
          <dd data-testid="fig-source">{meta.source}</dd>
        </div>
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

export function Inspector({ layer, status, selected, onClear }: Props) {
  const t = useT();
  const m = layer?.manifest;
  const confidence = (c: string) =>
    (t.inspector.confidenceLevels as Record<string, string>)[c] ?? c;

  return (
    <section className="inspector card" aria-labelledby="inspector-title" data-testid="inspector">
      <AreaFigures />

      <h3 className="card-title detail-title">{t.inspector.title}</h3>
      {selected ? (
        <>
          <dl className="rows" data-testid="selected-hotspot">
            <div className="row">
              <dt>{t.inspector.date}</dt>
              <dd className="num">{selected.date}</dd>
            </div>
            <div className="row">
              <dt>{t.inspector.sensor}</dt>
              <dd>{selected.sensor}</dd>
            </div>
            <div className="row">
              <dt>{t.inspector.frp}</dt>
              <dd className="num">
                {selected.frp.toFixed(1)} {t.units.mw}
              </dd>
            </div>
            <div className="row">
              <dt>{t.inspector.confidence}</dt>
              <dd className="num">{confidence(selected.confidence)}</dd>
            </div>
            <div className="row">
              <dt>{t.inspector.lat}</dt>
              <dd className="num">{coord(selected.lat)}</dd>
            </div>
            <div className="row">
              <dt>{t.inspector.lon}</dt>
              <dd className="num">{coord(selected.lon)}</dd>
            </div>
          </dl>
          <button type="button" className="btn" onClick={onClear}>
            {t.inspector.clear}
          </button>
        </>
      ) : (
        <p className="muted">
          {status === "loading" ? t.inspector.loading : status === "error" ? t.inspector.error : t.inspector.empty}
        </p>
      )}

      {m && (
        <dl className="rows provenance" data-testid="layer-provenance">
          <div className="row">
            <dt>{t.inspector.layer}</dt>
            <dd>
              {m.title}
              {m.experimental && <span className="flag">{t.inspector.experimental}</span>}
            </dd>
          </div>
          <div className="row">
            <dt>{t.inspector.source}</dt>
            <dd>{m.source}</dd>
          </div>
          <div className="row">
            <dt>{t.inspector.period}</dt>
            <dd className="num">{splitPeriod(m.period).join(" – ")}</dd>
          </div>
          <div className="row">
            <dt>{t.inspector.license}</dt>
            <dd>{m.license}</dd>
          </div>
        </dl>
      )}

      <Downloads />
    </section>
  );
}
