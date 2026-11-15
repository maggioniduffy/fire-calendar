"""SA1.6 completeness (P8): chosen level, 90 % rule, window end, in-progress month."""

from datetime import date, timedelta

import pandas as pd

from firecal.stages.grid import completeness as cp


def presence(sat="snpp", start=date(2012, 2, 1), skip=(), nrt_end=date(2026, 11, 2)):
    rows = []
    d = start
    while d <= nrt_end:
        if d not in skip:
            level = "country-sp" if d.year <= 2025 else "api-sp" if d <= date(2026, 7, 31) else "nrt"
            rows.append(
                {"satellite": sat, "acq_date": pd.Timestamp(d), "rows": 5, "product": "p", "level": level}
            )
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def status(table, sat, month):
    return table[(table["satellite"] == sat) & (table["month"] == month)].iloc[0]


def days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def test_status_rules():
    skip = days(date(2026, 3, 5), date(2026, 3, 20))  # 16 missing days in a 31-day month
    skip += days(date(2026, 10, 27), date(2026, 10, 31))  # NRT window ends 2026-10-26
    skip += days(date(2026, 11, 1), date(2026, 11, 2))
    pres = presence(skip=skip, nrt_end=date(2026, 11, 2))
    t = cp.completeness_table(pres, asof=date(2026, 11, 15))
    assert status(t, "snpp", "2026-01").status == "complete"
    assert status(t, "snpp", "2026-01").level == "api-sp"
    assert status(t, "snpp", "2026-03").status == "partial"  # 15 days < 90 % of 31
    assert status(t, "snpp", "2026-08").level == "nrt"
    assert status(t, "snpp", "2026-08").status == "complete"
    # NRT data stops before the month end: the window does not cover the month
    assert status(t, "snpp", "2026-10").status == "partial"
    assert status(t, "snpp", "2026-11").status == "in_progress"
    assert t["gated"].sum() == (t["month"] >= "2026-01").sum()
    assert not status(t, "snpp", "2025-12").gated


def test_first_partial_month_excluded_from_reference():
    pres = presence(start=date(2012, 1, 19))  # record starts mid-month
    t = cp.completeness_table(pres, asof=date(2026, 11, 15))
    # January reference holds 2013..2025 only (13 years), the partial 2012-01 is out
    assert status(t, "snpp", "2026-01").ref_n_years == 13
    assert status(t, "snpp", "2012-01").status == "partial"


def test_country_level_wins_over_api_sp_and_is_not_summed():
    pres = presence()
    dup = pres[pres["acq_date"].dt.year == 2025].copy()
    dup["level"] = "api-sp"
    t = cp.month_table(pd.concat([pres, dup], ignore_index=True))
    m = t[(t["satellite"] == "snpp") & (t["ym"] == 2025 * 12 + 4)].iloc[0]
    assert m["level"] == "country-sp" and m["days"] == 31 and m["rows"] == 31 * 5


def test_write_table_and_report(tmp_path):
    t = cp.completeness_table(presence(), asof=date(2026, 11, 15))
    p = cp.write_table(t, date(2026, 11, 15), tmp_path / "c.parquet")
    back = pd.read_parquet(p)
    assert len(back) == len(t)
    text = cp.render_report(t, date(2026, 11, 15))
    assert "in_progress" in text and "Gated months" in text
