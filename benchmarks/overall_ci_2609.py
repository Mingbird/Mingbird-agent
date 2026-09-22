# -*- coding: utf-8 -*-
"""Overall (pooled-across-models) difference: task-level bootstrap CI and
task-level sign permutation, plus the binary "cell at or above 0.5" view.

Reviewer request (DeepSeek M6): the headline margin (0.886 vs 0.631/0.479/0.405)
appeared in the abstract with no interval and no test, and the main metric is a
weighted partial score; a binary version (cell >= 0.5) was suggested as a second,
scale-free main metric.

Unit of analysis: the task. Each resample draws 18 tasks with replacement and
takes all four models of each drawn task, so model-level pairing is preserved
and the 72 cells are not treated as independent. The permutation test flips the
sign of each task's mean difference (10,000 draws, fixed seed), reporting a
two-sided Monte-Carlo p.

Usage:  python benchmarks/overall_ci_2609.py
Reads:  benchmarks/lrab_scores.csv (columns: harness,task,model,score,wall_seconds,...)
"""
import collections
import csv
import os
import random
import statistics

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lrab_scores.csv")
BASELINE = "Mingbird"
COMPETITORS = ["goose", "opencode", "agent-mini"]
SEED = 2609
BOOTSTRAP = 10000


def load():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    by = collections.defaultdict(dict)
    for r in rows:
        by[(r["task"], r["model"])][r["harness"]] = float(r["score"])
    tasks = sorted({k[0] for k in by})
    models = sorted({k[1] for k in by})
    return by, tasks, models


def main():
    by, tasks, models = load()
    print(f"{len(by)} cells = {len(tasks)} tasks x {len(models)} models")
    for arm in [BASELINE] + COMPETITORS:
        vals = [by[(t, m)][arm] for t in tasks for m in models]
        at_half = sum(1 for v in vals if v >= 0.5)
        print(f"  {arm:<11s} mean={statistics.mean(vals):.4f}  cells>=0.5: {at_half}/{len(vals)}")

    rng = random.Random(SEED)
    print(f"\npaired overall differences vs {BASELINE} "
          f"(task-level bootstrap {BOOTSTRAP}, seed {SEED}):")
    for arm in COMPETITORS:
        per_task = [statistics.mean([by[(t, m)][BASELINE] - by[(t, m)][arm] for m in models])
                    for t in tasks]
        obs = statistics.mean(per_task)
        boots = []
        for _ in range(BOOTSTRAP):
            draw = [per_task[rng.randrange(len(per_task))] for _ in tasks]
            boots.append(statistics.mean(draw))
        boots.sort()
        lo, hi = boots[int(0.025 * BOOTSTRAP)], boots[int(0.975 * BOOTSTRAP)]
        hits = 0
        for _ in range(BOOTSTRAP):
            s = [x if rng.random() < 0.5 else -x for x in per_task]
            if abs(statistics.mean(s)) >= abs(obs):
                hits += 1
        print(f"  vs {arm:<11s} delta={obs:+.4f}  CI95=[{lo:+.4f},{hi:+.4f}]  "
              f"perm p<={(hits + 1) / (BOOTSTRAP + 1):.4f}")


if __name__ == "__main__":
    main()
