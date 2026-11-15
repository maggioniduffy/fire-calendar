import { useId } from "react";
import { hasReported } from "../state/inspectorModel";
import { useT } from "../state/prefs";
import { useSelection } from "../state/SelectionContext";
import type { UiScale } from "../state/selection";

const OPTIONS: readonly UiScale[] = ["reported", "modis_eq", "viirs_eq"];

/**
 * Series choice (left panel). "Reportado" shows the per-sensor reported columns of `/calendar`; it is disabled,
 * with its reason, when the area has none. MODIS-eq / VIIRS-eq change the `scale` of the request.
 */
export function SeriesSection() {
  const t = useT();
  const { state, dispatch, data } = useSelection();
  const reasonId = useId();
  const reportedOff = data.status === "ready" && !hasReported(data.calendar);

  return (
    <div className="stack" data-testid="series">
      <h3 className="card-title">{t.series.title}</h3>
      <div className="segmented stacked" role="group" aria-label={t.series.group}>
        {OPTIONS.map((scale) => {
          const off = scale === "reported" && reportedOff;
          return (
            <button
              key={scale}
              type="button"
              aria-pressed={state.scale === scale}
              disabled={off}
              aria-describedby={off ? reasonId : undefined}
              data-testid={`series-${scale}`}
              onClick={() => dispatch({ type: "setScale", scale })}
            >
              {t.series[scale]}
            </button>
          );
        })}
      </div>
      {reportedOff && (
        <p className="muted" id={reasonId} data-testid="series-reason">
          {t.series.reportedUnavailable}
        </p>
      )}
    </div>
  );
}
