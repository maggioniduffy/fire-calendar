import { useT } from "../state/prefs";

export function HoverHeader() {
  const t = useT();
  return (
    <div className="hover-header-shell">
      <div className="hover-header-hot-zone" aria-hidden="true" />
      <header className="hover-header card tx" data-testid="hover-header">
        <img src="/brand/flame-64.png" alt="" width="20" height="20" />
        <span>{t.app.headerTitle}</span>
      </header>
    </div>
  );
}
