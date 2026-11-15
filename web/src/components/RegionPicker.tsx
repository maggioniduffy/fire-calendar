import { useId, useMemo } from "react";
import { getCatalog } from "../api/staticData";
import { useT } from "../state/prefs";
import { useSelection } from "../state/SelectionContext";
import { departmentsOf, provinceIdOf, provincesOf } from "../state/regionPicker";

/** Static mode (SA7.2) area choice: province and department selects, plus the note that custom areas need the local app. */
export function RegionPicker({ onChoose }: { onChoose: () => void }) {
  const t = useT();
  const { state, dispatch } = useSelection();
  const ids = { province: useId(), department: useId() };
  const areas = useMemo(() => getCatalog()?.areas ?? [], []);
  const provinces = useMemo(() => provincesOf(areas), [areas]);
  const id = state.area.kind === "region" ? state.area.id : null;
  const provinceId = id ? provinceIdOf(areas, id) : null;
  const departments = useMemo(() => (provinceId ? departmentsOf(areas, provinceId) : []), [areas, provinceId]);
  const department = id && id !== provinceId ? id : "";

  const choose = (next: string) => {
    onChoose();
    dispatch({ type: "setRegion", id: next });
  };

  return (
    <div className="stack" data-testid="region-picker">
      <div className="field">
        <label htmlFor={ids.province}>{t.area.province}</label>
        <select id={ids.province} value={provinceId ?? ""} data-testid="area-province" onChange={(e) => choose(e.target.value)}>
          {provinces.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={ids.department}>{t.area.department}</label>
        <select
          id={ids.department}
          value={department}
          data-testid="area-department"
          onChange={(e) => choose(e.target.value || provinceId!)}
        >
          <option value="">{t.area.wholeProvince}</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <p className="muted" data-testid="custom-area-note">
        {t.area.customNote}
      </p>
    </div>
  );
}
