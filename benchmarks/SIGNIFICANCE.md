# LRAB-288 paired significance analysis

Paired by task within each model (n=18 pairs); bootstrap CI over task resamples (10k, seed 42); Wilcoxon signed-rank two-sided p (normal approximation, tie-corrected). No multiple-comparison correction is applied within a model; the Holm-adjusted conclusion is stated per table.


## Model: gemma4_12b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 62 / 11 | +0.299 | [+0.129, +0.490] | 9/7/2 | 0.0098 |
| Mingbird vs agent-mini | 102 / 14 | +0.344 | [+0.191, +0.504] | 13/4/1 | 0.0017 |
| Mingbird vs opencode | 171 / 18 | +0.780 | [+0.641, +0.902] | 18/0/0 | 0.0002 |
  - Holm-adjusted p (Mingbird vs goose): 0.0098  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0033  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0005  ← significant at 0.05

## Model: gemma4_e2b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 136 / 16 | +0.533 | [+0.376, +0.682] | 16/2/0 | 0.0004 |
| Mingbird vs agent-mini | 166 / 18 | +0.552 | [+0.386, +0.699] | 17/0/1 | 0.0004 |
| Mingbird vs opencode | 171 / 18 | +0.782 | [+0.674, +0.881] | 18/0/0 | 0.0002 |
  - Holm-adjusted p (Mingbird vs goose): 0.0009  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0009  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0006  ← significant at 0.05

## Model: ornith1.5_35b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 37 / 9 | +0.117 | [-0.010, +0.262] | 8/9/1 | 0.0850 |
| Mingbird vs agent-mini | 153 / 17 | +0.847 | [+0.710, +0.960] | 17/1/0 | 0.0002 |
| Mingbird vs opencode | 31 / 8 | +0.163 | [+0.011, +0.338] | 7/10/1 | 0.0684 |
  - Holm-adjusted p (Mingbird vs goose): 0.1367
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0006  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.1367

## Model: qwen3.5_4b

| comparison | W+ / n | mean diff | 95% bootstrap CI | win/tie/loss | p |
|---|---|---|---|---|---|
| Mingbird vs goose | 78 / 12 | +0.285 | [+0.158, +0.421] | 12/6/0 | 0.0022 |
| Mingbird vs agent-mini | 70 / 12 | +0.215 | [+0.078, +0.366] | 10/6/2 | 0.0149 |
| Mingbird vs opencode | 105 / 14 | +0.517 | [+0.326, +0.706] | 14/4/0 | 0.0009 |
  - Holm-adjusted p (Mingbird vs goose): 0.0043  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs agent-mini): 0.0149  ← significant at 0.05
  - Holm-adjusted p (Mingbird vs opencode): 0.0026  ← significant at 0.05

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
| WF11 | qwen3.5_4b | gemma4_12b, gemma4_e2b, ornith1.5_35b |
| WF12 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF13 | — | gemma4_12b, gemma4_e2b, ornith1.5_35b, qwen3.5_4b |
| WF14 | — | gemma4_12b, gemma4_e2b |
| WF15 | — | gemma4_12b, ornith1.5_35b, qwen3.5_4b |
