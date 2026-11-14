import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPrefsStore, initialPrefs } from "./prefs";

describe("prefs store", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("defaults to Spanish and the system theme", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    expect(initialPrefs()).toEqual({ theme: "dark", lang: "es" });
  });

  it("restores a stored choice and ignores invalid values", () => {
    window.localStorage.setItem("firecal.prefs", JSON.stringify({ theme: "dark", lang: "en" }));
    expect(initialPrefs()).toEqual({ theme: "dark", lang: "en" });
    window.localStorage.setItem("firecal.prefs", JSON.stringify({ theme: "neon", lang: "fr" }));
    expect(initialPrefs().lang).toBe("es");
    expect(["light", "dark"]).toContain(initialPrefs().theme);
    window.localStorage.setItem("firecal.prefs", "{not json");
    expect(initialPrefs().lang).toBe("es");
  });

  it("applies theme and language to <html> without a reload", () => {
    const store = createPrefsStore({ theme: "light", lang: "es" });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.lang).toBe("es");
    store.toggleTheme();
    store.setLang("en");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.lang).toBe("en");
    expect(store.messages().tabs.map).toBe("Map");
  });

  it("notifies subscribers once per real change and persists it", () => {
    const store = createPrefsStore({ theme: "light", lang: "es" });
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    store.setTheme("light"); // no change
    store.setTheme("dark");
    store.setLang("en");
    expect(listener).toHaveBeenCalledTimes(2);
    expect(JSON.parse(window.localStorage.getItem("firecal.prefs")!)).toEqual({
      theme: "dark",
      lang: "en",
    });
    unsubscribe();
    store.setLang("es");
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("keeps working when storage throws", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const store = createPrefsStore({ theme: "light", lang: "es" });
    store.setLang("en");
    expect(store.get().lang).toBe("en");
  });
});
