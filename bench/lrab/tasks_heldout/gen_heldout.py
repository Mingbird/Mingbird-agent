#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Held-out LRAB task generator (review item M8/P2).

Produces 18 task JSONs that were NEVER instantiated during development:
same tier structure (2/4/9/3), same check-kind vocabulary, same fixtures,
different task surface (different questions, artifact names, thresholds and
ground truth).

Honest provenance note (do not paper over this):
  * ../gen_tasks.py is a hardcoded authoring file: a static TASKS list with no
    seed and no CLI. Re-running it can only reproduce the existing 15 WF
    tasks byte for byte. It cannot emit novel tasks.
  * ../gen_lhab.py IS seeded, but it regenerates the tier-4 fixtures into the
    shared ../fixtures/ directory and embeds the freshly drawn numbers into
    the checks. Re-running it with a new seed would overwrite the deployed
    fixtures the frozen dev set depends on, so it cannot be reused as-is.
  * This generator therefore takes the only faithful route: it RESAMPLES the
    task surface (topic angle, artifact naming, thresholds, wording, check
    composition) around each existing archetype with a seeded RNG, and it
    RECOMPUTES all numeric ground truth from the FROZEN fixtures on disk.
    Nothing in ../fixtures or ../tasks is read-modified-written; all output
    lands under tasks_heldout/.

Deterministic: python gen_heldout.py --seed 20260921
"""
import argparse
import csv
import json
import math
import os
import random
import statistics
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
LRAB = os.path.dirname(HERE)
FIX = os.path.join(LRAB, "fixtures")
OUT = HERE

# Check kinds understood by ../scoring/score_task.py (verified against source).
ALLOWED_KINDS = {
    "exists", "contains_any", "contains_groups", "contains_ordered",
    "not_contains", "min_words", "structure", "python_compiles",
    "spec_pytest", "script_pass", "file_min_bytes", "min_urls",
    "seed_unchanged", "image_valid",
}

TIER_DIR = {1: "tier1_retrieval", 2: "tier2_synthesis",
            3: "tier3_workflow", 4: "tier4_longhorizon"}


# --------------------------------------------------------------------------
# numeric ground-truth helpers (gen_lhab.py-style format variants, made
# robust against both rounding and truncation at 1/0 decimals)
# --------------------------------------------------------------------------
def num_variants(x, nd=1):
    v = set()
    for d in (nd, 0):
        v.add(f"{round(float(x), d):.{d}f}")
        tr = math.floor(abs(float(x)) * 10 ** d) / 10 ** d
        v.add(("{:." + str(d) + "f}").format(tr))
    v.add(f"{float(x):.2f}")
    if float(x) == int(float(x)):
        v.add(str(int(float(x))))
    return sorted(v)


def count_variants(c):
    return [str(c), f"{c:,}"]


# --------------------------------------------------------------------------
# Ground truth recomputed from the FROZEN fixtures (never regenerated)
# --------------------------------------------------------------------------
def truth_papers():
    """WF-01 fixture: recent (2022+) titanium-alloy papers."""
    recs = [json.loads(l) for l in open(os.path.join(FIX, "papers_db.jsonl"), encoding="utf-8")]
    recent = [r["id"] for r in recs if r["year"] >= 2022]
    alloys = sorted({r["alloy"] for r in recs if r["year"] >= 2022})
    return {"recent_ids": recent, "recent_alloys": alloys, "n_total": len(recs)}


def truth_sensor():
    """WF-05 fixture: quarantine-style cleaning ground truth."""
    rows = list(csv.DictReader(open(os.path.join(FIX, "messy_sensor_data.csv"), encoding="utf-8")))
    seen, keep = set(), []
    for r in rows:
        key = tuple(r.items())
        if key in seen:
            continue
        seen.add(key)
        if r["status"] != "ok":
            continue
        if any(r[k] == "" for k in ("temperature_C", "humidity_pct", "pressure_hPa")):
            continue
        t = float(r["temperature_C"])
        if t < -30 or t > 60:
            continue
        keep.append(r)
    return {"rows_in": len(rows), "rows_out": len(keep),
            "rejected": len(rows) - len(keep),
            "sensors": sorted({r["sensor_id"] for r in keep}),
            "bad_temps": ["9999", "-40"]}


def truth_aging():
    """WF-06 fixture: hardness/alpha-fraction angle."""
    rows = list(csv.DictReader(open(os.path.join(FIX, "aging_data.csv"), encoding="utf-8")))
    hv = [float(r["hardness_HV"]) for r in rows]
    peak = max(rows, key=lambda r: float(r["hardness_HV"]))
    anom = next(r for r in rows if r["aging_temperature_C"] == "620" and r["aging_time_h"] == "4")
    return {"hv_max": float(peak["hardness_HV"]),
            "hv_max_cond": f'{peak["aging_temperature_C"]}C/{peak["aging_time_h"]}h',
            "anom_uts_620_4h": float(anom["UTS_MPa"]),
            "uts_600_4h": float(next(r for r in rows if r["aging_temperature_C"] == "600"
                                     and r["aging_time_h"] == "4")["UTS_MPa"]),
            "n": len(rows)}


def truth_corpus():
    """LH-02 fixture: long-word index + energy lines + per-topic counts."""
    lines = open(os.path.join(FIX, "process_corpus.txt"), encoding="utf-8").read().splitlines()
    wc, topics, energy = Counter(), Counter(), 0
    for ln in lines:
        topics[ln.split("]")[0][1:]] += 1
        body = ln.split("] ", 1)[1].rsplit(" ref", 1)[0]
        ws = body.split()
        wc.update(ws)
        if "energy" in ws:
            energy += 1
    long8 = [(w, c) for w, c in wc.most_common(80) if len(w) >= 6][:8]
    return {"total_lines": len(lines),
            "distinct_lines": len(set(lines)),
            "duplicates": len(lines) - len(set(lines)),
            "energy_lines": energy, "long8": long8, "topics": dict(topics)}


def truth_multibatch():
    """LH-01 fixture: per-batch MEAN UTS + spread ground truth."""
    rows = list(csv.DictReader(open(os.path.join(FIX, "alloy_multibatch.csv"), encoding="utf-8")))
    by = Counter()
    uts = {}
    for r in rows:
        uts.setdefault(r["batch_id"], []).append(float(r["UTS_MPa"]))
    means = {b: statistics.mean(v) for b, v in uts.items()}
    spread = {b: round(max(v) - min(v), 1) for b, v in uts.items()}
    widest = max(spread, key=lambda b: spread[b])
    return {"batches": sorted(uts), "means": means, "spread": spread,
            "widest_batch": widest, "widest_spread": spread[widest],
            "n_rows": len(rows)}


def truth_onset():
    """WF-15 fixture: offset-threshold onset method (for the judge rubric)."""
    rows = list(csv.DictReader(open(os.path.join(FIX, "raw_measurements.csv"), encoding="utf-8")))
    temps = [500, 520, 540, 560, 580]
    delta = 1.0  # uOhm*cm above the series minimum
    t0s = {}
    for t in temps:
        s = [(float(r["t_min"]), float(r[f"R_{t}C"])) for r in rows]
        rmin = min(v for _, v in s)
        tmin = min(tt for tt, v in s if v == rmin)
        t0s[t] = next(tt for tt, v in s if tt > tmin and v >= rmin + delta)
    xs = [1.0 / (t + 273.15) for t in temps]
    ys = [math.log(1.0 / t0s[t]) for t in temps]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    ea = -slope * 8.314e-3
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    return {"delta": delta, "t0_min": t0s, "Ea_kJ_mol": round(ea, 1),
            "R2": round(1 - ss_res / ss_tot, 3)}


# --------------------------------------------------------------------------
# Reworded protocol headers (same contract as the originals, new wording)
# --------------------------------------------------------------------------
HEADERS = [
    ("You are an autonomous agent operating inside the current working directory. "
     "BEFORE anything else, write out a numbered plan that covers every step listed "
     "below (no fewer than {nsteps} steps). Use the planning/todo tool you have; if "
     "you have none, put the plan into plan.md. Then carry out the steps in order, "
     "writing every required file under the exact filename stated. Never invent "
     "content: every statement must be traceable to the fixture files shipped in "
     "this directory. Once every artifact exists and has been checked, wrap up with "
     "a brief completion summary."),
    ("You are working as an autonomous agent in this directory. Your first action "
     "is to produce a numbered plan spanning all of the steps below (minimum "
     "{nsteps} steps); use a todo/planning tool when available, otherwise save it "
     "as plan.md. Afterwards work through the steps sequentially and create each "
     "required file with precisely the filename given. Do not fabricate anything: "
     "ground every claim in the fixture files provided here. When everything is "
     "written and verified, close with a short summary of what was produced."),
]

LH_HEADERS = [
    ("You are an autonomous agent operating inside the current working directory. "
     "BEFORE anything else, write out a numbered plan that covers every step listed "
     "below. Use the planning/todo tool you have; if you have none, put the plan "
     "into plan.md. Then carry out the steps in order, writing every required file "
     "under the exact filename stated. This is a long task: push through ALL steps "
     "and do not stop early. Never fabricate content: every number you report must "
     "come from computation on the provided fixture files. When every artifact "
     "exists and has been verified, close with a brief summary."),
]


def fmt_steps(steps):
    return "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))


def floor(rng, base, lo=0.85, hi=1.15, grain=10):
    """Resample a word-count floor within +/-15% of the archetype value."""
    return int(round(base * rng.uniform(lo, hi) / grain) * grain)


# ==========================================================================
# Tier 1 variants
# ==========================================================================
def h01(rng, T):
    ids = T["papers"]["recent_ids"]
    probe = rng.sample(ids, 4)
    steps = [
        "Write the numbered plan", f"Screen papers_db.jsonl for year >= 2022 ({len(ids)} expected)",
        "Record the screening decisions in screening_log.md",
        "Build property_matrix.md from values actually present in the fixture",
        "Hunt for contradicting trends between recent papers -> gap_analysis.md",
        "Draft recent_review.md with inline [Sn] markers",
        "Write citation_index.md resolving every marker",
        "Final existence check of all five artifacts",
    ]
    prompt = (
        f"Act as a literature scout for a titanium-alloy group. The file "
        f"papers_db.jsonl in this directory holds {T['papers']['n_total']} records. "
        f"Build a map of the RECENT literature only: every paper published in 2022 or later.\n\n"
        f"Deliverables and required order (the plan must list at least {len(steps)} steps):\n"
        f"1. Produce your plan first.\n"
        f"2. Read papers_db.jsonl and select every record with year >= 2022; there are "
        f"{len(ids)} of them and every one must appear in screening_log.md as: id, title, "
        f"first author, year, DOI.\n"
        f"3. Write property_matrix.md: one row per selected paper with the alloy studied and "
        f"whatever quantitative properties the record carries (UTS, elongation, temperatures...). "
        f"Cells must quote the fixture verbatim; use 'n/a' when a record carries no value.\n"
        f"4. In gap_analysis.md, describe at least two points where the recent records disagree "
        f"in trend or scope, quoting the record ids that clash.\n"
        f"5. Write recent_review.md (target {floor(rng, 420)} words or more) with the sections "
        f"Trends, Methods landscape, Gaps, References.\n"
        f"6. Cite records inline as [Sxxx]; a marker may only be used if that id exists in "
        f"papers_db.jsonl.\n"
        f"7. Write citation_index.md mapping each marker used to its full citation line.\n"
        f"8. Confirm all five files exist, then finish.")
    doc = {
        "id": "HWF-01", "domain": "materials-recent-literature-map", "tier": 1,
        "fixtures": ["fixtures/papers_db.jsonl"],
        "milestones": [
            {"artifact": "screening_log.md", "check": "contains_any", "params": {"any_of": probe}},
            {"artifact": "property_matrix.md", "check": "contains_any",
             "params": {"any_of": T["papers"]["recent_alloys"][:4]}},
        ],
        "final": [
            {"artifact": "recent_review.md", "check": "structure",
             "params": {"required_sections": ["Trends", "References"], "min_words": 340}},
            {"artifact": "citation_index.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = (f"# Judge rubric — HWF-01 (recent-literature map variant)\n\n"
           f"Deterministic checks cover the screening log and matrix. Grade the rest 0-10:\n\n"
           f"1. Completeness (0-4): all {len(ids)} recent ids ({', '.join(ids)}) appear in "
           f"screening_log.md with the five required fields.\n"
           f"2. Matrix fidelity (0-2): property_matrix.md quotes only values present in the "
           f"fixture records; invented numbers score 0.\n"
           f"3. Gap analysis (0-2): at least two genuine disagreements between recent records, "
           f"each tied to concrete ids.\n"
           f"4. Review quality (0-2): Trends/Methods/Gaps sections are grounded and every "
           f"[Sxxx] marker resolves in citation_index.md.\n\n"
           f"Deduction (up to -2): citations of ids that do not exist in the fixture.\n")
    return doc, rub


def h02(rng, T):
    steps = [
        "Write the numbered plan", "Read draft_paper.md end to end against its Table 1",
        "Register every defect in issues_register.md",
        "Cross-check each prose number against Table 1 in evidence_table.md",
        "Rewrite only the Abstract and Conclusions (revised_abstract.md, revised_conclusions.md)",
        "Write verification_checklist.md", "Re-verify the two rewritten sections", "Final artifact check",
    ]
    prompt = (
        "You are a data-integrity auditor, then an editor. The manuscript draft_paper.md in "
        "this directory ships with several planted defects: at least one number in the running "
        "text that contradicts Table 1, an overclaiming statement, a method/table schedule "
        "mismatch, and a reference to a figure that was never supplied.\n\n"
        f"Required order of work (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read draft_paper.md and cross-check every numeric claim in the Abstract, Sections "
        "3.1/3.2 and the Conclusions against Table 1.\n"
        "3. Write issues_register.md: one numbered entry per defect with (a) location, "
        "(b) quoted evidence, (c) severity high/medium/low, (d) proposed correction. At least "
        "4 entries are expected.\n"
        "4. Write evidence_table.md: claim-as-written | table value | verdict (match/mismatch).\n"
        "5. Write revised_abstract.md and revised_conclusions.md — ONLY those two sections, "
        "rewritten so that every number agrees with Table 1, the overclaim is softened "
        "('suggests' rather than 'prove'), and no unsourced universal claim survives.\n"
        "6. Write verification_checklist.md: line-by-line confirmation that each registered "
        "issue is resolved by the rewrites.\n"
        "7. Confirm the four new files exist and quote no value absent from Table 1, then finish.")
    doc = {
        "id": "HWF-02", "domain": "manuscript-integrity-audit", "tier": 1,
        "fixtures": ["fixtures/draft_paper.md"],
        "milestones": [
            {"artifact": "issues_register.md", "check": "contains_any",
             "params": {"any_of": ["1105", "1080", "6 h"]}},
            {"artifact": "evidence_table.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "revised_conclusions.md", "check": "not_contains",
             "params": {"none_of": ["prove", "all Ti-6Al-4V product forms", "4 h or 6 h"]}},
            {"artifact": "verification_checklist.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-02 (integrity-audit variant)\n\n"
           "Deterministic checks cover the register and the cleaned conclusions. Grade 0-10:\n\n"
           "1. Defect coverage (0-4): the register catches the 1080-vs-1105 contradiction "
           "(Table 1 says 1105 at 550C/4h), the 'prove'/'all product forms' overclaims, the "
           "'4 h or 6 h' vs 8 h rows schedule mismatch, and the phantom Figure 1.\n"
           "2. Evidence table (0-2): every prose number is paired with its Table 1 value and "
           "a verdict.\n"
           "3. Rewrite fidelity (0-2): revised sections preserve the science, fix only the "
           "defects, and introduce no new unsourced claims.\n"
           "4. Checklist (0-2): maps each issue number to its resolution.\n\n"
           "Deduction (up to -2): rewrites that delete inconvenient data instead of correcting "
           "the prose.\n")
    return doc, rub


# ==========================================================================
# Tier 2 variants
# ==========================================================================
def h03(rng, T):
    steps = [
        "Write the numbered plan", "Study timetrack.py storage and dispatch pattern",
        "Specify the new day command in design_day.md", "Implement cmd_day and register it",
        "Write test_day.py (>=4 pytest cases)", "Run the suite until green",
        "Capture a real session in usage_day.md", "Compile check and final verification",
    ]
    prompt = (
        "Extend the CLI program timetrack.py (found in this directory) with a per-day report.\n\n"
        "Feature: `timetrack day --date YYYY-MM-DD [--project NAME]` prints, for the given "
        "calendar day, the finished-entry hours grouped by project plus a grand total line; "
        "with --project it filters to one project. Days with no finished entries print "
        "'no entries' and exit 0. The running timer is never counted.\n\n"
        f"Steps (plan at least {len(steps)}):\n"
        "1. Produce your plan.\n"
        "2. Read timetrack.py: note the entries.json format, the start/stop/report dispatch "
        "table, and how report skips running timers.\n"
        "3. Write design_day.md: output format, date filtering rule, empty-day behaviour, "
        "interaction with --project.\n"
        "4. Implement cmd_day in timetrack.py and register the subcommand.\n"
        "5. Write test_day.py with at least 4 pytest tests: multi-project day, --project "
        "filter, empty day, running timer excluded.\n"
        "6. Run python -m pytest test_day.py -q and fix until green; then run any other test "
        "files present to confirm no regression.\n"
        "7. Write usage_day.md showing one real command and its real output (capture an "
        "actual session; do not type expected output by hand).\n"
        "8. Verify python -m py_compile timetrack.py passes and all files exist, then finish.")
    doc = {
        "id": "HWF-03", "domain": "cli-feature-per-day-report", "tier": 2,
        "fixtures": ["fixtures/app_source/timetrack.py"],
        "milestones": [
            {"artifact": "design_day.md", "check": "exists"},
            {"artifact": "test_day.py", "check": "exists"},
        ],
        "final": [
            {"artifact": "timetrack.py", "check": "contains_any",
             "params": {"any_of": ["cmd_day", "day"]}},
            {"artifact": "usage_day.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-03 (day-report feature variant)\n\n"
           "Deterministic checks cover design/test docs and the wired command. Grade 0-10:\n\n"
           "1. Implementation (0-4): cmd_day filters entries by calendar day, excludes the "
           "running timer, honours --project, prints a correct grand total.\n"
           "2. Tests (0-3): >=4 meaningful pytest cases that would fail on a wrong "
           "implementation, all green.\n"
           "3. Docs (0-2): usage_day.md shows a genuinely captured session.\n"
           "4. Integration (0-1): argparse registration matches the existing style; no "
           "regression in start/stop/report.\n\n"
           "Deduction (up to -2): tests that assert nothing (tautologies).\n")
    return doc, rub


def h04(rng, T):
    steps = [
        "Write the numbered plan", "Run the failing suite and capture the baseline",
        "Analyse each failure in failure_analysis.md",
        "Write repro_tests.py reproducing every symptom BEFORE fixing",
        "Fix inventory.py without touching test_inventory.py",
        "Re-run pytest until 6/6 green", "Record the diff rationale in regression_notes.md",
        "Final compile + suite verification",
    ]
    prompt = (
        "The two-file project in this directory (inventory.py, test_inventory.py) fails its "
        "tests. test_inventory.py is the immutable specification.\n\n"
        f"Work order (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Copy inventory.py and test_inventory.py into the working directory if they are "
        "not already here; run python -m pytest test_inventory.py -q and paste the failing "
        "output into failure_analysis.md.\n"
        "3. In failure_analysis.md give one section per bug: failing test, root cause in the "
        "source, planned repair. Four distinct bugs are planted.\n"
        "4. BEFORE changing inventory.py, write repro_tests.py: small direct pytest cases "
        "(one per bug) that each demonstrate the faulty behaviour. Run it and attach the "
        "output to failure_analysis.md.\n"
        "5. Repair inventory.py. Public signatures must not change; test_inventory.py must "
        "not be edited.\n"
        "6. Re-run both suites until everything is green.\n"
        "7. Write regression_notes.md: per bug one line describing the actual code change, "
        "plus the tail of the final pytest run.\n"
        "8. Verify python -m py_compile inventory.py and finish.")
    doc = {
        "id": "HWF-04", "domain": "characterization-first-debugging", "tier": 2,
        "fixtures": ["fixtures/buggy_project/inventory.py", "fixtures/buggy_project/test_inventory.py"],
        "milestones": [
            {"artifact": "failure_analysis.md", "check": "exists"},
            {"artifact": "repro_tests.py", "check": "exists"},
        ],
        "final": [
            {"artifact": "inventory.py", "check": "spec_pytest",
             "params": {"seed_rel": "fixtures/buggy_project/test_inventory.py",
                        "command": "python -m pytest test_inventory.py -q",
                        "expect_stdout": "6 passed", "timeout_s": 180}},
            {"artifact": "regression_notes.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-04 (characterization-first variant)\n\n"
           "The spec_pytest gate enforces: test_inventory.py byte-identical to the seed and "
           "6/6 green. Grade the rest 0-10:\n\n"
           "1. Root causes (0-4): overwrite-instead-of-raise on duplicate SKU; ghost "
           "zero-quantity entries and negative stock; total_value ignoring qty; "
           "case-sensitive search.\n"
           "2. Characterization (0-3): repro_tests.py really reproduces each symptom and "
           "was demonstrably written before the fix (captured failing output counts).\n"
           "3. Notes (0-2): regression_notes.md ties each change to its bug.\n"
           "4. Hygiene (0-1): signatures unchanged, no test edits.\n\n"
           "Deduction (up to -2): 'fixes' that special-case the exact test inputs.\n")
    return doc, rub


def h05(rng, T):
    s = T["sensor"]
    steps = [
        "Write the numbered plan", "Inventory the raw file and count every defect class",
        "Write scrub.py (clean + quarantine with reasons)",
        "Produce tidy_data.csv (survivors only) and rejected.csv (one line per drop)",
        "Write sensor_rollup.csv from the CLEAN rows only",
        "Write validation_ledger.md with rows-in/dropped/out arithmetic",
        "Re-scan tidy_data.csv for residual defects", "Final verification",
    ]
    prompt = (
        f"Scrub the environmental log messy_sensor_data.csv in this directory — but unlike a "
        f"silent drop, every removed row must be accounted for.\n\n"
        f"Known defect classes: an impossible sentinel temperature, one physically "
        f"unreasonable value, a row with a missing field, status='error' rows, and an exact "
        f"duplicate row.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Write profile_notes.md: total rows, sensors present, and the count of each defect "
        "class you actually observe (inspect, do not guess).\n"
        "3. Write scrub.py implementing: drop exact duplicates; drop status != ok; treat "
        "temperature outside [-30, 60] as invalid; drop rows with any empty field. Every drop "
        "must append a line to rejected.csv carrying the original row plus a reason column.\n"
        "4. Run it: tidy_data.csv keeps the same header and only surviving rows; rejected.csv "
        "holds every dropped row with its reason.\n"
        "5. Produce sensor_rollup.csv (sensor_id, n_readings, mean_temp, min_temp, max_temp, "
        "all rounded to 2 decimals) computed from tidy_data.csv only.\n"
        "6. Write validation_ledger.md: rows in, dropped per rule, rows out — the arithmetic "
        "must balance; note the re-scan showing tidy_data.csv is free of every defect class.\n"
        "7. Verify all artifacts and finish.")
    doc = {
        "id": "HWF-05", "domain": "quarantine-cleaning-pipeline", "tier": 2,
        "fixtures": ["fixtures/messy_sensor_data.csv"],
        "milestones": [
            {"artifact": "profile_notes.md", "check": "exists"},
            {"artifact": "scrub.py", "check": "python_compiles"},
        ],
        "final": [
            {"artifact": "tidy_data.csv", "check": "exists"},
            {"artifact": "rejected.csv", "check": "contains_any",
             "params": {"any_of": s["bad_temps"]}},
            {"artifact": "sensor_rollup.csv", "check": "contains_any",
             "params": {"any_of": s["sensors"]}},
            {"artifact": "validation_ledger.md", "check": "min_words",
             "params": {"min_words": floor(rng, 100)}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = (f"# Judge rubric — HWF-05 (quarantine variant)\n\n"
           f"Ground truth: {s['rows_in']} raw rows -> {s['rows_out']} clean, "
           f"{s['rejected']} rejected (sentinel 9999, -40.0, one missing humidity, one "
           f"error row, one exact duplicate). Grade 0-10:\n\n"
           "1. Ledger arithmetic (0-4): rows-in = sum of per-rule drops + rows-out, exactly.\n"
           "2. Quarantine completeness (0-3): rejected.csv accounts for every dropped row "
           "with a correct reason; nothing vanishes silently.\n"
           "3. Rollup (0-2): stats computed from the clean rows only, correctly rounded.\n"
           "4. Re-scan (0-1): an actual second pass proving the tidy file is clean.\n\n"
           "Deduction (up to -2): counts that cannot be reproduced from the fixture.\n")
    return doc, rub


def h06(rng, T):
    a = T["aging"]
    steps = [
        "Write the numbered plan", "Read aging_data.csv and profile the hardness column",
        "Write stats_hardness.md (count/mean/min/max for hardness and alpha fraction)",
        f"Flag the non-monotonic UTS point in anomaly_watch.md",
        "Write plot_hardness.py producing fig_hardness.png and fig_ductility.png",
        "Run it and confirm both PNGs are non-trivial",
        "Write findings.md around numbers pulled from the data",
        "Final artifact verification",
    ]
    prompt = (
        "The file aging_data.csv in this directory is a Ti-6Al-4V aging matrix "
        "(temperature, time, UTS, elongation, hardness, alpha fraction, heat id). Study it "
        "from the hardness and microstructure side, not the tensile side.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Write stats_hardness.md: count/mean/min/max for hardness_HV and "
        "alpha_fraction_pct, plus the condition that maximizes hardness.\n"
        "3. While doing so, check UTS against temperature: one 4 h condition breaks the "
        "otherwise clean rise-then-fall pattern. Name it and quantify the deviation in "
        "anomaly_watch.md.\n"
        "4. Write plot_hardness.py: load the CSV; plot hardness vs aging temperature "
        "(fig_hardness.png) and elongation vs alpha fraction (fig_ductility.png); label axes "
        "with units and title both figures; print the hardness-peak condition to stdout.\n"
        "5. Run the script; both PNGs must exist and exceed 20KB.\n"
        f"6. Write findings.md ({floor(rng, 320)}+ words): the hardness trend, the "
        "elongation/alpha-fraction relationship, the anomalous UTS point and what could "
        "explain it, and one processing recommendation. At least 3 concrete numbers from the "
        "data must appear.\n"
        "7. List every artifact with its size, then finish.")
    doc = {
        "id": "HWF-06", "domain": "hardness-microstructure-analysis", "tier": 2,
        "fixtures": ["fixtures/aging_data.csv"],
        "milestones": [
            {"artifact": "stats_hardness.md", "check": "exists"},
            {"artifact": "anomaly_watch.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "fig_hardness.png", "check": "image_valid",
             "params": {"min_width": 200, "min_height": 100}},
            {"artifact": "fig_ductility.png", "check": "image_valid",
             "params": {"min_width": 200, "min_height": 100}},
            {"artifact": "plot_hardness.py", "check": "python_compiles"},
            {"artifact": "findings.md", "check": "contains_any",
             "params": {"any_of": [str(int(a["hv_max"])), f"{a['anom_uts_620_4h']:.0f}"]}},
            {"artifact": "findings.md", "check": "min_words",
             "params": {"min_words": floor(rng, 280)}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = (f"# Judge rubric — HWF-06 (hardness variant)\n\n"
           f"Ground truth: hardness peaks at {a['hv_max']:.0f} HV for {a['hv_max_cond']}; "
           f"the UTS anomaly is 620C/4h ({a['anom_uts_620_4h']:.0f} MPa, above the "
           f"{a['uts_600_4h']:.0f} MPa at 600C/4h, breaking monotonic decline). Grade 0-10:\n\n"
           "1. Statistics (0-3): correct count/mean/min/max for both columns.\n"
           "2. Anomaly (0-3): names 620C/4h, quantifies the break, discusses measurement "
           "error vs real effect.\n"
           "3. Figures (0-2): two labelled, unit-carrying plots of real data.\n"
           "4. Findings (0-2): >=3 correct numbers, honest recommendation.\n\n"
           "Deduction (up to -2): numbers not present in the fixture.\n")
    return doc, rub


# ==========================================================================
# Tier 3 variants
# ==========================================================================
def h07(rng, T):
    steps = [
        "Write the numbered plan", "Derive >=5 weighted criteria in needs.md",
        "Web-search >=5 candidates into landscape.md (URL each)",
        "Shortlist 3 with reasons", "Fetch primary pages for the shortlist",
        "Build matrix.md (criteria x candidates)", "Write verdict.md with trade-offs",
        "Collect all URLs in links.md", "Final verification",
    ]
    prompt = (
        "Research task (use your web_search / web_fetch or MCP search tools): a three-person "
        "research group wants a self-hosted, offline-tolerant markdown knowledge base with "
        "full-text search that must run comfortably on a single 4 GB RAM ARM board. Recommend "
        "one.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Write needs.md: at least 5 weighted criteria derived from the constraints above "
        "(resource ceiling, offline behaviour, search quality, packaging, backup/export), "
        "each with a justification line.\n"
        "3. Search the web and record at least 5 candidate projects in landscape.md, one "
        "line plus source URL each.\n"
        "4. Shortlist 3 in shortlist_notes.md with explicit keep/drop reasons.\n"
        "5. For each shortlisted candidate fetch its docs/GitHub page and extract: license, "
        "runtime, stated minimum RAM, search implementation, last release date.\n"
        "6. Write matrix.md: criteria rows, candidate columns, cells holding sourced facts.\n"
        f"7. Write verdict.md ({floor(rng, 260)}+ words): the scored decision, what the losers "
        "do better, and what fact would flip the recommendation. Every factual claim carries "
        "a URL.\n"
        "8. List every consulted URL in links.md (>=5 unique). Verify all files, then finish.")
    doc = {
        "id": "HWF-07", "domain": "web-research-knowledge-base-selection", "tier": 3,
        "fixtures": [],
        "milestones": [
            {"artifact": "needs.md", "check": "exists"},
            {"artifact": "landscape.md", "check": "min_urls", "params": {"min_urls": 5}},
        ],
        "final": [
            {"artifact": "matrix.md", "check": "exists"},
            {"artifact": "verdict.md", "check": "min_words",
             "params": {"min_words": floor(rng, 220)}},
            {"artifact": "links.md", "check": "min_urls", "params": {"min_urls": 5}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-07 (knowledge-base selection variant)\n\n"
           "Web-dependent: grade structure and internal consistency, not which project wins. "
           "0-10:\n\n"
           "1. Criteria (0-2): >=5, weighted, tied to the stated constraints.\n"
           "2. Sourcing (0-3): matrix cells carry URLs; no unsourced capability claims.\n"
           "3. Reasoning (0-3): verdict follows from the scores; flip-condition stated.\n"
           "4. Completeness (0-2): landscape/shortlist/matrix/links all present and "
           "cross-consistent.\n\n"
           "Deduction (up to -2): invented specs for candidates.\n")
    return doc, rub


def h08(rng, T):
    steps = [
        "Write the numbered plan", "Read api_requirements.md; extract the query-side contract",
        "Write design_query.md (pagination, windowing, aggregation rules)",
        "Write query_api.yaml covering the two GET operations",
        "Implement the mock with an in-memory store in app_query.py",
        "Exercise pagination + stats windows against a seeded store",
        "Capture the runs in demo.md", "Final verification",
    ]
    prompt = (
        "Implement the QUERY half of the SensorHub v2 API described in api_requirements.md "
        "(in this directory): the paginated GET /v2/readings and the hourly GET /v2/stats. "
        "The ingestion side already exists elsewhere; do not implement POST.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read api_requirements.md and write design_query.md: pagination defaults and "
        "limits, from/to filtering semantics, the 1h window bucketing rule for stats, and "
        "the RFC 7807 error shape for bad queries.\n"
        "3. Write query_api.yaml (OpenAPI 3.1) describing both GET operations with query "
        "parameters, response schemas and a Problem schema.\n"
        "4. Write app_query.py: a runnable Python mock (any framework, in-memory store, "
        "seeded with a few synthetic readings at startup) implementing both endpoints with "
        "the validation from your design notes.\n"
        "5. Seed the store with readings that span at least two hourly buckets and two "
        "sensors, then exercise: page 1 vs page 2, a from/to filter, and a stats window.\n"
        "6. Capture the real request/response pairs in demo.md — including one rejected "
        "query (e.g. from > to) with its problem+json body.\n"
        "7. Verify the server starts cleanly and all files exist, then finish.")
    doc = {
        "id": "HWF-08", "domain": "api-query-half-design-and-mock", "tier": 3,
        "fixtures": ["fixtures/api_requirements.md"],
        "milestones": [
            {"artifact": "design_query.md", "check": "exists"},
            {"artifact": "query_api.yaml", "check": "contains_any",
             "params": {"any_of": ["openapi: 3.1", "openapi: \"3.1\"", "/v2/stats"]}},
        ],
        "final": [
            {"artifact": "app_query.py", "check": "python_compiles"},
            {"artifact": "demo.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-08 (query-half variant)\n\n"
           "Grade 0-10:\n"
           "1. Spec fidelity (0-3): pagination limit/offset, sensor/from/to filters, hourly "
           "min/max/avg semantics exactly as the requirements state them.\n"
           "2. OpenAPI quality (0-3): 3.1 syntax that validates, complete parameter and "
           "schema definitions, Problem schema present.\n"
           "3. Mock correctness (0-2): seeded store demonstrably returns correct pages and "
           "aggregates.\n"
           "4. Demo (0-2): captured pairs including the rejection path.\n\n"
           "Deduction (up to -2): aggregation that averages averages, or pagination that "
           "repeats rows.\n")
    return doc, rub


def h09(rng, T):
    steps = [
        "Write the numbered plan", "Read legacy_slow_code.py and explain the four hot spots",
        "Write make_workload.py generating a deterministic corpus",
        "Capture reference outputs into baseline_outputs.json",
        "Profile with cProfile; save the top functions to profile_before.txt",
        "Write fast_impl.py with identical behaviour",
        "Benchmark both with bench.py; record numbers in bench_report.md",
        "Prove equivalence against baseline_outputs.json", "Final verification",
    ]
    prompt = (
        "Speed up legacy_slow_code.py (in this directory) while preserving its behaviour "
        "exactly. Deliver a benchmarked, equivalence-proved replacement.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read the module and write hotspot_notes.md: for each of the four documented hot "
        "spots, what it does and why it is slow.\n"
        "3. Write make_workload.py: build a deterministic corpus (>=40 .txt files, >=150 "
        "lines each, seeded pseudo-random English-like text) under workload/.\n"
        "4. Copy the original to reference_impl.py, run it on a reduced corpus and store its "
        "top_terms and dedupe_lines outputs in baseline_outputs.json.\n"
        "5. cProfile the original on the reduced corpus; save the top-15 lines to "
        "profile_before.txt.\n"
        "6. Write fast_impl.py exposing the same functions with the same signatures; use "
        "sound data structures (one-pass counting, sets for dedup...).\n"
        "7. Write bench.py timing both implementations on the SAME corpus (perf_counter, "
        "best of 3) and writing bench_report.md: baseline s, optimized s, speedup x.\n"
        "8. Equivalence: compare fast_impl outputs on the reduced corpus against "
        "baseline_outputs.json, assert equality, record the assertion outcome in "
        "bench_report.md. Then finish.")
    doc = {
        "id": "HWF-09", "domain": "benchmarked-refactor", "tier": 3,
        "fixtures": ["fixtures/legacy_slow_code.py"],
        "milestones": [
            {"artifact": "hotspot_notes.md", "check": "exists"},
            {"artifact": "baseline_outputs.json", "check": "exists"},
        ],
        "final": [
            {"artifact": "fast_impl.py", "check": "python_compiles"},
            {"artifact": "bench_report.md", "check": "min_words",
             "params": {"min_words": floor(rng, 130)}},
            {"artifact": "bench_report.md", "check": "contains_any",
             "params": {"any_of": ["top_terms", "term_frequency"]}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-09 (benchmarked refactor variant)\n\n"
           "Grade 0-10:\n"
           "1. Hot-spot diagnosis (0-3): correctly explains per-character concatenation, "
           "re-scan counting, per-term full re-scan, list-membership dedup.\n"
           "2. Methodology (0-3): deterministic corpus, same corpus for both timings, best-"
           "of-3, reference outputs captured before optimizing.\n"
           "3. Equivalence (0-2): a real assertion against baseline_outputs.json, recorded.\n"
           "4. Report (0-2): numbers add up; speedup honest.\n\n"
           "Deduction (up to -2): claimed speedup without timings, or behaviour drift.\n")
    return doc, rub


def h10(rng, T):
    steps = [
        "Write the numbered plan", "Read timetrack.py and enumerate the command surface",
        "Actually run each command; capture outputs",
        "Write cli_cheatsheet.md (one table per subcommand)",
        "Write quickstart.md (15-minute guide)",
        "Write usage_examples.md with >=2 fenced real transcripts",
        "Write failure_modes.md from the source's error paths",
        "Verify every documented command runs as documented",
    ]
    prompt = (
        "Produce operator documentation for the timetrack.py CLI in this directory: a "
        "cheat-sheet-first package built from the source AND from actually running it.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read timetrack.py fully; list every subcommand, argument and default.\n"
        "3. Really run: python timetrack.py start --note \"docs run\" docs-project; then "
        "stop; then report --since <today>. Keep the transcripts.\n"
        "4. Write cli_cheatsheet.md: one table per subcommand (syntax, options, effect), "
        f"at least {floor(rng, 220)} words overall.\n"
        "5. Write quickstart.md: a 15-minute path from zero to first weekly report.\n"
        "6. Write usage_examples.md with at least 2 real captured transcripts in fenced "
        "blocks.\n"
        "7. Write failure_modes.md: every error path visible in the source (already-running "
        "timer, stopping with nothing running, empty report) with the exact message text and "
        "the recovery action.\n"
        "8. Re-run every documented command to confirm the docs match reality, then finish.")
    doc = {
        "id": "HWF-10", "domain": "cli-cheatsheet-documentation", "tier": 3,
        "fixtures": ["fixtures/app_source/timetrack.py"],
        "milestones": [
            {"artifact": "cli_cheatsheet.md", "check": "contains_any",
             "params": {"any_of": ["start", "stop", "report"]}},
            {"artifact": "quickstart.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "usage_examples.md", "check": "exists"},
            {"artifact": "failure_modes.md", "check": "contains_any",
             "params": {"any_of": ["already running", "No running timer"]}},
            {"artifact": "cli_cheatsheet.md", "check": "min_words",
             "params": {"min_words": floor(rng, 200)}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-10 (cheatsheet variant)\n\n"
           "Grade 0-10:\n"
           "1. Coverage (0-3): all three subcommands with exact syntax and options.\n"
           "2. Authenticity (0-3): transcripts are real runs (timestamps/output consistent), "
           "not typed by hand.\n"
           "3. Failure modes (0-2): quotes the source's actual error strings with recovery.\n"
           "4. Quickstart (0-2): a novice could follow it end to end.\n\n"
           "Deduction (up to -2): documented flags that do not exist in the source.\n")
    return doc, rub


def h11(rng, T):
    steps = [
        "Write the numbered plan", "Read product_briefs.md closely",
        "Build a 3-year total-cost-of-ownership model in tco_model.md",
        "Score fit per product in fit_scores.md", "Assess switching/migration risk in migration_risk.md",
        "Write decision_memo.md recommending one product", "Verify arithmetic and constraints",
        "Final verification",
    ]
    prompt = (
        "A commercial contract-testing startup (6 users today, growing to 10) must pick a "
        "lab-information tool from product_briefs.md (in this directory). Non-negotiables: "
        "commercial licensing OK, data exportable to CSV at any time, working offline during "
        "client-site visits with poor connectivity.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read product_briefs.md and build tco_model.md: 3-year total cost of ownership "
        "per product for 6 then 10 users (licenses, hosting, onboarding/ops), with the "
        "assumptions stated per line.\n"
        "3. Write fit_scores.md: score each product 1-5 against each non-negotiable plus at "
        "least three criteria you derive yourself, one justification line per score.\n"
        "4. Write migration_risk.md: for the leading option, what it takes to move in and — "
        "critically — to move OUT later (data, formats, lock-in), with at least 3 risks.\n"
        f"5. Write decision_memo.md ({floor(rng, 280)}+ words): the recommendation, the "
        "runner-up and why it lost, the TCO delta, and what change would force a re-decision.\n"
        "6. Verify every number in the memo traces to tco_model.md or the brief; note the "
        "check inside decision_memo.md, then finish.")
    doc = {
        "id": "HWF-11", "domain": "tco-driven-product-selection", "tier": 3,
        "fixtures": ["fixtures/product_briefs.md"],
        "milestones": [
            {"artifact": "tco_model.md", "check": "exists"},
            {"artifact": "fit_scores.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "decision_memo.md", "check": "min_words",
             "params": {"min_words": floor(rng, 260)}},
            {"artifact": "migration_risk.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-11 (TCO variant)\n\n"
           "Ground truth from the brief: LabVault $45/user/mo annual-contract; SampleTracker "
           "Pro free academic / $12 commercial, single-user; OpenLabChain AGPL self-host + "
           "$99/mo hosting option. Grade 0-10:\n"
           "1. TCO arithmetic (0-4): 3-year, 6 and 10 user cases, assumptions stated, math "
           "correct.\n"
           "2. Fit scoring (0-2): tied to the stated non-negotiables.\n"
           "3. Exit analysis (0-2): genuine lock-in/export treatment (SampleTracker has CSV "
           "export; LabVault lock-in is explicit).\n"
           "4. Memo (0-2): decisive, quantitative, flip-condition present.\n\n"
           "Deduction (up to -2): costs invented beyond the brief without labelling as "
           "assumption.\n")
    return doc, rub


def h12(rng, T):
    steps = [
        "Write the numbered plan", "Fix audience, prerequisites and outcomes in syllabus.md",
        "Map all 10 weeks in module_map.md", "Detail sessions 1-2 in sessions/session01.md, session02.md",
        "Design assignments/project_brief.md", "Write grading_scheme.md",
        "Write readings.md with >=5 real resources", "Verify cross-references",
    ]
    prompt = (
        "Design a 10-week seminar course: 'Reliable Research Software for Experimental "
        "Scientists' (2h session per week; audience: 3rd-year undergraduates in materials or "
        "chemistry who have completed one introductory Python course; no git, no testing "
        "background assumed).\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Write syllabus.md: audience, prerequisites, and 5 measurable course-level "
        "learning outcomes (action verbs).\n"
        "3. Write module_map.md: for each of the 10 weeks — topic, 3 content bullets, the "
        "activity, and which learning outcome it serves. Cover at minimum: version control, "
        "automated testing, data provenance, reproducible environments, and one lab-data "
        "case study.\n"
        "4. Write sessions/session01.md and sessions/session02.md: slide-level outlines "
        "(>=10 slides each) with timing.\n"
        "5. Write assignments/project_brief.md: a graded project where students take a messy "
        "raw CSV from their lab, version it, clean it with a tested script, and reproduce "
        "one figure; state deliverables and marking points.\n"
        "6. Write grading_scheme.md: table mapping each assessment component to learning "
        "outcomes and Bloom levels.\n"
        "7. Write readings.md: at least 5 real, linkable resources (>=5 URLs).\n"
        "8. Confirm outcome codes are used consistently across files, then finish.")
    doc = {
        "id": "HWF-12", "domain": "research-software-course-design", "tier": 3,
        "fixtures": [],
        "milestones": [
            {"artifact": "syllabus.md", "check": "exists"},
            {"artifact": "module_map.md", "check": "contains_any",
             "params": {"any_of": ["Week 10", "week 10"]}},
        ],
        "final": [
            {"artifact": "sessions/session01.md", "check": "exists"},
            {"artifact": "assignments/project_brief.md", "check": "exists"},
            {"artifact": "readings.md", "check": "min_urls", "params": {"min_urls": 5}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-12 (research-software course variant)\n\n"
           "Grade 0-10:\n"
           "1. Constructive alignment (0-3): outcomes measurable; every week maps to one.\n"
           "2. Level fit (0-2): pitch matches no-git/no-testing beginners.\n"
           "3. Project realism (0-3): the CSV-to-figure project is doable and assesses the "
           "core outcomes.\n"
           "4. Resources (0-2): >=5 real links; grading table complete.\n\n"
           "Deduction (up to -2): fabricated URLs or weeks missing from module_map.md.\n")
    return doc, rub


def h13(rng, T):
    steps = [
        "Write the numbered plan", "Trace every PII path through the source",
        "Write data_flow_map.md keyed to the actual functions",
        "Write dpia.md (impact assessment, severity per flow)",
        "Refactor into payments_v2.py applying data-minimization fixes",
        "Write controls_checklist.md mapping each finding to its fix",
        "Verify payments_v2.py compiles", "Final verification",
    ]
    prompt = (
        "payment module privacy_audit_source.py in this directory handles user records for a "
        "payment feature. Redesign it under data-protection-by-design.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read the file and write data_flow_map.md: for each function, what personal data "
        "enters, where it is stored, what is logged, and what leaves the process.\n"
        "3. Write dpia.md — a data protection impact assessment: per identified flow, the "
        "risk to data subjects, its severity (critical/high/medium), and the GDPR principle "
        "or PCI DSS requirement at stake. At least 6 findings are present in the source.\n"
        "4. Write payments_v2.py: a refactor that tokenizes card data (store only a salted "
        "hash + last four digits), never persists or logs CVV/SSN/card numbers, uses an "
        "HTTPS endpoint for external validation, gates export to whitelisted columns, and "
        "implements real deletion (no shadow backup copy).\n"
        "5. Write controls_checklist.md: finding -> control implemented -> where in "
        "payments_v2.py.\n"
        "6. Confirm python -m py_compile payments_v2.py passes and all files exist, then "
        "finish.")
    doc = {
        "id": "HWF-13", "domain": "privacy-by-design-refactor", "tier": 3,
        "fixtures": ["fixtures/privacy_audit_source.py"],
        "milestones": [
            {"artifact": "data_flow_map.md", "check": "contains_any",
             "params": {"any_of": ["create_user", "export_users", "verify_card"]}},
            {"artifact": "dpia.md", "check": "min_words",
             "params": {"min_words": floor(rng, 340)}},
        ],
        "final": [
            {"artifact": "payments_v2.py", "check": "python_compiles"},
            {"artifact": "controls_checklist.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-13 (privacy-by-design variant)\n\n"
           "Planted findings: plaintext card/SSN storage; card+SSN into the log; CVV stored "
           "at all; plain-HTTP card validation; unrestricted full-PII export; hard-delete "
           "that copies PII into a shadow backup table. Grade 0-10:\n"
           "1. Flow map (0-3): keyed to create_user/export_users/delete_user/verify_card "
           "with storage/log/egress each.\n"
           "2. DPIA (0-3): >=6 findings, severity justified, article/requirement cited.\n"
           "3. Refactor (0-3): all six classes addressed; tokenization not obfuscation.\n"
           "4. Checklist (0-1): traceable finding->control->location.\n\n"
           "Deduction (up to -2): refactor that keeps logging any card digits.\n")
    return doc, rub


def h14(rng, T):
    steps = [
        "Write the numbered plan", "Read requirements_doc.md; list every committed item",
        "Write qa_capacity.md allocating tester-hours per RC per must-have",
        "Write descope_ladder.md (ordered cut list under 30% overrun)",
        "Write risk_register.md (>=5 risks, probability x impact)",
        "Write rollout_plan.md (beta -> RC -> GA with entry/exit criteria)",
        "Verify coverage of every must-have and every carried bug",
        "Final verification",
    ]
    prompt = (
        "From requirements_doc.md (in this directory) produce the QUALITY & ROLLOUT plan "
        "for HummingNote v2.0 — not the dev schedule: the QA and release-track view. "
        "Constraints: 1 QA engineer, about 60 tester-hours per release candidate, public "
        "beta targeted at week 10, B-101 must ship.\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read requirements_doc.md; write qa_capacity.md: for each must-have feature and "
        "carried bug (B-101/B-102/B-103), the test approach and an hour estimate per RC, "
        "totalling within the 60-hour envelope per RC. Show the arithmetic.\n"
        "3. Write descope_ladder.md: the ordered list of what gets cut first if effort "
        "overruns by 30%, with the reason per rung (B-101 and the E2EE threat model may "
        "never appear on it).\n"
        "4. Write risk_register.md: at least 5 risks with probability (H/M/L) x impact "
        "(H/M/L) and resulting priority.\n"
        f"5. Write rollout_plan.md ({floor(rng, 400)}+ words): the week-10 public beta, the "
        "RC cadence afterwards, GA entry criteria (including the published threat model), "
        "rollback strategy, and the exit criteria if the beta slips two weeks.\n"
        "6. Verify every committed item and all three bug ids appear across the plan; note "
        "the verification in rollout_plan.md, then finish.")
    doc = {
        "id": "HWF-14", "domain": "qa-and-rollout-planning", "tier": 3,
        "fixtures": ["fixtures/requirements_doc.md"],
        "milestones": [
            {"artifact": "qa_capacity.md", "check": "exists"},
            {"artifact": "descope_ladder.md", "check": "exists"},
        ],
        "final": [
            {"artifact": "rollout_plan.md", "check": "min_words",
             "params": {"min_words": floor(rng, 380)}},
            {"artifact": "rollout_plan.md", "check": "contains_any",
             "params": {"any_of": ["B-101", "B-102", "B-103"]}},
            {"artifact": "risk_register.md", "check": "exists"},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = ("# Judge rubric — HWF-14 (QA/rollout variant)\n\n"
           "Grade 0-10:\n"
           "1. QA arithmetic (0-4): per-RC hour allocation covers all must-haves + 3 bugs "
           "within 60h; sums shown.\n"
           "2. Descope ladder (0-2): ordered, reasoned, protects B-101 and the threat "
           "model.\n"
           "3. Rollout (0-3): beta/RC/GA with entry-exit criteria, rollback, slip plan.\n"
           "4. Risk register (0-1): >=5 risks properly prioritized.\n\n"
           "Deduction (up to -2): plans that quietly drop a committed must-have.\n")
    return doc, rub


def h15(rng, T):
    o = T["onset"]
    steps = [
        "Write the numbered plan", "Read experiment_description.md and raw_measurements.csv",
        "Specify the offset-threshold onset rule in method_note.md",
        "Implement threshold_onsets.py; produce onsets2.csv for the five series",
        "Implement ea_recompute.py (Arrhenius least squares on ln(1/t0) vs 1/T)",
        "Plot the fit as fig_offset.png", "Write audit2_report.md comparing with 152 kJ/mol",
        "State a verdict with justification", "Final verification",
    ]
    prompt = (
        "Re-audit the aging-kinetics paper from experiment_description.md with a DIFFERENT "
        "onset extractor than the paper's tangent method: an offset-threshold rule. "
        "raw_measurements.csv holds the five resistivity series (500-580C).\n\n"
        f"Required sequence (plan at least {len(steps)} steps):\n"
        "1. Produce your plan.\n"
        "2. Read both fixtures; write data_notes.md: per series, time range, sampling step, "
        "and the time of the resistivity minimum.\n"
        "3. Write method_note.md defining your rule precisely: t0 = the first sampled time "
        "STRICTLY AFTER the series minimum at which resistivity has risen 1.0 uOhm*cm above "
        "that minimum. State why a fixed-offset threshold is more reproducible than tangent "
        "intersection between analysts.\n"
        "4. Implement threshold_onsets.py accordingly and emit onsets2.csv "
        "(temperature_C, t0_min) for all five series.\n"
        "5. Implement ea_recompute.py: least-squares fit of ln(1/t0) = ln A - Ea/R * (1/T); "
        "print Ea in kJ/mol and R^2; run it on onsets2.csv.\n"
        "6. Save the fitted plot with labelled axes as fig_offset.png.\n"
        f"7. Write audit2_report.md ({floor(rng, 300)}+ words): recomputed Ea and R^2 versus "
        "the claimed 152 kJ/mol, answers to the four audit questions in the description, "
        "and a verdict (reproduced / partially / not) grounded in YOUR numbers.\n"
        "8. Verify every number in the report matches a script output, then finish.")
    doc = {
        "id": "HWF-15", "domain": "alternate-method-reproducibility-audit", "tier": 3,
        "fixtures": ["fixtures/experiment_description.md", "fixtures/raw_measurements.csv"],
        "milestones": [
            {"artifact": "method_note.md", "check": "contains_any",
             "params": {"any_of": ["threshold", "offset", "crossing"]}},
            {"artifact": "onsets2.csv", "check": "exists"},
        ],
        "final": [
            {"artifact": "ea_recompute.py", "check": "python_compiles"},
            {"artifact": "fig_offset.png", "check": "image_valid",
             "params": {"min_width": 200, "min_height": 100}},
            {"artifact": "audit2_report.md", "check": "min_words",
             "params": {"min_words": floor(rng, 280)}},
        ],
        "steps": steps, "prompt": prompt,
    }
    rub = (f"# Judge rubric — HWF-15 (alternate-method audit variant)\n\n"
           f"Ground truth under the specified rule (rise of {o['delta']} uOhm*cm above the "
           f"post-minimum): t0 = {o['t0_min']} min; the fit yields Ea = {o['Ea_kJ_mol']} "
           f"kJ/mol with R^2 = {o['R2']} — nowhere near the claimed 152 kJ/mol, and the "
           "sign/magnitude pattern exposes the non-monotonic onset ordering planted in the "
           "data. Grade 0-10:\n"
           "1. Rule implementation (0-4): exactly the stated threshold rule; onsets2.csv "
           "matches the ground truth within one sampling step.\n"
           "2. Fit correctness (0-2): proper least squares; Ea and R^2 reported honestly.\n"
           "3. Audit reasoning (0-3): confronts the discrepancy instead of rationalizing it; "
           "answers the four audit questions; verdict follows the numbers.\n"
           "4. Artifacts (0-1): labelled plot present.\n\n"
           "Deduction (up to -3): 'confirms 152 kJ/mol' without recomputation — automatic "
           "fail of items 2-3.\n")
    return doc, rub


# ==========================================================================
# Tier 4 variants (ground truth recomputed from the frozen fixtures)
# ==========================================================================
def l01(rng, T):
    m = T["multibatch"]
    batches = m["batches"]
    prof = [f"batch_profile_{b}.md" for b in batches]
    mean_groups = {b: num_variants(m["means"][b]) for b in batches}
    steps = ["Produce your numbered plan."]
    steps.append(f"Inspect alloy_multibatch.csv ({m['n_rows']} rows, batches "
                 + ", ".join(batches) + ").")
    steps.append("Write means_aggregate.py: per-batch count/mean of UTS and elongation, "
                 "plus per-batch UTS spread (max-min).")
    steps += [f"Run it and write batch_profile_{b}.md stating this batch's exact mean UTS "
              f"(the value itself, not a rounded category)." for b in batches]
    steps += [
        "Write means_check.json: per-batch mean UTS and the ranking of batches by mean UTS.",
        f"Identify the batch with the widest within-batch UTS spread and its spread value.",
        "Write synthesis.md (400+ words): mean-based ranking, how it differs from a "
        "peak-based view, the spread analysis, and one processing recommendation.",
        "Re-check synthesis.md against the profiles and write next_steps.md listing "
        "corrections or confirmations.",
    ]
    prompt = (LH_HEADERS[0] + "\n\nAnalyze alloy_multibatch.csv (8 batches, 625 rows each) "
              "from the AVERAGES side: rank batches by MEAN UTS and quantify within-batch "
              f"spread.\n\nRequired steps (plan at least {len(steps)}):\n" + fmt_steps(steps))
    doc = {
        "id": "HLH-01", "domain": "long-horizon-mean-aggregation-chain", "version": "1.0",
        "fixtures": ["fixtures/alloy_multibatch.csv"],
        "milestones": [{"artifact": p, "check": "contains_any",
                        "params": {"any_of": mean_groups[b]}}
                       for p, b in zip(prof, batches)],
        "final": [
            {"artifact": "means_aggregate.py", "check": "python_compiles"},
            {"artifact": "means_check.json", "check": "contains_groups",
             "params": {"groups": [mean_groups[b] for b in batches], "min_ratio": 1.0}},
            {"artifact": "synthesis.md", "check": "min_words", "params": {"min_words": 400}},
            {"artifact": "synthesis.md", "check": "contains_groups",
             "params": {"groups": [[m["widest_batch"]],
                                   num_variants(m["widest_spread"])], "min_ratio": 1.0}},
            {"artifact": "next_steps.md", "check": "exists"},
            {"artifact": "next_steps.md", "check": "min_words", "params": {"min_words": 20}},
        ],
        "required_plan_steps_min": len(steps), "plan_steps": steps, "prompt": prompt,
        "max_wall_minutes": 90, "resume_test": False,
    }
    rub = (f"# Judge rubric — HLH-01 (mean-aggregation variant)\n\n"
           f"Deterministic checks verify each batch_profile file contains its batch's true "
           f"mean UTS and that means_check.json carries all eight. Ground truth (1 dp): "
           + ", ".join(f"{b}={m['means'][b]:.1f}" for b in batches) + ".\n\n"
           f"Mean ranking: {' > '.join(sorted(m['means'], key=lambda b: -m['means'][b]))}. "
           f"Widest spread: {m['widest_batch']} at {m['widest_spread']:.1f} MPa; narrowest: "
           f"{min(m['spread'], key=lambda b: m['spread'][b])}. Grade the rest 0-10:\n\n"
           "1. Ranking correctness (0-4): exact mean order; the B02/B05 near-tie "
           f"({m['means']['B02']:.1f} vs {m['means']['B05']:.1f}) separates real computation "
           "from guessing.\n"
           "2. Spread analysis (0-2): widest batch named with value and a plausible "
           "process reading of high spread.\n"
           "3. Mean-vs-peak insight (0-2): notes where the mean ranking disagrees with a "
           "peak-based ranking and why that matters for specification limits.\n"
           "4. next_steps substance (0-2): concrete corrections/confirmations per file.\n\n"
           "Deduction (up to -2): means in the JSON inconsistent with the profile files.\n")
    return doc, rub


def l02(rng, T):
    c = T["corpus"]
    words8 = c["long8"]                       # (word, count) len>=6
    w_variants = {w: [w] for w, _ in words8}
    cnt_variants = {n: count_variants(n) for _, n in words8}
    topics = rng.sample(sorted(c["topics"]), 2)
    steps = [
        "Produce your plan (todo tool if available, otherwise plan.md).",
        "Check process_corpus.txt size — it far exceeds any context window; plan to script it.",
        "Write stream_stats.py that reads the file line by line (never whole into context).",
        "Compute the frequency table restricted to words of length >= 6, plus per-topic line "
        "counts, plus the number of lines containing the word 'energy'.",
        f"Write wordlen_index.json: the top-8 length>=6 words with exact counts.",
        "Detect exact duplicate lines and count them via the script.",
        f"Write topic_counts.md with a section per topic (at least '{topics[0]}' and "
        f"'{topics[1]}') giving lines per topic.",
        "Write energy_report.md stating how many lines contain 'energy' and how that "
        "compares to the theoretical even share.",
        "Write distinct_report.md (120+ words): raw lines vs distinct lines, duplicate "
        "count, method, one worked example.",
        "Re-run stream_stats.py and confirm every reported number reproduces.",
    ]
    prompt = (LH_HEADERS[0] + "\n\nProcess process_corpus.txt (far larger than your context "
              "window) with a long-word lens: index only words of at least 6 letters, count "
              "per-topic lines, and quantify the lines containing 'energy'.\n\n"
              "Required steps (plan at least 10):\n" + fmt_steps(steps))
    doc = {
        "id": "HLH-02", "domain": "long-horizon-context-pressure-variant", "version": "1.0",
        "fixtures": ["fixtures/process_corpus.txt"],
        "milestones": [
            {"artifact": "wordlen_index.json", "check": "contains_groups",
             "params": {"groups": [[w] for w, _ in words8[:4]], "min_ratio": 1.0}}],
        "final": [
            {"artifact": "stream_stats.py", "check": "python_compiles"},
            {"artifact": "wordlen_index.json", "check": "contains_groups",
             "params": {"groups": [w_variants[w] for w, _ in words8], "min_ratio": 1.0}},
            {"artifact": "wordlen_index.json", "check": "contains_groups",
             "params": {"groups": [cnt_variants[n] for _, n in words8], "min_ratio": 1.0}},
            {"artifact": "topic_counts.md", "check": "structure",
             "params": {"required_sections": topics}},
            {"artifact": "energy_report.md", "check": "contains_any",
             "params": {"any_of": num_variants(c["energy_lines"])}},
            {"artifact": "distinct_report.md", "check": "min_words",
             "params": {"min_words": 120}},
        ],
        "required_plan_steps_min": 10, "plan_steps": steps, "prompt": prompt,
        "max_wall_minutes": 90, "resume_test": False,
    }
    rub = (f"# Judge rubric — HLH-02 (long-word index variant)\n\n"
           f"Deterministic checks verify the index content. Ground truth: top-8 words of "
           f"length>=6 = {', '.join(f'{w} {n}' for w, n in words8)}; lines containing "
           f"'energy' = {c['energy_lines']}; raw lines = {c['total_lines']}, distinct = "
           f"{c['distinct_lines']} (so {c['duplicates']} exact duplicates). Per-topic counts "
           f"are 600 or 601. Grade the rest 0-10:\n\n"
           "1. Index correctness (0-4): all 8 words AND counts exact.\n"
           "2. Energy analysis (0-2): count correct and compared to the even-share "
           "baseline (1/20 of the vocabulary) with the right conclusion.\n"
           "3. Script-based evidence (0-2): streaming implementation; no whole-file read "
           "into chat context.\n"
           "4. Distinct report (0-2): duplicate count 5 with a concrete example.\n\n"
           "Deduction (up to -2): prose contradicting wordlen_index.json.\n")
    return doc, rub


def l03(rng, T):
    mods = [f"m{i:02d}" for i in range(1, 11)]
    fns = ["mean", "median", "variance", "slope", "interp", "smooth",
           "normalize", "integrate", "roots", "fit"]
    logs = [f"diag_{m}.md" for m in mods]
    steps = ["Produce your plan (todo tool if available, otherwise plan.md).",
             "Read test_suite.py first, then run python test_suite.py and capture the "
             "baseline output verbatim into baseline_failures.md."]
    steps += [f"Module {m} (calc_{fns[i-1]}): starting from the CURRENT failure list entry, "
              f"diagnose, fix, re-run the suite, write diag_{m}.md (bug, root cause, fix). "
              f"Work strictly in REVERSE order m10 -> m01." for i, m in enumerate(mods, 1)]
    steps += [
        "Write fix_narrative.md (300+ words): every fix with its root cause, in the order "
        "you applied them.",
        "Run the full suite one last time; record the output.",
        "Write final_report.md with sections 'all tests' and 'regression'.",
    ]
    prompt = (LH_HEADERS[0] + "\n\nRepair the 10-module signal pipeline (m01.py..m10.py plus "
              "test_suite.py are in the current directory; each module holds exactly one bug). "
              "Capture the baseline FIRST, then fix modules strictly in REVERSE order (m10 down "
              "to m01).\n\nRequired steps (plan at least 15):\n" + fmt_steps(steps))
    doc = {
        "id": "HLH-03", "domain": "long-horizon-endurance-reverse", "version": "1.0",
        "fixtures": [f"fixtures/buggy_pipeline_pkg/{m}.py" for m in mods] +
                    ["fixtures/buggy_pipeline_pkg/test_suite.py"],
        "milestones": [{"artifact": f, "check": "exists"} for f in ["baseline_failures.md"] + logs],
        "final": [
            {"artifact": f"{m}.py", "check": "python_compiles"} for m in mods
        ] + [
            {"artifact": "test_suite.py", "check": "script_pass",
             "params": {"command": "python test_suite.py",
                        "expect_stdout": "10 passed, 0 failed", "timeout_s": 120}},
            {"artifact": "fix_narrative.md", "check": "min_words",
             "params": {"min_words": 300}},
            {"artifact": "fix_narrative.md", "check": "contains_any",
             "params": {"any_of": fns[:5]}},
            {"artifact": "final_report.md", "check": "structure",
             "params": {"required_sections": ["all tests", "regression"]}},
        ],
        "required_plan_steps_min": 15, "plan_steps": steps, "prompt": prompt,
        "max_wall_minutes": 90, "resume_test": True, "kill_at_pct": 50,
    }
    rub = ("# Judge rubric — HLH-03 (reverse-order endurance variant)\n\n"
           "The script_pass gate enforces the suite oracle '10 passed, 0 failed'. Ground "
           "truth bugs: m01 divisor len+1; m02 median not mean-of-middle-two; m03 "
           "population variance (needs n-1); m04 slope not least-squares; m05 trailing "
           "None; m06 smoothing steps back `factor` instead of 1; m07 multiply by max "
           "instead of divide; m08 integer division; m09 one-based index slip; m10 returns "
           "a slice, not the intercept. Grade the rest 0-10:\n\n"
           "1. Baseline capture (0-2): baseline_failures.md quotes the initial run showing "
           "10 failures before any fix.\n"
           "2. Root-cause quality (0-4): >=8 diag logs state the actual cause with "
           "specifics.\n"
           "3. Order discipline (0-2): evidence of m10 -> m01 progression (per-module "
           "re-runs, not one batch rewrite).\n"
           "4. Final report (0-2): 'all tests' quotes the final suite output; 'regression' "
           "addresses cross-module breakage.\n\n"
           "Deduction (up to -2): test_suite.py edited (the suite is the oracle).\n")
    return doc, rub


# ==========================================================================
BUILDERS = [
    (1, h01), (1, h02),
    (2, h03), (2, h04), (2, h05), (2, h06),
    (3, h07), (3, h08), (3, h09), (3, h10), (3, h11), (3, h12), (3, h13), (3, h14),
    (3, h15),
    (4, l01), (4, l02), (4, l03),
]


def build(seed):
    rng = random.Random(seed)
    T = {"papers": truth_papers(), "sensor": truth_sensor(), "aging": truth_aging(),
         "corpus": truth_corpus(), "multibatch": truth_multibatch(), "onset": truth_onset()}
    out = []
    for tier, fn in BUILDERS:
        doc, rub = fn(rng, T)
        doc.pop("tier", None)                 # tier is implied by the directory
        if "final" in doc:                    # schema key is final_artifacts
            doc["final_artifacts"] = doc.pop("final")
        if "steps" in doc:                    # schema key is plan_steps
            doc["plan_steps"] = doc.pop("steps")
        if "version" not in doc:
            doc["version"] = "1.0"
        # reworded protocol header ( WF-style tasks ); tier-4 builders embed their own
        if tier in (1, 2, 3):
            head = HEADERS[rng.randrange(len(HEADERS))]
            n = doc.pop("required_plan_steps_min", len(doc["plan_steps"]))
            doc["prompt"] = head.format(nsteps=max(n, len(doc["plan_steps"]))) + "\n\n" + doc["prompt"]
            doc["required_plan_steps_min"] = n
        doc["judge_rubric"] = f"../tasks_heldout/rubrics/{doc['id']}.md"
        doc["max_wall_minutes"] = doc.get("max_wall_minutes") or 60
        doc.setdefault("notes", "")
        doc.setdefault("extra_judge_note", "")
        out.append((tier, doc, rub))
    return out


def main():
    ap = argparse.ArgumentParser(description="Generate held-out LRAB tasks")
    ap.add_argument("--seed", type=int, default=20260921)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    tasks = build(a.seed)
    rub_dir = os.path.join(a.out, "rubrics")
    os.makedirs(rub_dir, exist_ok=True)
    kinds = set()
    for tier, doc, rub in tasks:
        for grp in (doc["milestones"], doc["final_artifacts"]):
            for e in grp:
                kinds.add(e["check"])
                assert e["check"] in ALLOWED_KINDS, f"{doc['id']}: bad kind {e['check']}"
        td = os.path.join(a.out, TIER_DIR[tier])
        os.makedirs(td, exist_ok=True)
        p = os.path.join(td, doc["id"] + ".json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        with open(os.path.join(rub_dir, doc["id"] + ".md"), "w", encoding="utf-8") as f:
            f.write(rub)
        print(f"wrote {doc['id']} tier={tier} checks="
              f"{len(doc['milestones'])}+{len(doc['final_artifacts'])}")
    print(f"total: {len(tasks)} tasks | kinds used: {sorted(kinds)}")


if __name__ == "__main__":
    main()
