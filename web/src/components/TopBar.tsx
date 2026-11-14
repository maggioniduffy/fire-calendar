import { languageNames, languages } from "../i18n";
import { prefs, usePrefs, useT } from "../state/prefs";
import type { ThemeName } from "../theme/tokens";

const themes: readonly ThemeName[] = ["light", "dark"];

export function TopBar() {
  const t = useT();
  const { theme, lang } = usePrefs();
  return (
    <header className="topbar card tx" data-testid="topbar">
      <div className="brand">
        <h1 className="app-title">{t.app.title}</h1>
        <p className="event" title={t.app.challenge}>
          {t.app.event}
        </p>
        <p className="author">{t.app.author}</p>
      </div>
      <div className="prefs">
        <div className="segmented" role="group" aria-label={t.prefs.theme}>
          {themes.map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={theme === name}
              onClick={() => prefs.setTheme(name)}
              data-testid={`theme-${name}`}
            >
              {t.prefs[name]}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label={t.prefs.language}>
          {languages.map((code) => (
            <button
              key={code}
              type="button"
              lang={code}
              aria-pressed={lang === code}
              onClick={() => prefs.setLang(code)}
              data-testid={`lang-${code}`}
            >
              {languageNames[code]}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
