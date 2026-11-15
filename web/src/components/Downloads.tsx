import { useState } from "react";
import { ApiError, postExport, STATIC_MODE } from "../api/client";
import { filenameFromDisposition, saveBlob } from "../api/download";
import { useT } from "../state/prefs";
import { useSelection } from "../state/SelectionContext";
import { toRequest } from "../state/selection";

type Kind = "calendar" | "detections";
type Message = "error" | "detectionsUnavailable";

/**
 * CSV downloads for the selected area and period. The hot-spot CSV is offered until the server answers 404 (it
 * has no raw detections): then the button is removed for the rest of the session and a message says why. It is
 * not probed in advance because the only way to ask is to request the file itself.
 */
export function Downloads() {
  const t = useT();
  const { state } = useSelection();
  const [busy, setBusy] = useState<Kind | null>(null);
  const [detectionsAvailable, setDetectionsAvailable] = useState(true);
  const [message, setMessage] = useState<Message | null>(null);

  const download = async (kind: Kind) => {
    setBusy(kind);
    setMessage(null);
    try {
      const res = await postExport({ ...toRequest(state), kind });
      const name = filenameFromDisposition(res.headers.get("Content-Disposition")) ?? `firecal_${kind}.csv`;
      saveBlob(await res.blob(), name);
    } catch (e) {
      if (kind === "detections" && e instanceof ApiError && e.status === 404) {
        setDetectionsAvailable(false);
        setMessage("detectionsUnavailable");
      } else {
        setMessage("error");
      }
    } finally {
      setBusy(null);
    }
  };

  const button = (kind: Kind) => (
    <button type="button" className="btn primary" disabled={busy !== null} data-testid={`download-${kind}`} onClick={() => void download(kind)}>
      {busy === kind ? t.download.working : t.download[kind]}
    </button>
  );

  return (
    <div className="downloads stack" role="group" aria-label={t.download.group} data-testid="downloads">
      <div className="actions">
        {button("calendar")}
        {detectionsAvailable && !STATIC_MODE && button("detections")}
      </div>
      {STATIC_MODE && (
        <p className="muted" data-testid="download-static-note">
          {t.download.staticNote}
        </p>
      )}
      {message && (
        <p className="muted" role="status" data-testid="download-message">
          {t.download[message]}
        </p>
      )}
    </div>
  );
}
