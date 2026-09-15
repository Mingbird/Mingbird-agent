# Benchmarks

Numbers referenced from the [README](../README.md), with methodology and raw data.
Everything here is reproducible on your machine; nothing requires trusting us.

## LRAB-288 (our benchmark)

**Definition.** 4 harnesses × 4 open models × 18 tasks = **288 cells**.

- **Harnesses**: Mingbird, goose, agent-mini, opencode — stock, no patches, each driving the same Ollama backend on the same machine (Intel Arc B390 iGPU, 32 GB shared memory, Windows 11).
- **Models**: `gemma4:e2b` (2B) · `qwen3.5:4b` (4B) · `gemma4:12b` (12B) · `ornith-1.5:35b` (35B, multimodal).
- **Tasks**: 18 real tasks — 15 workflow tasks (WF-01…WF-15: code+tests, data analysis, web research with real search, file organization, refactoring, …) and 3 long-horizon tasks (LH-01…LH-03, multi-hour multi-phase builds).
- **Protocol**: per-cell budget — workflow 90 min, long-horizon 180 min; 1 retry, latest attempt wins; **timeouts score 0**; deterministic artifact-based scoring (files exist, tests actually pass, reports contain the required findings). Every cell runs in a fresh working directory; harness processes are isolated from the scoring.

**Per-model results** (average over 18 tasks; two Mingbird cells are noted below the table):

| Harness | 2B gemma4:e2b | 4B qwen3.5:4b | 12B gemma4:12b | 35B ornith-1.5 | overall |
|---|---|---|---|---|---|
| **Mingbird** | 0.821 | 0.876 | 0.906 | 0.941 | **0.886** |
| goose | 0.266 | 0.636 | 0.620 | 0.822 | 0.586 |
| agent-mini | 0.246 | 0.706 | 0.576 | 0.092 | 0.405 |
| opencode | 0.017 | 0.404 | 0.140 | 0.776 | 0.334 |

On the 3 long-horizon tasks Mingbird leads as well (0.827).

**Raw data**: [`lrab_scores.csv`](lrab_scores.csv) — all 288 cells (harness, task, model, score, wall time, attempt directory). Every number above is the mean of 18 rows of this file.

**Campaigns & notes** (audited post-publication):

- The matrix was collected in two campaigns under one protocol. The three baseline arms ran first (Sep 1–4) and were frozen at their stock versions; the Mingbird arm was then re-collected with the final v1.5.0 release code (Sep 13–14) on the same machine, task set, budgets, model tags, and scorer — so every published Mingbird cell reflects the released build, not an intermediate one.
- Mingbird's 72 cells: one zero (WF-08 at 35B — a run that completed in 276 s without producing artifacts; the finish gate rejected its completion claims, visible in the published transcript) and one partial (WF-09 at 4B — first attempt timed out, the allowed retry ended in a runner error, scored from its partial artifacts at 0.5 under latest-attempt-wins). Excluding the zero instead of scoring it would raise the 35B column to 0.996; we report 0.941.
- Mingbird ships more default tools than the baselines (persistent memory, skills, batch dispatch). A transcript audit shows zero uses of any of them across the 72 published transcripts.
- goose exposes no context-window knob and runs at its default; the other three harnesses are pinned to 32K. This is the one known configuration asymmetry (see DESIGN.md).

> LRAB was designed by us, so treat it as a *controlled experiment*, not a leaderboard: its value is that everything except the harness is held constant, and that every claim can be recomputed from the CSV.

**Design rationale & statistics**: [DESIGN.md](DESIGN.md) — task ladder, per-task
specifications, scoring architecture, freeze discipline, paired significance
analysis ([SIGNIFICANCE.md](SIGNIFICANCE.md), recomputable via
`analyze_significance.py`), and the threats-to-validity section. Short version:
Mingbird's edge over all three competitors is statistically significant on 2B
and 12B (Holm-corrected Wilcoxon, paired by task). On 4B the goose and
opencode comparisons are significant while agent-mini — its strongest tier —
is not (raw p = 0.074). On 35B the field compresses and Mingbird-vs-goose
does not reach significance (p=0.084) — we state that bound.

## τ²-bench: three domains × four harnesses (external, final)

[τ²-bench](https://github.com/sierra-research/tau2-bench) (Sierra Research) is an independent, published agent benchmark: a user simulator converses with the agent, which must use domain tools (a live domain database) to resolve the request. Scoring checks the final database state and natural-language assertions — an agent that bypasses its tool stream and fakes calls fails the DB check and scores 0, so harnesses cannot fake tool use.

All three domains are complete across four harnesses. Unified protocol, identical for every harness:

- **Agent side**: the same local `qwen3.5:4b` on Ollama (GPU full-speed, 65536 ctx tier).
- **User simulator**: cloud `qwen3.8-flash` for all four harnesses — not the official gpt-4o user setup, so official leaderboard numbers are a different setup and not comparable.
- pass^1, error cells score 0, DB final-state validation included.

| Harness | retail (114) | airline (50) | telecom (114) | 3-domain total (278) * |
|---|---|---|---|---|
| **Mingbird** | **0.789** | **0.740** | **1.000** | **0.867** |
| τ² native agent (llm_agent) | 0.640 | 0.520 | 1.000 | 0.766 |
| goose | 0.588 | 0.460 | 0.377 | 0.479 |
| opencode | 0.246 | 0.460 | 0.298 | 0.306 |

\* derived: per-task average over all 278 tasks, error cells counted as 0; recomputable from the per-trial data below.

Notes:

- retail: the official suite is 115 tasks; 114 run in this environment, scored the same way on all four sides.
- Error handling is symmetric across harnesses: llm_agent has 5 error cells scored 0 in retail (valid-only 0.670) and 5 in airline; Mingbird's retail run has zero error cells (114/114 ok). Before final numbers locked, error cells got one uniform rerun pass (same manifest, latest attempt wins) so transient infrastructure hiccups are not conflated with agent failures.
- telecom: all 456 cells completed ok, zero errors for all four harnesses — a saturated domain where the two leaders take full marks. It separates nothing; we report it as-is rather than dropping the domain.
- Adapter disclosure: Mingbird's adapter adds two mechanical safeguards on top of the identical prompt and toolset — a repeat-call nudge (one user-role message after 4 identical `(tool, args)` calls) and a parser fallback that recovers format-leaked tool calls into real ones. Both are verbatim in the published adapter source; the native agent receives no injected messages.
- Raw data: per-trial manifests for all three domains are in this repository — [tau2/retail_manifest.json](tau2/retail_manifest.json), [tau2/airline_manifest.json](tau2/airline_manifest.json), [tau2/telecom_manifest.json](tau2/telecom_manifest.json) (each keyed by task, with per-harness status/reward/wall).

## Ablations: which mechanism pays for itself (v1.5.0 code)

**Design.** 4 variants × 18 tasks (the LRAB task set, `gemma4:e2b`), one mechanism disabled per variant via the `AGENT_ABLATION` environment gate; **baseline = the same-code all-mechanisms arm** (n=18, total 0.821). Each variant writes to its own results directory, so resumed runs never cross-contaminate. Per-cell data: [ablation/ablation_scores.csv](ablation/ablation_scores.csv) (5 arms × 18 tasks).

| Variant | total (18 tasks) | Δ vs baseline |
|---|---|---|
| baseline (all mechanisms on) | 0.821 | — |
| − finish_gate | 0.723 | **−0.098** |
| − verify_feedback | 0.772 | −0.048 |
| − anti_loop | 0.805 | −0.015 |
| − flat_prefill | 0.818 | −0.003 |

All four mechanisms are non-negative; the contribution gradient is: prevent-early-finish > verify-feedback loop > anti-loop > prefill (neutral at 2B).

> The 0.821 baseline is not a separate control: it **is** the 2B column of the LRAB-288 table above — the same 18 cells, the same v1.5.0 code. The ablation and the headline results share one batch and one code version.

## BFCL v3 multi_turn (external, honest weak spot)

**Protocol.** 800 tasks (base / miss_func / miss_param / long_context, 200 each); same model `qwen3.5:4b`, `--temperature 0`, identical tool schema, official evaluator (bfcl-eval 2025.8.6.2, source unmodified).

Two arms:

- **qwen35-4b-FC**: BFCL's native OpenAI-compatible handler → Ollama `/v1` FC endpoint — the model's own function calling.
- **mingbird**: the harness generates tool-call primitives itself (`mb.call_chat` direct to Ollama) plus format-leak rescue and same-signature anti-loop. The mechanical differences are documented in the handler file headers.

| Arm | base | miss_func | miss_param | long_context | overall |
|---|---|---|---|---|---|
| Native FC (qwen35-4b-FC) | 60 | 35 | 38 | 53 | **46.50%** |
| Mingbird agent loop | 47 | 25 | 34 | 39 | 36.25% |

Per-category values are accuracy percentages (200 tasks each); overall is their equal-weight mean.

On a 4B, the model's native FC channel beats a general agent loop — the cost of generality, disclosed as-is. Mingbird's position is a real-task harness (LRAB and all three τ² domains), not an FC scoring machine; the native FC channel cannot carry LRAB-style multi-step artifact work in the first place (no working directory, no file tools, no budget management). Per-category scoring details for both arms are in [bfcl/score_qwen35-4b-FC/](bfcl/score_qwen35-4b-FC/) and [bfcl/score_mingbird/](bfcl/score_mingbird/); the summary table is [bfcl/data_multi_turn.csv](bfcl/data_multi_turn.csv).

## Reproducing

- LRAB: task fixtures, scoring code and the aggregation script ship in this repository under `benchmarks/` — the CSV above is the aggregation output.
- τ²: driven by a stock τ²-bench checkout (uv environment) plus a thin Mingbird adapter; per-trial manifests for all three domains are in [tau2/](tau2/) in this repository.
- BFCL: official bfcl-eval, source unmodified; both arm handlers and the per-category scoring details are in [bfcl/](bfcl/) in this repository.
- Ablation: per-cell scores via the `AGENT_ABLATION` gate are in [ablation/](ablation/) in this repository.
