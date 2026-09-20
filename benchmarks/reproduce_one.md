# Reproduce one LRAB cell in ~30 minutes

The fastest end-to-end check of the benchmark: run **one** Mingbird cell (WF-01, the smallest workflow task) with the stock scorer, on any Windows 11 machine with [Ollama](https://ollama.com) installed.

```powershell
git clone https://github.com/Mingbird/Mingbird-agent
cd Mingbird-agent
pip install -r requirements.txt          # or your env of choice; python 3.10+

ollama pull qwen3.5:4b                   # the campaign model tag

# run one cell: fresh workdir, 90-min budget, artifact scoring
# (the Mingbird arm is registered under the repo's historical name "hummingbird")
python bench/lrab/runners/run_bench.py `
  --agent hummingbird `
  --task  bench/lrab/tasks/tier3_workflow/WF-01.json `
  --model qwen3.5:4b
```

The runner prints the cell's score JSON (`milestone_score / final_score / total`) and leaves the transcript and the working directory for inspection. The published cell for this task+model scores **1.0** (row `Mingbird,WF01,qwen3.5_4b` in [`lrab_scores.csv`](lrab_scores.csv)); at 0 temperature and thinking off it is deterministic up to infrastructure noise, so a re-run should land on the same artifacts.

To compare against a published competitor cell (stock harness, same task/budget/model), see `bench/lrab/runners/` for the goose / opencode / agent-mini adapters and the transport-level sampling normalizer that pins temperature 0 + thinking off for harnesses without those knobs.

## Scoring only

```powershell
python bench/lrab/scoring/score_task.py --task bench/lrab/tasks/tier3_workflow/WF-01.json --workdir <cell-workdir>
```

Deterministic, artifact-based: files exist, tests actually pass, reports contain the required findings. The same scorer produced every cell in the CSV (`--no-judge` skips optional judge-model checks).

## Full matrix

288 cells at ~10 min/cell median is a multi-day single-machine job; the per-cell protocol above is identical, so any subset re-derives the corresponding rows. The complete raw data lives in [`lrab_scores.csv`](lrab_scores.csv) and the per-trial τ² data under [`tau2_nt0/`](tau2_nt0/).
