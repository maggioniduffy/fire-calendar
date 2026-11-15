import { createContext, useContext, useEffect, useMemo, useReducer, useState, type Dispatch, type ReactNode } from "react";
import { postCalendar, postStats } from "../api/client";
import type { CalendarPayload, StatsPayload } from "../api/types";
import { initialSelection, selectionReducer, toRequest, toStatsRequest, type SelectionAction, type SelectionState } from "./selection";

export type AreaData =
  | { status: "loading" }
  | { status: "ready"; calendar: CalendarPayload; stats: StatsPayload }
  | { status: "error"; message: string };

interface Value {
  state: SelectionState;
  dispatch: Dispatch<SelectionAction>;
  data: AreaData;
}

const Ctx = createContext<Value | null>(null);

type Fetched = { key: string; data: AreaData };

/**
 * Selection state plus the /calendar and /stats answers for it. The previous request is aborted when the area,
 * period or scale change; a result is only used when it belongs to the current request key.
 */
export function SelectionProvider({ children, initial = initialSelection }: { children: ReactNode; initial?: SelectionState }) {
  const [state, dispatch] = useReducer(selectionReducer, initial);
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const calendarBody = toRequest(state);
  const statsBody = toStatsRequest(state);
  const key = JSON.stringify([calendarBody, statsBody]);

  useEffect(() => {
    const ctl = new AbortController();
    Promise.all([postCalendar(calendarBody, ctl.signal), postStats(statsBody, ctl.signal)])
      .then(([calendar, stats]) => setFetched({ key, data: { status: "ready", calendar, stats } }))
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        setFetched({ key, data: { status: "error", message: e instanceof Error ? e.message : String(e) } });
      });
    return () => ctl.abort();
    // `key` encodes both bodies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // The chosen month defaults to the end of the period the calendar covers, once the first data loads.
  const loaded = fetched?.key === key && fetched.data.status === "ready" ? fetched.data.calendar.period.end : null;
  useEffect(() => {
    if (loaded && state.month === null) dispatch({ type: "setMonth", month: loaded });
  }, [loaded, state.month]);

  const value = useMemo(() => {
    const data: AreaData = fetched?.key === key ? fetched.data : { status: "loading" };
    return { state, dispatch, data };
  }, [state, fetched, key]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSelection(): Value {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSelection needs a SelectionProvider");
  return v;
}
