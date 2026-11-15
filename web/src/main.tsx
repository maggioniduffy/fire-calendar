import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./theme/tokens.css";
import "./styles.css";
import { App } from "./App";
import { SelectionProvider } from "./state/SelectionContext";
import { selectionFromSearch } from "./state/selection";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SelectionProvider initial={selectionFromSearch(window.location.search)}>
      <App />
    </SelectionProvider>
  </StrictMode>,
);
