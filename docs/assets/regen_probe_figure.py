"""Regenerate the frontier-probe figure (frontier model vs local 4B, same 18 tasks).

Run from anywhere:  python docs/assets/regen_probe_figure.py

Output (written next to this script):
  - probe_vs_local.png   grouped bars: per harness, local qwen3.5:4b (LRAB-288
                         4B column) against the hosted frontier model (probe)

Story the chart has to carry: with a defective scaffold the frontier model is
thrown away (agent-mini 0.706 -> 0.478), while intact scaffolds jump
(mingbird 0.876 -> 0.997, goose 0.801 -> 0.989, opencode 0.465 -> 0.925).

Style matches docs/assets/regen_figures.py: serif, flat colors, value labels,
no chart title, Mingbird highlighted. Numbers are checked against FACTS.md
before plotting; the script fails loudly if the CSVs stop reproducing them.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
LRAB = HERE.parent.parent / "benchmarks" / "lrab_scores.csv"
PROBE = HERE.parent.parent / "benchmarks" / "frontier_probe" / "frontier_probe_scores.csv"

# LRAB harness spelling -> probe arm spelling
ARMS = [
    ("Mingbird", "mingbird"),
    ("goose", "goose"),
    ("agent-mini", "agent-mini"),
    ("opencode", "opencode"),
]
COLORS = {
    "Mingbird": "#0e9488",
    "goose": "#4a545e",
    "agent-mini": "#8b949e",
    "opencode": "#c4ccd4",
}
LOCAL_TINT = "#e8edf2"   # light fill for the local-model bar
GRAY = "#555555"

# FACTS.md §4 (4B column) and §9 (probe). opencode's probe mean is over the 17
# scored cells; its WF-08 timeout is scored 0 in the paper's footnote (0.874).
EXPECTED_LOCAL = {"Mingbird": 0.876, "goose": 0.801, "agent-mini": 0.706, "opencode": 0.465}
EXPECTED_PROBE = {"Mingbird": 0.9966, "goose": 0.9887, "agent-mini": 0.4779, "opencode": 0.9250}

FIGSIZE = (12, 5.6)
DPI = 140


def mean_scores(path, key, want=None, filt=None):
    agg = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if filt and row.get(filt[0]) != filt[1]:
                continue
            if want is not None and row[key] != want:
                continue
            s = (row.get("score") or "").strip()
            if s:
                agg[row[key]].append(float(s))
    return {k: sum(v) / len(v) for k, v in agg.items()}


def check(local, probe):
    bad = []
    for h, arm in ARMS:
        if h not in local or round(local[h], 3) != round(EXPECTED_LOCAL[h], 3):
            bad.append(f"{h} local4B: got {local.get(h, float('nan')):.4f}, expected {EXPECTED_LOCAL[h]}")
        if arm not in probe or round(probe[arm], 3) != round(EXPECTED_PROBE[h], 3):
            bad.append(f"{h} probe: got {probe.get(arm, float('nan')):.4f}, expected {EXPECTED_PROBE[h]}")
    if bad:
        sys.exit("CSVs no longer reproduce FACTS.md numbers:\n  " + "\n  ".join(bad))


def draw(local, probe):
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    width = 0.36
    xs = range(len(ARMS))

    ax.bar([x - width / 2 for x in xs], [local[h] for h, _ in ARMS], width=width,
           label="local qwen3.5:4b (iGPU laptop)", color=LOCAL_TINT,
           edgecolor="#9aa4ae", linewidth=0.8)
    ax.bar([x + width / 2 for x in xs], [probe[a] for _, a in ARMS], width=width,
           label="hosted frontier model, same 18 tasks",
           color=[COLORS[h] for h, _ in ARMS], edgecolor="none")

    for x, (h, arm) in enumerate(ARMS):
        ax.annotate(f"{local[h]:.3f}", (x - width / 2, local[h]), xytext=(0, 2),
                    textcoords="offset points", ha="center", fontsize=8, color=GRAY)
        ax.annotate(f"{probe[arm]:.3f}", (x + width / 2, probe[arm]), xytext=(0, 2),
                    textcoords="offset points", ha="center", fontsize=8.5,
                    color=COLORS["Mingbird"] if h == "Mingbird" else GRAY,
                    fontweight="bold" if h == "Mingbird" else "normal")

    ax.set_xticks(list(xs))
    ax.set_xticklabels([h for h, _ in ARMS], fontsize=10.5)
    ax.set_ylim(0, 1.09)
    ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
    ax.set_ylabel("LRAB task score (18 tasks)", fontsize=10)
    ax.grid(axis="y", alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.10), fontsize=9.5)
    fig.tight_layout()
    fig.savefig(HERE / "probe_vs_local.png")
    plt.close(fig)


def main():
    local = mean_scores(LRAB, "harness", filt=("model", "qwen3.5_4b"))
    probe = mean_scores(PROBE, "arm")
    check(local, probe)
    draw(local, probe)
    print("wrote probe_vs_local.png")
    print("local4B:", {h: round(local[h], 4) for h, _ in ARMS})
    print("probe  :", {h: round(probe[a], 4) for h, a in ARMS})


if __name__ == "__main__":
    matplotlib.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"]})
    main()
