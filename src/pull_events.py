"""Week 1: inventory the KXCPI series.

Downloads every event and its markets (raw JSON kept untouched in data/raw/),
then summarizes them into data/clean/events_table.csv via build_series.
"""
import json
import pathlib
from datetime import datetime, timezone

import kalshi_api as api
from build_series import build_events_table

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

SERIES = "KXCPI"


def main():
    (RAW / "markets").mkdir(parents=True, exist_ok=True)
    CLEAN.mkdir(parents=True, exist_ok=True)

    events = api.get_all_events(SERIES)
    (RAW / "events.json").write_text(json.dumps(events, indent=1))
    print(f"events: {len(events)}")

    for ev in sorted(events, key=lambda e: e["event_ticker"]):
        et = ev["event_ticker"]
        markets = api.get_markets_for_event(et)
        (RAW / "markets" / f"{et}.json").write_text(json.dumps(markets, indent=1))
        print(f"  {et}: {len(markets)} markets")

    df = build_events_table()
    print(f"\nwrote {CLEAN / 'events_table.csv'} "
          f"({int(df.settled.sum())} settled of {len(df)} events)")
    print(f"pulled at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
