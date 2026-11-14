import { useT } from "../state/prefs";

/** Year × month calendar and anomalies arrive in SA4.3–SA4.4. */
export function CalendarStrip() {
  const t = useT();
  return (
    <section className="calendar card" aria-labelledby="calendar-title" data-testid="calendar-strip">
      <h2 className="card-title" id="calendar-title">
        {t.calendar.title}
      </h2>
      <p className="muted">{t.calendar.pending}</p>
    </section>
  );
}
