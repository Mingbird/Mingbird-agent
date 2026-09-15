"""Regenerate the LRAB figures from benchmarks/lrab_scores.csv.

Run from anywhere:  python docs/assets/regen_figures.py

Outputs (written next to this script):
  - lrab_by_model.png   grouped bars, per-model segment scores, 4 harnesses
  - lrab_overall.png    horizontal bars, overall score per harness

Style matches the previous figures: serif, flat colors, value labels, no
chart title. X-tick labels carry model name + parameter tier only — no
architecture tags (the old generator stamped "(MoE)" on the 35B group).

Every aggregate is checked against the FACTS.md numbers before plotting;
the script fails loudly if the CSV no longer reproduces them.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE.parent.parent / "benchmarks" / "lrab_scores.csv"

MODELS = [
    ("gemma4_e2b", "gemma4:e2b (2B)"),
    ("qwen3.5_4b", "qwen3.5:4b (4B)"),
    ("gemma4_12b", "gemma4:12b (12B)"),
    ("ornith1.5_35b", "ornith-1.5:35b (35B)"),
]
HARNESSES = ["Mingbird", "goose", "agent-mini", "opencode"]
COLORS = {
    "Mingbird": "#0e9488",
    "goose": "#4a545e",
    "agent-mini": "#8b949e",
    "opencode": "#c4ccd4",
}
GRAY = "#555555"

# FACTS.md §4 — the script refuses to draw figures from numbers that drift.
EXPECTED_SEGMENTS = {
    "Mingbird": [0.799, 0.921, 0.920, 0.939],
    "goose": [0.266, 0.636, 0.620, 0.822],
    "agent-mini": [0.246, 0.706, 0.576, 0.092],
    "opencode": [0.017, 0.404, 0.140, 0.776],
}
EXPECTED_OVERALL = {"Mingbird": 0.895, "goose": 0.586, "agent-mini": 0.405, "opencode": 0.334}

FIGSIZE = (12, 5.6)  # 1680 x 780 px at dpi=140, same canvas as the old figures
DPI = 140


def load_scores():
    seg = defaultdict(list)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seg[(row["harness"], row["model"])].append(float(row["score"]))
    segments = {
        h: [sum(seg[(h, m)]) / len(seg[(h, m)]) for m, _ in MODELS] for h in HARNESSES
    }
    overall = {h: sum(segments[h]) / len(MODELS) for h in HARNESSES}
    return segments, overall


def check(segments, overall):
    problems = []
    for h in HARNESSES:
        for i, got in enumerate(segments[h]):
            if round(got, 3) != EXPECTED_SEGMENTS[h][i]:
                problems.append(
                    f"{h} {MODELS[i][1]}: got {got:.3f}, expected {EXPECTED_SEGMENTS[h][i]}"
                )
        if round(overall[h], 3) != EXPECTED_OVERALL[h]:
            problems.append(f"{h} overall: got {overall[h]:.3f}, expected {EXPECTED_OVERALL[h]}")
    if problems:
        sys.exit("CSV does not reproduce FACTS.md numbers:\n  " + "\n  ".join(problems))


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def fig_by_model(segments):
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    n_groups, n_bars = len(MODELS), len(HARNESSES)
    width = 0.19
    offsets = [(i - (n_bars - 1) / 2) * width for i in range(n_bars)]

    for i, h in enumerate(HARNESSES):
        xs = [g + offsets[i] for g in range(n_groups)]
        vals = segments[h]
        ax.bar(xs, vals, width=width, label=h, color=COLORS[h], edgecolor="none")
        for x, v in zip(xs, vals):
            ax.annotate(
                f"{v:.3f}",
                (x, v),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                fontsize=7.5,
                color=COLORS["Mingbird"] if h == "Mingbird" else GRAY,
                fontweight="bold" if h == "Mingbird" else "normal",
            )

    ax.set_xticks(range(n_groups))
    ax.set_xticklabels([label for _, label in MODELS], fontsize=10)
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
    ax.set_ylabel("LRAB-288 task score", fontsize=10)
    ax.grid(axis="y", alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9)
    style_axes(ax)
    ax.legend(ncol=n_bars, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.10), fontsize=9)
    fig.tight_layout()
    fig.savefig(HERE / "lrab_by_model.png")
    plt.close(fig)


def fig_overall(overall):
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    order = sorted(HARNESSES, key=lambda h: overall[h])  # lowest at the bottom axis position 0
    ys = range(len(order))
    ax.barh(ys, [overall[h] for h in order], height=0.55, color=[COLORS[h] for h in order])
    for y, h in zip(ys, order):
        v = overall[h]
        ax.annotate(
            f"{v:.3f}",
            (v, y),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            color=COLORS["Mingbird"] if h == "Mingbird" else GRAY,
            fontweight="bold" if h == "Mingbird" else "normal",
        )
    ax.set_yticks(list(ys))
    ax.set_yticklabels(order, fontsize=10)
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0])
    ax.set_xlabel("LRAB-288 overall score", fontsize=10)
    ax.grid(axis="x", alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(HERE / "lrab_overall.png")
    plt.close(fig)


def main():
    segments, overall = load_scores()
    check(segments, overall)
    fig_by_model(segments)
    fig_overall(overall)
    print("wrote lrab_by_model.png, lrab_overall.png")
    print("xticks:", ", ".join(label for _, label in MODELS))


if __name__ == "__main__":
    matplotlib.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"]})
    main()
