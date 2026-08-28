#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate per-task judge rubric files for LRAB."""
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rubrics")
os.makedirs(BASE, exist_ok=True)

RUBRICS = {
"WF-01": """Grade the literature review (review_report.md + data_table.md + shortlist.md):
- Selection completeness: all aging-related papers from papers_db.jsonl selected? (papers S001-S005, S007, S008, S012 relate to aging; at least 6 expected)
- data_table.md: values traceable to the fixture (no invented numbers)?
- review_report.md: Abstract/Comparison/Mechanisms/Open questions sections present? 300+ words? [Sn] citations consistent with references.md?
- Professional tone and structure.""",
"WF-02": """Grade the review-revision loop:
- review_round1.md: at least 4 issues found, each with location/severity/fix? The planted problems are: (1) text says 1080 MPa at 550C but Table 1 says 1105 (data inconsistency); (2) citation [5] missing from reference list; (3) Figure 1 referenced but absent/unlabeled; (4) 'prove' overclaim in abstract+conclusion. Bonus: 4h vs 6h schedule ambiguity.
- revised_paper.md: all issues actually fixed?
- change_log.md: one line per issue, mapping real.""",
"WF-03": """Grade the feature implementation:
- cmd_export implemented with CSV output (project,start,end,hours,note), hours rounded to 2dp?
- --since filter by start date works?
- test_export.py has >=4 meaningful pytest tests (normal, filter, empty header-only, running-timer excluded)?
- EXPORT.md shows a real command + real output?
- timetrack.py still compiles and existing commands unbroken?""",
"WF-04": """Grade the bug fixes (inventory.py):
- BUG-1 add_item duplicate SKU now raises ValueError?
- BUG-2 remove_item to zero deletes SKU; negative now raises ValueError?
- BUG-3 total_value = qty * price summed?
- BUG-4 search case-insensitive?
- test_inventory.py untouched? All 6 tests pass (run pytest to verify)?
- fix_summary.md documents each change?""",
"WF-05": """Grade the cleaning pipeline:
- clean_data.py rules: exact dupes dropped, status!=ok dropped, temp outside [-30,60] dropped, missing fields dropped?
- clean_data.csv consistent with rules (spot-check)?
- validation_report.md numbers add up (in = dropped + out)?
- sensor_summary.csv stats match clean data (spot-check one sensor)?""",
"WF-06": """Grade the analysis:
- analysis.py runs and produces both figures with labeled axes/units?
- analysis.md 280+ words, >=3 concrete numbers from the data, trend + trade-off + 620C anomaly discussed?
- anomalies.md identifies the 620C UTS uptick (1040->1063) as anomalous vs monotone alpha-fraction trend?
- Figures non-trivial (real plots)?""",
"WF-07": """Grade the web research:
- criteria.md: >=5 criteria with weights summing to 100?
- >=5 distinct candidates with URLs? 3 shortlisted with reasons?
- comparison_matrix.md filled with sourced facts (not vague)?
- recommendation.md 220+ words, scored decision, trade-offs, every claim has URL?
- sources.md >=5 unique URLs?""",
"WF-08": """Grade the API implementation:
- openapi.yaml valid OpenAPI 3.1 covering POST /v2/readings, GET /v2/readings, GET /v2/stats with schemas?
- app.py implements validation: range checks, in-batch duplicate detection, X-Batch-Id idempotency, partial-batch accept+report?
- examples.md has real request/response per endpoint including a rejection case?
- Rate limit 429+Retry-After present (code or demo)?""",
"WF-09": """Grade the optimization:
- hotspots.md correctly identifies the 4 slow patterns (per-char concat, re-scan loop, per-term rescan, list membership)?
- optimized.py preserves signatures and outputs (equivalence check documented)?
- speedup_report.md: baseline time, optimized time, speedup factor, equivalence assertion result?
- Speedup should be substantial (>10x on the large corpus expected)?""",
"WF-10": """Grade the user manual:
- user_manual.md covers start/stop/report with syntax tables?
- At least 2 real captured outputs (commands actually ran)?
- Data storage section correct (~/.timetrack/entries.json, JSON format)?
- Troubleshooting covers already-running and empty-report cases?
- >=3 source-derived tips?""",
"WF-11": """Grade the competitive analysis:
- criteria.md: 6 weighted criteria summing to 100, derived from the group's constraints (offline, compliance, mixed OS)?
- scoring.md: 1-5 scores with per-criterion justification?
- comparison_matrix.md weighted totals compute correctly?
- recommendation justified with trade-offs; risk_factors.md >=3 risks with mitigations?""",
"WF-12": """Grade the curriculum:
- course_overview: audience/prereqs/5 measurable outcomes?
- week_by_week: 8 weeks each with topic, bullets, lab goal, outcome mapping (local LLM + agent + materials use cases)?
- lecture outlines for weeks 1-2, >=10 slides each?
- labs/lab1.md: 2h build-a-tool-calling-agent lab with starter sketch and deliverable?
- exam_blueprint maps questions to outcomes/Bloom? Resources >=5?""",
"WF-13": """Grade the privacy audit:
- pii_inventory.md: email/name/card/cvv/ssn all inventoried with storage/log/transfer locations?
- audit_report.md >=6 findings each with code location + GDPR/PCI mapping + severity + quoted evidence?
- payment_processor_fixed.py: no plaintext card/cvv/ssn storage, no secret logging, HTTPS only, export controls, proper deletion?
- remediation verified per finding; residual_risks.md >=3 items?""",
"WF-14": """Grade the release plan:
- effort_estimates.md: per-feature person-week estimates with assumptions?
- dependency_map.md: E2EE threat model before release, schema migration before sync, B-101 fixed before beta?
- risk_matrix.md >=5 risks with P x I and priority; mitigations concrete?
- release_plan.md: 12 weeks weekly, week-10 beta gate, QA hours within 60/RC, cut-list for 30% overrun?""",
"WF-15": """Grade the reproducibility audit:
- data_inventory.md: 5 series, ranges, intervals correct?
- onset_finder.py implements tangent-intersection; onsets.csv has 5 t0 values?
- arrhenius_fit.py computes Ea and R^2; fig_arrhenius.png real?
- audit_report.md answers all 4 audit questions; KEY: detects that raw data does NOT cleanly reproduce 152 kJ/mol (onset ordering non-monotonic with temperature) and reports the deviation honestly. An agent that blindly 'confirms' the claim fails this rubric.""",
}

for tid, text in RUBRICS.items():
    with open(os.path.join(BASE, tid + ".md"), "w", encoding="utf-8") as f:
        f.write(f"# Judge rubric — {tid}\n\n" + text + "\n")
print(f"wrote {len(RUBRICS)} rubrics -> {BASE}")
