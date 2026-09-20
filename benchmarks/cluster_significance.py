#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M2 fix: LRAB significance re-analysis under TASK-FAMILY (tier) clustering.

Motivation
----------
analyze_significance.py (public repo) treats the 18 LRAB tasks as independent
units for its Wilcoxon test and task-level bootstrap. But tasks are generated
in families: same-tier tasks come from the same generator and are highly
correlated, so the effective sample size is closer to 4 (tiers) than 18 (tasks).
This script re-runs the paired Mingbird-vs-competitor comparisons with the
cluster structure honored:

  1. CLUSTER BOOTSTRAP (primary, as specified):
     resample the 4 TIERS with replacement (draw 4 tiers), take ALL tasks of
     each drawn tier (a tier drawn k times contributes its tasks k times),
     compute the mean paired difference over the pooled task multiset.
     10,000 replicates, percentile 95% CI. Degenerate replicates (e.g. all 4
     draws land on the same tier) are KEPT as-is -- they are legitimate
     extreme draws of the cluster bootstrap, not errors; their frequency is
     reported.

  2. TIER-EQUAL-WEIGHT BOOTSTRAP (secondary robustness):
     same tier resampling, but the statistic is the unweighted mean of the 4
     drawn TIER means. With unbalanced tier sizes (2/4/9/3) the pooled-mean
     cluster bootstrap is centered near the equal-tier-weight estimand rather
     than the 18-task pooled mean, so this column shows the CI for that
     estimand explicitly.

  3. STRATIFIED SIGN-FLIP PERMUTATION TEST (auxiliary):
     within each tier, independently flip the sign of every paired difference,
     then aggregate to the pooled 18-task mean; two-sided Monte-Carlo p with
     the (count+1)/(B+1) correction. Holm-adjusted across the 3 comparisons
     within each model, mirroring the original writeup.

For apples-to-apples comparison the original task-level Wilcoxon signed-rank
p (normal approximation, tie-corrected, zeros dropped) and task-level
bootstrap CI are recomputed here with the same code/conventions as the public
analyze_significance.py -- every number in the output is computed from the
CSV, nothing is transcribed.

Reproduce: python cluster_significance.py [--csv <path>]
Deterministic (fixed seeds); stdlib only. Writes RESULTS.md next to this file.
"""
import csv
import math
import random
import statistics
import sys
import os

# ---------------------------------------------------------------- constants
CSV_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lrab_scores.csv")

MODELS = ["gemma4_e2b", "qwen3.5_4b", "gemma4_12b", "ornith1.5_35b"]  # 2B/4B/12B/35B
MODEL_LABEL = {"gemma4_e2b": "2B (gemma4_e2b)", "qwen3.5_4b": "4B (qwen3.5_4b)",
               "gemma4_12b": "12B (gemma4_12b)", "ornith1.5_35b": "35B (ornith1.5_35b)"}
COMPS = ["goose", "opencode", "agent-mini"]  # Mingbird vs each

# Task-family (tier) structure. CSV task ids are zero-padded, no dash.
TIERS = [
    ("tier1_retrieval",   ["WF01", "WF02"]),
    ("tier2_synthesis",   ["WF03", "WF04", "WF05", "WF06"]),
    ("tier3_workflow",    ["WF07", "WF08", "WF09", "WF10", "WF11", "WF12", "WF13", "WF14", "WF15"]),
    ("tier4_longhorizon", ["LH01", "LH02", "LH03"]),
]

N_BOOT = 10000
N_PERM = 10000
BOOT_SEED = 42          # same convention as public script
PERM_SEED = 20260920    # deterministic, independent stream from bootstrap
EPS = 1e-12


# ---------------------------------------------------------------- data load
def load(path):
    cells = {}
    n_rows = 0
    for r in csv.DictReader(open(path, encoding="utf-8")):
        h, task, model = r["harness"].strip(), r["task"].strip(), r["model"].strip()
        s = str(r["score"]).strip()
        cells[(h, model, task)] = float(s) if s else 0.0
        n_rows += 1
    # --- integrity checks: must be a complete 4 harness x 4 model x 18 task grid
    harnesses = sorted({h for (h, _, _) in cells})
    models = sorted({m for (_, m, _) in cells})
    tasks = sorted({t for (_, _, t) in cells})
    assert n_rows == len(cells) == 288, f"expected 288 unique cells, got {n_rows} rows / {len(cells)} cells"
    tier_tasks = [t for _, ts in TIERS for t in ts]
    assert sorted(tier_tasks) == tasks, f"tier mapping mismatch: {sorted(set(tasks) ^ set(tier_tasks))}"
    assert harnesses == ["Mingbird", "agent-mini", "goose", "opencode"], harnesses
    assert models == sorted(MODELS), models
    for h in harnesses:
        for m in models:
            for t in tasks:
                assert (h, m, t) in cells, f"missing cell {h}/{m}/{t}"
    return cells


# ------------------------------------------- original (task-level) methods
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


def wilcoxon_signed_rank(diffs):
    """Port of the public analyze_significance.py implementation."""
    d = [x for x in diffs if abs(x) > EPS]
    n = len(d)
    if n == 0:
        return 0.0, 0, 1.0
    ranks = _ranks([abs(x) for x in d])
    w_plus = sum(rk for rk, dv in zip(ranks, d) if dv > 0)
    mu = n * (n + 1) / 4
    from collections import defaultdict
    tie_groups = defaultdict(int)
    for x in [abs(x) for x in d]:
        tie_groups[x] += 1
    tie_term = sum(t ** 3 - t for t in tie_groups.values()) / 48.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24 - tie_term)
    if sigma == 0:
        return w_plus, n, 1.0
    z = (w_plus - mu) / sigma
    return w_plus, n, 2 * (1 - _norm_cdf(abs(z)))


def task_boot_ci(diffs, seed):
    """Task-level bootstrap, same convention as public script (percentile indices)."""
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(N_BOOT))
    return means[int(0.025 * N_BOOT)], means[int(0.975 * N_BOOT)]


# ------------------------------------------------------- cluster methods
def cluster_boot(diff_by_tier, seed):
    """Tier-level cluster bootstrap as specified: draw 4 tiers with replacement,
    pool ALL tasks of each drawn tier (multiplicity kept), mean over the pooled
    multiset. Returns (ci_lo, ci_hi, degenerate_counts, distinct_histogram).

    Degenerate replicate := all 4 draws land on the same tier (only 1 distinct
    tier) -> replicate mean equals that single tier's mean. Kept as-is; the
    histogram documents how often each distinct-tier count occurred.
    """
    rng = random.Random(seed)
    k = len(diff_by_tier)
    means = []
    distinct_hist = {1: 0, 2: 0, 3: 0, 4: 0}
    for _ in range(N_BOOT):
        draws = [rng.randrange(k) for _ in range(k)]
        pooled = []
        for idx in draws:
            pooled.extend(diff_by_tier[idx])
        means.append(sum(pooled) / len(pooled))
        distinct_hist[len(set(draws))] += 1
    means.sort()
    lo, hi = means[int(0.025 * N_BOOT)], means[int(0.975 * N_BOOT)]
    return lo, hi, distinct_hist[1], distinct_hist


def tier_equal_weight_boot(diff_by_tier, seed):
    """Secondary: same tier resampling; statistic = unweighted mean of the 4
    drawn TIER means (equal-tier-weight estimand)."""
    rng = random.Random(seed)
    k = len(diff_by_tier)
    tier_means = [statistics.mean(d) for d in diff_by_tier]
    means = sorted(statistics.mean([tier_means[rng.randrange(k)] for _ in range(k)])
                   for _ in range(N_BOOT))
    return means[int(0.025 * N_BOOT)], means[int(0.975 * N_BOOT)]


def stratified_permutation(diff_by_tier, seed):
    """Stratified sign-flip: flip signs of paired diffs independently WITHIN each
    tier, aggregate to the pooled 18-task mean. Two-sided Monte-Carlo p with
    (count+1)/(B+1) correction."""
    rng = random.Random(seed)
    all_d = [d for t in diff_by_tier for d in t]
    obs = statistics.mean(all_d)
    total = len(all_d)
    count = 0
    for _ in range(N_PERM):
        s = 0.0
        for t in diff_by_tier:
            for d in t:
                s += d if rng.random() < 0.5 else -d
        if abs(s / total) >= abs(obs) - EPS:
            count += 1
    return (count + 1) / (N_PERM + 1), count


def holm(ps):
    """Holm step-down adjustment across the 3 comparisons of a model."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj, cur = [0.0] * m, 0.0
    for rank, idx in enumerate(order):
        cur = max(cur, (m - rank) * ps[idx])
        adj[idx] = min(1.0, cur)
    return adj


# ---------------------------------------------------------------- main
def main(csv_path):
    cells = load(csv_path)
    tier_names = [name for name, _ in TIERS]
    out = []
    out.append("# M2: LRAB significance under task-family (tier) clustering")
    out.append("")
    out.append(f"Source CSV: `{csv_path}` (288 rows = 4 harnesses x 4 models x 18 tasks, "
               "completeness verified). Tier structure: "
               + "; ".join(f"{n} (k={len(ts)})" for n, ts in TIERS) + ".")
    out.append("")
    out.append(f"Cluster bootstrap: resample 4 tiers with replacement, pool all tasks of drawn "
               f"tiers (multiplicity kept), mean paired diff; {N_BOOT:,} replicates; percentile "
               f"95% CI. Sign-flip permutation: signs flipped independently within tiers, "
               f"pooled-mean statistic, {N_PERM:,} permutations, (count+1)/(B+1) correction; "
               f"Holm across the 3 comparisons within each model. Seeds fixed (bootstrap 42+, "
               f"permutation {PERM_SEED}+). 'Task-level' columns recompute the public "
               f"analyze_significance.py numbers from the same CSV for side-by-side reading.")
    out.append("")

    cmp_idx = 0
    for model in MODELS:
        out.append(f"\n## Model: {MODEL_LABEL[model]}\n")
        out.append("| comparison | mean diff (18 tasks) | task-level bootstrap CI (orig) | "
                   "cluster bootstrap CI (tier-resampled, pooled) | crosses 0? | "
                   "equal-tier-weight mean (CI) | perm p (stratified) | Holm p | task-level Wilcoxon p (orig) |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        rows, ps, notes = [], [], []
        for comp in COMPS:
            diffs = [cells[("Mingbird", model, t)] - cells[(comp, model, t)] for _, ts in TIERS for t in ts]
            diff_by_tier = [[cells[("Mingbird", model, t)] - cells[(comp, model, t)] for t in ts]
                            for _, ts in TIERS]

            md = statistics.mean(diffs)
            t_lo, t_hi = task_boot_ci(diffs, BOOT_SEED + cmp_idx)
            c_lo, c_hi, n_degen, distinct_hist = cluster_boot(diff_by_tier, BOOT_SEED + cmp_idx)
            ew_mean = statistics.mean([statistics.mean(d) for d in diff_by_tier])
            w_lo, w_hi = tier_equal_weight_boot(diff_by_tier, BOOT_SEED + cmp_idx)
            p_perm, _ = stratified_permutation(diff_by_tier, PERM_SEED + cmp_idx)
            _, _, p_wil = wilcoxon_signed_rank(diffs)
            ps.append(p_perm)

            crosses = (c_lo < 0 < c_hi) or (abs(c_lo) < EPS and abs(c_hi) < EPS)
            excl = "excludes 0 (" + ("+" if c_lo > 0 else "-") + ")" if not crosses else "CROSSES 0"

            rows.append((comp, md, t_lo, t_hi, c_lo, c_hi, excl, ew_mean, w_lo, w_hi, p_perm, p_wil))
            notes.append((comp, n_degen, distinct_hist))
            cmp_idx += 1
        adj = holm(ps)
        for (comp, md, t_lo, t_hi, c_lo, c_hi, excl, ew_mean, w_lo, w_hi, p_perm, p_wil), a in zip(rows, adj):
            out.append(f"| Mingbird vs {comp} | {md:+.3f} | [{t_lo:+.3f}, {t_hi:+.3f}] "
                       f"| [{c_lo:+.3f}, {c_hi:+.3f}] | {excl} "
                       f"| {ew_mean:+.3f} [{w_lo:+.3f}, {w_hi:+.3f}] "
                       f"| {p_perm:.4f} | {a:.4f} | {p_wil:.4f} |")
        for comp, a in zip(COMPS, adj):
            out.append(f"  - Holm-adjusted stratified-permutation p (Mingbird vs {comp}): {a:.4f}"
                       + ("  <- significant at 0.05" if a < 0.05 else ""))
        for comp, n_degen, distinct_hist in notes:
            out.append(f"  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs {comp}): "
                       f"{n_degen}/{N_BOOT} ({100.0 * n_degen / N_BOOT:.2f}%); "
                       f"distinct-tier draw histogram 1/2/3/4: "
                       f"{distinct_hist[1]}/{distinct_hist[2]}/{distinct_hist[3]}/{distinct_hist[4]}")
    # cleaner: dedicated per-tier table
    out.append("\n## Per-tier mean paired differences (diagnostics)\n")
    out.append("| model | competitor | " + " | ".join(n for n, _ in TIERS) + " | pooled (18) | equal-tier |")
    out.append("|---|---|---|---|---|---|---|---|")
    for model in MODELS:
        for comp in COMPS:
            tier_m = [statistics.mean([cells[("Mingbird", model, t)] - cells[(comp, model, t)] for t in ts])
                      for _, ts in TIERS]
            pooled = statistics.mean([d for _, ts in TIERS
                                      for d in [cells[("Mingbird", model, t)] - cells[(comp, model, t)] for t in ts]])
            out.append(f"| {MODEL_LABEL[model]} | {comp} | "
                       + " | ".join(f"{v:+.3f}" for v in tier_m)
                       + f" | {pooled:+.3f} | {statistics.mean(tier_m):+.3f} |")

    text = "\n".join(out) + "\n"
    here = os.path.dirname(os.path.abspath(__file__))
    res_path = os.path.join(here, "RESULTS.md")
    open(res_path, "w", encoding="utf-8").write(text)
    print(text)
    print(f"written: {res_path}")


if __name__ == "__main__":
    csvp = CSV_DEFAULT
    if "--csv" in sys.argv:
        csvp = sys.argv[sys.argv.index("--csv") + 1]
    main(csvp)
