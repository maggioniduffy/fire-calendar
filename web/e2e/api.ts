import { expect, test as base, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * Serves the SYNTHETIC API fixtures (backend/scripts/web_fixtures.py) so e2e needs no backend.
 *
 * A request is matched by its canonical key (same format as `request_key` in the Python script):
 *   "POST /calendar area=preset:cordoba scale=viirs_eq [month=YYYY-MM] [start=YYYY-MM] [end=YYYY-MM] [ref=YYYY-MM]"
 * (`bbox` is not part of the key)
 * with areas `preset:<id>`, `circle:<lat 2dp>,<lon 2dp>,<radius>` and `polygon` (any vertices).
 * An unknown request answers 404 and is recorded; the auto fixture below fails the test on any of them.
 */

const DIR = join(import.meta.dirname, "fixtures/api");
interface FixtureIndex {
  requests: Record<string, string>;
  /** Status and headers per file (default: 200 JSON). */
  responses?: Record<string, { status: number; headers: Record<string, string> }>;
}
const readIndex = (name: string) => JSON.parse(readFileSync(join(DIR, name), "utf8")) as FixtureIndex;
// index.json: area calendar/stats, /cells, /detections; index-inspector.json: chosen-month stats and /export.csv.
const indexes = [readIndex("index.json"), readIndex("index-inspector.json")];
const index = { requests: Object.assign({}, ...indexes.map((i) => i.requests)) as Record<string, string> };
const responses = Object.assign({}, ...indexes.map((i) => i.responses ?? {})) as NonNullable<FixtureIndex["responses"]>;

/** Status, headers and body of a fixture file, as the real server answered when it was generated. */
export function fixtureResponse(file: string) {
  const meta = responses[file] ?? { status: 200, headers: {} };
  const contentType = file.endsWith(".csv") ? "text/csv; charset=utf-8" : "application/json";
  return {
    status: meta.status,
    headers: { ...meta.headers, "content-type": contentType },
    body: readFileSync(join(DIR, file), "utf8"),
  };
}

interface ApiBody {
  preset?: string;
  area?: { type: string; lat?: number; lon?: number; radius_km?: number };
  scale?: string;
  start?: string;
  end?: string;
  ref?: string;
  month?: string;
  bbox?: number[];
  kind?: string;
}

/** Per-month answers live in one file per area + scale: the body field that picks the month, by path. */
const MONTH_FIELD = { "/cells": "month", "/detections": "month", "/stats": "ref" } as const;

export function requestKey(path: string, body: ApiBody): string {
  let area: string;
  if (body.preset !== undefined) area = `preset:${body.preset}`;
  else if (body.area?.type === "circle") {
    area = `circle:${body.area.lat!.toFixed(2)},${body.area.lon!.toFixed(2)},${body.area.radius_km}`;
  } else area = "polygon";
  const parts = [`POST ${path}`, `area=${area}`, `scale=${body.scale ?? "viirs_eq"}`];
  for (const k of ["month", "start", "end", "ref", "kind"] as const) if (body[k]) parts.push(`${k}=${body[k]}`);
  return parts.join(" ");
}

/** Readable form of an unmatched request: path and body fields (the key format is an internal detail). */
function describe(method: string, path: string, body: unknown, why = "no fixture"): string {
  return `${method} ${path} ${JSON.stringify(body)} (${why}; regenerate with backend/scripts/web_fixtures.py or request a month it holds)`;
}

export interface RecordedRequest {
  method: string;
  path: string;
  body: ApiBody & Record<string, unknown>;
  key: string;
}

export interface ApiMock {
  /** Every API request the page made, in order. */
  requests: RecordedRequest[];
  /** Keys of requests with no fixture (answered 404). */
  unmatched: string[];
  /** Requests to a path (e.g. "/calendar"). */
  to(path: string): RecordedRequest[];
}

export async function installApi(page: Page): Promise<ApiMock> {
  const mock: ApiMock = {
    requests: [],
    unmatched: [],
    to: (path) => mock.requests.filter((r) => r.path === path),
  };
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const req = route.request();
      const path = new URL(req.url()).pathname.replace(/^\/api/, "");
      const body = (req.postDataJSON() ?? {}) as RecordedRequest["body"];
      const key = requestKey(path, body);
      mock.requests.push({ method: req.method(), path, body, key });
      // Per-month fixtures hold every month in one file: the lookup key has `*` where the month goes.
      const field = MONTH_FIELD[path as keyof typeof MONTH_FIELD];
      const picked = field ? body[field] : undefined;
      const lookup = picked ? requestKey(path, { ...body, [field]: "*" }) : key;
      const file = req.method() === "POST" ? index.requests[lookup] : undefined;
      if (!file) {
        mock.unmatched.push(describe(req.method(), path, body));
        return route.fulfill({ status: 404, json: { detail: `no fixture for ${key}` } });
      }
      let answer = fixtureResponse(file);
      if (picked && answer.status === 200) {
        const entry = (JSON.parse(answer.body) as { months: Record<string, unknown> }).months[picked as string];
        if (!entry) {
          mock.unmatched.push(describe(req.method(), path, body, "month not in the fixture file"));
          return route.fulfill({ status: 404, json: { detail: `no fixture month for ${key}` } });
        }
        answer = { ...answer, body: JSON.stringify(entry) };
      }
      return route.fulfill(answer);
    },
  );
  return mock;
}

/** `test` with an auto `api` fixture: fails the test when the app asked for something without a fixture. */
export const test = base.extend<{ api: ApiMock }>({
  api: [
    async ({ page }, use) => {
      const mock = await installApi(page);
      await use(mock);
      expect(mock.unmatched, "API requests without a fixture").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
