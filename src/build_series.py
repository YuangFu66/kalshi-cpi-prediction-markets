"""Week 2 steps 2-3: clean the raw data and construct the forecast series.

KXCPI markets are threshold contracts: "Will CPI (MoM, one decimal) rise more
than x%?". The mid price of each contract estimates the survival probability
S(x) = P(CPI > x). Differencing S across adjacent thresholds gives a full
probability distribution over the upcoming print. See DECISIONS.md for every
judgment call made here.

Outputs (data/clean/):
  events_table.csv      one row per monthly event: contracts, dates, settled print
  market_day.csv        one row per (market, day): bid, ask, mid, spread, volume
  distribution_day.csv  one row per (event, day): implied distribution summary
  forecast_snapshots.csv one row per (settled event, horizon in {30,14,7,1})
"""
import json
import math
import pathlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from cpi_values import settled_value

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

ET = ZoneInfo("America/New_York")
GRID = 0.1          # CPI settles on a one-decimal grid
MAX_SPREAD = 0.90   # markets quoted 0/100 carry no information -> drop
HORIZONS = [30, 14, 7, 1]
SNAP_TOLERANCE = 3  # nearest available day within +/- this many days


def parse_threshold(ticker, event_ticker):
    """KXCPI-26MAY-T-0.3 -> -0.3 ; CPI-22JUL-T0.1 -> 0.1 ;
    CPI-22AUG-TN0.1 -> -0.1 (old negative format) ; None if not a T market."""
    suffix = ticker[len(event_ticker) + 1:]
    if not suffix.startswith("T"):
        return None
    body = suffix[1:]
    if body.startswith("N"):
        body = "-" + body[1:]
    try:
        return float(body)
    except ValueError:
        return None


def build_events_table():
    """One row per monthly event, summarized from the raw events + markets files."""
    titles = {e["event_ticker"]: e.get("title", "")
              for e in json.loads((RAW / "events.json").read_text())}
    rows = []
    for mf in sorted((RAW / "markets").glob("*.json")):
        et = mf.stem
        markets = json.loads(mf.read_text())
        results = [m.get("result") or "" for m in markets]
        settled = bool(markets) and all(r in ("yes", "no") for r in results)
        # the settled CPI print is stored on each market as expiration_value
        thr = {m["ticker"]: t for m in markets
               if (t := parse_threshold(m["ticker"], et)) is not None}
        actual = settled_value(markets, thr) if settled else None
        volume = sum(float(m.get("volume_fp") or m.get("volume") or 0)
                     for m in markets)
        opens = [m["open_time"] for m in markets if m.get("open_time")]
        closes = [m["close_time"] for m in markets if m.get("close_time")]
        rows.append({
            "event_ticker": et,
            "title": titles.get(et, ""),
            "n_markets": len(markets),
            "first_open_time": min(opens) if opens else None,
            "close_time": max(closes) if closes else None,
            "settled": settled,
            "actual_cpi_mom": actual,
            "total_volume": round(volume, 2),
        })
    df = pd.DataFrame(rows)
    df.to_csv(CLEAN / "events_table.csv", index=False)
    return df


def candle_close(candle, side):
    """Close price of yes_bid/yes_ask; the live tier calls the field
    'close_dollars' while the historical tier calls it 'close'."""
    d = candle.get(side, {}) or {}
    v = d.get("close", d.get("close_dollars"))
    return None if v is None else float(v)


def candle_num(candle, key):
    """volume / open_interest, whichever suffix the tier uses."""
    v = candle.get(key, candle.get(key + "_fp"))
    return float(v or 0)


def candle_date(end_period_ts):
    """A daily candle ends at midnight ET; label it with the day it covers."""
    dt = datetime.fromtimestamp(end_period_ts - 1, tz=timezone.utc).astimezone(ET)
    return dt.date()


def load_market_days():
    rows = []
    unparsed = []
    for mf in sorted((RAW / "markets").glob("*.json")):
        event_ticker = mf.stem
        markets = json.loads(mf.read_text())
        results = [m.get("result") or "" for m in markets]
        settled = bool(markets) and all(r in ("yes", "no") for r in results)
        thr_by_ticker = {m["ticker"]: t for m in markets
                         if (t := parse_threshold(m["ticker"], event_ticker)) is not None}
        actual = settled_value(markets, thr_by_ticker) if settled else None
        release_date = max(
            datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
            .astimezone(ET).date()
            for m in markets if m.get("close_time"))

        for m in markets:
            thr = parse_threshold(m["ticker"], event_ticker)
            if thr is None:
                unparsed.append(m["ticker"])
                continue
            cf = RAW / "candles" / f"{m['ticker']}.json"
            if not cf.exists():
                continue
            for c in json.loads(cf.read_text()):
                bid = candle_close(c, "yes_bid")
                ask = candle_close(c, "yes_ask")
                if bid is None or ask is None:
                    continue
                d = candle_date(c["end_period_ts"])
                rows.append({
                    "event_ticker": event_ticker,
                    "ticker": m["ticker"],
                    "threshold": thr,
                    "date": d,
                    "days_to_release": (release_date - d).days,
                    "yes_bid": bid,
                    "yes_ask": ask,
                    "mid": (bid + ask) / 2,
                    # the mid IS the market-implied P(CPI > threshold);
                    # named explicitly so the table is self-documenting
                    "implied_prob_above": (bid + ask) / 2,
                    "spread": ask - bid,
                    "volume": candle_num(c, "volume"),
                    "open_interest": candle_num(c, "open_interest"),
                    "settled": settled,
                    "actual_cpi_mom": actual,
                    "release_date": release_date,
                })
    if unparsed:
        print(f"NOTE: {len(unparsed)} markets skipped (non-threshold ticker "
              f"format): {sorted(set(unparsed))[:10]}")
    df = pd.DataFrame(rows)
    df = df[(df.days_to_release >= 0) & (df.days_to_release <= 150)]
    return df


def implied_distribution(day_df):
    """From one (event, day) slice of threshold mids, build the distribution.

    Returns dict with implied mean/sd, prob of the true outcome bin, and
    data-quality diagnostics, or None if fewer than 2 informative thresholds.
    """
    g = day_df[day_df.spread <= MAX_SPREAD].sort_values("threshold")
    if len(g) < 2:
        return None
    thresholds = g.threshold.to_list()
    surv = g.mid.to_list()

    # enforce monotonicity: S(x) must be non-increasing in x
    violation = 0.0
    fixed = [surv[0]]
    for s in surv[1:]:
        violation = max(violation, s - fixed[-1])
        fixed.append(min(s, fixed[-1]))
    surv = fixed

    # bins: (-inf, x1], (x1, x2], ..., (xn, inf)
    probs = [1 - surv[0]]
    values = [thresholds[0]]                       # bottom tail, see DECISIONS.md
    for i in range(len(thresholds) - 1):
        probs.append(surv[i] - surv[i + 1])
        # representative value of (a, b] on the 0.1 grid
        values.append((thresholds[i] + thresholds[i + 1] + GRID) / 2)
    probs.append(surv[-1])
    values.append(thresholds[-1] + GRID)           # top tail, see DECISIONS.md

    total = sum(probs)
    if total <= 0:
        return None
    probs = [max(p, 0.0) / sum(max(q, 0.0) for q in probs) for p in probs]

    mean = sum(p * v for p, v in zip(probs, values))
    var = sum(p * (v - mean) ** 2 for p, v in zip(probs, values))

    out = {
        "implied_mean": mean,
        "implied_sd": math.sqrt(max(var, 0.0)),
        "prob_sum_raw": total,          # pre-normalization; coherence measure
        "mono_violation": violation,
        "n_thresholds": len(thresholds),
        "avg_spread": g.spread.mean(),
        "day_volume": g.volume.sum(),
    }

    actual = day_df.actual_cpi_mom.iloc[0]
    if pd.notna(actual):
        idx = len(thresholds)                       # default: top tail
        if actual <= thresholds[0]:
            idx = 0
        else:
            for i in range(len(thresholds) - 1):
                if thresholds[i] < actual <= thresholds[i + 1]:
                    idx = i + 1
                    break
        out["prob_true_bin"] = probs[idx]
        out["abs_error_mean"] = abs(mean - actual)
    return out


def main():
    ev = build_events_table()
    print(f"events_table.csv: {len(ev)} events, {int(ev.settled.sum())} settled")

    md = load_market_days()
    md.to_csv(CLEAN / "market_day.csv", index=False)
    print(f"market_day.csv: {len(md)} rows, "
          f"{md.ticker.nunique()} markets, {md.event_ticker.nunique()} events")

    dist_rows = []
    for (ev, d), g in md.groupby(["event_ticker", "date"]):
        r = implied_distribution(g)
        if r is None:
            continue
        r.update({
            "event_ticker": ev,
            "date": d,
            "days_to_release": g.days_to_release.iloc[0],
            "release_date": g.release_date.iloc[0],
            "settled": g.settled.iloc[0],
            "actual_cpi_mom": g.actual_cpi_mom.iloc[0],
        })
        dist_rows.append(r)
    dd = pd.DataFrame(dist_rows).sort_values(["event_ticker", "date"])
    front = ["event_ticker", "date", "days_to_release", "release_date",
             "settled", "actual_cpi_mom", "implied_mean", "implied_sd",
             "prob_true_bin", "abs_error_mean"]
    dd = dd[front + [c for c in dd.columns if c not in front]]
    dd.to_csv(CLEAN / "distribution_day.csv", index=False)
    print(f"distribution_day.csv: {len(dd)} event-days")

    # fixed-horizon snapshots for settled events
    snaps = []
    for ev, g in dd[dd.settled & dd.actual_cpi_mom.notna()].groupby("event_ticker"):
        for h in HORIZONS:
            g2 = g.assign(dist=(g.days_to_release - h).abs())
            g2 = g2[g2.dist <= SNAP_TOLERANCE]
            if g2.empty:
                continue
            row = g2.sort_values(["dist", "days_to_release"]).iloc[0].to_dict()
            row["horizon"] = h
            row.pop("dist")
            snaps.append(row)
    sd = pd.DataFrame(snaps)
    sd = sd[["event_ticker", "horizon"] + [c for c in sd.columns
                                           if c not in ("event_ticker", "horizon")]]
    sd.to_csv(CLEAN / "forecast_snapshots.csv", index=False)
    print(f"forecast_snapshots.csv: {len(sd)} rows "
          f"({sd.event_ticker.nunique()} settled events x up to {len(HORIZONS)} horizons)")


if __name__ == "__main__":
    main()
