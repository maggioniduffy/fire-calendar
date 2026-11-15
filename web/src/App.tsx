import { lazy, Suspense, useEffect, useState } from "react";
import { TopBar } from "./components/TopBar";
import { LeftPanel } from "./components/LeftPanel";
import { Inspector } from "./components/Inspector";
import { CalendarStrip } from "./components/CalendarStrip";
import { Dashboard } from "./components/dashboard/Dashboard";
import { loadLayers } from "./layers/loadLayers";
import type { Hotspot, PointLayer } from "./layers/manifest";
import { useT } from "./state/prefs";

const MapView = lazy(() => import("./components/MapView"));

type Tab = "map" | "dashboard";
const tabs: readonly Tab[] = ["map", "dashboard"];

export function App() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("map");
  const [layers, setLayers] = useState<PointLayer[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [selected, setSelected] = useState<Hotspot | null>(null);

  useEffect(() => {
    document.title = `${t.app.title} · ${t.app.event}`;
  }, [t]);

  useEffect(() => {
    loadLayers()
      .then((l) => {
        setLayers(l);
        setStatus("ready");
      })
      .catch(() => setStatus("error"));
  }, []);

  return (
    <div className="shell">
      <TopBar />
      <LeftPanel />
      <main className="center card" data-testid="center">
        <div className="tabs" role="tablist" aria-label={t.tabs.label}>
          {tabs.map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              tabIndex={tab === id ? 0 : -1}
              onClick={() => setTab(id)}
              onKeyDown={(e) => {
                if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
                const next = tabs[(tabs.indexOf(id) + 1) % tabs.length];
                setTab(next);
                document.getElementById(`tab-${next}`)?.focus();
              }}
            >
              {t.tabs[id]}
            </button>
          ))}
        </div>
        <div className="tab-panel" role="tabpanel" id="panel-map" aria-labelledby="tab-map" hidden={tab !== "map"}>
          <Suspense fallback={<div className="map" />}>
            <MapView layers={layers} selected={selected} onSelect={setSelected} />
          </Suspense>
        </div>
        <div
          className="tab-panel dashboard"
          role="tabpanel"
          id="panel-dashboard"
          aria-labelledby="tab-dashboard"
          hidden={tab !== "dashboard"}
        >
          <Dashboard />
        </div>
      </main>
      <Inspector
        layer={layers[0] ?? null}
        status={status}
        selected={selected}
        onClear={() => setSelected(null)}
      />
      <CalendarStrip />
    </div>
  );
}
