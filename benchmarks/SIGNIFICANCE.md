# LRAB-288 paired significance analysis

Paired by task within each model (n=18 pairs); bootstrap CI over task resamples (10k, seed 42); Wilcoxon signed-rank two-sided p (normal approximation, tie-corrected). No multiple-comparison correction is applied within a model; the Holm-adjusted conclusion is stated per table.


## Model: gemma4_12b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 50 / 10 | +0.286 | [+0.109, +0.480] | 8/8/2 | 0.0215 |
| Mingbird vs agent-mini | 102 / 14 | +0.330 | [+0.175, +0.489] | 12/4/2 | 0.0021 |
| Mingbird vs opencode | 153 / 17 | +0.766 | [+0.622, +0.894] | 17/1/0 | 0.0003 |
  - Holm-adjusted p (Mingbird vs goose): 0.0215  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0041  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0008  ← significant at 0.05

## Model: gemma4_e2b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 132 / 16 | +0.555 | [+0.366, +0.726] | 14/2/2 | 0.0009 |
| Mingbird vs agent-mini | 171 / 18 | +0.574 | [+0.462, +0.688] | 18/0/0 | 0.0002 |
| Mingbird vs opencode | 171 / 18 | +0.804 | [+0.714, +0.890] | 18/0/0 | 0.0002 |
  - Holm-adjusted p (Mingbird vs goose): 0.0009  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0006  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0006  ← significant at 0.05

## Model: ornith1.5_35b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 37 / 9 | +0.119 | [-0.008, +0.266] | 8/9/1 | 0.0842 |
| Mingbird vs agent-mini | 153 / 17 | +0.849 | [+0.711, +0.961] | 17/1/0 | 0.0002 |
| Mingbird vs opencode | 31 / 8 | +0.165 | [+0.011, +0.343] | 7/10/1 | 0.0680 |
  - Holm-adjusted p (Mingbird vs goose): 0.1360
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0005  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.1360

## Model: qwen3.5_4b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 90 / 13 | +0.240 | [+0.121, +0.374] | 12/5/1 | 0.0021 |
| Mingbird vs agent-mini | 71 / 13 | +0.170 | [+0.016, +0.335] | 10/5/3 | 0.0743 |
| Mingbird vs opencode | 124 / 16 | +0.472 | [+0.247, +0.690] | 13/2/3 | 0.0039 |
  - Holm-adjusted p (Mingbird vs goose): 0.0062  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0743
  - Holm-adjusted p (Mingbird vs opencode): 0.0077  ← significant at 0.05

## Task discrimination (per task x model, spread across 4 harnesses)

| task | models with zero spread | models with spread >= 0.5 |
|---|---|---|
| LH01 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| LH02 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| LH03 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF01 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF02 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF03 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF04 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF05 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF06 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF07 | — | gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF08 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF09 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF10 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF11 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF12 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF13 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF14 | — | gemma4_12b, gemma4_e2b |
| WF15 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |

written: SIGNIFICANCE.md
