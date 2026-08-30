#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate LRAB-H (tier4_longhorizon): fixtures + task JSONs with embedded ground truth.

Long-horizon design goals (design/2026-08-29-e2b-agentmini-lrabh.md):
  LH-01  deep dependency chain  — 8 slice stats -> cross-validation -> two-pass report
  LH-02  context pressure       — ~400KB corpus exceeds any context; must script, not read
  LH-03  endurance + resume     — 10-module fix pipeline (~40 tool calls), resume_test marker

Deterministic: seeded RNG, ground-truth numbers computed here and embedded into the
task JSONs' contains_any checks (with common format variants), so scoring is stable
against agent-side rounding. Run:  python gen_lhab.py
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
TASKS = os.path.join(HERE, "tasks", "tier4_longhorizon")
RUBRICS = os.path.join(HERE, "rubrics")

PROMPT_HEAD = ("You are an autonomous agent working in the current directory. "
               "FIRST create a numbered plan covering every step below. Use your "
               "available planning/todo tool if you have one; otherwise write the plan "
               "to plan.md. Then execute the steps one by one, creating each required "
               "file with the exact filename given. Long task: work through ALL steps "
               "persistently, do not stop early. Do not fabricate content: every number "
               "you report must be computed from the provided fixture files. When all "
               "artifacts are written and verified, finish with a short summary.")


def num_variants(x):
    """Format variants so contains_any survives agent-side rounding."""
    v = [f"{x:.1f}", f"{x:.0f}", f"{int(round(x))}"]
    return sorted(set(v))


# ---------------------------------------------------------------- LH-01
def gen_lh01():
    rng = random.Random(4101)
    batches = [f"B{i:02d}" for i in range(1, 9)]
    rows = []
    peak = {}
    anom = {"batch": "B06", "temp": None}      # injected dip: B06 @ base_t+150
    for b in batches:
        base_t = rng.choice([400, 425, 450, 475, 500, 525])
        slope = rng.uniform(0.8, 1.6)          # UTS per degree above base
        cap = rng.uniform(1350, 1550)
        best = -1e9
        for i in range(625):
            t = base_t + (i % 10) * 25
            h = 2 + (i % 8)
            uts = min(cap, 900 + slope * (t - base_t) + rng.gauss(0, 18))
            if b == anom["batch"] and t == base_t + 150:
                uts -= 90                       # injected anomaly dip (mid-range, off-trend)
                anom["temp"] = t
            el = max(2, 18 - (t - 400) / 40 + rng.gauss(0, 1.2))
            hv = 280 + (uts - 900) / 6 + rng.gauss(0, 6)
            rows.append((b, t, h, round(uts, 1), round(el, 1), round(hv, 1)))
            best = max(best, uts)
        peak[b] = round(best, 1)
    with open(os.path.join(FIX, "alloy_multibatch.csv"), "w", encoding="utf-8") as f:
        f.write("batch_id,temperature_C,time_h,UTS_MPa,elongation_pct,hardness_HV\n")
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")

    slice_files = [f"slice_stats_{b}.md" for b in batches]
    # 判分加厚(P0):每个 slice 文件必须含本批真实峰值(此前 4 个 exists 会让
    # "建 4 个空文件+糊报告"接近满分)。里程碑 = 8 × 内容校验。
    milestones = [{"artifact": s, "check": "contains_any",
                   "params": {"any_of": num_variants(peak[b])}}
                  for s, b in zip(slice_files, batches)]
    final = [
        {"artifact": "slice_aggregate.py", "check": "python_compiles"},
        {"artifact": "cross_validation.json", "check": "contains_groups",
         "params": {"groups": [num_variants(peak[b]) for b in batches],
                    "min_ratio": 1.0}},
        # 排名顺序对 JSON 键序脆弱(键通常按批号序插入,先于 ranking 数组出现),
        # 确定性侧只查值齐全;排序正确性交给 judge rubric。
        {"artifact": "master_report.md", "check": "min_words", "params": {"min_words": 400}},
        {"artifact": "master_report.md", "check": "contains_groups",
         "params": {"groups": [[anom["batch"]], [str(anom["temp"])]],
                    "min_ratio": 1.0}},
        {"artifact": "revision_notes.md", "check": "exists"},
        {"artifact": "revision_notes.md", "check": "min_words", "params": {"min_words": 20}},
    ]
    steps = ["Create your plan (todo tool if available, otherwise plan.md).",
             "Inspect alloy_multibatch.csv (5000 rows, 8 batches B01..B08).",
             "Write slice_aggregate.py: per-batch count/mean/max of UTS, elongation, hardness."]
    steps += [f"Run slice_aggregate.py and write slice_stats_{b}.md (exact peak UTS value required)."
              for b in batches]
    steps += ["Write cross_validation.json: per-batch peak UTS and the batch ranking by peak UTS.",
              "Identify the anomalous batch/condition (a non-monotonic UTS dip) and record it.",
              "Write master_report.md (400+ words): batch ranking, spread, anomaly discussion, recommendation.",
              "Re-check master_report.md against slice_stats files and write revision_notes.md listing any corrections."]
    task = {
        "id": "LH-01", "domain": "long-horizon-dependency-chain", "version": "1.0",
        "fixtures": ["fixtures/alloy_multibatch.csv"],
        "prompt": PROMPT_HEAD + "\n\nAnalyze alloy_multibatch.csv (8 alloy batches, 625 rows each).\n\nRequired steps (plan at least 15):\n" +
                  "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)),
        "required_plan_steps_min": 15,
        "plan_steps": steps,
        "milestones": milestones, "final_artifacts": final,
        "judge_rubric": "rubrics/LH-01.md",
        "max_wall_minutes": 90, "resume_test": False,
        "notes": "Deep dependency chain: 8 slice stats feed cross-validation feed report feed revision.",
        "extra_judge_note": "",
    }
    ranking = [b for b, _ in sorted(peak.items(), key=lambda kv: -kv[1])]
    truth = {"peak_uts_per_batch": peak, "ranking": ranking,
             "anomaly": {"batch": anom["batch"], "temp_C": anom["temp"], "dip_MPa": 90}}
    return task, truth


# ---------------------------------------------------------------- LH-02
def gen_lh02():
    rng = random.Random(4202)
    topics = ["diffusion", "creep", "fatigue", "welding", "corrosion", "precipitation",
              "recrystallization", "twinning", "segregation", "annealing"]
    words = ["the", "alloy", "phase", "boundary", "energy", "model", "data", "grain",
             "stress", "temperature", "rate", "sample", "peak", "time", "process",
             "structure", "fraction", "test", "curve", "field"]
    lines = []
    for i in range(6000):
        t = topics[i % len(topics)]
        n = rng.randint(8, 16)
        sent = f"[{t}] " + " ".join(rng.choice(words) for _ in range(n)) + f" ref{i:05d}."
        lines.append(sent)
    # Inject exact duplicate lines (dedup step has real ground truth)
    for pos in (137, 1954, 3707, 5222, 5888):
        lines.insert(pos, lines[pos - 1])
    corpus = "\n".join(lines)
    with open(os.path.join(FIX, "process_corpus.txt"), "w", encoding="utf-8") as f:
        f.write(corpus)
    # ground truth
    from collections import Counter
    counts = Counter()
    total_words = 0
    for ln in lines:
        body = ln.split("] ", 1)[1].rsplit(" ref", 1)[0]
        ws = body.split()
        total_words += len(ws)
        counts.update(ws)
    top8 = counts.most_common(8)
    per_topic = Counter(ln.split("]")[0][1:] for ln in lines)
    truth = {"total_lines": len(lines), "total_words": total_words,
             "top8": top8, "lines_per_topic": dict(per_topic),
             "duplicates": 5,
             "corpus_bytes": len(corpus.encode('utf-8'))}
    final = [
        {"artifact": "build_index.py", "check": "python_compiles"},
        {"artifact": "freq_index.json", "check": "exists"},
        # 加厚:top-8 全部词 + 每词精确计数(此前 any-of 前 4 词,不带计数也能满分)
        {"artifact": "freq_index.json", "check": "contains_groups",
         "params": {"groups": [[w] for w, _ in top8], "min_ratio": 1.0}},
        {"artifact": "freq_index.json", "check": "contains_groups",
         "params": {"groups": [[str(c), f"{c:,}"] for _, c in top8], "min_ratio": 1.0}},
        {"artifact": "dedup_report.md", "check": "min_words", "params": {"min_words": 150}},
        {"artifact": "corpus_summary.md", "check": "contains_any",
         "params": {"any_of": num_variants(total_words) + [f"{total_words:,}"]}},
        {"artifact": "corpus_summary.md", "check": "structure",
         "params": {"required_sections": ["topic", "duplicate"]}},
    ]
    steps = ["Create your plan (todo tool if available, otherwise plan.md).",
             "Check process_corpus.txt size — it is far too large to read whole; plan a script-based approach.",
             "Write build_index.py: stream the file line by line (do NOT load it whole into chat context).",
             "Compute per-line word counts and per-topic line counts via the script.",
             "Write freq_index.json: top-8 words with exact counts, plus total word count.",
             "Detect duplicate sentences (exact repeat) and count them via the script.",
             "Write dedup_report.md (150+ words): duplicate count, method, examples.",
             "Write corpus_summary.md with sections 'topic' and 'duplicate': lines per topic, totals.",
             "Re-run build_index.py to confirm the numbers in your reports match freq_index.json."]
    task = {
        "id": "LH-02", "domain": "long-horizon-context-pressure", "version": "1.0",
        "fixtures": ["fixtures/process_corpus.txt"],
        "prompt": PROMPT_HEAD + "\n\nProcess process_corpus.txt (" +
                  f"{truth['corpus_bytes'] // 1024}KB — far larger than your context window).\n\n"
                  "Required steps (plan at least 9):\n" +
                  "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)),
        "required_plan_steps_min": 9, "plan_steps": steps,
        "milestones": [{"artifact": "freq_index.json", "check": "contains_groups",
                        "params": {"groups": [[w] for w, _ in top8[:4]], "min_ratio": 1.0}}],
        "final_artifacts": final, "judge_rubric": "rubrics/LH-02.md",
        "max_wall_minutes": 90, "resume_test": False,
        "notes": "400KB corpus: read-all strategies blow context; only script-based processing survives.",
        "extra_judge_note": "",
    }
    return task, truth


# ---------------------------------------------------------------- LH-03
def gen_lh03():
    funcs = []
    for i in range(1, 11):
        name = f"calc_{['mean', 'median', 'variance', 'slope', 'interp', 'smooth', 'normalize', 'integrate', 'roots', 'fit'][i-1]}"
        funcs.append((f"m{i:02d}", name))
    modules = []
    bugs = ["divisor off by one", "median wrong for even n", "population instead of sample",
            "slope formula wrong", "trailing None element", "wrong smoothing window",
            "multiply instead of divide", "integer division", "off-by-one index", "wrong return value"]
    for idx, (mod, fn) in enumerate(funcs):
        body = f'"""Module {mod}: {fn}."""\n\n\ndef {fn}(values, factor=1.0):\n'
        if idx == 0:
            body += ('    total = 0.0\n    for v in values:\n        total += v\n'
                     '    return total / (len(values) + 1)   # BUG: divisor off by one\n')
        elif idx == 1:
            body += ('    vs = sorted(values)\n    n = len(vs)\n'
                     '    return vs[n // 2]   # BUG: wrong median for even n\n')
        elif idx == 2:
            body += ('    m = sum(values) / len(values)\n'
                     '    return sum((v - m) ** 2 for v in values) / len(values)   # BUG: population, should be sample (n-1)\n')
        elif idx == 3:
            body += ('    n = len(values)\n    sx = sum(range(n))\n    sy = sum(values)\n'
                     '    return sy / sx if sx else 0.0   # BUG: not least-squares slope\n')
        elif idx == 4:
            body += ('    out = []\n    for i in range(len(values) - 1):\n'
                     '        out.append(values[i] + (values[i + 1] - values[i]) * factor)\n'
                     '    return out + [None]   # BUG: trailing None element\n')
        elif idx == 5:
            body += ('    out = []\n    for i in range(len(values)):\n        if i == 0:\n'
                     '            out.append(values[0])\n        else:\n'
                     '            out.append((values[i] + values[max(0, i - factor)]) / 2)   # BUG: steps back factor, should be 1\n'
                     '    return out\n')
        elif idx == 6:
            body += ('    mx = max(values)\n    return [v * mx for v in values]   # BUG: multiply instead of divide\n')
        elif idx == 7:
            body += ('    total = 0\n    for v in values:\n        total += v\n'
                     '    return total // len(values)   # BUG: integer division\n')
        elif idx == 8:
            body += ('    lo = 0\n    for i, v in enumerate(values):\n'
                     '        if v < factor:\n            lo = i + 1\n'
                     '    return lo + 1   # BUG: off-by-one (treats index as 1-based)\n')
        else:
            body += ('    return values[1:]   # BUG: returns a slice, not the intercept\n')
        modules.append((mod, fn, body))
    pkg_dir = os.path.join(FIX, "buggy_pipeline_pkg")
    os.makedirs(pkg_dir, exist_ok=True)
    for mod, fn, body in modules:
        with open(os.path.join(pkg_dir, f"{mod}.py"), "w", encoding="utf-8") as f:
            f.write(body)
    tests = ['"""Test suite for buggy_pipeline_pkg. Run: python test_suite.py"""',
             "import importlib, traceback\n",
             "CASE = [1.0, 2.0, 3.0, 4.0]",
             "# (module, function, expected result on CASE with factor=2)",
             "EXPECTED = ["]
    expected = [
        ("2.5",), ("2.5",), ("5 / 3",), ("1.0",),
        ("[3.0, 4.0, 5.0]",), ("[1.0, 1.5, 2.5, 3.5]",),
        ("[0.25, 0.5, 0.75, 1.0]",), ("7.5",), ("1",), ("1.0",),
    ]
    for (m, fn, _), exp in zip(modules, expected):
        tests.append(f'    ("{m}", "{fn}", {exp[0]}),')
    tests += ["]\n",
              "def close(a, b):",
              "    if isinstance(b, list):",
              "        return isinstance(a, list) and len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))",
              "    if isinstance(b, (int, float)) and isinstance(a, (int, float)) and not isinstance(a, bool):",
              "        return abs(a - b) < 1e-9",
              "    return a == b\n",
              "def main():", "    passed = failed = 0",
              "    for mod, fn, want in EXPECTED:",
              "        try:",
              "            m = importlib.import_module(mod)",
              "            f = getattr(m, fn)",
              "            got = f(CASE, 2)",
              "            if close(got, want):",
              "                print(f'PASS {mod}.{fn}')",
              "                passed += 1",
              "            else:",
              "                print(f'FAIL {mod}.{fn}: got {got!r}, want {want!r}')",
              "                failed += 1",
              "        except Exception as e:",
              "            print(f'FAIL {mod}.{fn}: {type(e).__name__}: {e}')",
              "            failed += 1",
              "    print(f'{passed} passed, {failed} failed')",
              "", 'if __name__ == "__main__":', "    main()", ""]
    with open(os.path.join(pkg_dir, "test_suite.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(tests))
    truth = {"modules": [m for m, _, _ in modules], "functions": [fn for _, fn, _ in modules],
             "bugs": bugs}
    per_module_logs = [f"fix_log_{m}.md" for m, _, _ in modules]
    # 加厚:里程碑 = 全部 10 个模块日志(逐模块推进的证据),不再只查前 3。
    final = [{"artifact": f"{m}.py", "check": "python_compiles"} for m, _, _ in modules]
    final += [
        # 端到端验证:修复必须让测试套件真绿("10 passed, 0 failed"),
        # 不是"改到能编译"。这是 LH-03 与真实调试工作对齐的核心判据。
        {"artifact": "test_suite.py", "check": "script_pass",
         "params": {"command": "python test_suite.py",
                    "expect_stdout": "10 passed, 0 failed", "timeout_s": 120}},
        {"artifact": "fix_log.md", "check": "min_words", "params": {"min_words": 300}},
        {"artifact": "fix_log.md", "check": "contains_any",
         "params": {"any_of": [fn for _, fn, _ in modules[:5]]}},
        {"artifact": "integration_report.md", "check": "structure",
         "params": {"required_sections": ["all tests", "regression"]}},
    ]
    steps = ["Create your plan (todo tool if available, otherwise plan.md).",
             "List the 10 modules (m01.py..m10.py) and test_suite.py; read test_suite.py first.",
             "Run python test_suite.py to get the baseline failure list."]
    steps += [f"Module {m} ({fn}): diagnose, fix, re-run test_suite.py, write fix_log_{m}.md "
              f"(bug, root cause, fix). Do the modules strictly in order m01..m10." for m, fn, _ in modules]
    steps += ["Write fix_log.md (300+ words): all fixes with root causes.",
              "Run the full test suite one final time; record the result.",
              "Write integration_report.md with sections 'all tests' and 'regression'."]
    task = {
        "id": "LH-03", "domain": "long-horizon-endurance-resume", "version": "1.0",
        "fixtures": [f"fixtures/buggy_pipeline_pkg/{m}.py" for m, _, _ in modules] +
                    ["fixtures/buggy_pipeline_pkg/test_suite.py"],
        "prompt": PROMPT_HEAD + "\n\nFix the 10-module signal pipeline "
                  "(modules m01.py..m10.py and test_suite.py are in the current directory; "
                  "each module has exactly one bug). Work strictly module by module.\n\n"
                  "Required steps (plan at least 15):\n" +
                  "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)),
        "required_plan_steps_min": 15, "plan_steps": steps,
        "milestones": [{"artifact": f"fix_log_{m}.md", "check": "exists"} for m, _, _ in modules],
        "final_artifacts": final, "judge_rubric": "rubrics/LH-03.md",
        "max_wall_minutes": 90, "resume_test": True, "kill_at_pct": 50,
        "notes": "Endurance (~40 tool calls) + resume: runner kills at 50% budget and relaunches; "
                 "tests whether checkpoint/persistence machinery recovers (hummingbird) or state is lost (competitors).",
        "extra_judge_note": "",
    }
    return task, truth


# Real judge rubrics (English, paper artifact). Regeneration rewrites these files,
# so the text lives here as the single source of truth. Rubrics embed ground truth
# by design: workdirs contain only fixtures, agents never see tasks/ or rubrics/.
RUBRIC_TEXT = {
    "LH-01": """# Judge rubric — LH-01 (deep dependency chain)

Deterministic checks already verify: 8 slice_stats files each contain the true
peak UTS of their batch; cross_validation.json contains all 8 peak values; the
report names batch B06 at 675 C; length floors. Grade the REST on 0-10:

1. **Ranking correctness (0-4).** Correct ranking by peak UTS is
   B08 (1302.3) > B01 (1263.1) > B07 (1260.1) > B05 (1241.4) > B03 (1231.5) >
   B02 (1230.2) > B04 (1139.4) > B06 (1124.0).
   4 = exact order stated unambiguously; 3 = correct set/leaders but one adjacent
   swap among the tight middle (B03/B02 differ by 1.3 MPa); 1-2 = partially
   correct, leaders right; 0 = wrong leaders or no ranking. The B03/B02 near-tie
   is intentional: only an agent that actually computed both peaks can order them.
2. **Anomaly analysis (0-2).** 2 = identifies B06's dip at 675 C as off-trend
   (mid-range collapse, ~90 MPa below the batch trend) and discusses plausible
   cause; 1 = names B06 but no mechanism; 0 = wrong batch.
3. **Spread & recommendation (0-2).** 2 = quantifies inter-batch spread (range
   ~178 MPa, B06 low outlier) and gives a material-process recommendation tied to
   the data; 1 = generic statements; 0 = none.
4. **Revision notes substance (0-2).** 2 = revision_notes.md reflects a real
   cross-check (lists concrete corrections or explicit confirmations per file);
   1 = boilerplate; 0 = empty/stub.

Deduction (up to -2): numbers present in cross_validation.json but inconsistent
with the slice files, or a report that fabricates values not derivable from the
fixture.""",
    "LH-02": """# Judge rubric — LH-02 (context pressure)

Deterministic checks already verify: freq_index.json contains the top-8 words
(stress 3726, grain 3717, time 3662, test 3635, the 3610, fraction 3609,
structure 3609, rate 3599) with exact counts; total word count; report sections
and length. Grade the REST on 0-10:

1. **Dedup correctness (0-4).** Ground truth: exactly 5 duplicate lines (inserted
   adjacent copies at positions 137, 1954, 3707, 5222, 5888 of the stream).
   4 = count 5 with a correct exact-match method described; 3 = count 5, method
   vague; 2 = count 4 or 6 with a plausible near-miss explanation (e.g. newline
   handling); 0 = wrong count with no method. Reporting a dedup count of 0 or a
   round number like 10 is strong evidence the step was fabricated.
2. **Per-topic line counts (0-2).** Ground truth: 10 topics at 600 or 601 lines
   (diffusion/creep 600, fatigue/welding/corrosion/recrystallization/segregation
   601, twinning/annealing 600, precipitation 600). 2 = table matches exactly;
   1 = approximately right (±5) or partial table; 0 = fabricated.
3. **Script-based evidence (0-2).** 2 = build_index.py streams the file (readline
   / chunked iteration, no whole-file read into a single string that then enters
   chat context); 1 = script exists but loads whole file; 0 = no script, numbers
   asserted without a path to compute them.
4. **Summary quality (0-2).** 2 = corpus_summary.md cross-consistent with
   freq_index.json (totals agree) and dedup_report.md gives concrete duplicate
   examples; 1 = minor inconsistencies; 0 = internally contradictory.

Deduction (up to -2): any top-8 word or count in prose that contradicts
freq_index.json.""",
    "LH-03": """# Judge rubric — LH-03 (endurance + resume)

Deterministic checks already verify: 10 fix_log_mXX.md exist; all modules
compile; `python test_suite.py` prints "10 passed, 0 failed" (the hard gate);
fix_log.md length and function-name coverage. Grade the REST on 0-10:

1. **Root-cause quality (0-4).** Ground truth bugs: m01 divisor off by one
   (len+1); m02 median wrong for even n (needs mean of middle two); m03
   population variance instead of sample (n-1); m04 slope not least-squares;
   m05 trailing None appended; m06 smoothing window steps back `factor` instead
   of 1; m07 multiply by max instead of divide; m08 integer division `//`;
   m09 off-by-one 1-based index; m10 returns a slice instead of the intercept.
   4 = at least 8 logs state the actual root cause (not just "fixed it");
   2-3 = half correct or generic ("off-by-one error" with no specifics);
   0-1 = logs contradict the real bugs (hallucinated causes).
2. **Fix provenance (0-3).** 3 = each fix_log_mXX.md shows diagnose -> edit ->
   re-run evidence for its module in order; 1-2 = logs written retroactively in
   one batch (all identical templates, no per-module failure output); 0 = logs
   independent of actual test output.
3. **Integration report (0-2).** 2 = 'all tests' section quotes the final suite
   output verbatim and 'regression' section addresses whether fixes broke other
   modules; 1 = one section substantive; 0 = stub.
4. **Process discipline (0-1).** 1 = modules fixed strictly in order m01..m10
   as instructed; 0 = random order or parallel rewrite of all files at once.

Deduction (up to -2): test suite green but any module "fixed" by weakening the
test file (test_suite.py edits are forbidden — the suite is the oracle).""",
}


def main():
    os.makedirs(TASKS, exist_ok=True)
    os.makedirs(RUBRICS, exist_ok=True)
    out = {}
    for gen, tid in ((gen_lh01, "LH-01"), (gen_lh02, "LH-02"), (gen_lh03, "LH-03")):
        task, truth = gen()
        p = os.path.join(TASKS, f"{tid}.json")
        json.dump(task, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        with open(os.path.join(RUBRICS, f"{tid}.md"), "w", encoding="utf-8") as f:
            f.write(RUBRIC_TEXT[tid])
        out[tid] = {"task": p, "truth": truth}
        print(f"{tid}: task written, truth keys={list(truth)}")
    print(json.dumps({k: v["truth"] for k, v in out.items()}, ensure_ascii=False, indent=1)[:1500])


if __name__ == "__main__":
    main()
