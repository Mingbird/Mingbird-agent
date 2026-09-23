# Frontier-model probe: one cloud model, four harnesses

The LRAB-288 matrix varies the **model** (2B–35B) at fixed local hardware.
This probe holds the model fixed at a hosted frontier model and varies only
the **harness** — the cleanest decomposition of "model contribution vs
harness contribution" we can run.

## Protocol

- **Model**: hosted `qwen3.8-flash` (DashScope compatible-mode endpoint),
  temperature 0, thinking disabled (`enable_thinking=false`) — the same
  unified protocol as the main matrix.
- **Apparatus**: a local shim presents the cloud endpoint as an Ollama
  service (`/api/chat`, `/api/tags`, plus an OpenAI-compatible
  `/v1/chat/completions` with SSE passthrough). Every harness runs
  **unmodified** against it; each harness speaks its native protocol.
- **Arms**: mingbird, goose, opencode, agent-mini — the same four harnesses
  as the main matrix, stock versions (see the paper's appendix for version
  pins).
- **Tasks**: all 18 LRAB tasks (15 workflow + 3 long-horizon). Budgets:
  60 min/task (WF), 90 min/task (LH). Deterministic artifact scoring,
  identical to the main matrix. One trial per arm per task (per-cell API
  cost bounds replication).
- **Cost**: the full campaign is 3,126 model calls / 53.7M prompt tokens /
  0.8M completion tokens.

## Results

| Harness | WF (15) | LH (3) | Total (18) |
|---|---|---|---|
| **mingbird** | **1.000** | 0.980 | **0.997** |
| goose | 0.990 | 0.980 | 0.989 |
| opencode* | 0.913 | 0.980 | 0.925* |
| agent-mini | 0.490 | 0.415 | 0.478 |

\*opencode WF-08 hits the 60-minute budget: it starts the task's mock API
server in the foreground and blocks on it (goose completes the same task in
776 s). The WF mean is over the 14 scored cells; counting the timeout as 0
gives a total of 0.874 — ranking unchanged.

LH-02 scores 0.939 under **all four** harnesses — a task-side cap, not
harness variance.

## Reading

- Under the local 4B model the best-to-worst harness gap on these tasks is
  0.17 (0.876 vs 0.706); pinned to a frontier model it widens to 0.52
  (0.997 vs 0.478). That headline spread is carried by one arm, though: the
  three well-formed scaffolds sit within 0.07 of each other. So the claim is
  deliberately narrower than "the harness is the ceiling": **a defective
  scaffold buries more than half of a frontier model's measured capability,
  while between intact harnesses the model remains the bigger lever**
  (fixing the harness and swapping local 4B for the frontier model moves
  mingbird +0.121, goose +0.188, opencode +0.460).
- Failures are mechanistic, not noise: opencode's model replies "what
  task?" and exits on WF-03 under its scaffold (the same model does not do
  this under the others), and opencode's foreground-server block on WF-08
  contrasts with goose finishing the identical task in 776 s.

## Data

[`frontier_probe_scores.csv`](frontier_probe_scores.csv) — one row per
arm × task (72 rows): score, failure mode, wall seconds. Per-cell
transcripts are retained and will ship with the paper's artifact package.

## Caveats

This is a probe, not a leaderboard: a single hosted model (not a frozen
snapshot), one trial per cell, and a cloud endpoint rather than local
weights. It supports one directional claim — harness choice dominates at
fixed model — and nothing about any specific model's ranking.
