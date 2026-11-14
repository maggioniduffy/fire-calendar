import { splitPeriod, type Hotspot, type PointLayer } from "../layers/manifest";
import { useT } from "../state/prefs";

interface Props {
  layer: PointLayer | null;
  status: "loading" | "ready" | "error";
  selected: Hotspot | null;
  onClear: () => void;
}

const coord = (v: number) => v.toFixed(2);

export function Inspector({ layer, status, selected, onClear }: Props) {
  const t = useT();
  const m = layer?.manifest;
  const confidence = (c: string) =>
    (t.inspector.confidenceLevels as Record<string, string>)[c] ?? c;

  return (
    <section className="inspector card" aria-labelledby="inspector-title" data-testid="inspector">
      <h2 className="card-title" id="inspector-title">
        {t.inspector.title}
      </h2>

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
    </section>
  );
}
