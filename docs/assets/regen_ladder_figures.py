"""Regenerate the ladder-paper figures from the numbers of arXiv:2611.21407.

Run from anywhere:  python docs/assets/regen_ladder_figures.py

Outputs (written next to this script):
  - ladder_by_size.png     grouped bars, mean artifact score, 5 harnesses x 4 rungs
  - ladder_quiet_stop.png  100% stacked bars, what each arm leaves on disk (Table 8)

The per-cell archive is not in the repo, so there is no CSV to recompute from:
the numbers below are pinned to the paper's Tables 4 and 8 verbatim. The script
fails loudly if the pinned matrix stops satisfying the paper's own invariants
(row sums, column totals, the 357-cell census), so a silent typo cannot reach
the figures.

Style matches the older repo figures: serif, flat colors, value labels,
no chart title.
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
DPI = 140

# ---- Table 4, deployment reading (a cell at the wall budget scores zero) ----
RUNGS = ["0.75B", "1.9B", "3.7B", "4.7B"]
RUNG_FAMILIES = ["Qwen3.5", "Qwen3.5", "Granite 4.2", "Qwen3.5"]
EXPECTED_SCORES = {
    "Mingbird": [0.664, 0.593, 0.762, 0.968],
    "pi": [0.172, 0.409, 0.714, 0.893],
    "OpenCode": [0.112, 0.295, 0.000, 0.632],
    "goose": [0.186, 0.372, 0.262, 0.718],
    "mini-swe-agent": [0.012, 0.029, 0.279, 0.150],
}
EXPECTED_SPANS = [0.653, 0.564, 0.762, 0.819]

# ---- Table 8, what each arm leaves on disk over the 357 usable cells ----
# none-split: (normal exit = the quiet stop, wall budget, other termination)
EXPECTED_CELLS = {
    # arm: (complete, partial, none_quiet, none_budget, none_other, usable)
    "mini-swe-agent": (4, 18, 34, 7, 9, 72),
    "OpenCode": (12, 28, 22, 10, 0, 72),
    "goose": (22, 23, 15, 8, 3, 71),
    "pi": (37, 20, 10, 4, 1, 72),
    "Mingbird": (52, 14, 4, 0, 0, 70),
}

COLORS = {
    "Mingbird": "#0e9488",
    "pi": "#4a545e",
    "goose": "#7d8b99",
    "OpenCode": "#b9c2cb",
    "mini-swe-agent": "#e0e5ea",
}
HARNESS_ORDER = ["Mingbird", "pi", "OpenCode", "goose", "mini-swe-agent"]

SEG_COLORS = {
    "complete": "#0e9488",
    "partial": "#9fbab6",
    "quiet": "#e07b39",   # none of the artifacts, normal exit
    "budget": "#4a545e",
    "other": "#c4ccd4",
}
GRAY = "#555555"

FIGSIZE_A = (12, 5.6)
FIGSIZE_B = (12, 5.2)


def check_invariants():
    problems = []
    # span column of Table 4
    for i, rung in enumerate(RUNGS):
        vals = {h: EXPECTED_SCORES[h][i] for h in HARNESS_ORDER}
        span = round(max(vals.values()) - min(vals.values()), 3)
        # paper spans come from unrounded means, so allow one final-digit slip
        if abs(span - EXPECTED_SPANS[i]) > 0.0011:   # one final-digit slip from unrounded means
            problems.append(f"{rung}: span {span} != paper {EXPECTED_SPANS[i]}")
    # Table 8 census
    total = 0
    complete_sum = quiet_sum = none_sum = 0
    for arm, (c, p, nq, nb, no, usable) in EXPECTED_CELLS.items():
        if c + p + nq + nb + no != usable:
            problems.append(f"{arm}: row sums to {c+p+nq+nb+no}, usable is {usable}")
        total += usable
        complete_sum += c
        quiet_sum += nq
        none_sum += nq + nb + no
    if total != 357:
        problems.append(f"usable cells total {total} != paper 357")
    if complete_sum != 127:
        problems.append(f"complete sets total {complete_sum} != paper 127")
    if none_sum != 127:
        problems.append(f"empty cells total {none_sum} != paper 127")
    if quiet_sum != 85:
        problems.append(f"quiet stops total {quiet_sum} != paper 85")
    if problems:
        sys.exit("Pinned numbers do not satisfy the paper's invariants:\n  " + "\n  ".join(problems))


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def fig_ladder():
    fig, ax = plt.subplots(figsize=FIGSIZE_A, dpi=DPI)
    n_rungs, n_bars = len(RUNGS), len(HARNESS_ORDER)
    width = 0.17
    offsets = [(i - (n_bars - 1) / 2) * width for i in range(n_bars)]

    for i, h in enumerate(HARNESS_ORDER):
        vals = EXPECTED_SCORES[h]
        xs = [g + offsets[i] for g in range(n_rungs)]
        ax.bar(xs, vals, width=width, label=h, color=COLORS[h], edgecolor="none")
        for x, v in zip(xs, vals):
            ax.annotate(
                f"{v:.3f}",
                (x, v),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                fontsize=7,
                color=COLORS["Mingbird"] if h == "Mingbird" else GRAY,
                fontweight="bold" if h == "Mingbird" else "normal",
            )

    tick_labels = [
        f"{rung}\n({fam})" if fam != "Granite 4.2" else f"{rung}*\n(Granite 4.2)"
        for rung, fam in zip(RUNGS, RUNG_FAMILIES)
    ]
    ax.set_xticks(range(n_rungs))
    ax.set_xticklabels(tick_labels, fontsize=10)
    ax.set_ylim(0, 1.06)
    ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
    ax.set_ylabel("Mean artifact score (0\u20131)", fontsize=10)
    ax.grid(axis="y", alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9)
    style_axes(ax)
    ax.legend(ncol=n_bars, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.11), fontsize=9)
    ax.text(
        0.0, -0.16,
        "Held-out suite, deployment reading: a cell that reaches its wall budget scores zero. "
        "* single cross-family rung (Granite 4.2); every other rung is Qwen3.5.",
        transform=ax.transAxes, fontsize=8, color=GRAY,
    )
    fig.tight_layout()
    fig.savefig(HERE / "ladder_by_size.png", bbox_inches="tight")
    plt.close(fig)


def fig_quiet_stop():
    # rows sorted by empty rate, descending: mini, OpenCode, goose, pi, Mingbird
    arms = list(EXPECTED_CELLS.keys())
    fig, ax = plt.subplots(figsize=FIGSIZE_B, dpi=DPI)

    ys = range(len(arms))
    lefts = [0.0] * len(arms)
    seg_keys = ["complete", "partial", "quiet", "budget", "other"]

    def seg_values(idx):
        c, p, nq, nb, no, usable = EXPECTED_CELLS[arms[idx]]
        return [c / usable, p / usable, nq / usable, nb / usable, no / usable]

    for y in ys:
        vals = seg_values(y)
        for k, v in zip(seg_keys, vals):
            ax.barh(y, v, left=lefts[y], height=0.58, color=SEG_COLORS[k], edgecolor="white", linewidth=0.5)
            if v >= 0.07:
                dark_bg = k in ("complete", "budget", "quiet")
                ax.annotate(
                    f"{v * 100:.0f}%",
                    (lefts[y] + v / 2, y),
                    ha="center", va="center", fontsize=8,
                    color="white" if dark_bg else "#333333",
                    fontweight="bold" if k == "quiet" else "normal",
                )
            lefts[y] += v

    labels = [
        f"{arm} \u00b7 {EXPECTED_CELLS[arm][5]} cells"
        for arm in arms
    ]
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, fontsize=10)
    # bold the Mingbird row
    for tick in ax.get_yticklabels():
        if tick.get_text().startswith("Mingbird"):
            tick.set_fontweight("bold")
            tick.set_color(COLORS["Mingbird"])
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=9)
    ax.set_xlabel("Share of the arm's usable cells (357 total)", fontsize=10)
    ax.grid(axis="x", alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    style_axes(ax)

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=SEG_COLORS["complete"]),
        plt.Rectangle((0, 0), 1, 1, color=SEG_COLORS["partial"]),
        plt.Rectangle((0, 0), 1, 1, color=SEG_COLORS["quiet"]),
        plt.Rectangle((0, 0), 1, 1, color=SEG_COLORS["budget"]),
        plt.Rectangle((0, 0), 1, 1, color=SEG_COLORS["other"]),
    ]
    ax.legend(
        legend_handles,
        ["every declared artifact written", "some artifacts",
         "none \u2014 exited normally (the quiet stop)", "none \u2014 reached wall budget",
         "none \u2014 other end"],
        ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.16), fontsize=8.5,
    )
    ax.text(
        0.0, -0.18,
        "The quiet stop: 85 of the 127 empty cells ended with a normal process exit \u2014 "
        "exit status alone credits work that was never written.",
        transform=ax.transAxes, fontsize=8, color=GRAY,
    )
    fig.tight_layout()
    fig.savefig(HERE / "ladder_quiet_stop.png", bbox_inches="tight")
    plt.close(fig)


def main():
    check_invariants()
    fig_ladder()
    fig_quiet_stop()
    print("wrote ladder_by_size.png, ladder_quiet_stop.png")


if __name__ == "__main__":
    matplotlib.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"]})
    main()
