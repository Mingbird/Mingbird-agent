# LRAB — Local Research & work-flow Agent Benchmark

**Version:** 0.2.0 (2026-08-28)
**Design goal:** Measure *long-horizon workflow reliability* of AI agents driven by **small/local LLMs** across **15 distinct domains**, with deterministic, reproducible grading.

## Design principles

1. **Long-horizon by construction.** Every task requires a plan of **≥8 discrete steps** (agents are instructed to build and maintain a todo list). Grading includes *milestone artifacts* (intermediate files), not only the final deliverable — an agent cannot pass by one lucky final write.
2. **15 disjoint domains.** Each task targets a different professional domain (research, software engineering, data, web, QA, education, planning, ...). Domain breadth mirrors AgentBench-style coverage; per-task depth (8+ steps) exceeds GAIA L1 short tasks.
3. **Offline-first, deterministic grading.** All task inputs are fixed fixtures shipped with the benchmark. Grading is *deterministic first* (file existence, structural checks, regex/field checks against known-answer fixtures); an LLM judge (fixed model, never the model-under-test) scores only open-ended quality dimensions, against a fixed rubric. Web-dependent tasks grade on *artifact structure* (sources cited, matrix shape), never on live page content, so scores remain comparable across run dates.
4. **No train/test contamination.** Fixtures are synthetic (synthetic DOIs `10.9000/synthetic.*`), written for this benchmark, and seeded with *known planted properties* (contradictions, missing references, outliers) that the grading keys check for. Models cannot "recall" answers; they must execute the workflow.
5. **Fair cross-agent comparison.** Same Ollama instance, same model tag, same context window, same wall-clock budget per task. Each agent's default configuration is recorded and disclosed. The only deliberate variable is the **agent runtime**.

## Task matrix (15 domains)

| ID | Domain | Tier | Plan steps | Key tools exercised |
|-----|--------|------|-----------|---------------------|
| WF-01 | Materials literature review | research | 9 | search(fixture DB), read, write |
| WF-02 | Peer-review & revision loop | research | 10 | read, analysis, multi-doc write |
| WF-03 | Software feature implementation | software | 10 | read code, code, test, bash |
| WF-04 | Bug localization & fix | software | 9 | test, read, code, bash |
| WF-05 | Data cleaning pipeline | data | 10 | read CSV, code, bash, validate |
| WF-06 | Statistical analysis & visualization | data | 10 | code, matplotlib, report |
| WF-07 | Web research & technology selection | web | 11 | web_search, web_fetch, matrix, report |
| WF-08 | API design & mock implementation | software | 10 | design, code, docs |
| WF-09 | Performance profiling & refactoring | software | 10 | bash, profile, code, verify |
| WF-10 | User manual from source code | tech-writing | 9 | read code, docs, examples |
| WF-11 | Competitive analysis report | business | 10 | read briefs, matrix, report |
| WF-12 | Course curriculum design | education | 9 | structure, slides outline, exercises |
| WF-13 | Privacy compliance audit | security | 10 | read code/config, findings, fixes |
| WF-14 | Release planning from requirements | planning | 10 | decompose, risk matrix, schedule |
| WF-15 | Experiment reproducibility audit | research | 10 | recompute, compare, deviation report |

## Task JSON schema

```json
{
  "id": "WF-01",
  "domain": "materials-literature-review",
  "version": "1.0",
  "fixtures": ["papers_db.jsonl", "aging_data.csv"],
  "prompt": "...(full English task instruction, includes the 8+ step plan skeleton)...",
  "required_plan_steps_min": 8,
  "milestones": [
    {"artifact": "shortlist.md", "check": "exists_and_contains", "params": {"any_of": ["S002", "Ti-5553"]}}
  ],
  "final_artifacts": [
    {"artifact": "review_report.md", "check": "structure", "params": {"required_sections": ["Abstract", "References"]}}
  ],
  "judge_rubric": "rubrics/wf01.md",
  "max_wall_minutes": 45,
  "notes": "..."
}
```

## Grading model

- **Milestone score (0-1):** deterministic checks over intermediate artifacts, averaged. Weight 40%.
- **Final artifact score (0-1):** deterministic structural checks. Weight 30%.
- **Quality score (0-1):** LLM judge (fixed model, e.g. `ornith-1.5:35b`, never the model-under-test when the MUT is 35B — in that case the judge is a distinct model and disclosed) against the per-task rubric. Weight 30%.
- **Plan compliance gate:** if the agent's transcript shows fewer than 8 planned steps, cap total at 0.5 (long-horizon reliability is the construct under test).
- **Failure modes recorded:** fake-finish (finish without artifacts), loop (≥3 identical calls), crash, timeout — reported alongside scores.

## Runner protocol

Each runner implements: `run(task_json, workdir, model, timeout_min) -> RunResult{exit_code, transcript_path, wall_seconds, token_usage?}`.

| Runner | Invocation |
|---|---|
| Hummingbird | `python ollama_agent.py <model> task_input.txt <workdir>` |
| opencode | `opencode run --model <ollama/model> "<prompt>"` (cwd = workdir) |
| agent-mini | `agent-mini "<prompt>"` (cwd = workdir) |
| goose | `goose run "<prompt>"` (cwd = workdir) |

All runs sequential (single GPU, exclusive). Transcript, workdir snapshot, and per-task JSON results archived under `results/<run-id>/`.

## Fairness disclosures (published with results)

- Each agent's default settings that we could not or did not pin (e.g. goose temperature) are explicitly listed.
- temp=0 for Hummingbird; other agents run at their defaults (documented; one uncontrolled variable per agent, following the atomic-agent GAIA precedent).
- Single run per cell (temp=0 deterministic for HB); multi-seed noted as future work.
- Judge model is fixed across all cells and never the model-under-test (when MUT = 35B, judge = a distinct smaller model; disclosed).

## Reproduction

```bash
# 1. Install benchmark environment (no heavy deps; scoring needs pandas, matplotlib)
pip install -r bench/lrab/requirements.txt

# 2. Smoke: run Hummingbird on one task
python bench/lrab/runners/hummingbird_runner.py --task bench/lrab/tasks/tier2_synthesis/WF-06.json --workdir /tmp/lrab_smoke

# 3. Score
python bench/lrab/scoring/score_task.py --task ... --workdir ...
```
