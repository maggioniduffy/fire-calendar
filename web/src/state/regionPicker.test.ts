import { describe, expect, it } from "vitest";
import type { RegionInfo } from "../api/staticClient";
import { departmentsOf, pointInOutline, provinceAtPoint, provinceIdOf, provincesOf } from "./regionPicker";
import { initialSelection, selectionReducer, toCellsRequest, toRequest, areaBounds } from "./selection";

const mk = (id: string, kind: RegionInfo["kind"], name: string, province_id: string | null, bbox: RegionInfo["bbox"]): RegionInfo => ({
  id, kind, name, province_id, bbox, area_km2: 1, n_cells: 1,
});
const areas = [
  mk("p-tucuman", "province", "Tucumán", null, [-28, -26, -66, -64]),
  mk("p-cordoba", "province", "Córdoba", null, [-35, -29, -65, -61]),
  mk("p-ñuble", "province", "Ñandú", null, [-40, -39, -70, -69]),
  mk("p-buenos-aires", "province", "Buenos Aires", null, [-40, -33, -63, -57]),
  mk("d-cordoba-rio-cuarto", "department", "Río Cuarto", "p-cordoba", [-34, -32, -65, -63]),
  mk("d-cordoba-calamuchita", "department", "Calamuchita", "p-cordoba", [-33, -31, -65, -64]),
  mk("d-cordoba-ischilin", "department", "Ischilín", "p-cordoba", [-31, -30, -65, -63]),
  mk("d-tucuman-capital", "department", "Capital", "p-tucuman", [-27, -26, -66, -65]),
];
const square = (w: number, s: number, e: number, n: number) => [[[w, s], [e, s], [e, n], [w, n], [w, s]]];

describe("area picker lists", () => {
  it("sorts provinces with Spanish collation and departments of one province", () => {
    expect(provincesOf(areas).map((p) => p.name)).toEqual(["Buenos Aires", "Córdoba", "Ñandú", "Tucumán"]);
    expect(departmentsOf(areas, "p-cordoba").map((d) => d.name)).toEqual(["Calamuchita", "Ischilín", "Río Cuarto"]);
    expect(departmentsOf(areas, "p-nope")).toEqual([]);
  });

  it("finds the province of a province or department id", () => {
    expect(provinceIdOf(areas, "p-cordoba")).toBe("p-cordoba");
    expect(provinceIdOf(areas, "d-tucuman-capital")).toBe("p-tucuman");
    expect(provinceIdOf(areas, "zzz")).toBeNull();
  });
});

describe("point in province", () => {
  it("ray casting handles holes outside the ring and multipolygons", () => {
    const outline = [...square(0, 0, 2, 2), ...square(10, 10, 12, 12)];
    expect(pointInOutline(outline, 1, 1)).toBe(true);
    expect(pointInOutline(outline, 11, 11)).toBe(true);
    expect(pointInOutline(outline, 5, 5)).toBe(false);
  });

  it("picks the province by bbox then outline, and null outside Argentina", async () => {
    const fetched: string[] = [];
    const outlineOf = async (id: string) => {
      fetched.push(id);
      return id === "p-cordoba" ? square(-65, -35, -61, -29) : square(-66, -28, -64, -26);
    };
    expect(await provinceAtPoint(areas, -31.4, -64.2, outlineOf)).toBe("p-cordoba");
    expect(fetched).toEqual(["p-cordoba"]); // only candidates whose bbox holds the point are fetched
    expect(await provinceAtPoint(areas, 48.8, 2.3, outlineOf)).toBeNull();
    expect(fetched).toEqual(["p-cordoba"]);
  });

  it("a point in a province bbox but outside its outline is not in it", async () => {
    const triangle = [[[-65, -35], [-61, -35], [-65, -29], [-65, -35]]];
    expect(await provinceAtPoint(areas, -30, -62, async () => triangle)).toBeNull();
  });
});

describe("region area in the selection", () => {
  it("setRegion selects a region and requests it by id", () => {
    const s = selectionReducer(initialSelection, { type: "setRegion", id: "d-cordoba-ischilin" });
    expect(s.area).toEqual({ kind: "region", id: "d-cordoba-ischilin" });
    expect(toRequest(s)).toEqual({ scale: "viirs_eq", region: "d-cordoba-ischilin" });
    expect(toCellsRequest({ ...s, month: "2020-01" }, [-31, -30, -65, -64])).toEqual({
      region: "d-cordoba-ischilin",
      scale: "viirs_eq",
      month: "2020-01",
      bbox: [-31, -30, -65, -64],
    });
  });

  it("fits the map to the region bbox as [west, south, east, north]", () => {
    expect(areaBounds({ kind: "region", id: "x" }, [1, 2, 3, 4], [-31, -30, -65, -63])).toEqual([-65, -31, -63, -30]);
    expect(areaBounds({ kind: "region", id: "x" }, [1, 2, 3, 4])).toEqual([1, 2, 3, 4]);
  });
});
