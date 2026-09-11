#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Statistical re-analysis of LRAB-288 (no new runs - same CSV as the tables).

Outputs, per model (2B/4B/12B/35B), for Mingbird vs each competitor:
  - paired task-level win/tie/loss over the 18 tasks
  - mean paired difference with 95% bootstrap CI (10k resamples, seed=42)
  - Wilcoxon signed-rank p (normal approximation with tie correction; zeros dropped)
Plus task-level discrimination (per task x model: spread across the 4 harnesses).

Reproduce:  python analyze_significance.py [--csv lrab_scores.csv]
Deterministic (seeded); stdlib only.
"""
import csv
import math
import random
import statistics
import sys
from collections import defaultdict

HARNesses = ["Mingbird", "goose", "agent-mini", "opencode"]
COMP = [h for h in HARNesses if h != "Mingbird"]


def load(path):
    cells = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        h, task, model = r["harness"].strip(), r["task"].strip(), r["model"].strip()
        s = str(r["score"]).strip()
        cells[(h, model, task)] = float(s) if s else 0.0
    return cells


def wilcoxon_signed_rank(pairs):
    """pairs: list of (a, b). Returns (W, n_nonzero, p_two_sided_normal)."""
    d = [a - b for a, b in pairs if abs(a - b) > 1e-12]
    n = len(d)
    if n == 0:
        return 0.0, 0, 1.0
    ranks = _ranks([abs(x) for x in d])
    w_plus = sum(rk for rk, dv in zip(ranks, d) if dv > 0)
    mu = n * (n + 1) / 4
    # tie correction
    tie_groups = defaultdict(int)
    for x in [abs(x) for x in d]:
        tie_groups[x] += 1
    tie_term = sum(t**3 - t for t in tie_groups.values()) / 48.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24 - tie_term)
    if sigma == 0:
        return w_plus, n, 1.0
    z = (w_plus - mu) / sigma
    p = 2 * (1 - _norm_cdf(abs(z)))
    return w_plus, n, p


def _ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def boot_ci(diffs, iters=10000, seed=42):
    rng = random.Random(seed)
    n = len(diffs)
    means = []
    for _ in range(iters):
        means.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def main(csv_path):
    cells = load(csv_path)
    models = sorted({m for (_, m, _) in cells})
    tasks = sorted({t for (_, _, t) in cells})
    out = ["# LRAB-288 paired significance analysis\n",
           "Paired by task within each model (n=18 pairs); bootstrap CI over task "
           "resamples (10k, seed 42); Wilcoxon signed-rank two-sided p (normal "
           "approximation, tie-corrected). No multiple-comparison correction is "
           "applied within a model; the Holm-adjusted conclusion is stated per table.\n"]
    min_p = {}
    for model in models:
        out.append(f"\n## Model: {model}\n")
        out.append("| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |")
        out.append("|---|---|---|---|---|---|")
        ps = []
        for comp in COMP:
            pairs, w = [], {"win": 0, "tie": 0, "loss": 0}
            for t in tasks:
                a = cells[("Mingbird", model, t)]
                b = cells[(comp, model, t)]
                pairs.append((a, b))
                w["win" if a > b + 1e-12 else ("loss" if a < b - 1e-12 else "tie")] += 1
            diffs = [a - b for a, b in pairs]
            md = statistics.mean(diffs)
            lo, hi = boot_ci(diffs)
            W, n, p = wilcoxon_signed_rank(pairs)
            ps.append(p)
            out.append(f"| Mingbird vs {comp} | {W:.0f} / {n} | {md:+.3f} "
                       f"| [{lo:+.3f}, {hi:+.3f}] "
                       f"| {w['win']}/{w['tie']}/{w['loss']} | {p:.4f} |")
        # Holm across the 3 comparisons of this model
        order = sorted(range(3), key=lambda i: ps[i])
        adj, cur = [0.0] * 3, 0.0
        for rank, idx in enumerate(order):
            cur = max(cur, (3 - rank) * ps[idx])
            adj[idx] = min(1.0, cur)
        for comp, a in zip(COMP, adj):
            out.append(f"  - Holm-adjusted p (Mingbird vs {comp}): {a:.4f}"
                       + ("  ← significant at 0.05" if a < 0.05 else ""))
            min_p[(model, comp)] = a
    # discrimination
    out.append("\n## Task discrimination (per task x model, spread across 4 harnesses)\n")
    out.append("| task | models with zero spread | models with spread >= 0.5 |")
    out.append("|---|---|---|")
    for t in tasks:
        zero, disc = [], []
        for model in models:
            scores = [cells[(h, model, t)] for h in HARNesses]
            spread = max(scores) - min(scores)
            if spread < 1e-12:
                zero.append(model)
            if spread >= 0.5:
                disc.append(model)
        out.append(f"| {t} | {', '.join(zero) or '—'} | {', '.join(disc) or '—'} |")
    text = "\n".join(out) + "\n"
    open("SIGNIFICANCE.md", "w", encoding="utf-8").write(text)
    print(text)
    print("written: SIGNIFICANCE.md")


if __name__ == "__main__":
    csvp = "lrab_scores.csv"
    if "--csv" in sys.argv:
        csvp = sys.argv[sys.argv.index("--csv") + 1]
    main(csvp)
