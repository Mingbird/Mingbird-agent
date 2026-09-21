# M2: LRAB significance under task-family (tier) clustering

Source CSV: `C:\Users\99491\dev\mingbird-v16\benchmarks\lrab_scores.csv` (288 rows = 4 harnesses x 4 models x 18 tasks, completeness verified). Tier structure: tier1_retrieval (k=2); tier2_synthesis (k=4); tier3_workflow (k=9); tier4_longhorizon (k=3).

Cluster bootstrap: resample 4 tiers with replacement, pool all tasks of drawn tiers (multiplicity kept), mean paired diff; 10,000 replicates; percentile 95% CI. Sign-flip permutation: signs flipped independently within tiers, pooled-mean statistic, 10,000 permutations, (count+1)/(B+1) correction; Holm across the 3 comparisons within each model. Seeds fixed (bootstrap 42+, permutation 20260920+). 'Task-level' columns recompute the public analyze_significance.py numbers from the same CSV for side-by-side reading.


## Model: 2B (gemma4_e2b)

| comparison | mean diff (18 tasks) | task-level bootstrap CI (orig) | cluster bootstrap CI (tier-resampled, pooled) | crosses 0? | equal-tier-weight mean (CI) | perm p (stratified) | Holm p | task-level Wilcoxon p (orig) |
|---|---|---|---|---|---|---|---|---|
| Mingbird vs goose | +0.550 | [+0.375, +0.712] | [+0.417, +0.894] | excludes 0 (+) | +0.666 [+0.421, +0.912] | 0.0001 | 0.0003 | 0.0008 |
| Mingbird vs opencode | +0.804 | [+0.712, +0.886] | [+0.704, +0.976] | excludes 0 (+) | +0.868 [+0.753, +0.982] | 0.0001 | 0.0003 | 0.0002 |
| Mingbird vs agent-mini | +0.574 | [+0.460, +0.687] | [+0.448, +0.785] | excludes 0 (+) | +0.638 [+0.500, +0.768] | 0.0001 | 0.0003 | 0.0002 |
  - Holm-adjusted stratified-permutation p (Mingbird vs goose): 0.0003  <- significant at 0.05
  - Holm-adjusted stratified-permutation p (Mingbird vs opencode): 0.0003  <- significant at 0.05
  - Holm-adjusted stratified-permutation p (Mingbird vs agent-mini): 0.0003  <- significant at 0.05
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs goose): 158/10000 (1.58%); distinct-tier draw histogram 1/2/3/4: 158/3243/5673/926
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs opencode): 151/10000 (1.51%); distinct-tier draw histogram 1/2/3/4: 151/3256/5661/932
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs agent-mini): 136/10000 (1.36%); distinct-tier draw histogram 1/2/3/4: 136/3317/5607/940

## Model: 4B (qwen3.5_4b)

| comparison | mean diff (18 tasks) | task-level bootstrap CI (orig) | cluster bootstrap CI (tier-resampled, pooled) | crosses 0? | equal-tier-weight mean (CI) | perm p (stratified) | Holm p | task-level Wilcoxon p (orig) |
|---|---|---|---|---|---|---|---|---|
| Mingbird vs goose | +0.074 | [-0.039, +0.215] | [+0.021, +0.104] | excludes 0 (+) | +0.052 [+0.013, +0.094] | 0.3529 | 0.3529 | 0.3258 |
| Mingbird vs opencode | +0.410 | [+0.178, +0.639] | [+0.168, +0.714] | excludes 0 (+) | +0.432 [+0.150, +0.697] | 0.0062 | 0.0186 | 0.0060 |
| Mingbird vs agent-mini | +0.170 | [+0.011, +0.335] | [-0.133, +0.286] | CROSSES 0 | +0.090 [-0.110, +0.291] | 0.0654 | 0.1308 | 0.0743 |
  - Holm-adjusted stratified-permutation p (Mingbird vs goose): 0.3529
  - Holm-adjusted stratified-permutation p (Mingbird vs opencode): 0.0186  <- significant at 0.05
  - Holm-adjusted stratified-permutation p (Mingbird vs agent-mini): 0.1308
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs goose): 157/10000 (1.57%); distinct-tier draw histogram 1/2/3/4: 157/3241/5631/971
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs opencode): 154/10000 (1.54%); distinct-tier draw histogram 1/2/3/4: 154/3278/5644/924
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs agent-mini): 174/10000 (1.74%); distinct-tier draw histogram 1/2/3/4: 174/3273/5600/953

## Model: 12B (gemma4_12b)

| comparison | mean diff (18 tasks) | task-level bootstrap CI (orig) | cluster bootstrap CI (tier-resampled, pooled) | crosses 0? | equal-tier-weight mean (CI) | perm p (stratified) | Holm p | task-level Wilcoxon p (orig) |
|---|---|---|---|---|---|---|---|---|
| Mingbird vs goose | +0.134 | [+0.026, +0.264] | [+0.029, +0.352] | excludes 0 (+) | +0.149 [+0.018, +0.317] | 0.0360 | 0.0360 | 0.0466 |
| Mingbird vs opencode | +0.367 | [+0.226, +0.511] | [+0.266, +0.643] | excludes 0 (+) | +0.422 [+0.274, +0.670] | 0.0001 | 0.0003 | 0.0010 |
| Mingbird vs agent-mini | +0.330 | [+0.175, +0.488] | [+0.087, +0.444] | excludes 0 (+) | +0.261 [+0.073, +0.450] | 0.0003 | 0.0006 | 0.0021 |
  - Holm-adjusted stratified-permutation p (Mingbird vs goose): 0.0360  <- significant at 0.05
  - Holm-adjusted stratified-permutation p (Mingbird vs opencode): 0.0003  <- significant at 0.05
  - Holm-adjusted stratified-permutation p (Mingbird vs agent-mini): 0.0006  <- significant at 0.05
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs goose): 158/10000 (1.58%); distinct-tier draw histogram 1/2/3/4: 158/3259/5660/923
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs opencode): 171/10000 (1.71%); distinct-tier draw histogram 1/2/3/4: 171/3196/5689/944
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs agent-mini): 151/10000 (1.51%); distinct-tier draw histogram 1/2/3/4: 151/3278/5631/940

## Model: 35B (ornith1.5_35b)

| comparison | mean diff (18 tasks) | task-level bootstrap CI (orig) | cluster bootstrap CI (tier-resampled, pooled) | crosses 0? | equal-tier-weight mean (CI) | perm p (stratified) | Holm p | task-level Wilcoxon p (orig) |
|---|---|---|---|---|---|---|---|---|
| Mingbird vs goose | +0.262 | [+0.094, +0.452] | [+0.105, +0.571] | excludes 0 (+) | +0.285 [+0.062, +0.579] | 0.0160 | 0.0320 | 0.0208 |
| Mingbird vs opencode | +0.045 | [-0.090, +0.192] | [-0.007, +0.205] | CROSSES 0 | +0.072 [-0.006, +0.222] | 0.6218 | 0.6218 | 0.4652 |
| Mingbird vs agent-mini | +0.849 | [+0.706, +0.964] | [+0.764, +1.000] | excludes 0 (+) | +0.901 [+0.802, +1.000] | 0.0001 | 0.0003 | 0.0002 |
  - Holm-adjusted stratified-permutation p (Mingbird vs goose): 0.0320  <- significant at 0.05
  - Holm-adjusted stratified-permutation p (Mingbird vs opencode): 0.6218
  - Holm-adjusted stratified-permutation p (Mingbird vs agent-mini): 0.0003  <- significant at 0.05
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs goose): 171/10000 (1.71%); distinct-tier draw histogram 1/2/3/4: 171/3242/5663/924
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs opencode): 178/10000 (1.78%); distinct-tier draw histogram 1/2/3/4: 178/3266/5622/934
  - degenerate cluster replicates (all 4 draws = same tier, Mingbird vs agent-mini): 140/10000 (1.40%); distinct-tier draw histogram 1/2/3/4: 140/3264/5634/962

## Per-tier mean paired differences (diagnostics)

| model | competitor | tier1_retrieval | tier2_synthesis | tier3_workflow | tier4_longhorizon | pooled (18) | equal-tier |
|---|---|---|---|---|---|---|---|
| 2B (gemma4_e2b) | goose | +1.000 | +0.428 | +0.413 | +0.823 | +0.550 | +0.666 |
| 2B (gemma4_e2b) | opencode | +1.000 | +0.964 | +0.682 | +0.823 | +0.804 | +0.868 |
| 2B (gemma4_e2b) | agent-mini | +0.714 | +0.821 | +0.428 | +0.590 | +0.574 | +0.638 |
| 4B (qwen3.5_4b) | goose | +0.000 | +0.053 | +0.111 | +0.042 | +0.074 | +0.052 |
| 4B (qwen3.5_4b) | opencode | +0.643 | +0.750 | +0.349 | -0.014 | +0.410 | +0.432 |
| 4B (qwen3.5_4b) | agent-mini | +0.000 | +0.304 | +0.278 | -0.221 | +0.170 | +0.090 |
| 12B (gemma4_12b) | goose | +0.000 | +0.411 | +0.036 | +0.151 | +0.134 | +0.149 |
| 12B (gemma4_12b) | opencode | +0.322 | +0.322 | +0.258 | +0.786 | +0.367 | +0.422 |
| 12B (gemma4_12b) | agent-mini | +0.000 | +0.518 | +0.381 | +0.145 | +0.330 | +0.261 |
| 35B (ornith1.5_35b) | goose | +0.000 | +0.250 | +0.175 | +0.714 | +0.262 | +0.285 |
| 35B (ornith1.5_35b) | opencode | +0.000 | +0.000 | -0.008 | +0.296 | +0.045 | +0.072 |
| 35B (ornith1.5_35b) | agent-mini | +1.000 | +1.000 | +0.746 | +0.859 | +0.849 | +0.901 |
