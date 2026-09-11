# Benchmarks

Numbers referenced from the [README](../README.md), with methodology and raw data.
Everything here is reproducible on your machine; nothing requires trusting us.

## LRAB-288 (our benchmark)

**Definition.** 4 harnesses × 4 open models × 18 tasks = **288 cells**.

- **Harnesses**: Mingbird, goose, agent-mini, opencode — stock, no patches, each driving the same Ollama backend on the same machine (Intel Arc B390 iGPU, 32 GB shared memory, Windows 11).
- **Models**: `gemma4:e2b` (2B) · `qwen3.5:4b` (4B) · `gemma4:12b` (12B) · `ornith-1.5:35b` (35B MoE, multimodal).
- **Tasks**: 18 real tasks — 15 workflow tasks (WF-01…WF-15: code+tests, data analysis, web research with real search, file organization, refactoring, …) and 3 long-horizon tasks (LH-01…LH-03, multi-hour multi-phase builds).
- **Protocol**: per-cell budget — workflow 90 min, long-horizon 180 min; 1 retry, latest attempt wins; **timeouts score 0**; deterministic artifact-based scoring (files exist, tests actually pass, reports contain the required findings). Every cell runs in a fresh working directory; harness processes are isolated from the scoring.

**Per-model results** (average over 18 tasks; Mingbird's 35B cell includes one timeout scored 0):

| Harness | 2B gemma4:e2b | 4B qwen3.5:4b | 12B gemma4:12b | 35B ornith-1.5 | overall |
|---|---|---|---|---|---|
| **Mingbird** | 0.799 | 0.921 | 0.920 | 0.938 | **0.895** |
| goose | 0.266 | 0.636 | 0.620 | 0.822 | 0.586 |
| agent-mini | 0.246 | 0.706 | 0.576 | 0.092 | 0.405 |
| opencode | 0.017 | 0.404 | 0.140 | 0.776 | 0.334 |

**Raw data**: [`lrab_scores.csv`](lrab_scores.csv) — all 288 cells (harness, task, model, score, wall time, attempt directory). Every number above is the mean of 18 rows of this file. Full task transcripts land in this folder as final numbers lock.

**Deviations & notes** (audited post-publication; full detail in RESULTS.md):

- Two 2B cells (WF-13, LH-01) were re-run after the batch ended, for a tool-call parse-failure investigation, under the same latest-attempt-wins aggregation. This lifted Mingbird's overall from 0.883 to 0.895 (2B segment 0.753 → 0.799). The ranking is identical under either convention.
- Mingbird's frozen test build included a text-file post-processor that rewrote literal `\n`/`\t` escape sequences in Markdown deliverables; it fired on 8 of the 72 cells. A cell-by-cell audit found zero score impact (5 of the 8 cells score 1.0; the other 3 lost points on unrelated items).
- Mingbird ships more default tools than the baselines (persistent memory, skills, batch dispatch). A transcript audit shows zero uses of any of them across the 72 final transcripts.
- goose exposes no context-window knob and runs at its default; the other three harnesses are pinned to 32K. This is the one known configuration asymmetry (METHODS §5).

> LRAB was designed by us, so treat it as a *controlled experiment*, not a leaderboard: its value is that everything except the harness is held constant, and that every claim can be recomputed from the CSV.

**Design rationale & statistics**: [DESIGN.md](DESIGN.md) — task ladder, per-task
specifications, scoring architecture, freeze discipline, paired significance
analysis ([SIGNIFICANCE.md](SIGNIFICANCE.md), recomputable via
`analyze_significance.py`), and the threats-to-validity section. Short version:
Mingbird's edge is statistically significant on 2B/4B/12B (Holm-corrected
Wilcoxon, paired by task); on 35B the field compresses and Mingbird-vs-goose
does not reach significance — we state that bound.

## τ²-bench retail (external benchmark)

[τ²-bench](https://github.com/sierra-research/tau2-bench) (Sierra Research) is an independent, published agent benchmark: a user-simulator converses with the agent, which must use domain tools (retail database) to resolve the request. Scoring checks the final database state and natural-language assertions — an agent that bypasses its tool stream scores 0 on the DB check, so harnesses cannot fake tool use.

| Agent (same local 4B model `qwen3.5:4b`) | retail-115 pass rate (err-as-0) |
|---|---|
| **Mingbird (harness)** | **0.746** |
| τ²-bench native LLM agent | 0.430 |

- Protocol: pass^1, trial 1, seed 42, identical user simulator on both sides, identical tool schemas and policy prompts. Valid-trial conditioning: 0.780 vs 0.662.
- Mingbird's adapter adds two mechanical safeguards on top of the identical prompt and toolset: a repeat-call nudge (one user-role message after 4 identical `(tool, args)` calls) and a parser fallback that recovers format-leaked tool calls into real ones. Both are verbatim in the published adapter source; the native agent receives no injected messages.
- **Disclosure**: the user simulator is a cloud model (`qwen3.8-flash`), not the official τ² setup — so the published **gpt-4o 0.604** line (official setup, leaderboard reference) is shown for scale only and is not a same-conditions comparison.
- The native baseline includes 40/114 cells that end with an **empty assistant message** (no content, no tool calls) — a failure mode of reasoning-style model output that the baseline's own message validation rejects. We did **not** patch the baseline: a harness's own brittleness is part of what is being measured, and error cells score 0. Before final numbers lock, every harness's error cells get one uniform rerun pass (same manifest, latest attempt wins) so transient infrastructure hiccups are not conflated with agent failures.
- **Running now**: the same comparison for CLI harnesses **goose** and **opencode**, connected through MCP (their native tool mechanism). That table appears here as batches complete.

## Reproducing

- LRAB: task fixtures, scoring code and the aggregation script ship in this repository under `benchmarks/` (final numbers lock) — the CSV above is the aggregation output.
- τ²: driven by a stock τ²-bench checkout (`pip install tau2-bench` style uv environment) plus a thin Mingbird adapter; adapter code and full per-cell traces are published alongside the final numbers.
