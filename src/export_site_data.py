"""Export the tables behind the interactive site (site/data/*.json).

Everything here is derived from the committed clean tables and results, so
the site always shows exactly what the pipeline produced:

  summary.json        headline numbers, accuracy and Diebold-Mariano tables
  comparison.json     every forecaster per settled event and horizon
  events.json         for every settled event, the full market-implied
                      distribution on every trading day (bins, mean, SD,
                      liquidity diagnostics) plus the Cleveland Fed nowcast path
  horizon_curve.json  MAE of Kalshi vs. the nowcast as a function of days
                      before release, pooled over the headline sample
"""
import json
import math
import pathlib

import pandas as pd

from build_series import GRID, implied_bins, true_bin_index
from evaluate import EXCLUDE_HEADLINE

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
EXT = ROOT / "data" / "external"
RESULTS = ROOT / "results"
SITE = ROOT / "site" / "data"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
CURVE_MAX_DAYS = 60


def event_month(ticker):
    tail = ticker.split("-")[-1]
    return f"20{tail[:2]}-{MONTHS[tail[2:]]:02d}"


def num(x, nd=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def records(df, nd=4):
    out = []
    for row in df.to_dict("records"):
        out.append({k: (num(v, nd) if isinstance(v, float) else
                        (int(v) if hasattr(v, "item") and isinstance(v.item(), int) else v))
                    for k, v in row.items()})
    return out


def bin_labels(thresholds):
    labels = [f"≤ {thresholds[0]:.1f}"]
    for a, b in zip(thresholds[:-1], thresholds[1:]):
        labels.append(f"{b:.1f}" if abs(b - a - GRID) < 1e-9 else f"({a:.1f}, {b:.1f}]")
    labels.append(f"> {thresholds[-1]:.1f}")
    return labels


def dump(name, obj):
    path = SITE / name
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"  {name}: {path.stat().st_size / 1024:.0f} KB")


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    comp = pd.read_csv(RESULTS / "comparison.csv", dtype={"month": str})
    acc = pd.read_csv(RESULTS / "accuracy_by_horizon.csv")
    dm = pd.read_csv(RESULTS / "diebold_mariano.csv")
    ev = pd.read_csv(CLEAN / "events_table.csv")
    md = pd.read_csv(CLEAN / "market_day.csv")
    dd = pd.read_csv(CLEAN / "distribution_day.csv")
    nc = pd.read_csv(EXT / "cleveland_nowcast_daily.csv", dtype={"target_month": str})

    # ---- summary ----
    h1 = acc[(acc["sample"] == "headline") & (acc.horizon_days == 1)].set_index("forecaster")
    t1 = dm[(dm["sample"] == "headline") & (dm.horizon_days == 1)
            & (dm.benchmark == "cleveland") & (dm.loss == "abs")].iloc[0]
    summary = {
        "data_snapshot": "Kalshi pulled 2026-07-21; Cleveland Fed and BLS 2026-08-04",
        "headline": {
            "n": int(t1.n),
            "kalshi_mae_1d": num(h1.loc["kalshi", "mae"]),
            "cleveland_mae_1d": num(h1.loc["cleveland", "mae"]),
            "dm_t_1d": num(t1.dm_t, 2), "dm_p_1d": num(t1.dm_p),
            "kalshi_closer_1d": int(t1.kalshi_closer),
            "excluded": sorted(EXCLUDE_HEADLINE),
        },
        "accuracy": records(acc),
        "dm": records(dm[dm.loss == "abs"].drop(columns=["loss"])),
    }
    dump("summary.json", summary)

    # ---- comparison ----
    cols = ["event_ticker", "month", "horizon_days", "snapshot_date", "release_date",
            "actual_first_release", "kalshi_implied_mean", "cleveland_nowcast",
            "naive_last_print", "naive_avg_12m"]
    dump("comparison.json", {"rows": records(comp[cols], 3)})

    # ---- events: full distribution on every day ----
    ev = ev[ev.settled & ev.actual_cpi_mom.notna()]
    events = []
    for _, e in ev.sort_values("event_ticker").iterrows():
        et = e.event_ticker
        m = md[md.event_ticker == et]
        if m.empty:
            continue
        actual = float(e.actual_cpi_mom)
        release = m.release_date.iloc[0]
        days = []
        for (date, d2r), g in m.groupby(["date", "days_to_release"]):
            bins = implied_bins(g)
            if bins is None:
                continue
            gg, thr, surv, probs, values, violation = bins
            total = sum(probs)
            if total <= 0:
                continue
            probs = [max(p, 0.0) / sum(max(q, 0.0) for q in probs) for p in probs]
            mean = sum(p * v for p, v in zip(probs, values))
            var = sum(p * (v - mean) ** 2 for p, v in zip(probs, values))
            days.append({
                "d": int(d2r), "date": date,
                "mean": num(mean), "sd": num(math.sqrt(max(var, 0.0))),
                "p_true": num(probs[true_bin_index(thr, actual)]),
                "n": len(thr), "spread": num(gg.spread.mean()),
                "volume": num(gg.volume.sum(), 0), "mono": num(violation),
                "thr": [num(t, 1) for t in thr],
                "labels": bin_labels(thr), "p": [num(p, 3) for p in probs],
                "v": [num(v, 2) for v in values],
                "true_idx": true_bin_index(thr, actual),
            })
        if not days:
            continue
        days.sort(key=lambda r: -r["d"])
        month = event_month(et)
        rel = pd.Timestamp(release)
        path = {}
        for _, r in nc[nc.target_month == month].sort_values("nowcast_date").iterrows():
            d = (rel - pd.Timestamp(r.nowcast_date)).days
            if d >= 0:
                path[d] = num(r.cpi_mom_nowcast, 3)
        events.append({
            "ticker": et, "month": month, "release_date": release, "actual": actual,
            "n_markets": int(e.n_markets), "headline": et not in EXCLUDE_HEADLINE,
            "days": days,
            "cleveland": [{"d": d, "v": v} for d, v in sorted(path.items(), reverse=True)],
        })
    dump("events.json", {"events": events})

    # ---- horizon curve: pooled MAE by days before release ----
    dd = dd[dd.settled & dd.actual_cpi_mom.notna() & ~dd.event_ticker.isin(EXCLUDE_HEADLINE)]
    dd = dd[dd.days_to_release <= CURVE_MAX_DAYS].copy()
    dd["month"] = dd.event_ticker.map(event_month)
    rows = []
    for d in range(CURVE_MAX_DAYS, -1, -1):
        g = dd[dd.days_to_release == d]
        ek, ec = [], []
        for _, r in g.iterrows():
            n_ = nc[(nc.target_month == r.month) & (nc.nowcast_date <= r.date)]
            if n_.empty:
                continue
            ek.append(abs(r.implied_mean - r.actual_cpi_mom))
            ec.append(abs(n_.cpi_mom_nowcast.iloc[-1] - r.actual_cpi_mom))
        if len(ek) >= 10:
            rows.append({"d": d, "n": len(ek),
                         "kalshi_mae": num(sum(ek) / len(ek)),
                         "cleveland_mae": num(sum(ec) / len(ec))})
    dump("horizon_curve.json", {"max_days": CURVE_MAX_DAYS, "rows": rows})
    print(f"events exported: {len(events)}; event-days: {sum(len(e['days']) for e in events)}")


if __name__ == "__main__":
    main()
