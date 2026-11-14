import { useId, useState } from "react";
import { useT } from "../state/prefs";

/** Area, period and sensor. Placeholders until SA4.1 and phase 3 land. */
export function LeftPanel() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <aside className="left card" data-testid="left-panel" data-open={open} aria-labelledby={`${bodyId}-title`}>
      <div className="card-head">
        <h2 className="card-title" id={`${bodyId}-title`}>
          {t.panel.title}
        </h2>
        <button
          type="button"
          className="drawer-toggle"
          aria-expanded={open}
          aria-controls={bodyId}
          aria-label={open ? t.panel.close : t.panel.open}
          onClick={() => setOpen((o) => !o)}
          data-testid="drawer-toggle"
        >
          <span aria-hidden="true" className="chevron" />
        </button>
      </div>
      <dl className="rows drawer-body" id={bodyId}>
        <div className="row">
          <dt>{t.panel.area}</dt>
          <dd>{t.panel.areaDefault}</dd>
        </div>
        <div className="row">
          <dt>{t.panel.period}</dt>
          <dd className="pending">{t.panel.pending}</dd>
        </div>
        <div className="row">
          <dt>{t.panel.sensor}</dt>
          <dd className="pending">{t.panel.pending}</dd>
        </div>
      </dl>
    </aside>
  );
}
