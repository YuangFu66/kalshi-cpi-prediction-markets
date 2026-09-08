"""Benchmark data: BLS CPI-U, seasonally adjusted, all items (series CUSR0000SA0).

Used only to flag months whose first-release MoM print was later revised
(results/true_cpi.csv). The public BLS API v2 needs no key for a single
series over at most ten years. The raw response is stored untouched in
data/external/ and skipped if it already exists (idempotent, like the other
pull scripts).

Source: https://api.bls.gov/publicAPI/v2/timeseries/data/
"""
import pathlib

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "bls_cpi_cusr0000sa0.json"
URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/CUSR0000SA0"


def main(start_year=2020, end_year=2026):
    if OUT.exists():
        print(f"{OUT.name} already present; delete it to re-download")
        return
    r = requests.get(URL, params={"startyear": start_year, "endyear": end_year}, timeout=60)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise SystemExit(f"BLS API error: {body.get('message')}")
    OUT.write_text(r.text)
    n = len(body["Results"]["series"][0]["data"])
    print(f"wrote {OUT} ({n} monthly observations)")


if __name__ == "__main__":
    main()
