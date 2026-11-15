import { useEffect, useRef, useState } from "react";
import { languageNames, languages } from "../i18n";
import { prefs, usePrefs, useT } from "../state/prefs";
import type { ThemeName } from "../theme/tokens";

const themes: readonly ThemeName[] = ["light", "dark"];

function SettingsModal({ onClose }: { onClose: () => void }) {
  const t = useT();
  const { theme, lang } = usePrefs();
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="settings-dialog"
      aria-labelledby="settings-title"
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault();
        dialogRef.current?.close();
      }}
    >
      <div className="settings-heading">
        <h2 className="card-title" id="settings-title">{t.app.settings}</h2>
        <button className="dialog-close" type="button" aria-label={t.app.closeSettings} onClick={() => dialogRef.current?.close()} data-testid="close-settings">
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <div className="settings-controls">
        <div className="segmented" role="group" aria-label={t.prefs.theme}>
          {themes.map((name) => (
            <button key={name} type="button" aria-pressed={theme === name} onClick={() => prefs.setTheme(name)} data-testid={`theme-${name}`}>
              {t.prefs[name]}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label={t.prefs.language}>
          {languages.map((code) => (
            <button key={code} type="button" lang={code} aria-pressed={lang === code} onClick={() => prefs.setLang(code)} data-testid={`lang-${code}`}>
              {languageNames[code]}
            </button>
          ))}
        </div>
      </div>
      <footer className="settings-footer">
        <span>{t.app.event}</span>
        <span>{t.app.challenge}</span>
        <span>{t.app.author}</span>
      </footer>
    </dialog>
  );
}

export function SettingsButton() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button ref={buttonRef} className="settings-button" type="button" aria-label={t.app.settings} onClick={() => setOpen(true)} data-testid="settings-button">
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          {/* Lucide "settings" icon (ISC license). */}
          <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
      {open && <SettingsModal onClose={() => { setOpen(false); buttonRef.current?.focus(); }} />}
    </>
  );
}
