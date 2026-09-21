# LRAB-288 paired significance analysis

Paired by task within each model (n=18 pairs); bootstrap CI over task resamples (10k, seed 42); Wilcoxon signed-rank two-sided p (normal approximation, tie-corrected). No multiple-comparison correction is applied within a model; the Holm-adjusted conclusion is stated per table.


## Model: gemma4_12b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 47 / 10 | +0.134 | [+0.026, +0.264] | 8/8/2 | 0.0466 |
| Mingbird vs agent-mini | 102 / 14 | +0.330 | [+0.175, +0.489] | 12/4/2 | 0.0021 |
| Mingbird vs opencode | 105 / 14 | +0.367 | [+0.231, +0.514] | 14/4/0 | 0.0010 |
  - Holm-adjusted p (Mingbird vs goose): 0.0466  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0041  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0029  ← significant at 0.05

## Model: gemma4_e2b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 133 / 16 | +0.550 | [+0.377, +0.713] | 15/2/1 | 0.0008 |
| Mingbird vs agent-mini | 171 / 18 | +0.574 | [+0.462, +0.688] | 18/0/0 | 0.0002 |
| Mingbird vs opencode | 171 / 18 | +0.804 | [+0.714, +0.890] | 18/0/0 | 0.0002 |
  - Holm-adjusted p (Mingbird vs goose): 0.0008  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0006  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0006  ← significant at 0.05

## Model: ornith1.5_35b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 42 / 9 | +0.262 | [+0.094, +0.445] | 8/9/1 | 0.0208 |
| Mingbird vs agent-mini | 153 / 17 | +0.849 | [+0.711, +0.961] | 17/1/0 | 0.0002 |
| Mingbird vs opencode | 7 / 4 | +0.045 | [-0.088, +0.188] | 3/14/1 | 0.4652 |
  - Holm-adjusted p (Mingbird vs goose): 0.0415  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0005  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.4652

## Model: qwen3.5_4b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 25 / 8 | +0.074 | [-0.038, +0.216] | 5/10/3 | 0.3258 |
| Mingbird vs agent-mini | 71 / 13 | +0.170 | [+0.016, +0.335] | 10/5/3 | 0.0743 |
| Mingbird vs opencode | 108 / 15 | +0.410 | [+0.176, +0.637] | 12/3/3 | 0.0060 |
  - Holm-adjusted p (Mingbird vs goose): 0.3258
  - Holm-adjusted p (Mingbird vs agent-mini): 0.1486
  - Holm-adjusted p (Mingbird vs opencode): 0.0181  ← significant at 0.05

## Task discrimination (per task x model, spread across 4 harnesses)

| task | models with zero spread | models with spread >= 0.5 |
|---|---|---|
| LH01 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| LH02 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| LH03 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF01 | — | gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF02 | — | gemma4_e2b, ornith1.5_35b |
| WF03 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF04 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF05 | — | gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF06 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF07 | — | ornith1.5_35b, qwen3.5_4b |
| WF08 | — | gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF09 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF10 | — | gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF11 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF12 | gemma4_12b, qwen3.5_4b | gemma4_e2b, ornith1.5_35b |
| WF13 | — | gemma4_e2b, ornith1.5_35b |
| WF14 | — | gemma4_12b, gemma4_e2b, qwen3.5_4b |
| WF15 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |

written: SIGNIFICANCE.md

## Task-family cluster robustness (2026-09-20)

The 18 tasks are generated in four families (tier1 2 / tier2 4 / tier3 9 / tier4 3), so task-level pairing overstates independence. `cluster_significance.py` re-runs the analysis with the family as the unit: cluster bootstrap over the four families (10k resamples, tier members drawn whole) plus a family-stratified sign permutation test (10k, Holm-corrected within model). Headline: **at 2B all three comparisons remain significant (adjusted permutation p = 0.0003 each; cluster-bootstrap CIs exclude zero)** — the 2B advantage is present in all four families. 12B vs goose survives marginally (CI lower bound +0.029, adjusted p = 0.036; effect concentrated in two families). No nonsignificant comparison becomes significant; 4B vs agent-mini's edge finding disappears (CI now crosses zero, consistent with its adjusted p).


## Correction (2026-09-22, review round 2)

The 2026-09-20 summary above overstates family-level robustness; corrected reading
(now in the paper's family-clustering paragraph):

1. The stratified sign permutation flips TASK-level signs within tiers (it is a
   task-level test, not a family-level one); a family-level flip would have only
   2^4 = 16 sign patterns (min two-sided p = 0.125), so with four families NO
   family-level significance claim is available for any comparison.
2. A cluster-bootstrap CI cannot cross zero when all four family means share a
   sign; at 2B all three comparisons, at 4B-vs-goose, and at 12B-vs-goose
   (tier-1 mean exactly 0.000) fall in this uninformative-by-construction class.
3. The strongest family-level statement available at 2B is descriptive: all four
   family means strictly positive (e.g. +1.000/+0.428/+0.413/+0.823 vs goose).

Per-tier diagnostics: RESULTS.md (cluster_significance.py, seeded).
tau2 McNemar-based significance: TAU2_SIGNIFICANCE.md (tau2_significance.py).
