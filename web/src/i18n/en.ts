import type { Messages } from "./index";

const en: Messages = {
  app: {
    title: "Fire calendar",
    event: "NASA Space Apps 2026 · CONAE challenge",
    challenge: "Harmonization of MODIS and VIIRS Hot Spots",
    author: "Faustino Maggioni Duffy",
  },
  prefs: {
    theme: "Theme",
    light: "Light",
    dark: "Dark",
    language: "Language",
  },
  panel: {
    title: "Area and period",
    area: "Area",
    areaDefault: "Córdoba province",
    period: "Period",
    sensor: "Sensor",
    pending: "Pending",
    open: "Show area and period",
    close: "Hide area and period",
  },
  tabs: {
    label: "View",
    map: "Map",
    dashboard: "Dashboard",
  },
  map: {
    label: "Hot spot map",
  },
  dashboard: {
    pending: "Area charts arrive with the harmonized series.",
  },
  inspector: {
    title: "Details",
    empty: "Tap a hot spot on the map to see its data.",
    layer: "Layer",
    source: "Source",
    period: "Period",
    license: "License",
    experimental: "Experimental",
    date: "Date",
    sensor: "Sensor",
    frp: "FRP",
    confidence: "Confidence",
    confidenceLevels: { l: "low", n: "nominal", h: "high" },
    lat: "Latitude",
    lon: "Longitude",
    clear: "Clear selection",
    loading: "Loading layer…",
    error: "The layer could not be loaded.",
  },
  calendar: {
    title: "Calendar",
    pending: "The year × month calendar arrives with the harmonized series.",
  },
  units: {
    mw: "MW",
  },
};

export default en;
