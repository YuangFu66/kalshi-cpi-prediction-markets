"""Benchmark data: Cleveland Fed daily inflation nowcasts (month-over-month CPI).

The nowcasting page's chart is fed by a JSON file that contains the full
archive back to July 2013: for every target month, the daily path of the
model's MoM CPI nowcast plus the actual print. We store the raw JSON
untouched in data/external/ and flatten the CPI series to a tidy CSV.

Source: https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting
Data:   /-/media/files/webcharts/inflationnowcasting/nowcast_month.json
"""
import json
import pathlib
import re
import urllib.request

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"
URL = ("https://www.clevelandfed.org/-/media/files/webcharts/"
       "inflationnowcasting/nowcast_month.json?sc_lang=en")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DATE_RE = re.compile(r"^(\d{2})/(\d{2})$")


def fetch():
    raw = EXT / "cleveland_nowcast_month.json"
    if not raw.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        raw.write_bytes(urllib.request.urlopen(req, timeout=60).read())
    return json.loads(raw.read_text())


def parse(charts):
    rows = []
    for item in charts:
        sub = item["chart"]["subcaption"]              # e.g. "2026-6"
        tgt_year, tgt_month = (int(x) for x in sub.split("-"))
        cats = item["categories"][0]["category"]
        series = {s["seriesname"]: s["data"] for s in item.get("dataset", [])}
        cpi = series.get("CPI Inflation", [])
        actual = series.get("Actual CPI Inflation", [])

        year, prev_month = tgt_year, None
        for i, cat in enumerate(cats):
            m = DATE_RE.match(cat.get("label", ""))
            if not m:
                continue                               # release markers etc.
            mon, day = int(m.group(1)), int(m.group(2))
            if prev_month is None and mon > tgt_month:
                year = tgt_year - 1                    # series starts in Dec for a Jan target
            if prev_month is not None and mon < prev_month:
                year += 1                              # rolled over a year boundary
            prev_month = mon

            def val(s):
                v = s[i].get("value") if i < len(s) else None
                return float(v) if v not in (None, "") else None

            nc = val(cpi)
            if nc is None:
                continue
            rows.append({
                "target_month": f"{tgt_year}-{tgt_month:02d}",
                "nowcast_date": f"{year}-{mon:02d}-{day:02d}",
                "cpi_mom_nowcast": nc,
                "cpi_mom_actual_clevelandfed": val(actual),
            })
    return pd.DataFrame(rows)


def main():
    df = parse(fetch())
    df = df.sort_values(["target_month", "nowcast_date"])
    out = EXT / "cleveland_nowcast_daily.csv"
    df.to_csv(out, index=False)
    print(f"{out.name}: {len(df)} daily nowcasts, "
          f"{df.target_month.nunique()} target months "
          f"({df.target_month.min()} .. {df.target_month.max()})")


if __name__ == "__main__":
    main()
