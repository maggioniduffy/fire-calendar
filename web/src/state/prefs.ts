import { useSyncExternalStore } from "react";
import type { ThemeName } from "../theme/tokens";
import { catalogues, type Lang, type Messages } from "../i18n";

export interface Prefs {
  theme: ThemeName;
  lang: Lang;
}

const STORAGE_KEY = "firecal.prefs";

function readStored(): Partial<Prefs> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    const out: Partial<Prefs> = {};
    if (parsed.theme === "light" || parsed.theme === "dark") out.theme = parsed.theme;
    if (parsed.lang === "es" || parsed.lang === "en") out.lang = parsed.lang;
    return out;
  } catch {
    return {};
  }
}

function systemTheme(): ThemeName {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Initial preferences: stored choice, else system theme and Spanish. */
export function initialPrefs(): Prefs {
  const stored = readStored();
  return { theme: stored.theme ?? systemTheme(), lang: stored.lang ?? "es" };
}

type Listener = () => void;

export function createPrefsStore(initial: Prefs = initialPrefs()) {
  let state = initial;
  const listeners = new Set<Listener>();

  const apply = () => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = state.theme;
    document.documentElement.lang = state.lang;
  };

  const set = (patch: Partial<Prefs>) => {
    const next = { ...state, ...patch };
    if (next.theme === state.theme && next.lang === state.lang) return;
    state = next;
    apply();
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Storage can be unavailable (private mode); the choice still applies in memory.
    }
    listeners.forEach((l) => l());
  };

  apply();

  return {
    get: () => state,
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setTheme: (theme: ThemeName) => set({ theme }),
    setLang: (lang: Lang) => set({ lang }),
    toggleTheme: () => set({ theme: state.theme === "light" ? "dark" : "light" }),
    messages: (): Messages => catalogues[state.lang],
  };
}

export type PrefsStore = ReturnType<typeof createPrefsStore>;

export const prefs = createPrefsStore();

export function usePrefs(store: PrefsStore = prefs): Prefs {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

/** Current message catalogue; re-renders on language change. */
export function useT(store: PrefsStore = prefs): Messages {
  return catalogues[usePrefs(store).lang];
}
