#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the 15 LRAB task JSON files (deterministic, reviewable)."""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "tasks")

COMMON = (
    "You are an autonomous agent working in the current directory. "
    "FIRST call todo(action=create) with a numbered plan covering every step below (at least {nsteps} steps). "
    "Then execute the steps one by one, creating each required file with the exact filename given. "
    "Do not fabricate content: base every claim on the provided fixture files in this directory. "
    "When all artifacts are written and verified, call finish with a short summary."
)

TASKS = [
    # ---------------- Tier 1: research/retrieval ----------------
    {
        "id": "WF-01", "domain": "materials-literature-review", "tier": 1,
        "fixtures": ["fixtures/papers_db.jsonl"],
        "steps": [
            "Create todo plan", "Load and scan papers_db.jsonl", "Select aging-related papers (>=6)",
            "Extract per-paper metadata", "Build comparison table", "Identify data contradictions",
            "Draft review body with [n] citations", "Write references section", "Verify all artifacts exist",
        ],
        "prompt": """You are a materials researcher. Using papers_db.jsonl in this directory, produce a mini literature review on "aging treatment of titanium alloys".

Required steps (plan at least 9):
1. Plan with todo(action=create).
2. Read papers_db.jsonl and identify ALL papers whose abstract concerns aging/precipitation of titanium alloys (expect 6 or more).
3. Write shortlist.md listing each selected paper as: id, title, first author, year, DOI.
4. Write data_table.md with a comparison table: paper id | alloy | aging temp (C) | UTS (MPa) | elongation (%), using only values present in the fixture.
5. Note any data contradiction between papers (e.g., different strength trends at similar temperatures) in contradictions.md.
6. Write review_report.md (400-600 words) with sections: Abstract, Comparison, Mechanisms, Open questions, References.
7. Cite papers as [S001]-style ids in the text; every cited id must exist in papers_db.jsonl.
8. Write references.md mapping each [Sn] marker to its full citation line.
9. Verify all 4 files exist (list them), then finish.""",
        "milestones": [
            {"artifact": "shortlist.md", "check": "contains_any", "params": {"any_of": ["S001", "S002", "S003"]}},
            {"artifact": "data_table.md", "check": "contains_any", "params": {"any_of": ["Ti-6Al-4V", "Ti-5553", "aging"]}},
        ],
        "final": [
            {"artifact": "review_report.md", "check": "structure", "params": {"required_sections": ["Abstract", "References"], "min_words": 350}},
            {"artifact": "references.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf01.md",
    },
    {
        "id": "WF-02", "domain": "peer-review-revision-loop", "tier": 1,
        "fixtures": ["fixtures/draft_paper.md"],
        "steps": [
            "Create todo plan", "Read draft thoroughly", "Catalog issues (data/reference/figure/overclaim)",
            "Write review_round1.md", "Plan revisions per issue", "Write revised_paper.md",
            "Write change_log.md mapping issue->fix", "Verify consistency of revision", "Re-verify artifacts",
        ],
        "prompt": """You are a peer reviewer and then the author. The manuscript draft_paper.md contains at least 4 distinct problems (data inconsistencies, a dangling citation, a missing figure, an overclaim, and/or schedule inconsistencies).

Required steps (plan at least 9):
1. Plan with todo(action=create).
2. Read draft_paper.md carefully, cross-checking every number in the text against Table 1 and every citation against the reference list.
3. Write review_round1.md: numbered issues, each with (a) location, (b) problem, (c) severity [high/medium/low], (d) suggested fix. Find at least 4 issues.
4. For each issue write a concrete revision decision in revision_plan.md.
5. Apply all revisions and write revised_paper.md (full corrected manuscript, same structure).
6. Write change_log.md: one line per issue, "issue N -> what changed where".
7. Re-check revised_paper.md: no dangling citations, all numbers consistent with Table 1, no overclaim wording ("prove" -> "suggest").
8. Verify all files exist and are consistent with each other, then finish.""",
        "milestones": [
            {"artifact": "review_round1.md", "check": "contains_any", "params": {"any_of": ["1080", "1105", "[5]"]}},
            {"artifact": "revision_plan.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "revised_paper.md", "check": "not_contains", "params": {"none_of": ["proves", "[5]"]}},
            {"artifact": "change_log.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf02.md",
    },
    # ---------------- Tier 2: software ----------------
    {
        "id": "WF-03", "domain": "software-feature-implementation", "tier": 2,
        "fixtures": ["fixtures/app_source/timetrack.py"],
        "steps": [
            "Create todo plan", "Read timetrack.py to understand structure", "Design export format (CSV)",
            "Implement cmd_export", "Wire into argparse", "Write test_export.py",
            "Run tests and fix failures", "Verify edge case (empty entries)", "Write usage example in EXPORT.md",
        ],
        "prompt": """Implement a new feature in the time-tracker program timetrack.py (in this directory).

Feature: `timetrack export --format csv --since YYYY-MM-DD` writes a CSV report of all finished entries (project,start,end,hours,note) to stdout or a file. `hours` is rounded to 2 decimals. `--since` filters by start date. Empty result produces a header-only CSV.

Required steps (plan at least 9):
1. Plan with todo(action=create).
2. Read timetrack.py and understand its storage format and command pattern.
3. Write design_notes.md: CSV column order, rounding rule, edge cases (no entries, running timer excluded).
4. Implement cmd_export in timetrack.py and register it in argparse.
5. Write test_export.py with at least 4 pytest tests (normal export, --since filter, empty state header-only, running timer excluded).
6. Run the tests (python -m pytest test_export.py -q) and fix until green.
7. Also run any other test files to confirm no regression.
8. Write EXPORT.md with a usage example (real command + real output).
9. Verify timetrack.py still compiles (python -m py_compile timetrack.py) and all files exist, then finish.""",
        "milestones": [
            {"artifact": "design_notes.md", "check": "exists"},
            {"artifact": "test_export.py", "check": "exists"},
        ],
        "final": [
            {"artifact": "EXPORT.md", "check": "exists"},
            {"artifact": "timetrack.py", "check": "contains_any", "params": {"any_of": ["cmd_export", "export"]}},
        ],
        "rubric": "rubrics/wf03.md",
    },
    {
        "id": "WF-04", "domain": "bug-localization-and-fix", "tier": 2,
        "fixtures": ["fixtures/buggy_project/inventory.py", "fixtures/buggy_project/test_inventory.py"],
        "steps": [
            "Create todo plan", "Copy fixtures into workdir", "Run failing tests to see failures",
            "Diagnose BUG-1 (duplicate SKU)", "Diagnose BUG-2 (zero/negative qty)", "Diagnose BUG-3 (total_value)",
            "Diagnose BUG-4 (case-sensitive search)", "Fix inventory.py for all bugs", "Run tests until green",
        ],
        "prompt": """The project in this directory (inventory.py, test_inventory.py) has failing tests. test_inventory.py is the specification and MUST NOT be modified.

Required steps (plan at least 9):
1. Plan with todo(action=create).
2. Copy inventory.py and test_inventory.py into the current working directory if not already here.
3. Run python -m pytest test_inventory.py -q and record which tests fail and why.
4. Read inventory.py and write bug_report.md: one section per bug (symptom from test output, root cause in code, planned fix). Expect at least 4 distinct bugs.
5. Fix inventory.py so every test passes. Keep the public function signatures unchanged. Do not edit test_inventory.py.
6. Re-run python -m pytest test_inventory.py -q until fully green.
7. Write fix_summary.md: bug -> one-line description of the actual change.
8. Run a final full pytest with -q and paste the tail into fix_summary.md.
9. Verify all files exist and tests are green, then finish.""",
        "milestones": [
            {"artifact": "bug_report.md", "check": "exists"},
            {"artifact": "fix_summary.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "inventory.py", "check": "python_compiles"},
            {"artifact": "test_inventory.py", "check": "exists"},
        ],
        "rubric": "rubrics/wf04.md",
        "extra_judge_note": "Run the tests yourself if possible: pytest must pass 6/6. Check the agent did not modify test_inventory.py.",
    },
    {
        "id": "WF-05", "domain": "data-cleaning-pipeline", "tier": 2,
        "fixtures": ["fixtures/messy_sensor_data.csv"],
        "steps": [
            "Create todo plan", "Profile the raw CSV (rows, columns, issues)",
            "Define cleaning rules (duplicates, sentinels, missing, outliers, duplicates-by-key)",
            "Implement clean_data.py", "Run pipeline to produce clean_data.csv",
            "Write validation_report.md (rows in/out, issues fixed per rule)",
            "Compute per-sensor summary into sensor_summary.csv",
            "Cross-check summary against clean data", "Verify artifacts",
        ],
        "prompt": """Clean the sensor dataset messy_sensor_data.csv (in this directory). Known issues: an impossible sentinel temperature (9999), a physically impossible value (-40.0 at room conditions), missing humidity, status='error' rows, and at least one exact duplicate row.

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Write profile_raw.md: total rows, distinct sensors, count of each issue type found (inspect the data; do not guess).
3. Write clean_data.py implementing rules: drop exact duplicate rows; drop rows with status != ok; treat temperature outside [-30, 60] as invalid and drop; drop rows with any missing field; document each rule as a comment.
4. Run it to produce clean_data.csv (same header).
5. Write validation_report.md: rows in -> rows dropped per rule -> rows out (numbers must add up).
6. Produce sensor_summary.csv: sensor_id, n_readings, mean_temp, min_temp, max_temp (rounded to 2 decimals), from the CLEAN data.
7. Sanity-check: no sensor in summary has mean_temp outside [-30, 60]; write the check result into validation_report.md.
8. Verify clean_data.csv has no duplicates/sentinels (re-scan), then finish.""",
        "milestones": [
            {"artifact": "profile_raw.md", "check": "exists"},
            {"artifact": "clean_data.py", "check": "python_compiles"},
        ],
        "final": [
            {"artifact": "clean_data.csv", "check": "exists"},
            {"artifact": "sensor_summary.csv", "check": "exists"},
            {"artifact": "validation_report.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf05.md",
    },
    {
        "id": "WF-06", "domain": "statistical-analysis-visualization", "tier": 2,
        "fixtures": ["fixtures/aging_data.csv"],
        "steps": [
            "Create todo plan", "Read aging_data.csv and inspect columns", "Compute descriptive statistics",
            "Identify the strength peak and the anomalous point", "Write analysis.py (pandas/matplotlib)",
            "Generate figures: fig_strength.png, fig_elongation.png", "Draft analysis.md with numbers",
            "Verify figures exist and are non-empty", "Finalize report",
        ],
        "prompt": """Analyze aging_data.csv (Ti-6Al-4V aging dataset: temperature, time, UTS, elongation, hardness, alpha fraction).

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read the CSV and write descriptive_stats.md: for UTS and elongation give count/mean/min/max.
3. Identify the peak UTS condition and note the 620C/4h row: does UTS behave monotonically with temperature? Flag any anomaly in anomalies.md.
4. Write analysis.py that: loads the CSV, plots UTS vs temperature and elongation vs temperature (labeled axes, units, title), saves fig_strength.png and fig_elongation.png, and prints peak/valley conditions to stdout.
5. Run analysis.py and confirm both PNG files exist and are non-trivial (>20KB).
6. Write analysis.md (300-500 words): trend description, the strength-ductility trade-off, the 620C anomaly discussion (possible measurement error vs real effect), and one actionable recommendation.
7. Include at least 3 concrete numbers from the data in analysis.md.
8. Verify artifacts (list files with sizes), then finish.""",
        "milestones": [
            {"artifact": "anomalies.md", "check": "exists"},
            {"artifact": "analysis.py", "check": "python_compiles"},
        ],
        "final": [
            {"artifact": "fig_strength.png", "check": "file_min_bytes", "params": {"min_bytes": 20000}},
            {"artifact": "fig_elongation.png", "check": "file_min_bytes", "params": {"min_bytes": 20000}},
            {"artifact": "analysis.md", "check": "min_words", "params": {"min_words": 280}},
        ],
        "rubric": "rubrics/wf06.md",
    },
    # ---------------- Tier 3: workflow ----------------
    {
        "id": "WF-07", "domain": "web-research-technology-selection", "tier": 3,
        "fixtures": [],
        "steps": [
            "Create todo plan", "Define selection criteria (5+)", "Search for candidates (>=5)",
            "Shortlist 3 with source URLs", "Fetch and read primary pages",
            "Build comparison matrix (criteria x products)", "Score against criteria",
            "Write recommendation with trade-offs", "List all source URLs", "Verify artifacts",
        ],
        "prompt": """Research task (use web_search/web_fetch or MCP search tools): recommend a self-hosted vector database for a small team building an offline-first RAG application.

Required steps (plan at least 11):
1. Plan with todo(action=create).
2. Write criteria.md: at least 5 weighted criteria (license, resource footprint, hybrid search, ecosystem, ops complexity) with justification.
3. Search the web and write candidates.md listing at least 5 candidate projects with one-line description and source URL each.
4. Shortlist 3 candidates in shortlist.md with the reason for shortlisting/exclusion.
5. For each shortlisted candidate, fetch its primary docs/GitHub page and extract: license, language, minimum RAM, hybrid search support (yes/no), last release date.
6. Write comparison_matrix.md: criteria as rows, candidates as columns, cells filled with sourced facts.
7. Write recommendation.md (250-400 words): scored decision, trade-offs, and what would change the choice. Every factual claim must have a URL.
8. List all consulted URLs in sources.md (>=5 unique URLs).
9. Verify all files exist, then finish.""",
        "milestones": [
            {"artifact": "criteria.md", "check": "exists"},
            {"artifact": "candidates.md", "check": "min_urls", "params": {"min_urls": 5}},
        ],
        "final": [
            {"artifact": "comparison_matrix.md", "check": "exists"},
            {"artifact": "recommendation.md", "check": "min_words", "params": {"min_words": 220}},
            {"artifact": "sources.md", "check": "min_urls", "params": {"min_urls": 5}},
        ],
        "rubric": "rubrics/wf07.md",
        "notes": "Web-dependent: grade on artifact structure and internal consistency, not on which product wins.",
    },
    {
        "id": "WF-08", "domain": "api-design-and-mock", "tier": 3,
        "fixtures": ["fixtures/api_requirements.md"],
        "steps": [
            "Create todo plan", "Read requirements and clarify data model", "Design error model (RFC 7807)",
            "Write openapi.yaml (3 endpoints + schemas)", "Implement mock server (in-memory)",
            "Implement validation rules from requirements", "Write examples.md (per-endpoint pairs)",
            "Test endpoints with curl/requests and record outputs", "Verify all artifacts",
        ],
        "prompt": """Implement the SensorHub v2 ingestion API from api_requirements.md (in this directory).

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read api_requirements.md and write design_notes.md: data model, validation order, idempotency mechanism, error payload shape.
3. Write openapi.yaml (OpenAPI 3.1): the two /v2/readings operations and GET /v2/stats, with schemas for Reading, BatchRequest, BatchResult, and a Problem schema.
4. Implement a runnable mock (Python, any framework, in-memory store) in app.py: implement validation (range checks, duplicate detection within batch, X-Batch-Id idempotency) exactly as the requirements state.
5. Write examples.md: for each endpoint, one real request and its real response (run the server and capture).
6. Demonstrate the rejection path: one batch containing an invalid reading; show the valid subset was accepted and the rejected item reported.
7. Show the rate-limit response is configured (429 + Retry-After) — a config/code excerpt in examples.md is sufficient.
8. Verify the server starts without errors and all files exist, then finish.""",
        "milestones": [
            {"artifact": "design_notes.md", "check": "exists"},
            {"artifact": "openapi.yaml", "check": "contains_any", "params": {"any_of": ["openapi: 3.1", "openapi: \"3.1\"", "/v2/readings"]}},
        ],
        "final": [
            {"artifact": "app.py", "check": "python_compiles"},
            {"artifact": "examples.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf08.md",
    },
    {
        "id": "WF-09", "domain": "performance-profiling-refactoring", "tier": 3,
        "fixtures": ["fixtures/legacy_slow_code.py"],
        "steps": [
            "Create todo plan", "Copy fixture into workdir and read it", "Build a corpus generator (make_corpus.py)",
            "Baseline: time top_terms on the corpus, record numbers", "Profile with cProfile, identify hot spots",
            "Optimize term_frequency (single pass, no re-scan)", "Optimize dedupe_lines (set-based)",
            "Re-time and compute speedup, record numbers", "Verify identical outputs (before vs after)",
        ],
        "prompt": """Optimize legacy_slow_code.py (in this directory) for speed WITHOUT changing its behavior.

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read legacy_slow_code.py and write hotspots.md: the 4 intended hot spots and why each is slow.
3. Write make_corpus.py: generate a deterministic test corpus (>=50 .txt files, >=200 lines each, seeded random English-like text) into corpus/ so timings are measurable.
4. Copy the original to reference_impl.py. Run it on a reduced corpus and save its outputs (top_terms list and dedupe_lines list) to reference_outputs.json.
5. Profile the original with cProfile on the reduced corpus; paste the top functions into profile_baseline.txt.
6. Write optimized.py with the same public functions and identical signatures/outputs. Use appropriate data structures (e.g. single-pass counting, sets).
7. Time both implementations on the SAME corpus (time.perf_counter, best of 3) and write speedup_report.md: baseline s, optimized s, speedup x.
8. Prove equivalence: load reference_outputs.json and compare against optimized.py outputs on the same reduced corpus; assert equal and record the check in speedup_report.md.
9. Run the full-size corpus with optimized.py and record the time, then finish.""",
        "milestones": [
            {"artifact": "hotspots.md", "check": "exists"},
            {"artifact": "reference_outputs.json", "check": "exists"},
        ],
        "final": [
            {"artifact": "optimized.py", "check": "python_compiles"},
            {"artifact": "speedup_report.md", "check": "min_words", "params": {"min_words": 120}},
        ],
        "rubric": "rubrics/wf09.md",
    },
    {
        "id": "WF-10", "domain": "user-manual-from-source", "tier": 3,
        "fixtures": ["fixtures/app_source/timetrack.py"],
        "steps": [
            "Create todo plan", "Read timetrack.py fully", "Enumerate commands and options",
            "Test each command by actually running it", "Write manual sections per command",
            "Include real captured outputs", "Add troubleshooting section", "Verify examples match behavior",
        ],
        "prompt": """Write a complete user manual for the timetrack.py CLI (in this directory) by reading the source AND actually running the commands.

Required steps (plan at least 9):
1. Plan with todo(action=create).
2. Read timetrack.py and write command_inventory.md: every subcommand, its arguments, and what it does.
3. Actually run: python timetrack.py start --note "manual test" demo-project; then stop; then report. Capture real outputs.
4. Write user_manual.md with sections: Introduction, Installation, Getting started, Commands (start/stop/report, each with syntax table, options, one real captured example), Data storage (where entries.json lives and its format), Troubleshooting (already-running error, empty report).
5. Include at least 2 real captured terminal outputs in fenced code blocks.
6. Add a "Tips" section: at least 3 tips derived from the source (e.g. notes accumulate, report skips running timers).
7. Verify every command example in the manual actually works (re-run them), then finish.""",
        "milestones": [
            {"artifact": "command_inventory.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "user_manual.md", "check": "min_words", "params": {"min_words": 400}},
            {"artifact": "user_manual.md", "check": "contains_any", "params": {"any_of": ["Troubleshooting", "troubleshooting"]}},
        ],
        "rubric": "rubrics/wf10.md",
    },
    {
        "id": "WF-11", "domain": "competitive-analysis-report", "tier": 3,
        "fixtures": ["fixtures/product_briefs.md"],
        "steps": [
            "Create todo plan", "Read product briefs", "Define evaluation criteria with weights",
            "Score each product per criterion", "Identify the target segment fit",
            "Write comparison_matrix.md", "Write recommendation_report.md with trade-offs",
            "Add risk factors and mitigation", "Verify artifacts",
        ],
        "prompt": """A materials research group (8-15 researchers, mixed OS, intermittent lab network, one compliance-constrained member) must choose a lab information platform. Product briefs are in product_briefs.md.

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read product_briefs.md and write criteria.md: 6 weighted criteria (weights sum to 100) derived from the group's stated constraints.
3. Score each product (A/B/C) per criterion with a 1-5 scale and one-line justification each, in scoring.md.
4. Compute weighted totals and write comparison_matrix.md (criteria as rows, products as columns, totals row).
5. Identify which product fits the target segment best and which constraint is decisive — in recommendation_report.md (300-450 words).
6. Include trade-offs: what the group gives up with the recommended choice.
7. Write risk_factors.md: at least 3 risks of the recommendation with mitigations.
8. Verify matrix math (weights*scores sum correctly) and note the check in recommendation_report.md, then finish.""",
        "milestones": [
            {"artifact": "criteria.md", "check": "exists"},
            {"artifact": "scoring.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "comparison_matrix.md", "check": "exists"},
            {"artifact": "recommendation_report.md", "check": "min_words", "params": {"min_words": 280}},
            {"artifact": "risk_factors.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf11.md",
    },
    {
        "id": "WF-12", "domain": "course-curriculum-design", "tier": 3,
        "fixtures": [],
        "steps": [
            "Create todo plan", "Define audience and prerequisites", "Design 8-week module map",
            "Write learning outcomes per week", "Create lecture outline for weeks 1-3",
            "Design lab exercises with starter code sketch", "Write exam blueprint (question types x outcomes)",
            "Write prerequisites_and_resources.md", "Verify artifacts",
        ],
        "prompt": """Design a complete university course: "Practical AI Agents for Materials Researchers" (8 weeks, 2h lecture + 2h lab per week, audience: materials science MSc students with basic Python).

Required steps (plan at least 9):
1. Plan with todo(action=create).
2. Write course_overview.md: audience, prerequisites, 5 course-level learning outcomes (measurable verbs).
3. Write week_by_week.md: for each of the 8 weeks — topic, 3 lecture bullets, lab goal, and the learning outcome it maps to. Include local LLM + agent concepts (ollama, tool calling, evaluation) and materials use cases.
4. Write lecture_outlines/week1.md and week2.md: slide-by-slide outline (>=10 slides each).
5. Write labs/lab1.md: a 2-hour lab where students build a minimal tool-calling agent against a local model; include starter code sketch and expected deliverable.
6. Write exam_blueprint.md: table mapping question types (10 MC, 4 short answer, 1 project) to learning outcomes and Bloom levels.
7. Write prerequisites_and_resources.md: software to install, reading list (>=5 real resources).
8. Verify all files exist and outcomes are consistently referenced, then finish.""",
        "milestones": [
            {"artifact": "course_overview.md", "check": "exists"},
            {"artifact": "week_by_week.md", "check": "contains_any", "params": {"any_of": ["Week 8", "week 8"]}},
        ],
        "final": [
            {"artifact": "exam_blueprint.md", "check": "exists"},
            {"artifact": "labs/lab1.md", "check": "exists"},
            {"artifact": "prerequisites_and_resources.md", "check": "min_urls", "params": {"min_urls": 5}},
        ],
        "rubric": "rubrics/wf12.md",
    },
    {
        "id": "WF-13", "domain": "privacy-compliance-audit", "tier": 3,
        "fixtures": ["fixtures/privacy_audit_source.py"],
        "steps": [
            "Create todo plan", "Read payment_processor.py line by line", "Inventory PII flows (collect/store/log/transfer)",
            "Map findings to GDPR/PCI principles", "Write audit_report.md with severity ratings",
            "Write remediation plan per finding", "Implement fixes into payment_processor_fixed.py",
            "Verify fixes address each finding", "Summarize residual risks",
        ],
        "prompt": """Audit privacy_audit_source.py (a payment module) for privacy and compliance problems.

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read the file and write pii_inventory.md: every piece of PII handled, where it is stored, logged, or transmitted.
3. Identify at least 6 distinct findings (plaintext storage, logging of card/SSN, unencrypted transfer, missing retention, unauthorized export, no access control) and write audit_report.md: each finding with (a) code location, (b) GDPR article or PCI DSS requirement implicated, (c) severity (critical/high/medium), (d) evidence (quoted line).
4. Write remediation_plan.md: per finding, the concrete fix and its priority order.
5. Write payment_processor_fixed.py implementing the fixes (hash/tokenize card storage, no CVV storage, no secret logging, HTTPS, export controls, proper deletion).
6. For each finding, verify the fix addresses it and mark the verification in remediation_plan.md.
7. Write residual_risks.md: what remains risky even after fixes (at least 3 items).
8. Verify payment_processor_fixed.py compiles (python -m py_compile), then finish.""",
        "milestones": [
            {"artifact": "pii_inventory.md", "check": "exists"},
            {"artifact": "audit_report.md", "check": "min_words", "params": {"min_words": 350}},
        ],
        "final": [
            {"artifact": "payment_processor_fixed.py", "check": "python_compiles"},
            {"artifact": "remediation_plan.md", "check": "exists"},
            {"artifact": "residual_risks.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf13.md",
    },
    {
        "id": "WF-14", "domain": "release-planning", "tier": 3,
        "fixtures": ["fixtures/requirements_doc.md"],
        "steps": [
            "Create todo plan", "Read requirements and constraints", "Estimate effort per must/should feature",
            "Sequence work respecting dependencies (B-101 before beta)", "Allocate team capacity across 12 weeks",
            "Write risk_matrix.md (probability x impact)", "Write mitigation plan for top risks",
            "Produce release_plan.md with milestones and beta gate", "Verify plan covers all committed items",
        ],
        "prompt": """Produce a v2.0 release plan for HummingNote from requirements_doc.md (in this directory). Team: 3 devs, 1 QA (60 tester-hours per RC), part-time designer. 12 weeks. Public beta at week 10. B-101 data loss must ship.

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read requirements_doc.md and write effort_estimates.md: for each must-have feature and carried bug, an estimate in person-weeks with a one-line breakdown and stated assumptions.
3. Write dependency_map.md: what blocks what (e.g. E2EE threat model before release; schema migration before sync).
4. Write risk_matrix.md: at least 5 risks with probability (H/M/L) x impact (H/M/L) and the resulting priority.
5. Write mitigations.md: concrete mitigation for each high-priority risk.
6. Write release_plan.md: 12-week schedule (weekly resolution) showing feature work, QA windows, the week-10 beta gate, and which items ship if the beta slips.
7. Include a cut-list: what is dropped first if effort estimates overrun by 30%.
8. Verify: every must-have feature and B-101 appears in the plan; QA hours fit within 60 per RC; note the verification in release_plan.md, then finish.""",
        "milestones": [
            {"artifact": "effort_estimates.md", "check": "exists"},
            {"artifact": "risk_matrix.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "release_plan.md", "check": "min_words", "params": {"min_words": 400}},
            {"artifact": "mitigations.md", "check": "exists"},
        ],
        "rubric": "rubrics/wf14.md",
    },
    {
        "id": "WF-15", "domain": "experiment-reproducibility-audit", "tier": 3,
        "fixtures": ["fixtures/experiment_description.md", "fixtures/raw_measurements.csv"],
        "steps": [
            "Create todo plan", "Read the paper description and raw data", "Plot/inspect each series (two-stage behavior check)",
            "Implement tangent-intersection onset finder (onset_finder.py)", "Compute t0 for all five series",
            "Fit Arrhenius ln(1/t0) vs 1/T, compute activation energy", "Compare with the claimed 152 kJ/mol",
            "Write audit_report.md (recomputed numbers, deviations)", "State verdict on reproducibility",
        ],
        "prompt": """Audit the reproducibility of an aging-kinetics paper. experiment_description.md describes the claimed procedure and result (activation energy 152 kJ/mol). raw_measurements.csv contains the underlying resistivity series for five temperatures. Auxiliary expectations are stated in the description.

Required steps (plan at least 10):
1. Plan with todo(action=create).
2. Read both files; write data_inventory.md: series per temperature, time range, sampling interval.
3. Write a quick visual/numeric check (values.py) that shows whether each series has the described slight decrease then rise; record the minimum-resistivity time per series in data_inventory.md.
4. Implement onset_finder.py: tangent-intersection onset time t0 for a given series (fit two lines: pre-minimum and post-minimum segments; intersect). Document the method in the file.
5. Compute t0 for all five series; write onsets.csv (temperature, t0_min).
6. Implement arrhenius_fit.py: fit ln(1/t0) = ln(A) - Ea/R * (1/T) using least squares; output Ea in kJ/mol and R^2; run it on onsets.csv.
7. Write audit_report.md: recomputed Ea vs claimed 152 kJ/mol, per-question answers to the four audit questions in the description, and a verdict (reproduced / partially reproduced / not reproduced) with justification.
8. Include the fitted plot as fig_arrhenius.png (labeled axes).
9. Verify all artifacts exist and numbers in audit_report.md match script outputs, then finish.""",
        "milestones": [
            {"artifact": "data_inventory.md", "check": "exists"},
            {"artifact": "onsets.csv", "check": "exists"},
        ],
        "final": [
            {"artifact": "audit_report.md", "check": "min_words", "params": {"min_words": 300}},
            {"artifact": "fig_arrhenius.png", "check": "file_min_bytes", "params": {"min_bytes": 15000}},
            {"artifact": "arrhenius_fit.py", "check": "python_compiles"},
        ],
        "rubric": "rubrics/wf15.md",
        "notes": "Planted property: raw data does NOT reproduce a clean 152 kJ/mol (onset ordering vs temperature is non-monotonic by design). The audit must detect and report the deviation — agents that 'confirm' the claim without recomputing fail the judge.",
    },
]


def main():
    os.makedirs(OUT, exist_ok=True)
    count = 0
    for t in TASKS:
        doc = {
            "id": t["id"],
            "domain": t["domain"],
            "version": "1.0",
            "fixtures": t["fixtures"],
            "prompt": COMMON.format(nsteps=len(t["steps"])) + "\n\n" + t["prompt"],
            "required_plan_steps_min": len(t["steps"]),
            "plan_steps": t["steps"],
            "milestones": t["milestones"],
            "final_artifacts": t["final"],
            "judge_rubric": t.get("rubric"),
            "max_wall_minutes": 60,
            "notes": t.get("notes", ""),
            "extra_judge_note": t.get("extra_judge_note", ""),
        }
        tier = {1: "tier1_retrieval", 2: "tier2_synthesis", 3: "tier3_workflow"}[t["tier"]]
        path = os.path.join(OUT, tier, t["id"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        count += 1
        print(f"wrote {t['id']} ({t['domain']}, {len(t['steps'])} steps)")
    print(f"total: {count} tasks")


if __name__ == "__main__":
    main()
