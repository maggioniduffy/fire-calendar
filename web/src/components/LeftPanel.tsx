import { useEffect, useId, useState, type FormEvent } from "react";
import { format } from "../i18n";
import { useSelection } from "../state/SelectionContext";
import {
  DEFAULT_RADIUS_KM,
  parseNumber,
  validateCircle,
  type AreaError,
} from "../state/selection";
import { useT } from "../state/prefs";

type GeoMessage = "geoDenied" | "geoUnavailable" | "geoUnsupported" | AreaError;

/** Enter closes and Esc cancels the polygon being drawn. Capture phase so a focused button does not eat Enter. */
function useDrawKeys(active: boolean, finish: () => void, cancel: () => void) {
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter" && e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Enter") finish();
      else cancel();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [active, finish, cancel]);
}

/** Area choice (preset, coordinates + radius, drawn polygon, my location) and the state of its data. */
export function LeftPanel() {
  const t = useT();
  const { state, dispatch, data } = useSelection();
  const { area, draw } = state;
  const [open, setOpen] = useState(false);
  const [coordsOpen, setCoordsOpen] = useState(false);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [radius, setRadius] = useState(String(DEFAULT_RADIUS_KM));
  const [formError, setFormError] = useState<"missing" | AreaError | null>(null);
  const [geoMessage, setGeoMessage] = useState<GeoMessage | null>(null);
  const [locating, setLocating] = useState(false);
  const bodyId = useId();
  const ids = { lat: useId(), lon: useId(), radius: useId(), err: useId() };

  const finish = () => dispatch({ type: "drawFinish" });
  const cancel = () => dispatch({ type: "drawCancel" });
  useDrawKeys(draw.active, finish, cancel);

  const chooseArea = () => {
    setGeoMessage(null);
    setFormError(null);
  };

  const submitCoords = (e: FormEvent) => {
    e.preventDefault();
    const la = parseNumber(lat);
    const lo = parseNumber(lon);
    const r = parseNumber(radius);
    if (la === null || lo === null || r === null) return setFormError("missing");
    const error = validateCircle(la, lo, r);
    if (error) return setFormError(error);
    chooseArea();
    dispatch({ type: "setCircle", lat: la, lon: lo, radiusKm: r, source: "manual" });
  };

  const useMyLocation = () => {
    setGeoMessage(null);
    if (!("geolocation" in navigator)) return setGeoMessage("geoUnsupported");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false);
        const error = validateCircle(coords.latitude, coords.longitude, DEFAULT_RADIUS_KM);
        if (error) return setGeoMessage(error);
        setCoordsOpen(false);
        dispatch({
          type: "setCircle",
          lat: coords.latitude,
          lon: coords.longitude,
          radiusKm: DEFAULT_RADIUS_KM,
          source: "geolocation",
        });
      },
      (err) => {
        setLocating(false);
        setGeoMessage(err.code === err.PERMISSION_DENIED ? "geoDenied" : "geoUnavailable");
      },
      { timeout: 10_000, maximumAge: 60_000 },
    );
  };

  const presetActive = area.kind === "preset" && !coordsOpen && !draw.active;
  const coordsActive = !draw.active && (coordsOpen || (area.kind === "circle" && area.source === "manual"));
  const drawActive = draw.active || area.kind === "polygon";
  const locationActive = !draw.active && !coordsOpen && area.kind === "circle" && area.source === "geolocation";
  const drawError = draw.error ? t.area.errors[draw.error] : null;
  const message = geoMessage ? t.area.errors[geoMessage] : null;

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
      <div className="drawer-body stack" id={bodyId}>
        <div className="segmented stacked" role="group" aria-label={t.area.modes}>
          <button
            type="button"
            aria-pressed={presetActive}
            data-testid="area-preset"
            onClick={() => {
              chooseArea();
              setCoordsOpen(false);
              dispatch({ type: "setPreset" });
            }}
          >
            {t.area.cordoba}
          </button>
          <button
            type="button"
            aria-pressed={coordsActive}
            aria-expanded={coordsOpen}
            data-testid="area-coords"
            onClick={() => {
              chooseArea();
              if (draw.active) cancel();
              setCoordsOpen(true);
            }}
          >
            {t.area.coords}
          </button>
          <button
            type="button"
            aria-pressed={drawActive}
            data-testid="area-draw"
            onClick={() => {
              chooseArea();
              setCoordsOpen(false);
              dispatch({ type: "drawStart" });
            }}
          >
            {t.area.draw}
          </button>
        </div>

        {coordsOpen && (
          <form className="stack" onSubmit={submitCoords} noValidate data-testid="coords-form">
            <div className="field">
              <label htmlFor={ids.lat}>{t.area.lat}</label>
              <input
                id={ids.lat}
                className="num"
                inputMode="decimal"
                autoComplete="off"
                placeholder="-31.42"
                value={lat}
                aria-invalid={formError !== null}
                aria-describedby={formError ? ids.err : undefined}
                onChange={(e) => setLat(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor={ids.lon}>{t.area.lon}</label>
              <input
                id={ids.lon}
                className="num"
                inputMode="decimal"
                autoComplete="off"
                placeholder="-64.18"
                value={lon}
                aria-invalid={formError !== null}
                aria-describedby={formError ? ids.err : undefined}
                onChange={(e) => setLon(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor={ids.radius}>{t.area.radius}</label>
              <input
                id={ids.radius}
                className="num"
                inputMode="decimal"
                autoComplete="off"
                value={radius}
                aria-invalid={formError !== null}
                aria-describedby={formError ? ids.err : undefined}
                onChange={(e) => setRadius(e.target.value)}
              />
            </div>
            {formError && (
              <p className="field-error" id={ids.err} role="alert" data-testid="coords-error">
                {t.area.errors[formError]}
              </p>
            )}
            <button type="submit" className="btn primary">
              {t.area.apply}
            </button>
          </form>
        )}

        {draw.active && (
          <div className="stack" data-testid="draw-panel">
            <p className="muted" role="status">
              {t.area.drawHint}
            </p>
            <p className="num" data-testid="draw-count">
              {format(t.area.drawVertices, { n: draw.vertices.length })}
            </p>
            {drawError && (
              <p className="field-error" role="alert" data-testid="draw-error">
                {drawError}
              </p>
            )}
            <div className="actions">
              <button type="button" className="btn primary" disabled={draw.vertices.length < 3} onClick={finish}>
                {t.area.drawClose}
              </button>
              <button type="button" className="btn" onClick={cancel}>
                {t.area.drawCancel}
              </button>
            </div>
          </div>
        )}

        <div className="stack">
          <button
            type="button"
            className="btn"
            aria-pressed={locationActive}
            disabled={locating}
            data-testid="area-location"
            onClick={useMyLocation}
          >
            {t.area.myLocation}
          </button>
          {message && (
            <p className="field-error" role="alert" data-testid="geo-message">
              {message}
            </p>
          )}
        </div>

        <div className="data-status" data-testid="data-status" data-state={data.status} aria-live="polite">
          {data.status === "loading" && <p className="muted">{t.area.status.loading}</p>}
          {data.status === "error" && <p className="field-error">{t.area.status.error}</p>}
          {data.status === "ready" && (
            <>
              <p className="num" data-testid="data-cells">
                {format(t.area.status.ready, {
                  cells: data.calendar.n_cells,
                  start: data.calendar.period.start,
                  end: data.calendar.period.end,
                })}
              </p>
              <p className="muted">{format(t.area.status.source, { source: data.calendar.meta.source })}</p>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
