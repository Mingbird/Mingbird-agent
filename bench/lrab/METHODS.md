# LRAB Methodology: Scoring, Aggregation, and Timeout Rules

> Status: rules below were fixed **before any batch of each layer began** and applied
> uniformly to all agents and models. Where a rule was amended mid-campaign, the
> amendment and its date are recorded in §6 — nothing is silently re-specified
> after seeing results. (First written 2026-08-31 as the consolidated reference for
> the JOSS/HN write-up; rules themselves are listed with their adoption dates.)

## 1. Deterministic scoring (no LLM judge)

- Every rubric check is code: file existence, exact filename, line/JSON path
  content, numeric match within tolerance, word-count soft target, PNG validity
  (signature + IEND + PIL decode), `contains_groups` / `contains_ordered` /
  `script_pass` (added 2026-08-30 for the long-horizon layer).
- `judge_rubric` fields on tasks are **reported alongside** the deterministic
  score for qualitative reading, but never enter the numeric score.
- Score = weighted sum of passed checks / total, in [0, 1] per cell.

## 2. Cell model and attempt policy

- A **cell** = (agent, model, task). One run produces one directory
  `<agent>_<TASK>_<model>_m<attempt>_<MMDD_HHMMSS>` under `eval_results/`.
- **Retry policy (uniform, all four agents):** a cell that hits its wall-clock
  timeout is re-run exactly once as a fresh attempt (`m1`) in a new directory.
  Non-timeout failures (`early_finish`, `no_artifacts`, `error`, `completed`)
  are NOT retried. Adoption: 2026-08-28.
- **Attribution:** when a cell has multiple attempts, the result is the
  **latest attempt** (by run-directory timestamp). All aggregators
  (`batch_status.py`, `analyze_batch64.py`) dedupe by cell key before
  averaging. Adoption: 2026-08-29 (after the 64-cell batch showed 3 timeout
  retries on hummingbird all passing on retry).

## 3. Timeout handling

- A cell at timeout with no final artifacts scores **0** in the headline table.
  Its `duration_sec` is recorded as the budget (not the true completion time),
  and `failure_mode: timeout` is kept in the data so timeout-only analyses are
  possible.
- **Budgets by layer (identical across all four agents):** 40 min/cell for the
  workflow layer (WF-*), 90 min/cell for the long-horizon layer (LH-*).
  Rationale for the WF number: an earlier 25-min budget produced 5 timeouts
  that all completed healthily at 40 min (documented as a budget artifact,
  2026-08-28/29). Timeouts are therefore reported **only** after budget
  adequacy is verified for the model in question — "small model timed out"
  requires first ruling out budget artifacts and environment pollution.
- Reported separately: `timeout` vs `error` vs `early_finish` vs `no_artifacts`
  vs `completed` — a 0 from a timeout is not conflated with a 0 from a
  judged-but-wrong submission in the failure-mode breakdown tables.

## 4. Kill-resume protocol (LH-03, checkpoint task)

- Design: the harness kills the agent process tree (`taskkill /F /T`) at 50% of
  the cell budget, then restarts the **same command**; the agent is expected to
  resume from its own on-disk checkpoint. Scoring runs **once**, after the
  second stage ends. Total wall budget stays 90 min (kill + resume share it).
- `killed: false` in `score.json` resume metadata simply means the agent
  finished before the kill point — legitimate outcome, not an anomaly.
- Hummingbird resumes from its session checkpoint automatically; competitors
  have no checkpoint mechanism and restart from scratch — this is the feature
  the task measures, not an unfairness (documented per-agent capability).
- **Variance disclosure:** same-cell repeats of LH-03 varied up to 0.58
  (4b: 0.424 → 1.0). Any LH-03 claim in the paper must cite n>1 or explicitly
  declare single-run variance. Recorded 2026-08-30.

## 5. Fairness controls (all agents, adopted 2026-08-28)

| Dimension | Setting |
|---|---|
| Model | Same local ollama instance, identical tags: `ornith-1.5:35b`, `gemma4:12b`, `qwen3.5:4b`, `gemma4:e2b` |
| Context | 32768 pinned for hummingbird/opencode/agent-mini; goose has no ctx knob → ollama default (sole deviation, disclosed) |
| Temperature | 0 for all (goose default, disclosed) |
| Web search | DuckDuckGo source for all four (MCP for three, built-in client for agent-mini — same upstream, different exposure, disclosed) |
| Task prompts | Tool-name-neutral wording, byte-identical across agents |
| Skills/tools | Each agent runs with its own default toolset; no agent-specific task hints |
| Hardware | One machine (Intel Ultra X7 358H + Arc B390, 32 GB), one driver version per batch; batches serialized on one GPU — no concurrent-cell confounds |

## 6. Amendments log

- 2026-08-28: budgets 25→40 min (WF) after artifact audit; latest-attempt
  attribution made explicit.
- 2026-08-30: LH layer introduced with 90-min budgets and kill-resume protocol
  (design predates any LH results); `stale_alert_sec` made watcher-configurable
  (monitoring only — never affects scores).
- 2026-08-31: this consolidated document written after the competitor LH wave
  began; §2–5 rules are restatements of what was actually executed, with dates.

## 7. Reproducibility artifacts

- `MATRIX_MANIFEST*.json` (timestamped copies since 2026-08-30 — the
  overwrite hazard on the single-name manifest is itself disclosed),
  `eval_results/logs/matrix_*.log` (stdout tee), per-cell `score.json` +
  `transcript.txt` + `workdir/` snapshot.
- Aggregate tables are generated, never hand-edited:
  `analyze_batch64.py --patterns ... --out ...`.
