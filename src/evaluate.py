"""Evaluate the market's point forecast against benchmarks at fixed horizons.

Input:  results/comparison.csv   one row per settled event x horizon, every
        forecaster read on the same snapshot date (built by build_benchmarks.py)
Output: results/accuracy_by_horizon.csv   n / MAE / RMSE / bias per forecaster
        results/diebold_mariano.csv       Kalshi vs. each benchmark, per horizon
        results/evaluation.md             the same tables rendered for GitHub

Two evaluation samples are reported (see DECISIONS.md, "Evaluation sample"):
  headline  every settled event with a full implied distribution, excluding
            KXCPI-25OCT: the BLS never published October 2025 CPI (federal
            shutdown), so there is no first-release print to grade against.
  all       the same events plus KXCPI-25OCT, graded on Kalshi's settlement.

Diebold-Mariano (1995) test.  For each event t, d_t = L(e_kalshi) - L(e_bench)
with L = absolute error (as presented) or squared error.  Under equal accuracy
E[d_t] = 0; the statistic mean(d) / sqrt(var(mean(d))) is compared with the
standard normal.  The forecasts are one-step-ahead (one per monthly release,
no overlap), so the default long-run variance is the sample variance -- the
paired t-test.  A Newey-West variance with 2 lags is reported alongside as a
robustness check against serial correlation in the loss differential.
"""
import math
import pathlib
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

EXCLUDE_HEADLINE = {"KXCPI-25OCT"}      # no BLS first release (Oct 2025 shutdown)
HORIZONS = [30, 14, 7, 1]
HAC_LAG_ROBUST = 2

FORECASTERS = {                          # key -> column in comparison.csv
    "kalshi": "kalshi_implied_mean",
    "cleveland": "cleveland_nowcast",
    "naive_last": "naive_last_print",
    "naive_avg12": "naive_avg_12m",
}
LABELS = {
    "kalshi": "Kalshi implied mean",
    "cleveland": "Cleveland Fed nowcast",
    "naive_last": "Naive: last released print",
    "naive_avg12": "Naive: mean of last 12 prints",
}
BENCHMARKS = ["cleveland", "naive_last", "naive_avg12"]


def hac_variance_of_mean(d, lag):
    """Newey-West (Bartlett) long-run variance of the sample mean of d.

    lag=0 reduces to the ordinary sample variance / n, i.e. the paired t-test.
    """
    d = np.asarray(d, dtype=float)
    n = len(d)
    dm = d - d.mean()
    s = (dm ** 2).sum() / (n - 1)
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (dm[k:] * dm[:-k]).sum() / (n - 1)
    return s / n


def dm_test(loss_a, loss_b, lag=0):
    """Diebold-Mariano test of equal expected loss.

    Returns (n, mean loss differential, t statistic, two-sided normal p-value).
    A negative statistic means forecaster A has the smaller losses.
    """
    d = np.asarray(loss_a, dtype=float) - np.asarray(loss_b, dtype=float)
    n = len(d)
    var = hac_variance_of_mean(d, lag)
    if n < 2 or var <= 0:
        return n, float(d.mean()), float("nan"), float("nan")
    t = d.mean() / math.sqrt(var)
    p = 2 * (1 - NormalDist().cdf(abs(t)))
    return n, float(d.mean()), float(t), float(p)


def evaluate(comp, sample):
    acc_rows, dm_rows = [], []
    for h in HORIZONS:
        d = comp[comp.horizon_days == h]
        for key, col in FORECASTERS.items():
            g = d.dropna(subset=[col, "actual_first_release"])
            err = g[col] - g.actual_first_release
            acc_rows.append({
                "sample": sample, "horizon_days": h, "forecaster": key,
                "n": len(g),
                "mae": err.abs().mean(),
                "rmse": math.sqrt((err ** 2).mean()),
                "bias": err.mean(),
            })
        for key in BENCHMARKS:
            col = FORECASTERS[key]
            g = d.dropna(subset=["kalshi_implied_mean", col, "actual_first_release"])
            ek = (g.kalshi_implied_mean - g.actual_first_release).abs()
            eb = (g[col] - g.actual_first_release).abs()
            for loss, la, lb in [("abs", ek, eb), ("sq", ek ** 2, eb ** 2)]:
                n, mean_d, t, p = dm_test(la, lb, lag=0)
                _, _, t2, p2 = dm_test(la, lb, lag=HAC_LAG_ROBUST)
                dm_rows.append({
                    "sample": sample, "horizon_days": h, "benchmark": key,
                    "loss": loss, "n": n,
                    "kalshi_mean_loss": la.mean(), "benchmark_mean_loss": lb.mean(),
                    "mean_loss_diff": mean_d, "dm_t": t, "dm_p": p,
                    "dm_t_hac2": t2, "dm_p_hac2": p2,
                    "kalshi_closer": int((ek < eb).sum()),
                    "benchmark_closer": int((eb < ek).sum()),
                    "ties": int((ek == eb).sum()),
                })
    return pd.DataFrame(acc_rows), pd.DataFrame(dm_rows)


def md_table(rows, columns):
    """rows: list of dicts; columns: list of (key, header, format)."""
    out = ["| " + " | ".join(c[1] for c in columns) + " |",
           "|" + "|".join("---" for _ in columns) + "|"]
    for r in rows:
        cells = []
        for key, _, fmt in columns:
            v = r[key]
            cells.append("" if v is None or (isinstance(v, float) and math.isnan(v))
                         else (fmt.format(v) if fmt else str(v)))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def accuracy_rows(acc, sample, metric):
    rows = []
    for h in HORIZONS:
        a = acc[(acc["sample"] == sample) & (acc.horizon_days == h)].set_index("forecaster")
        row = {"horizon": h, "n": int(a.loc["kalshi", "n"])}
        for key in FORECASTERS:
            row[key] = float(a.loc[key, metric])
        rows.append(row)
    return rows


def dm_rows(dm, sample, benchmark, loss="abs"):
    rows = []
    for h in HORIZONS:
        r = dm[(dm["sample"] == sample) & (dm.horizon_days == h)
               & (dm.benchmark == benchmark) & (dm.loss == loss)].iloc[0]
        rows.append({
            "horizon": h, "n": int(r.n),
            "k": r.kalshi_mean_loss, "b": r.benchmark_mean_loss,
            "diff": r.mean_loss_diff, "t": r.dm_t, "p": r.dm_p,
            "t2": r.dm_t_hac2, "p2": r.dm_p_hac2,
            "wins": f"{int(r.kalshi_closer)} / {int(r.n)}",
        })
    return rows


def write_markdown(acc, dm, samples):
    ACC_COLS = [("horizon", "Days before release", "{}"), ("n", "Events", "{}")] + [
        (k, LABELS[k], "{:.3f}") for k in FORECASTERS]
    DM_COLS = [("horizon", "Days before release", "{}"), ("n", "Events", "{}"),
               ("k", "Kalshi loss", "{:.3f}"), ("b", "Benchmark loss", "{:.3f}"),
               ("diff", "Mean loss diff.", "{:+.3f}"), ("t", "DM t", "{:.2f}"),
               ("p", "p-value", "{:.3f}"), ("t2", "t (NW, 2 lags)", "{:.2f}"),
               ("p2", "p (NW)", "{:.3f}"), ("wins", "Kalshi closer", "{}")]
    L = []
    L.append("# Evaluation results\n")
    L.append("Generated by `src/evaluate.py` from `results/comparison.csv` "
             "(built by `src/build_benchmarks.py`). Every forecaster is read on the "
             "same snapshot date, 30/14/7/1 days before each CPI release, and graded "
             "against the first-release print. Errors are in percentage points of "
             "month-over-month headline CPI.\n")
    L.append("Samples:\n")
    for s, comp in samples.items():
        n = comp[comp.horizon_days == 1].event_ticker.nunique()
        months = comp.month.min() + " to " + comp.month.max()
        if s == "headline":
            L.append(f"- **headline** — {n} settled events (target months {months}) with a "
                     f"full implied distribution and a BLS first-release print. "
                     f"{', '.join(sorted(EXCLUDE_HEADLINE))} is excluded: the BLS never "
                     f"published October 2025 CPI (federal shutdown).")
        else:
            L.append(f"- **all** — the same plus {', '.join(sorted(EXCLUDE_HEADLINE))} "
                     f"graded on Kalshi's settlement value ({n} events).")
    L.append("")
    for s in samples:
        title = "Headline sample" if s == "headline" else "Robustness: all settled events"
        L.append(f"## {title}\n")
        L.append("### Mean absolute error (pp)\n")
        L.append(md_table(accuracy_rows(acc, s, "mae"), ACC_COLS) + "\n")
        L.append("### Root mean squared error (pp)\n")
        L.append(md_table(accuracy_rows(acc, s, "rmse"), ACC_COLS) + "\n")
        L.append("### Bias: mean(forecast − actual) (pp)\n")
        L.append(md_table(accuracy_rows(acc, s, "bias"), [
            (k, h, "{:+.3f}") if k not in ("horizon", "n") else (k, h, f) for k, h, f in ACC_COLS]) + "\n")
        for b in BENCHMARKS:
            L.append(f"### Diebold–Mariano: Kalshi vs. {LABELS[b]} (absolute-error loss)\n")
            L.append(md_table(dm_rows(dm, s, b, "abs"), DM_COLS) + "\n")
        L.append("### Diebold–Mariano: Kalshi vs. Cleveland Fed nowcast (squared-error loss)\n")
        L.append(md_table(dm_rows(dm, s, "cleveland", "sq"), DM_COLS) + "\n")
    L.append("Reading the DM tables: a negative mean loss difference means Kalshi's "
             "errors are smaller; the p-value is the probability of a gap at least this "
             "large if the two forecasters were equally accurate. `DM t` uses the sample "
             "variance (one-step-ahead monthly forecasts do not overlap); the Newey–West "
             "columns allow for serial correlation in the loss differential.\n")
    (RESULTS / "evaluation.md").write_text("\n".join(L))


def main():
    comp = pd.read_csv(RESULTS / "comparison.csv", dtype={"month": str})
    samples = {
        "headline": comp[~comp.event_ticker.isin(EXCLUDE_HEADLINE)],
        "all": comp,
    }
    accs, dms = [], []
    for s, c in samples.items():
        a, d = evaluate(c, s)
        accs.append(a)
        dms.append(d)
    acc = pd.concat(accs, ignore_index=True)
    dm = pd.concat(dms, ignore_index=True)
    acc.to_csv(RESULTS / "accuracy_by_horizon.csv", index=False, float_format="%.6f")
    dm.to_csv(RESULTS / "diebold_mariano.csv", index=False, float_format="%.6f")
    write_markdown(acc, dm, samples)

    h = acc[(acc["sample"] == "headline") & (acc.horizon_days == 1)].set_index("forecaster")
    t = dm[(dm["sample"] == "headline") & (dm.horizon_days == 1)
           & (dm.benchmark == "cleveland") & (dm.loss == "abs")].iloc[0]
    print(f"headline sample, 1 day before release (n={int(t.n)}): "
          f"MAE Kalshi {h.loc['kalshi', 'mae']:.3f} vs Cleveland {h.loc['cleveland', 'mae']:.3f} | "
          f"DM t = {t.dm_t:.2f}, p = {t.dm_p:.3f} | Kalshi closer in {int(t.kalshi_closer)} of {int(t.n)}")
    print(f"wrote {RESULTS / 'accuracy_by_horizon.csv'}, {RESULTS / 'diebold_mariano.csv'}, "
          f"{RESULTS / 'evaluation.md'}")


if __name__ == "__main__":
    main()
