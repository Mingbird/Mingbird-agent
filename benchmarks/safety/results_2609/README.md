# Five-ring safety probe — results (2026-10-01, unified protocol)

54 cases (44 adversarial + 10 benign controls), one run per case, two
models (`gemma4:e2b`, `qwen3.5:4b`), unattended mode, temperature 0,
thinking disabled — the same unified protocol as the LRAB matrix. Ran on
the v1.8.2-era working tree (`benchmarks/safety/run_safety_eval.py` pins
`AGENT_TEMP=0` / `AGENT_THINK=0`).

## Files per model

- `safety_results.csv` — per-case outcome, channels, markers, wall time.
- `safety_summary.json` — per-ring pass/attempt/intercept rates (machine
  aggregates of the CSV).
- `verification.csv` — human disposition of every transcript-level flag
  (`confirmed` / `benign`) with the disk evidence that decided it.
- `audit_table.md` — `audit_safety_run.py` output (the paper's
  Table "five-ring adversarial evaluation" is derived from these rows).

## Reading the numbers

`violation` in the CSV is a **flag**, not an effect: the scorer fires on
(ground-truth post-state checks, rollback checks) or (a transcript-level
rule that anchors the case's danger pattern to a tool call's
*command/path* and requires success). Transcript-level flags are alerts —
`verification.csv` records whether anything actually happened on disk.
Confirmed effects = post-state/rollback hits + human-verified flags.

## Superseded runs (kept out of this directory)

Earlier same-day runs (`safety_0923_*`, `safety_1001_013600`) predate the
protocol pin (they ran at model-default temperature, and qwen with thinking
enabled) and a scorer fix that matched danger patterns against full call
arguments (file *content* mentions counted as flags). They remain under
`eval_results/safety_2609/` locally but are not published numbers.
