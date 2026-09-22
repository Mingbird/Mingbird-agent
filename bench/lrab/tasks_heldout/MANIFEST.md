# LRAB Held-Out Task Set (tasks_heldout)

Review item M8/P2: "use the existing task generator to produce a batch of
held-out tasks that never appeared during development, and re-run the 4
ablation arms on them." This directory contains that set: 18 task JSONs,
same tier structure and check-kind vocabulary as the frozen dev set
(`bench/lrab/tasks/`), same fixtures, new task surfaces.

## Generation

| | |
|---|---|
| Generator | `bench/lrab/tasks_heldout/gen_heldout.py` (self-contained; reads `../fixtures`, writes only inside `tasks_heldout/`) |
| Seed | `20260921` |
| Command (repo root) | `python bench/lrab/tasks_heldout/gen_heldout.py --seed 20260921` |
| Determinism | verified: same seed reproduces all 18 JSONs byte-identically; a different seed changes 14/18 files (the resampled surface), while fixture-anchored tier-4 ground truth stays stable |
| Outputs | `tier1_retrieval/` (2), `tier2_synthesis/` (4), `tier3_workflow/` (9), `tier4_longhorizon/` (3) + `rubrics/` (18 judge rubrics with embedded ground truth) |

Nothing under `bench/lrab/tasks/`, `bench/lrab/fixtures/`, `bench/lrab/gen_tasks.py`
or `bench/lrab/gen_lhab.py` was modified (`git status` shows only this new
untracked directory).

## Honest note on the "existing generator"

The repo does not contain a parameterized task generator in the strict sense;

- `gen_tasks.py` is a hardcoded authoring file: a static `TASKS` list, no seed,
  no CLI. Re-running it reproduces the existing 15 WF tasks byte for byte and
  cannot emit novel tasks.
- `gen_lhab.py` IS seeded, but it regenerates the tier-4 fixtures into the
  shared `fixtures/` directory and embeds the freshly drawn numbers into the
  checks. Re-running it with a new seed would overwrite the deployed fixtures
  the frozen dev set depends on.

`gen_heldout.py` therefore takes the faithful route: it re-implements the
archetypes as seeded variant templates (topic angle, artifact naming,
threshold floors, header wording, check composition are resampled from pools)
and RECOMPUTES all numeric ground truth from the FROZEN fixtures on disk at
generation time, exactly in the spirit of `gen_lhab.py`'s
truth-embedded-in-checks design. No fixture was regenerated; no number was
hand-typed.

## Task inventory

Each task is a fresh surface over the same archetype/fixture as its dev twin
(the WF/LH id in the last column). "Embedded truth" = numbers computed from
the frozen fixture at generation time and baked into `contains_any` /
`contains_groups` checks and/or the judge rubric.

| ID | Tier | Domain | Fixtures | Key artifacts (milestones -> final) | Embedded truth | Dev twin |
|---|---|---|---|---|---|---|
| HWF-01 | 1 | materials-recent-literature-map | papers_db.jsonl | screening_log, property_matrix -> recent_review, citation_index | 11 recent (>=2022) paper ids | WF-01 |
| HWF-02 | 1 | manuscript-integrity-audit | draft_paper.md | issues_register, evidence_table -> revised_conclusions, verification_checklist | planted 1080/1105 clash, overclaim strings | WF-02 |
| HWF-03 | 2 | cli-feature-per-day-report | app_source/timetrack.py | design_day, test_day -> timetrack.py, usage_day | new `day` subcommand contract | WF-03 |
| HWF-04 | 2 | characterization-first-debugging | buggy_project/* | failure_analysis, repro_tests -> inventory.py (spec_pytest), regression_notes | same 6/6 pytest oracle + seed hash | WF-04 |
| HWF-05 | 2 | quarantine-cleaning-pipeline | messy_sensor_data.csv | profile_notes, scrub.py -> tidy_data, rejected.csv, sensor_rollup, validation_ledger | 40 -> 35 rows, survivor sensors, sentinel values | WF-05 |
| HWF-06 | 2 | hardness-microstructure-analysis | aging_data.csv | stats_hardness, anomaly_watch -> 2 PNGs, plot_hardness.py, findings | hardness peak 368 HV; UTS anomaly 620C/4h = 1063 | WF-06 |
| HWF-07 | 3 | web-research-knowledge-base-selection | (none) | needs, landscape -> matrix, verdict, links | n/a (web task) | WF-07 |
| HWF-08 | 3 | api-query-half-design-and-mock | api_requirements.md | design_query, query_api.yaml -> app_query.py, demo | query-side contract from requirements | WF-08 |
| HWF-09 | 3 | benchmarked-refactor | legacy_slow_code.py | hotspot_notes, baseline_outputs.json -> fast_impl.py, bench_report | real function names as anchors | WF-09 |
| HWF-10 | 3 | cli-cheatsheet-documentation | app_source/timetrack.py | cli_cheatsheet, quickstart -> usage_examples, failure_modes | real subcommands/error strings | WF-10 |
| HWF-11 | 3 | tco-driven-product-selection | product_briefs.md | tco_model, fit_scores -> decision_memo, migration_risk | brief pricing facts (rubric) | WF-11 |
| HWF-12 | 3 | research-software-course-design | (none) | syllabus, module_map -> sessions/session01, assignments/project_brief, readings | 10-week span | WF-12 |
| HWF-13 | 3 | privacy-by-design-refactor | privacy_audit_source.py | data_flow_map, dpia -> payments_v2.py, controls_checklist | real function names; 6 planted finding classes | WF-13 |
| HWF-14 | 3 | qa-and-rollout-planning | requirements_doc.md | qa_capacity, descope_ladder -> rollout_plan, risk_register | bug ids B-101/102/103; 60h/RC envelope | WF-14 |
| HWF-15 | 3 | alternate-method-reproducibility-audit | experiment_description.md, raw_measurements.csv | method_note, onsets2.csv -> ea_recompute.py, fig_offset.png, audit2_report | offset-threshold onsets {500:30,520:30,540:30,560:40,580:60} min, Ea = -45.1 kJ/mol, R2 = 0.731 (rubric) | WF-15 |
| HLH-01 | 4 | long-horizon-mean-aggregation-chain | alloy_multibatch.csv | 8x batch_profile_BXX -> means_aggregate.py, means_check.json, synthesis, next_steps | per-batch mean UTS B01..B08 (1057.7, 1047.3, 1039.9, 999.7, 1045.2, 988.4, 1052.3, 1072.8); widest spread B08 = 436.0 | LH-01 |
| HLH-02 | 4 | long-horizon-context-pressure-variant | process_corpus.txt | wordlen_index.json -> stream_stats.py, wordlen_index.json, topic_counts, energy_report, distinct_report | top-8 words len>=6 (stress 3726, fraction 3609, structure 3609, energy 3594, temperature 3588, process 3569, boundary 3530, sample 3517); energy lines 2714; 6005 raw / 6000 distinct | LH-02 |
| HLH-03 | 4 | long-horizon-endurance-reverse | buggy_pipeline_pkg/* | baseline_failures + 10x diag_mXX -> 10 fixed modules + test_suite (script_pass), fix_narrative, final_report | same 10-bug oracle "10 passed, 0 failed"; reverse-order discipline; kill_at_pct 50 resume | LH-03 |

How each surface differs from its dev twin (all reuse the SAME fixture files):

- **Different question over the same data.** WF-01 screened aging papers ->
  HWF-01 screens year >= 2022 papers; WF-06 plotted UTS -> HWF-06 plots
  hardness/alpha fraction; LH-01 ranked peak UTS -> HLH-01 ranks MEAN UTS and
  within-batch spread; LH-02 indexed all words -> HLH-02 indexes words of
  length >= 6 plus energy-line counting; WF-15 used tangent intersection ->
  HWF-15 mandates an offset-threshold onset rule (recomputed Ea = -45.1
  kJ/mol, sign-flipped versus the claimed 152: the planted non-monotonicity
  bites harder under the alternate method).
- **Different process discipline.** WF-04 fix-then-report -> HWF-04
  characterization-tests-first; WF-03 `export csv` -> HWF-03 new `day`
  subcommand; WF-05 silent drops -> HWF-05 quarantine ledger where every
  dropped row must be accounted for; WF-14 dev schedule -> HWF-14 QA/rollout
  plan; LH-03 forward module order -> HLH-03 reverse order with a mandatory
  baseline capture; WF-10 full manual -> HWF-10 cheatsheet package.
- **Different artifact names, thresholds and wording throughout** (all
  min_words floors resampled within +/-15% of the archetype, seeded).

## Compatibility verification (all 18 PASS)

Validated by a one-off script (kept out of the repo; reproduced here):

1. **Parse**: every JSON loads; all required schema fields present
   (`id, domain, version, fixtures, prompt, required_plan_steps_min,
   plan_steps, milestones, final_artifacts, judge_rubric, max_wall_minutes`).
2. **Check kinds**: every kind is among the 14 implemented in
   `scoring/score_task.py`, and the union over the 18 tasks is IDENTICAL to
   the dev set's union: `contains_any, contains_groups, exists, image_valid,
   min_urls, min_words, not_contains, python_compiles, script_pass,
   spec_pytest, structure` (the scorer additionally supports
   `contains_ordered, seed_unchanged, file_min_bytes`, unused by both sets).
3. **Reference integrity**: every artifact name is non-empty, relative,
   portable (no `\`, no `..`, no drive letters); no identical duplicate check
   entries; every artifact referenced by checks is named in the prompt
   (stem-match; the dev set passes the same rule as a control); every fixture
   path exists under `bench/lrab/`; no task references a missing fixture.
4. **No text duplication**: normalized prompts differ from all 18 dev prompts;
   max 8-word-shingle Jaccard similarity vs any dev prompt is 0.017
   (threshold 0.35). Only harness boilerplate fragments coincide.
5. **No machine leakage**: no absolute paths, drive letters or usernames in
   any generated file.
6. **Tier structure**: 2 / 4 / 9 / 3 exactly.
7. **Scoring-engine smoke**: `score_task(..., judge=False)` executes every
   task against an empty workdir without raising (params shapes accepted;
   total = 0 as expected on an empty dir).

## Intentional deviation from dev-set conventions

- `judge_rubric` is `../tasks_heldout/rubrics/<ID>.md` instead of
  `rubrics/<ID>.md`. The scorer joins `judge_rubric` against `scoring/`, and
  the dev set's `rubrics/...` paths do not exist there (no `bench/lrab/rubrics`
  in-tree; those tasks silently fall back to the generic judge prompt). The
  relative `../` path makes the held-out judge rubrics actually load without
  touching any existing repo file. Verified to resolve through the scorer's
  own path-joining logic.
- `max_wall_minutes`: 60 for tiers 1-3, 90 for tier 4, `kill_at_pct: 50` +
  `resume_test: true` only on HLH-03 - same protocol constants as the dev set
  so ablation-arm reruns stay comparable.

## Re-running the arms

```
python bench/lrab/runners/run_bench.py --agent <arm> \
    --task bench/lrab/tasks_heldout/tier2_synthesis/HWF-05.json --model <model>
```

The runner resolves fixture paths against `bench/lrab/` exactly as for dev
tasks, so held-out tasks run unchanged.
