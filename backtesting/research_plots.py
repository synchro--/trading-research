#!/usr/bin/env python3
"""Generate all figures for the master DCA research report.

Reads backtesting/data/{dca_vs_lumpsum,dip_dca,mm_cushion}.json and writes
PNGs into research/plots/. Run: uv run python -m backtesting.research_plots
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtesting" / "data"
OUT = ROOT / "research" / "plots"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

PORTS = ("stocks_100", "80_20", "60_40", "golden_butterfly")
PORT_LABELS = {
    "stocks_100": "100% stocks",
    "80_20": "80/20",
    "60_40": "60/40",
    "golden_butterfly": "Golden Butterfly",
}
LS_MAIN = json.load(open(DATA / "dca_vs_lumpsum.json"))
DIP = json.load(open(DATA / "dip_dca.json"))
MM = json.load(open(DATA / "mm_cushion.json"))
HYBRID = json.load(open(DATA / "hybrid_split.json"))
CRASH = json.load(open(DATA / "crash_deploy.json"))
DEEP = json.load(open(DATA / "deep" / "deep_history.json"))

LS_STRATS = ("lump_sum", "dca_mid", "oracle_1m", "oracle_pt_3m", "oracle_pt_6m",
             "oracle_cy_3m", "oracle_cy_6m")
LS_COLS = {"lump_sum": "#c0392b", "dca_mid": "#5d6d7e",
           "oracle_1m": "#2980b9", "oracle_pt_3m": "#2980b9", "oracle_pt_6m": "#215f8b",
           "oracle_cy_3m": "#27ae60", "oracle_cy_6m": "#1e8449"}


def idx(summary_rows):
    rows = {}
    for r in summary_rows:
        rows[(r["portfolio"], r["strategy"])] = r
    return rows


def records_by(records, portfolio, strategy):
    return [(r["start"], r["terminal"]) for r in records
            if r["portfolio"] == portfolio and r["strategy"] == strategy]


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    print(f"  [plot] {name}")


def pooled_rows(payload):
    return [r for r in payload["summary"] if r["portfolio"] == "pooled"]


# ---------------------------------------------------------------- LS vs DCA
def plot_ls_vs_dca():
    idx_rows = defaultdict(dict)
    for r in LS_MAIN["summary"]:
        idx_rows[(r["portfolio"], r["strategy"])] = r
    rows = idx_rows

    # A1: median terminal by strategy x portfolio
    fig, ax = plt.subplots(figsize=(9.5, 4))
    w = 0.8 / len(LS_STRATS)
    xs = np.arange(len(PORTS))
    for i, s in enumerate(LS_STRATS):
        vals = [rows[(p, s)]["median"] / 1000 for p in PORTS]
        ax.bar(xs + (i - (len(LS_STRATS) - 1) / 2) * w, vals, width=w, label=s, color=LS_COLS[s])
    ax.set_xticks(xs)
    ax.set_xticklabels([PORT_LABELS[p] for p in PORTS])
    ax.set_ylabel("median terminal (k€)")
    ax.set_title("LS vs DCA — median terminal wealth per window (identical invested amounts, 500/mo)")
    ax.legend(ncol=4, fontsize=7)
    save(fig, "a1_median_terminal.png")

    # A2: distribution of per-window advantage vs lump sum (pooled)
    def records_h(records, portfolio, strategy):
        return [(r["horizon_years"], r["start"], r["terminal"]) for r in records
                if r["portfolio"] == portfolio and r["strategy"] == strategy]

    fig, ax = plt.subplots(figsize=(9.5, 4))
    for s in LS_STRATS[1:]:  # lump_sum is the reference itself
        advs = []
        for p in PORTS:
            ls_map = {(h, k): t for h, k, t in records_h(LS_MAIN["records"], p, "lump_sum")}
            for h, k, t in records_h(LS_MAIN["records"], p, s):
                advs.append(t / ls_map[(h, k)] - 1.0)
        advs = np.asarray(advs)
        ax.hist(advs * 100, bins=80, alpha=0.45, range=(-90, 90),
                label=f"{s} (med {np.median(advs):+.0%})", color=LS_COLS[s], density=True)
    ax.axvline(0, color="black", lw=1)
    ax.set_xlabel("terminal advantage vs lump sum within the same window (%)")
    ax.set_ylabel("density")
    ax.set_title("Distribution of per-window terminal advantage vs lump sum (pooled, all portfolios & horizons)")
    ax.legend(ncol=3, fontsize=7)
    save(fig, "a2_advantage_distribution.png")

    # A3: win rate vs lump sum by horizon
    rec_ls = {p: dict(records_by(LS_MAIN["records"], p, "lump_sum")) for p in PORTS}
    fig, ax = plt.subplots(figsize=(9.5, 4))
    horizons = [10, 12, 14, 16, 18, 20]
    xs = np.arange(len(horizons))
    for i, s in enumerate(LS_STRATS[1:]):
        win = []
        for hy in horizons:
            wcount = tcount = 0
            for p in PORTS:
                mine = [(r["start"], r["terminal"]) for r, in [(0, 0)] if False] \
                    if False else [
                        (r["start"], r["terminal"]) for r in LS_MAIN["records"]
                        if r["portfolio"] == p and r["strategy"] == s and r["horizon_years"] == hy
                    ]
                for k, t in mine:
                    wcount += t > rec_ls[p][k]
                    tcount += 1
            win.append(wcount / max(tcount, 1))
        ax.bar(xs + (i - 2) * 0.13, np.array(win) * 100, width=0.15, label=s, color=LS_COLS[s])
    ax.axhline(50, color="black", ls="--", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{h}y" for h in horizons])
    ax.set_ylabel("win rate vs lump sum (%)")
    ax.set_title("How often does each DCA-family strategy beat lump sum? (all portfolios pooled per horizon)")
    ax.legend(ncol=3, fontsize=7)
    save(fig, "a3_winrate_by_horizon.png")

    # A4: per-horizon median terminal (stocks_100)
    hm = LS_MAIN["horizon_medians"]["stocks_100"]
    horizons = sorted(int(k) for k in next(iter(hm.values())))
    fig, ax = plt.subplots(figsize=(9.5, 4))
    xs = np.arange(len(horizons))
    for i, s in enumerate(LS_STRATS):
        vals = [hm[s][str(h)] / 1000 for h in horizons]
        ax.bar(xs + (i - 3) * 0.115, vals, width=0.13, label=s, color=LS_COLS[s])
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{h}y" for h in horizons])
    ax.set_ylabel("median terminal (k€)")
    ax.set_title("stocks_100 — median terminal by horizon (X grows with horizon: 60k → 120k)")
    ax.legend(ncol=4, fontsize=7)
    save(fig, "a4_medians_by_horizon.png")


# ------------------------------------------------------------ DCA vs oracle
def plot_dip_family():
    pooled = {r["strategy"]: r for r in pooled_rows(DIP)}
    per_port = defaultdict(dict)
    for r in DIP["summary"]:
        per_port[r["portfolio"]][r["strategy"]] = r
    strategies = tuple(pooled)
    palette = plt.cm.tab20.colors
    cmap = {s: palette[i % 20] for i, s in enumerate(strategies)}

    # B1: EUR-for-EUR advantage vs dca_mid per portfolio
    fig, ax = plt.subplots(figsize=(11, 4.4))
    xs = np.arange(len(PORTS))
    n = len(strategies)
    for i, s in enumerate(strategies):
        vals = [per_port[p][s]["per_euro_adv_median_vs_dca"] * 100 for p in PORTS]
        ax.bar(xs + (i - (n - 1) / 2) * (0.8 / n), vals, width=0.8 / n, label=s, color=cmap[s])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([PORT_LABELS[p] for p in PORTS])
    ax.set_ylabel("EUR-for-EUR timing advantage vs naive DCA (%, median)")
    ax.set_title("DCA vs oracle & dip strategies — per-EUR timing skill (dip_dca study, all trigger variants)")
    ax.legend(ncol=3, fontsize=7)
    save(fig, "b1_dip_family_per_euro.png")

    # B2: oracle ladder vs naive DCA
    fig, ax = plt.subplots(figsize=(9.5, 4))
    ladder = ("dca_mid", "oracle_1m", "oracle_pt_3m", "oracle_pt_6m", "oracle_cy_3m", "oracle_cy_6m")
    xs = np.arange(len(PORTS))
    n = len(ladder)
    for i, s in enumerate(ladder):
        vals = [per_port[p][s]["adv_median_vs_dca_mid"] * 100 for p in PORTS]
        ax.bar(xs + (i - (n - 1) / 2) * (0.8 / n), vals, width=0.8 / n,
               label=s, color="#95a5a6" if i == 0 else "#8e44ad")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels([PORT_LABELS[p] for p in PORTS])
    ax.set_ylabel("terminal advantage vs dca_mid (%, median)")
    ax.set_title("Oracle ladder — hindsight dip knowledge by patience horizon (1m, 3m, 3m-cycle, 6m, 6m-cycle)")
    ax.legend(ncol=3, fontsize=7)
    save(fig, "b2_oracle_ladder.png")

    # B3: trigger rate by portfolio for implementable rules
    fig, ax = plt.subplots(figsize=(9, 3.8))
    rules = [s for s in strategies
             if isinstance(per_port["stocks_100"].get(s, {}).get("triggered_months_pct"), float)]
    xs = np.arange(len(PORTS))
    for i, s in enumerate(rules):
        vals = [per_port[p][s]["triggered_months_pct"] * 100 for p in PORTS]
        ax.bar(xs + (i - (len(rules) - 1) / 2) * (0.8 / len(rules)), vals, width=0.8 / len(rules),
               label=s, color=cmap[s])
    ax.set_xticks(xs)
    ax.set_xticklabels([PORT_LABELS[p] for p in PORTS])
    ax.set_ylabel("% of months that trigger a deployment")
    ax.set_title("Implementable dip rules — trigger frequency by portfolio")
    ax.legend(ncol=2, fontsize=7)
    save(fig, "b3_trigger_rates.png")

    # B4: skill vs capital deployed (pooled)
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for s in strategies:
        r = pooled[s]
        ax.scatter(r["median_invested"], r["per_euro_adv_median_vs_dca"] * 100, s=60, color=cmap[s])
        ax.annotate(s, (r["median_invested"], r["per_euro_adv_median_vs_dca"] * 100),
                    fontsize=7, alpha=0.9, xytext=(4, 3), textcoords="offset points")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("median invested per window (k€)")
    ax.set_ylabel("EUR-for-EUR timing edge vs dca_mid (%, median)")
    ax.set_title("Timing skill vs capital deployed — dip family, pooled")
    save(fig, "b4_skill_vs_capital.png")


# ---------------------------------------------------------------- cushion
def plot_cushion():
    idx_rows = defaultdict(dict)
    for r in MM["summary"]:
        idx_rows[(r["portfolio"], r["strategy"])] = r
    rows = idx_rows
    strategies = ("lump_sum_30k", "dca_cushion", "oracle_cushion", "dip2x_mm")
    cols = {"lump_sum_30k": "#c0392b", "dca_cushion": "#5d6d7e",
            "oracle_cushion": "#8e44ad", "dip2x_mm": "#e67e22"}
    xs = np.arange(len(PORTS))

    fig, ax = plt.subplots(figsize=(9.5, 4))
    for i, s in enumerate(strategies):
        vals = [rows[(p, s)]["median"] / 1000 for p in PORTS]
        ax.bar(xs + (i - 1.5) * 0.2, vals, width=0.2, label=s, color=cols[s])
    ax.set_xticks(xs)
    ax.set_xticklabels([PORT_LABELS[p] for p in PORTS])
    ax.set_ylabel("median total (portfolio + MMF left) k€")
    ax.set_title("Cushion study — same budget (30k reserve + 500/mo), four allocation policies")
    ax.legend(ncol=4, fontsize=7)
    save(fig, "c1_cushion_medians.png")

    fig, ax = plt.subplots(figsize=(9.5, 4))
    for i, s in enumerate(strategies):
        t = [rows[(p, s)]["median"] / 1000 for p in PORTS]
        mm = [rows[(p, s)]["median_mmf_left"] / 1000 for p in PORTS]
        ax.bar(xs + (i - 1.5) * 0.2, [ti - mi for ti, mi in zip(t, mm)], width=0.2,
               color=cols[s], label=s)
        ax.bar(xs + (i - 1.5) * 0.2, mm, width=0.2,
               bottom=[ti - mi for ti, mi in zip(t, mm)],
               color=cols[s], alpha=0.35, hatch="//")
    ax.set_xticks(xs)
    ax.set_xticklabels([PORT_LABELS[p] for p in PORTS])
    ax.set_ylabel("median terminal split k€")
    ax.set_title("Median terminal split: equity/portfolio part (solid) vs leftover money-market reserve (hatched)")
    ax.legend(ncol=2, fontsize=8)
    save(fig, "c2_cushion_split.png")


# ------------------------------------------------------------- ALL vs ALL
def plot_all_vs_all():
    pooled_ls = {r["strategy"]: r for r in pooled_rows(LS_MAIN)}
    pooled_dip = {r["strategy"]: r for r in pooled_rows(DIP)}
    pooled_mm = {r["strategy"]: r for r in pooled_rows(MM)}

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), gridspec_kw={"width_ratios": [2.1, 1.0]})

    # Panel A: matched-capital family — median per-window per-EUR edge vs naive DCA (=1.0)
    # (adv_median_vs_dca_mid is the same statistic in both study artifacts)
    entries = {s: 1.0 + r["adv_median_vs_dca_mid"] for s, r in pooled_ls.items()}
    for s, r in pooled_dip.items():
        if s not in entries:  # dip-capital strategies: use the per-EUR metric
            entries[s] = 1.0 + r["per_euro_adv_median_vs_dca"]
    keep = sorted(entries.items())
    names_a = [s for s, _ in keep]
    vals_a = [v for _, v in keep]
    colors_a = [
        "#c0392b" if "lump" in s else "#8e44ad" if s.startswith("oracle") else "#2c7fb8"
        for s in names_a
    ]
    bars = axes[0].barh(names_a, vals_a, color=colors_a)
    axes[0].invert_yaxis()
    axes[0].axvline(1.0, color="black", lw=0.8, ls="--")
    axes[0].set_xlabel("per-window per-EUR wealth vs naive mid-month DCA (=1.0), median")
    axes[0].set_title("Matched-capital family (every strategy invests X = 500×months per window)\n"
                      "red = lump sum, purple = hindsight oracles, blue = implementable rules")
    for i, v in enumerate(vals_a):
        axes[0].text(v, i, f" {v:.3f}", va="center", fontsize=7.5)
    axes[0].set_xlim(min(0.9, min(vals_a) - 0.02), max(vals_a) * 1.08)

    # Panel B: cushion family relative to lump_sum_30k
    pooled_mm = {r["strategy"]: r for r in pooled_rows(MM)}
    names_b = ("lump_sum_30k", "dca_cushion", "oracle_cushion", "dip2x_mm")
    ls_med = pooled_mm["lump_sum_30k"]["median"]
    rel = [pooled_mm[s]["median"] / ls_med for s in names_b]
    cols_b = ["#c0392b", "#5d6d7e", "#8e44ad", "#e67e22"]
    axes[1].barh(names_b, rel, color=cols_b)
    axes[1].invert_yaxis()
    axes[1].axvline(1.0, color="black", lw=0.8)
    axes[1].set_xlim(0, 1.15)
    axes[1].set_xlabel("total terminal relative to lump sum (=1.0)")
    axes[1].set_title("Cushion family (30k + 500/mo budget)\nsame income pools, four policies")
    for i, v in enumerate(rel):
        axes[1].text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=8)
    save(fig, "d1_all_vs_all_tournament.png")


def plot_hybrid():
    pooled = {r["strategy"]: r for r in HYBRID["summary"] if r["portfolio"] == "pooled"}
    splits = sorted({s for s in pooled if s.startswith("hyb") and not s.endswith("dip")})
    grid = {}
    for s in splits:
        head, tail = s.split("_m")
        grid[(int(head[3:]), "m" + tail)] = pooled[s]["adv_median_vs_ls"] * 100
    alpha_rows = sorted({k[0] for k in grid})
    m_cols = [c for c in ("m12", "m24", "mfull") if any((a, c) in grid for a in alpha_rows)]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), gridspec_kw={"width_ratios": [1.25, 1]})
    mat = np.array([[grid[(a, c)] for c in m_cols] for a in alpha_rows])
    im = axes[0].imshow(mat, cmap="RdYlGn", vmin=-15, vmax=0, aspect="auto")
    axes[0].set_xticks(range(len(m_cols)), [c.replace("m", "").replace("full", "full-window") + ("" if c.endswith("full") else "mo") for c in m_cols])
    axes[0].set_yticks(range(len(alpha_rows)), [f"{a}% LS" for a in alpha_rows])
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            axes[0].text(j, i, f"{mat[i, j]:+.1f}%", ha="center", va="center", fontsize=8)
    axes[0].set_title("Median terminal vs lump sum\n(α of budget at day 0 × tail length)")
    axes[0].set_xlabel("deployment tail for the remaining (1−α)")
    axes[0].grid(False)
    fig.colorbar(im, ax=axes[0], shrink=0.8, label="median advantage vs LS (%)")

    names = ["ls", "hyb75_m12", "hyb50_m12", "hyb25_m12", "hyb50_mfull", "dca_full"]
    under = [pooled[n]["underwater_12m"] * 100 for n in names]
    axes[1].barh(names, under, color=["#c0392b", "#e67e22", "#f1c40f", "#f39c12", "#8e44ad", "#5d6d7e"])
    axes[1].invert_yaxis()
    axes[1].set_xlabel("% of windows with wealth below budget at month 12")
    axes[1].set_title("First-year regret (Vanguard-style)\nhigher = more likely to be down after 1 year")
    for i, v in enumerate(under):
        axes[1].text(v + 0.3, i, f"{v:.0f}%", va="center", fontsize=8)
    save(fig, "f1_hybrid_frontier.png")


def plot_crash():
    pooled = [r for r in CRASH["summary"] if r["portfolio"] == "pooled"]
    order = [s for s in ("ls", "wait20_dca12", "wait20_lump", "wait20_tranches", "wait30_lump", "parked")]
    by = {r["strategy"]: r for r in pooled}
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    med = [by[s]["adv_median_vs_ls"] * 100 for s in order]
    mean = [by[s]["adv_mean_vs_ls"] * 100 for s in order]
    xs = np.arange(len(order))
    axes[0].bar(xs - 0.2, med, width=0.4, label="median adv", color="#e67e22")
    axes[0].bar(xs + 0.2, mean, width=0.4, label="mean adv", color="#c0392b")
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].set_xticks(xs, order, rotation=20, ha="right", fontsize=7.5)
    axes[0].set_ylabel("terminal advantage vs lump sum (%)")
    axes[0].set_title("Cash-is-king: wait for a crash, then deploy (windfall budget X)")
    axes[0].legend(fontsize=8)

    trig = [by[s]["trigger_rate"] * 100 for s in order]
    axes[1].barh(order, trig, color="#2c7fb8")
    axes[1].invert_yaxis()
    axes[1].set_xlabel("% of windows that triggered at least once")
    axes[1].set_title("Did the crash come at all?\n(missed trigger = the money stays in cash)")
    for i, v in enumerate(trig):
        axes[1].text(v + 1, i, f"{v:.0f}%", va="center", fontsize=8)
    save(fig, "g1_crash_deploy.png")


def plot_deep():
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw={"width_ratios": [1.4, 1]})
    per = DEEP["per_window_10y_stocks"]
    x = [int(r["start"][:4]) + (int(r["start"][5:7]) - 1) / 12 for r in per]
    y = [r["dca_adv"] * 100 for r in per]
    yo = [r["oracle_adv"] * 100 for r in per]
    axes[0].plot(x, y, lw=0.7, color="#2c3e50", label="DCA vs lump sum")
    axes[0].plot(x, yo, lw=0.7, color="#8e44ad", alpha=0.8, label="oracle_cy_6m vs lump sum")
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].axvspan(1929, 1940, color="#c0392b", alpha=0.08)
    axes[0].text(1931, max(y) * 0.75, "1929-40:\nDCA wins big", color="#c0392b", fontsize=8)
    axes[0].set_xlabel("window start (10y windows, US stocks 1926-2026)")
    axes[0].set_ylabel("terminal advantage vs lump sum (%)")
    axes[0].set_title("Deep history: 1,082 rolling 10y windows since 1926")
    axes[0].legend(fontsize=8)

    dec = sorted(
        [(r["decade"], r["mean_adv"] * 100, r["n"]) for r in DEEP["decade_mean_adv"] if r["portfolio"] == "stocks_100"]
    )
    axes[1].bar([str(d) + "s" for d, _, _ in dec], [v for _, v, _ in dec], color="#5d6d7e")
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].set_ylabel("mean DCA advantage vs LS (%)")
    axes[1].set_title("Mean DCA-vs-LS by start decade\n(all horizons pooled, stocks)")
    axes[1].tick_params(axis="x", rotation=45, labelsize=7)
    save(fig, "h1_deep_history.png")


def main() -> None:
    plot_ls_vs_dca()
    plot_dip_family()
    plot_cushion()
    plot_all_vs_all()
    plot_hybrid()
    plot_crash()
    plot_deep()
    print(f"\nwrote figures to {OUT}")


if __name__ == "__main__":
    main()
