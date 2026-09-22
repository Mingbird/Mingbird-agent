#!/usr/bin/env python3
"""Figure 9 of the Mingbird preprint: measured prefill cost curve.

Input (read-only, one row per model x tool-surface width):
    benchmarks/failure_forms/cost_curve_data_2609.csv
      model, tool_count, n_runs, median_s, iqr_s, min_s,
      median_prompt_ms, median_prompt_tokens, wall_s_med, anchor,
      source_file, note

What is plotted
    x = median_prompt_tokens   -- tokens actually reported by the backend
                                  (Ollama prompt_eval_count) for that payload
    y = median_s               -- median prompt-evaluation (prefill) seconds
    Each model keeps its own measured x values: the two tiers do NOT share a
    tool-count axis and no equal-value alignment between them is implied.
    Axes are log-log (both quantities span ~2 decades).

Anchors (hollow markers, identified by their tool_count in the CSV):
    19  tools -- bench clean instance (cat: full category route), no MCP
    31  tools -- global real user configuration (18 builtin + 12 MCP + mcp_call)
    256 tools -- duplicated/renamed payloads, the width ceiling measured here

Fit lines
    Thin dashed line per model over the anchor window [19, 256] tool widths.
    Degree is chosen from the data, not hardcoded: a quadratic is used only if
    its leading coefficient is positive AND it cuts the RMS residual to below
    half of the linear fit's (i.e. the growth is materially super-linear),
    otherwise the linear fit is kept. Coefficients, R^2 and the implied
    ms/prefill-token slope are printed so the text's quoted numbers can be
    re-checked against the CSV.

Deliberately NOT plotted
    * Error bars. The iqr_s column is empty in the source data: per-run values
      were never persisted, so no dispersion is recoverable. The script asserts
      this rather than silently drawing nothing.
    * The harness's static prefill budgets (the _estimate_tokens figures quoted
      in the text): they come from a harness-side estimator, i.e. a different
      measurement basis than the backend token counts on this axis.

Run:  python benchmarks/failure_forms/make_fig9_costcurve.py
Outputs (this directory): fig9_costcurve.pdf, fig9_costcurve.png (300 dpi)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "cost_curve_data_2609.csv"   # 与本脚本同目录(sibling)
OUT_STEM = "fig9_costcurve"

# Okabe-Ito pair; line style and marker shape differ as well, so the two tiers
# stay separable in grayscale and under colour-vision deficiency.
STYLE = {
    "qwen3.5:4b": dict(tier="4B", color="#0072B2", ls="-", marker="s"),
    "gemma4:e2b": dict(tier="2B", color="#D55E00", ls="--", marker="o"),
}
ANCHOR_TOOLS = (19, 31)          # annotated in the CSV 'anchor' column
FIT_LO, FIT_HI = 19, None        # window: first anchored width .. widest width

# Small anchor labels: point offset and alignment, tuned so no label sits on a
# curve or on the other tier's label.
LABEL_POS = {
    ("qwen3.5:4b", 19): (-6, 4, "right", "bottom"),
    ("qwen3.5:4b", 31): (7, -4, "left", "top"),
    ("qwen3.5:4b", 256): (-7, -7, "right", "top"),
    ("gemma4:e2b", 19): (-6, -10, "right", "top"),
    ("gemma4:e2b", 31): (7, -5, "left", "top"),
    ("gemma4:e2b", 256): (-7, 1, "right", "bottom"),
}

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.labelsize": 9,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.linestyle": ":",
    "grid.alpha": 0.6,
    "axes.axisbelow": True,
    "figure.dpi": 150,
    "legend.frameon": False,
})


def load() -> dict[str, list[tuple[int, float, float]]]:
    """model -> sorted [(tool_count, prompt_tokens, seconds), ...]."""
    data: dict[str, list[tuple[int, float, float]]] = {}
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    if not rows:
        sys.exit(f"no rows in {CSV_PATH}")
    for r in rows:
        if not r["median_prompt_tokens"] or not r["median_s"]:
            continue
        data.setdefault(r["model"], []).append(
            (int(r["tool_count"]), float(r["median_prompt_tokens"]),
             float(r["median_s"])))
    for m in data:
        data[m].sort()
    # Hard guard: this figure must not imply a dispersion it cannot show.
    empty_iqr = all(not r["iqr_s"].strip() for r in rows)
    if not empty_iqr:
        sys.exit("iqr_s is populated; re-check before omitting error bars")
    print(f"read {len(rows)} rows from {CSV_PATH.name}: "
          f"iqr_s empty in every row -> no error bars drawn")
    return data


def choose_fit(x: np.ndarray, y: np.ndarray) -> tuple[int, dict]:
    """Linear unless a positive-curvature quadratic clearly beats it."""
    fits = {}
    for deg in (1, 2):
        coef = np.polyfit(x, y, deg)
        resid = y - np.polyval(coef, x)
        fits[deg] = dict(
            coef=coef,
            rms=float(np.sqrt(np.mean(resid ** 2))),
            r2=1.0 - float(np.sum(resid ** 2)) / float(np.sum((y - y.mean()) ** 2)),
        )
    superlinear = fits[2]["coef"][0] > 0 and fits[2]["rms"] < 0.5 * fits[1]["rms"]
    return (2 if superlinear else 1), fits


def plot_series(ax, model: str, pts: list[tuple[int, float, float]]) -> None:
    st = STYLE[model]
    tool = np.array([p[0] for p in pts])
    tok = np.array([p[1] for p in pts])
    sec = np.array([p[2] for p in pts])

    ax.plot(tok, sec, ls=st["ls"], color=st["color"], lw=1.3, zorder=3,
            marker=st["marker"], ms=4.0, mfc=st["color"], mec="black", mew=0.4,
            label=f"{model} ({st['tier']} tier)")

    hi = FIT_HI if FIT_HI is not None else int(tool.max())
    win = (tool >= FIT_LO) & (tool <= hi)
    deg, fits = choose_fit(tok[win], sec[win])
    coef = fits[deg]["coef"]
    xf = np.array([tok[win][0], tok[win][-1]])
    ax.plot(xf, np.polyval(coef, xf), ls=(0, (1.6, 2.4)), color=st["color"],
            lw=0.75, zorder=2)

    anchors = set(ANCHOR_TOOLS) | {int(tool.max())}
    for tc, tk, sc in [(int(a), float(b), float(c)) for a, b, c in zip(tool, tok, sec)
                       if int(a) in anchors]:
        ax.plot([tk], [sc], ls="none", marker=st["marker"], ms=9, mfc="white",
                mec=st["color"], mew=1.4, zorder=5)
        dx, dy, ha, va = LABEL_POS.get((model, tc), (7, 4, "left", "bottom"))
        ax.annotate(f"{tc}", (tk, sc), textcoords="offset points",
                    xytext=(dx, dy), ha=ha, va=va, fontsize=6.5, style="italic",
                    color=st["color"], zorder=6,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=0.7))

    # Report the fit in both units so the text's ~ms/token figure is checkable.
    slope_ms = coef[-2] * 1000.0 if deg == 1 else float("nan")
    print(f"[{model}] window {FIT_LO}-{hi} tools, degree {deg}: "
          + " ".join(f"{c:.6g}" for c in coef)
          + f"  R2={fits[deg]['r2']:.4f}"
          + (f"  slope={slope_ms:.4f} ms/token" if deg == 1 else
             f"  quadratic term={coef[0]:.3g} (>0: super-linear)"))


def main() -> None:
    data = load()
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    for model in STYLE:
        if model in data:
            plot_series(ax, model, data[model])

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(200, 4.2e4)
    ax.set_ylim(0.15, 90)
    ax.set_xlabel("measured prompt tokens (Ollama prompt_eval_count)")
    ax.set_ylabel("prefill time (s, median of 3 runs)")

    ax.plot([], [], ls="none", marker="s", ms=8, mfc="white", mec="#555555",
            mew=1.3, label="tool-surface anchor (19 / 31 / 256 tools)")
    ax.legend(loc="upper left", fontsize=7.5, handlelength=2.4,
              labelspacing=0.4, borderaxespad=0.3)

    fig.tight_layout()
    fig.savefig(HERE / f"{OUT_STEM}.pdf", bbox_inches="tight")
    fig.savefig(HERE / f"{OUT_STEM}.png", bbox_inches="tight", dpi=300)
    plt.close(fig)
    print(f"wrote {OUT_STEM}.pdf / {OUT_STEM}.png in {HERE}")


if __name__ == "__main__":
    main()
