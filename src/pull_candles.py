"""Week 2 step 1: download daily candlesticks for every KXCPI market.

Reads the raw market files produced by pull_events.py and saves one JSON of
daily candles per market under data/raw/candles/. Idempotent: markets whose
candle file already exists are skipped, so the script can be re-run safely.
"""
import json
import pathlib
from datetime import datetime, timedelta, timezone

import kalshi_api as api

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CANDLE_DIR = RAW / "candles"

SERIES = "KXCPI"


def ts(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def main():
    market_files = sorted((RAW / "markets").glob("*.json"))
    todo, skipped, empty = 0, 0, 0
    for mf in market_files:
        markets = json.loads(mf.read_text())
        for m in markets:
            ticker = m["ticker"]
            out = CANDLE_DIR / f"{ticker}.json"
            if out.exists():
                skipped += 1
                continue
            if not m.get("open_time") or not m.get("close_time"):
                continue
            start = ts(m["open_time"]) - 86400
            end = min(ts(m["close_time"]) + 86400,
                      int(datetime.now(timezone.utc).timestamp()))
            candles = api.get_daily_candles(SERIES, ticker, start, end)
            out.write_text(json.dumps(candles, indent=1))
            todo += 1
            if not candles:
                empty += 1
            if todo % 50 == 0:
                print(f"  fetched {todo} markets...")
    print(f"fetched {todo}, skipped (already present) {skipped}, "
          f"empty candle files {empty}")


if __name__ == "__main__":
    main()
