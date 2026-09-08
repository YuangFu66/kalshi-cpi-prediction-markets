"""Grouped bar chart: forecast error by horizon, Kalshi vs. Cleveland Fed
(results/error_by_horizon.png). MAE and RMSE panels, headline sample, with the
Diebold-Mariano p-value under each horizon."""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"

# palette: slot1 blue, slot2 orange; ink / chrome tokens
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, SECOND, MUTED, BASE, SURFACE = "#0b0b0b", "#52514e", "#898781", "#c3c2b7", "#fcfcfb"
HORIZONS = [30, 14, 7, 1]
XLABELS = ["30 days out", "14 days out", "7 days out", "1 day out"]


def rounded_bar(ax, x, height, width, color, radius):
    """A column with a rounded data-end and a square base (radius in data units of x)."""
    x0, x1 = x - width / 2, x + width / 2
    r = min(radius, width / 2)
    ry = r * (ax.get_ylim()[1] - ax.get_ylim()[0]) / (ax.get_xlim()[1] - ax.get_xlim()[0]) \
        * ax.get_window_extent().width / ax.get_window_extent().height
    ry = min(ry, height / 2)
    verts = [(x0, 0), (x1, 0), (x1, height - ry),
             (x1, height), (x1 - r, height),            # top-right corner (quadratic)
             (x0 + r, height),
             (x0, height), (x0, height - ry),           # top-left corner (quadratic)
             (x0, 0)]
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO,
             Path.CURVE3, Path.CURVE3,
             Path.LINETO,
             Path.CURVE3, Path.CURVE3,
             Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, edgecolor="none", zorder=3))


def panel(ax, title, k, c, pvals=None):
    ymax = max(max(k), max(c)) * 1.22
    ax.set_xlim(-0.6, len(HORIZONS) - 0.4)
    ax.set_ylim(0, ymax)
    width, gap = 0.30, 0.03                      # a surface-colored gap between the pair
    for i, (vk, vc) in enumerate(zip(k, c)):
        for dx, v, col in [(-(width + gap) / 2, vk, BLUE), ((width + gap) / 2, vc, ORANGE)]:
            rounded_bar(ax, i + dx, v, width, col, radius=0.045)
            ax.text(i + dx, v + ymax * 0.018, f"{v:.3f}", ha="center", va="bottom",
                    fontsize=9.5, color=SECOND)
    ax.axhline(0, color=BASE, lw=1, zorder=2)
    ax.set_xticks(range(len(HORIZONS)))
    ax.set_xticklabels(XLABELS, color=SECOND, fontsize=10)
    ax.set_yticks([])                            # every column is labeled; no redundant axis
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(axis="x", length=0, pad=6)
    ax.set_title(title, loc="left", color=INK, fontsize=11.5, fontweight="bold", pad=10)
    if pvals is not None:
        for i, p in enumerate(pvals):
            txt = "p < 0.001" if p < 0.001 else f"p = {p:.3f}" if p < 0.01 else f"p = {p:.2f}"
            ax.text(i, -ymax * 0.135, txt, ha="center", va="top", fontsize=9, color=MUTED)
        ax.text(-0.6, -ymax * 0.135, "DM p", ha="left", va="top", fontsize=9, color=MUTED,
                style="italic")
        ax.text(-0.6, -ymax * 0.215, "Diebold–Mariano test of equal accuracy; p < 0.05 means the "
                "gap is unlikely to be luck", ha="left", va="top", fontsize=8.5, color=MUTED)


def main():
    acc = pd.read_csv(RESULTS / "accuracy_by_horizon.csv")
    dm = pd.read_csv(RESULTS / "diebold_mariano.csv")
    acc = acc[acc["sample"] == "headline"]
    dm = dm[(dm["sample"] == "headline") & (dm.benchmark == "cleveland") & (dm.loss == "abs")]

    def series(fc, metric):
        s = acc[acc.forecaster == fc].set_index("horizon_days")[metric]
        return [float(s[h]) for h in HORIZONS]
    n = int(acc[(acc.forecaster == "kalshi") & (acc.horizon_days == 1)].n.iloc[0])
    pvals = [float(dm[dm.horizon_days == h].dm_p.iloc[0]) for h in HORIZONS]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), dpi=170)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes:
        ax.set_facecolor(SURFACE)
    fig.canvas.draw()                            # window extents needed for corner radii
    panel(axes[0], "Mean absolute error (pp)", series("kalshi", "mae"),
          series("cleveland", "mae"), pvals)
    panel(axes[1], "Root mean squared error (pp)", series("kalshi", "rmse"),
          series("cleveland", "rmse"))

    fig.suptitle("The market beats the model at every horizon", x=0.045, y=0.985,
                 ha="left", color=INK, fontsize=14, fontweight="bold")
    fig.text(0.045, 0.915, f"Kalshi implied mean vs. Cleveland Fed nowcast, graded against the "
             f"first-release CPI print  ·  {n} settled releases", color=MUTED, fontsize=10)
    handles = [plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=ORANGE)]
    fig.legend(handles, ["Kalshi implied mean", "Cleveland Fed nowcast"], loc="upper right",
               bbox_to_anchor=(0.985, 0.985), frameon=False, ncol=2, fontsize=10, labelcolor=INK,
               handlelength=1.2, handleheight=1.0)
    fig.subplots_adjust(left=0.045, right=0.985, top=0.80, bottom=0.19, wspace=0.12)
    out = RESULTS / "error_by_horizon.png"
    fig.savefig(out, facecolor=SURFACE)
    print("wrote", out)


if __name__ == "__main__":
    main()
