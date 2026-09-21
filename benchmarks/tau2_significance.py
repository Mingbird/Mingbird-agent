#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tau2-bench paired significance analysis (review round 2, 2026-09-22).

Primary test: exact McNemar on discordant pairs (per-task outcomes are
pass/fail, so the paired Wilcoxon reduces to a sign test; both are
reported). Holm correction across the two comparisons (Mingbird vs native
LLM agent, Mingbird vs opencode). Also reports the discriminating-domain
subset (retail + airline; telecom is near-saturated at 0.93-1.00 for
every arm) and per-domain win/tie/loss.

Reproduce:  python tau2_significance.py
Data:       benchmarks/tau2/{retail,airline,telecom}_manifest.json
            (278 tasks, three arms, unified protocol nt0)
Outputs:    TAU2_SIGNIFICANCE.md next to this file. stdlib only.
"""
import json
import math
import os
from math import comb, erf, sqrt

HERE = os.path.dirname(os.path.abspath(__file__))
DOMS = ["retail", "airline", "telecom"]
COMPS = ["llm_agent", "opencode"]
COMP_LABEL = {"llm_agent": "native LLM agent", "opencode": "opencode"}


def load():
    data = {}
    for d in DOMS:
        p = os.path.join(HERE, "tau2", f"{d}_manifest.json")
        data[d] = json.load(open(p, encoding="utf-8"))
    return data


def counts(recs, comp):
    b = c = t = 0
    for _k, rec in recs.items():
        a1, a2 = rec["mingbird"]["reward"], rec[comp]["reward"]
        if a1 > a2:
            b += 1
        elif a1 < a2:
            c += 1
        else:
            t += 1
    return b, t, c


def wilcoxon_sign_asym(b, c):
    """Binary paired differences: scipy wilcoxon (zero_method='wilcox',
    normal approximation without continuity correction) reduces to this."""
    n = b + c
    if n == 0:
        return 1.0
    z = abs(b - c) / sqrt(n)
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    lo = min(b, c)
    return min(1.0, 2 * sum(comb(n, k) for k in range(0, lo + 1)) / 2 ** n)


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, cur = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        cur = max(cur, (len(ps) - rank) * ps[i])
        adj[i] = min(1.0, cur)
    return adj


def main():
    data = load()
    out = ["# tau2-bench paired significance (exact McNemar primary)\n",
           "Per-task outcomes are pass/fail (reward 0/1). McNemar exact on",
           "discordant pairs is the primary test; Wilcoxon (normal approx,",
           "zeros dropped) reduces to the sign test on binary pairs and is",
           "shown for continuity with the paper's earlier wording. Holm k=2",
           "across the two comparisons.\n"]

    pooled = {}
    for comp in COMPS:
        per_dom = {d: counts(data[d], comp) for d in DOMS}
        tb = sum(x[0] for x in per_dom.values())
        tt = sum(x[1] for x in per_dom.values())
        tc = sum(x[2] for x in per_dom.values())
        n = tb + tt + tc
        pw, pm = wilcoxon_sign_asym(tb, tc), mcnemar_exact(tb, tc)
        rb = per_dom["retail"][0] + per_dom["airline"][0]
        rc = per_dom["retail"][2] + per_dom["airline"][2]
        rt = per_dom["retail"][1] + per_dom["airline"][1]
        pooled[comp] = pm
        out += [
            f"## Mingbird vs {COMP_LABEL[comp]}",
            f"- pooled ({n} tasks): {tb}W / {tt}T / {tc}L",
            f"  McNemar exact p = {pm:.4g} | Wilcoxon p = {pw:.4g}",
            f"- discriminating subset retail+airline ({rb+rt+rc} tasks): "
            f"{rb}W / {rt}T / {rc}L, McNemar p = {mcnemar_exact(rb, rc):.4g}",
            f"- per-domain: " + ", ".join(f"{d} {per_dom[d][0]}/{per_dom[d][1]}/{per_dom[d][2]}"
                                          for d in DOMS),
            "",
        ]
    adj = holm([pooled[c] for c in COMPS])
    for c, a in zip(COMPS, adj):
        out.append(f"Holm-adjusted (k=2) McNemar p, vs {COMP_LABEL[c]}: {a:.4g}"
                   + ("  <- significant at 0.05" if a < 0.05 else ""))
    out += ["",
            "Effect-size retention (common opponent opencode): paired margin",
            "+0.407 on LRAB-288 vs +0.119 here (29% retained); the native arm",
            "does not appear in the LRAB matrix.",
            ""]
    text = "\n".join(out) + "\n"
    path = os.path.join(HERE, "TAU2_SIGNIFICANCE.md")
    open(path, "w", encoding="utf-8").write(text)
    print(text)
    print(f"written: {path}")


if __name__ == "__main__":
    main()
