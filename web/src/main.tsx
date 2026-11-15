import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./theme/tokens.css";
import "./styles.css";
import { App } from "./App";
import { SelectionProvider } from "./state/SelectionContext";
import { prefs } from "./state/prefs";
import { STATIC_MODE } from "./api/client";
import { loadCatalog } from "./api/staticData";
import { selectionFromSearch, withDefaultArea, initialSelection } from "./state/selection";

/** Static mode starts on the manifest's default area; the catalogue (manifest + areas) is loaded before rendering. */
async function start() {
  let base = initialSelection;
  let failed = false;
  if (STATIC_MODE) {
    try {
      const { manifest } = await loadCatalog();
      base = withDefaultArea({ kind: "region", id: manifest.default_area });
    } catch {
      failed = true;
    }
  }
  const root = createRoot(document.getElementById("root")!);
  root.render(
    <StrictMode>
      {failed ? (
        <p role="alert">{prefs.messages().app.dataLoadFailed}</p>
      ) : (
        <SelectionProvider initial={selectionFromSearch(window.location.search, base)}>
          <App />
        </SelectionProvider>
      )}
    </StrictMode>,
  );
}

void start();
