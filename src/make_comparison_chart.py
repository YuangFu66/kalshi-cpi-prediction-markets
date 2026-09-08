"""Line chart: actual CPI print vs. Kalshi and Cleveland Fed forecasts one day
before release, for every settled event (results/forecast_comparison.png)."""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

# palette: slot1 blue, slot2 orange; ink / chrome tokens
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID, BASE, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def main():
    comp = pd.read_csv(RESULTS / "comparison.csv", dtype={"month": str})
    d = comp[comp.horizon_days == 1].copy()
    d["m"] = pd.to_datetime(d.month + "-01")
    d = d.sort_values("m")
    span = f"{d.m.iloc[0]:%b %Y} – {d.m.iloc[-1]:%b %Y}"

    fig, ax = plt.subplots(figsize=(13, 5.2), dpi=170)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(d.m, d.actual_first_release, color=INK, lw=2, zorder=3,
            marker="o", ms=3.5, label="Actual CPI (first release)")
    ax.plot(d.m, d.kalshi_implied_mean, color=BLUE, lw=2, zorder=2,
            label="Kalshi implied mean")
    ax.plot(d.m, d.cleveland_nowcast, color=ORANGE, lw=2, zorder=1,
            label="Cleveland Fed nowcast")

    last = d.iloc[-1]                      # direct labels at the right edge
    for y, txt, c, dy in [(last.actual_first_release, "Actual", INK, -4),
                          (last.kalshi_implied_mean, "Kalshi", BLUE, 2),
                          (last.cleveland_nowcast, "Cleveland Fed", ORANGE, 14)]:
        ax.annotate(txt, xy=(last.m, y), xytext=(8, dy), textcoords="offset points",
                    color=c, fontsize=10, fontweight="bold", va="center")

    ax.set_title("Forecasts one day before release vs. the actual CPI print",
                 color=INK, fontsize=14, fontweight="bold", loc="left", pad=14)
    ax.text(0, 1.015, f"Headline CPI, month-over-month %  ·  {len(d)} settled Kalshi "
            f"events, target months {span}",
            transform=ax.transAxes, color=MUTED, fontsize=10)

    ax.axhline(0, color=BASE, lw=1, zorder=0)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=10)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("MoM change (%)", color=MUTED, fontsize=10)
    ax.margins(x=0.015)
    ax.set_xlim(d.m.min() - pd.Timedelta(days=20), d.m.max() + pd.Timedelta(days=170))
    ax.legend(loc="upper right", frameon=False, fontsize=10, labelcolor=INK)

    fig.tight_layout()
    out = RESULTS / "forecast_comparison.png"
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    print("wrote", out)


if __name__ == "__main__":
    main()
