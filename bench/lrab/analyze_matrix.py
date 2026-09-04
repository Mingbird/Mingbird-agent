#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze LRAB matrix results → summary table + graceful-degradation chart.

Single source of truth: eval_results/<cell>/score.json directories, run-3
window only (2026-09-02 15:25:15 onward = the 288-cell final matrix).

Protocol (2026-09-04 final):
  - latest-attempt-wins per (agent, model, task): attempt number first, then
    dirname timestamp as tie-break; a poisoned dir without score.json loses
    to any future attempt but 0-scores the cell if it is the latest.
  - timeout / missing-total / missing score.json count 0 (denominator 18).
  - MATRIX_MANIFEST.json is NOT consumed for scores: mid-batch manifests are
    incremental snapshots (probe lesson 09-03) and manifest dedup was
    first-success-wins, which systematically inflated scores.
  - run-1/run-2 (09-02 <= 15:25, incl. the VRAM-anomaly window) are excluded
    by dirname timestamp; a 288-cell completeness assertion gates output.

Usage:
  python analyze_matrix.py [--results ~/dev/hummingbird/eval_results] [--chart out.png]
"""
import argparse, json, os, re, glob, sys

RUN3_WINDOW = ("0902", "152515")
NAME_RE = re.compile(r"^(hummingbird|goose|opencode|agentmini)_(.+?)_(.+)_m(\d+)_(\d{4})_(\d{6})$")
EXPECTED_AGENTS = ["hummingbird", "opencode", "agentmini", "goose"]
EXPECTED_MODELS = ["gemma4_e2b", "qwen3.5_4b", "gemma4_12b", "ornith1.5_35b"]
EXPECTED_TASKS = [f"WF{i:02d}" for i in range(1, 16)] + [f"LH{i:02d}" for i in range(1, 4)]
TOTAL_CELLS = len(EXPECTED_AGENTS) * len(EXPECTED_MODELS) * len(EXPECTED_TASKS)  # 288

def load_scores(results_dir):
    """Scan run-3-window cell dirs, latest-attempt-wins per cell.

    Returns {cell_key: {"total": float, "failure_mode": str, "dir": str}} where
    total is 0.0 for timeout / no-total / no-score.json cells."""
    cells = {}
    for d in glob.glob(os.path.join(results_dir, "*_*")):
        b = os.path.basename(d)
        m = NAME_RE.match(b)
        if not m or not os.path.isdir(d):
            continue
        if (m.group(5), m.group(6)) < RUN3_WINDOW:
            continue  # run-1/run-2 contamination (incl. VRAM-anomaly window)
        agent, task, model = m.group(1), m.group(2), m.group(3)
        att = (int(m.group(4)), b)
        sd = None
        sp = os.path.join(d, "score.json")
        if os.path.isfile(sp):
            try:
                sd = json.load(open(sp, encoding="utf-8"))
            except Exception:
                sd = None
        cur = cells.get((agent, task, model))
        if cur is None or att > cur["att"]:
            t = sd.get("total") if isinstance(sd, dict) else None
            cells[(agent, task, model)] = {
                "att": att,
                "total": t if isinstance(t, (int, float)) else 0.0,
                "failure_mode": (sd or {}).get("failure_mode", "no_score"),
                "dir": b,
            }
    # completeness gate: every planned cell must have >= 1 run-3 attempt
    missing = []
    for ag in EXPECTED_AGENTS:
        for md in EXPECTED_MODELS:
            for tk in EXPECTED_TASKS:
                if (ag, tk, md) not in cells:
                    missing.append(f"{ag}:{md}:{tk}")
    if len(cells) != TOTAL_CELLS or missing:
        print(f"INCOMPLETE: {len(cells)}/{TOTAL_CELLS} cells in run-3 window; "
              f"missing: {missing}", file=sys.stderr)
        sys.exit(1)
    return cells

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.expanduser("~/dev/hummingbird/eval_results"))
    ap.add_argument("--chart", default="", help="save degradation chart PNG path")
    a = ap.parse_args()

    cells = load_scores(a.results)
    print(f"288-cell final matrix, run-3 window (>= {RUN3_WINDOW[0]} {RUN3_WINDOW[1]}), "
          f"latest-attempt-wins, timeout/no-score = 0\n")

    def mean(ag, md, task_filter=None):
        vals = [c["total"] for (x, tk, y), c in cells.items()
                if x == ag and (md is None or y == md)
                and (task_filter is None or task_filter(tk))]
        return sum(vals) / len(vals) if vals else float("nan")

    models = EXPECTED_MODELS
    print(f"{'agent':14s}" + "".join(f"{m:>15s}" for m in models) + f"{'OVERALL':>10s}{'LH-only':>10s}")
    cell_stats = {}
    for ag in EXPECTED_AGENTS:
        row = []
        for md in models:
            m = mean(ag, md)
            row.append(f"{m:>15.3f}")
            cell_stats[(ag, md)] = {
                "mean": m,
                "failures": [c["failure_mode"] for (x, tk, y), c in cells.items()
                             if x == ag and y == md and c["failure_mode"] not in ("completed", "ok")],
            }
        overall = sum(mean(ag, md) for md in models) / len(models)
        lh = mean(ag, None, task_filter=lambda tk: tk.startswith("LH"))
        row.append(f"{overall:>10.3f}{lh:>10.3f}")
        print(f"{ag:14s}" + "".join(row))

    print("\n-- failure modes (non-completed latest attempts) --")
    for (ag, md), st in sorted(cell_stats.items()):
        if st["failures"]:
            print(f"  {ag:12s} {md:16s}: {st['failures']}")

    if a.chart:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 5))
            order = list(reversed(EXPECTED_MODELS))  # e2b -> 35b left to right? keep 35b first
            order = ["ornith1.5_35b", "gemma4_12b", "qwen3.5_4b", "gemma4_e2b"]
            x = list(range(len(order)))
            for ag in EXPECTED_AGENTS:
                ys = [cell_stats[(ag, md)]["mean"] for md in order]
                ax.plot(x, ys, marker="o", label=ag)
            ax.set_xticks(x)
            ax.set_xticklabels(["35b", "12b", "4b", "e2b"])
            ax.set_xlabel("model (35B → 2B)")
            ax.set_ylabel("mean task score (0-1)")
            ax.set_title("LRAB 288: graceful degradation across model sizes")
            ax.legend()
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            fig.savefig(a.chart, dpi=150)
            print(f"\nchart saved: {a.chart}")
        except Exception as e:
            print(f"chart failed (matplotlib missing?): {e}")

if __name__ == "__main__":
    main()
