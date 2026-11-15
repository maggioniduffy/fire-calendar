import { createContext, useContext, useEffect, useMemo, useReducer, useState, type Dispatch, type ReactNode } from "react";
import { postCalendar, postStats } from "../api/client";
import type { CalendarPayload, StatsPayload } from "../api/types";
import { initialSelection, selectionReducer, toRequest, toStatsRequest, type SelectionAction, type SelectionState } from "./selection";

export type AreaData =
  | { status: "loading" }
  /**
   * `stats` answers the chosen month only when `statsPending` is false. While a new month loads, the previous
   * answer of the same area stays (its climatology does not depend on the month), so the calendar does not flicker.
   */
  | { status: "ready"; calendar: CalendarPayload; stats: StatsPayload; statsPending: boolean }
  | { status: "error"; message: string };

interface Value {
  state: SelectionState;
  dispatch: Dispatch<SelectionAction>;
  data: AreaData;
}

const Ctx = createContext<Value | null>(null);

type Result<T> = { key: string; data: T } | { key: string; error: string };
type Stats = Result<StatsPayload> & { base: string };

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Selection state plus the answers for it. /calendar depends on area, period and scale only; /stats also on the
 * chosen month (`ref`), so changing the month refetches /stats but not /calendar. Each request is aborted when its
 * key changes, and a result is only used when it belongs to the current key.
 */
export function SelectionProvider({ children, initial = initialSelection }: { children: ReactNode; initial?: SelectionState }) {
  const [state, dispatch] = useReducer(selectionReducer, initial);
  const [calendar, setCalendar] = useState<Result<CalendarPayload> | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const calendarBody = toRequest(state);
  const calendarKey = JSON.stringify(calendarBody);
  // The latest month of the period is what the backend answers without `ref`: asking for it by name is the same
  // request. Taken from the last calendar loaded (any area), so changing the area does not add a `ref`.
  const latest = calendar && "data" in calendar ? calendar.data.period.end : null;
  const statsBody = toStatsRequest(state, latest);
  const statsKey = JSON.stringify(statsBody);

  useEffect(() => {
    const ctl = new AbortController();
    postCalendar(calendarBody, ctl.signal)
      .then((data) => setCalendar({ key: calendarKey, data }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setCalendar({ key: calendarKey, error: messageOf(e) });
      });
    return () => ctl.abort();
    // `calendarKey` encodes the body.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calendarKey]);

  useEffect(() => {
    const ctl = new AbortController();
    postStats(statsBody, ctl.signal)
      .then((data) => setStats({ key: statsKey, base: calendarKey, data }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setStats({ key: statsKey, base: calendarKey, error: messageOf(e) });
      });
    return () => ctl.abort();
    // `statsKey` encodes the body (and `calendarKey` is part of it apart from `ref`).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statsKey]);

  // The chosen month defaults to the end of the period the calendar covers, once the first data loads.
  const loadedEnd = calendar?.key === calendarKey && "data" in calendar ? calendar.data.period.end : null;
  useEffect(() => {
    if (loadedEnd && state.month === null) dispatch({ type: "setMonth", month: loadedEnd });
  }, [loadedEnd, state.month]);

  const loadedStart = calendar?.key === calendarKey && "data" in calendar ? calendar.data.period.start : null;
  useEffect(() => {
    if (loadedStart && loadedEnd && (state.calendarPeriod?.start !== loadedStart || state.calendarPeriod?.end !== loadedEnd)) {
      dispatch({ type: "setCalendarPeriod", period: { start: loadedStart, end: loadedEnd } });
    }
  }, [loadedStart, loadedEnd, state.calendarPeriod?.start, state.calendarPeriod?.end]);

  const value = useMemo<Value>(() => {
    const cal = calendar?.key === calendarKey ? calendar : null;
    const st = stats?.key === statsKey ? stats : null;
    // A stats answer of the same area (other month) is usable for the calendar while the new one loads.
    const stale = stats && stats.base === calendarKey && "data" in stats ? stats : null;
    let data: AreaData = { status: "loading" };
    if (cal && "error" in cal) data = { status: "error", message: cal.error };
    else if (st && "error" in st) data = { status: "error", message: st.error };
    else if (cal && "data" in cal) {
      const usable = st && "data" in st ? st : stale;
      if (usable) data = { status: "ready", calendar: cal.data, stats: usable.data, statsPending: usable !== st };
    }
    return { state, dispatch, data };
  }, [state, calendar, stats, calendarKey, statsKey]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelection(): Value {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSelection needs a SelectionProvider");
  return v;
}
