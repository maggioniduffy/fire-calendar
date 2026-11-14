from datetime import date

import pandas as pd

from firecal.io.firms_profile import profile


def test_profile(tmp_path):
    def row(d, t=0, pct=80):
        return {
            "sensor": "modis",
            "satellite": "terra",
            "product": "modis",
            "acq_date": date.fromisoformat(d),
            "year": int(d[:4]),
            "daynight": "D",
            "latitude": 0.0,
            "longitude": 0.0,
            "confidence_pct": pct,
            "confidence_class": "high",
            "frp": 1.0,
            "type": t,
        }

    d = tmp_path / "det" / "product=modis" / "year=2020"
    d.mkdir(parents=True)
    pd.DataFrame(
        [row("2020-01-05"), row("2020-01-06", t=1), row("2020-04-01"), row("2020-04-02", pct=5)]
    ).to_parquet(d / "part-0.parquet")
    dl = tmp_path / "downloads.json"
    dl.write_text('{"records": [{"product": "viirs-jpss1", "year": 2018, "status": "missing"}]}')
    md = profile(tmp_path / "det", dl)
    assert "| 2020 | 4 / 2 |" in md
    assert "| modis | 1 | 1 | 0 |" in md
    assert "viirs-jpss1 2018" in md
    assert "modis: 2020-02, 2020-03" in md
