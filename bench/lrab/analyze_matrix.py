#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyze LRAB matrix results → summary table + graceful-degradation chart.

Reads eval_results/MATRIX_MANIFEST.json (or falls back to scanning eval_results/*/score.json),
groups by (agent, model), averages task scores, and prints a comparison table.

Usage:
  python analyze_matrix.py [--results ~/dev/hummingbird/eval_results] [--chart out.png]
"""
import argparse, json, os, glob

def load_scores(results_dir):
    """Prefer MATRIX_MANIFEST.json (clean matrix runs only); else scan score.json files.
    Skipping smoke/dev runs avoids polluting the published matrix."""
    man = os.path.join(results_dir, "MATRIX_MANIFEST.json")
    if os.path.exists(man):
        m = json.load(open(man, encoding="utf-8"))
        scores = []
        for c in m.get("cells", []):
            if not c.get("ok"):
                continue
            for att in c.get("attempts", []):
                if att.get("total") is not None:
                    scores.append({
                        "agent": c["agent"], "model": c["model"],
                        "task_id": c["task"], "total": att["total"],
                        "failure_mode": "completed",
                    })
                    break
        if scores:
            return scores
    # fallback: scan score.json
    scores = []
    for score_path in glob.glob(os.path.join(results_dir, "*", "score.json")):
        try:
            s = json.load(open(score_path, encoding="utf-8"))
        except Exception:
            continue
        if not s.get("agent") or not s.get("model"):
            continue
        scores.append(s)
    return scores

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.expanduser("~/dev/hummingbird/eval_results"))
    ap.add_argument("--chart", default="", help="save degradation chart PNG path")
    a = ap.parse_args()

    scores = load_scores(a.results)
    if not scores:
        print("no scored runs found in", a.results); return

    # group: agent -> model -> list of (task, total, failure_mode)
    groups = {}
    for s in scores:
        ag, md = s["agent"], s["model"]
        groups.setdefault(ag, {}).setdefault(md, []).append({
            "task": s.get("task_id"), "total": s.get("total", 0),
            "failure": s.get("failure_mode", "completed"),
        })

    # table: rows=agent, cols=model, val=mean total
    agents = sorted(groups)
    models = sorted({m for g in groups.values() for m in g})
    print(f"{'agent':14s} " + " ".join(f"{m:>12s}" for m in models) + "   mean")
    cell_stats = {}
    for ag in agents:
        row = []
        for md in models:
            runs = groups.get(ag, {}).get(md, [])
            if runs:
                mean = sum(r["total"] for r in runs) / len(runs)
                row.append(f"{mean:>12.2f}")
                cell_stats[(ag, md)] = {"mean": mean, "n": len(runs),
                                        "failures": [r["failure"] for r in runs if r["failure"] != "completed"]}
            else:
                row.append(f"{'—':>12s}")
        means = [cell_stats[(ag, md)]["mean"] for md in models if (ag, md) in cell_stats]
        row.append(f"{sum(means)/len(means):>6.2f}" if means else "")
        print(f"{ag:14s} " + " ".join(row))

    # failure-mode summary for small-model cells
    print("\n-- failure modes (non-completed cells) --")
    for (ag, md), st in sorted(cell_stats.items()):
        if st["failures"]:
            print(f"  {ag:12s} {md:16s}: {st['failures']}")

    # chart
    if a.chart:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(8, 5))
            # x: model order 35b->e2b (only models actually present, in gradient order)
            order = ["ornith-1.5:35b", "gemma4:12b", "qwen3.5:4b", "gemma4:e2b"]
            present = [o for o in order if o in models]
            x = list(range(len(present)))
            for ag in agents:
                ys = [cell_stats.get((ag, md), {}).get("mean", float("nan")) for md in present]
                ax.plot(x, ys, marker="o", label=ag)
            ax.set_xticks(x)
            ax.set_xticklabels([o.split(":")[0] for o in present], rotation=15)
            ax.set_xlabel("model (35B → 2B)")
            ax.set_ylabel("mean task score (0-1)")
            ax.set_title("Graceful degradation across model sizes")
            ax.legend()
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            fig.savefig(a.chart, dpi=150)
            print(f"\nchart saved: {a.chart}")
        except Exception as e:
            print(f"chart failed (matplotlib missing?): {e}")

if __name__ == "__main__":
    main()
