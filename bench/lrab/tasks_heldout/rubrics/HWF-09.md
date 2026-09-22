# Judge rubric — HWF-09 (benchmarked refactor variant)

Grade 0-10:
1. Hot-spot diagnosis (0-3): correctly explains per-character concatenation, re-scan counting, per-term full re-scan, list-membership dedup.
2. Methodology (0-3): deterministic corpus, same corpus for both timings, best-of-3, reference outputs captured before optimizing.
3. Equivalence (0-2): a real assertion against baseline_outputs.json, recorded.
4. Report (0-2): numbers add up; speedup honest.

Deduction (up to -2): claimed speedup without timings, or behaviour drift.
