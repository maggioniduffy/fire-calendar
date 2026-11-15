import { describe, expect, it } from "vitest";
import { filenameFromDisposition } from "./download";

describe("filenameFromDisposition", () => {
  it("reads a quoted file name", () => {
    expect(filenameFromDisposition('attachment; filename="firecal_calendar_viirs_eq_2005-01_2016-12.csv"')).toBe(
      "firecal_calendar_viirs_eq_2005-01_2016-12.csv",
    );
  });
  it("reads an unquoted and an RFC 5987 name", () => {
    expect(filenameFromDisposition("attachment; filename=a.csv")).toBe("a.csv");
    expect(filenameFromDisposition("attachment; filename*=UTF-8''a%20b.csv")).toBe("a b.csv");
  });
  it("never keeps path separators", () => {
    expect(filenameFromDisposition('attachment; filename="../x.csv"')).toBe(".._x.csv");
  });
  it("is null without a file name", () => {
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("attachment")).toBeNull();
  });
});
