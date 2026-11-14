import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import es from "./es";
import en from "./en";

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "string" ? [`${prefix}${k}`] : keys(v as object, `${prefix}${k}.`),
  );
}

function values(obj: object): string[] {
  return Object.values(obj).flatMap((v) => (typeof v === "string" ? [v] : values(v as object)));
}

function tsxFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return tsxFiles(path);
    return name.endsWith(".tsx") && !name.endsWith(".test.tsx") ? [path] : [];
  });
}

describe("i18n catalogues", () => {
  it("es and en have the same keys", () => {
    expect(keys(en).sort()).toEqual(keys(es).sort());
  });

  it("no message is empty", () => {
    for (const v of [...values(es), ...values(en)]) expect(v.trim()).not.toBe("");
  });

  it("no UI string is hard-coded in components", () => {
    const src = join(__dirname, "..");
    const offenders: string[] = [];
    for (const file of tsxFiles(src)) {
      const code = readFileSync(file, "utf8");
      // Text between JSX tags that contains a letter, e.g. <p>Hola</p>.
      for (const m of code.matchAll(/(?<!=)>([^<>{}`]*\p{L}[^<>{}`]*)</gu)) {
        if (!/[=;(]|=>/.test(m[1])) offenders.push(`${file}: ${m[1].trim()}`);
      }
      // Literal accessible names and tooltips.
      for (const m of code.matchAll(/\b(aria-label|title|placeholder|alt)="([^"]*\p{L}[^"]*)"/gu)) {
        offenders.push(`${file}: ${m[1]}="${m[2]}"`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
