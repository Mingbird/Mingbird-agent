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
    for b in batches:
        base_t = rng.choice([400, 425, 450, 475, 500, 525])
        slope = rng.uniform(0.8, 1.6)          # UTS per degree above base
        cap = rng.uniform(1350, 1550)
        best = -1e9
        for i in range(625):
            t = base_t + (i % 10) * 25
            h = 2 + (i % 8)
            uts = min(cap, 900 + slope * (t - base_t) + rng.gauss(0, 18))
            if b == "B06" and t == base_t + 150:
                uts -= 90                       # injected anomaly dip (mid-range, off-trend)
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
    milestones = [{"artifact": s, "check": "exists"} for s in slice_files[:4]]
    final = [
        {"artifact": "slice_aggregate.py", "check": "python_compiles"},
        {"artifact": "cross_validation.json", "check": "exists"},
        {"artifact": "master_report.md", "check": "min_words", "params": {"min_words": 400}},
        {"artifact": "master_report.md", "check": "contains_any",
         "params": {"any_of": sum([num_variants(peak[b]) for b in ("B02", "B07")], [])}},
        {"artifact": "revision_notes.md", "check": "exists"},
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
    truth = {"peak_uts_per_batch": peak}
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
        {"artifact": "freq_index.json", "check": "contains_any",
         "params": {"any_of": [w for w, _ in top8[:4]]}},
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
        "milestones": [{"artifact": "freq_index.json", "check": "exists"}],
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
    final = [{"artifact": f"{m}.py", "check": "python_compiles"} for m, _, _ in modules]
    final += [
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
        "prompt": PROMPT_HEAD + "\n\nFix the 10-module signal pipeline in buggy_pipeline_pkg/ "
                  "(each module m01.py..m10.py has exactly one bug). Work strictly module by module.\n\n"
                  "Required steps (plan at least 15):\n" +
                  "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)),
        "required_plan_steps_min": 15, "plan_steps": steps,
        "milestones": [{"artifact": f"fix_log_{m}.md", "check": "exists"} for m, _, _ in modules[:3]],
        "final_artifacts": final, "judge_rubric": "rubrics/LH-03.md",
        "max_wall_minutes": 90, "resume_test": True, "kill_at_pct": 50,
        "notes": "Endurance (~40 tool calls) + resume: runner kills at 50% budget and relaunches; "
                 "tests whether checkpoint/persistence machinery recovers (hummingbird) or state is lost (competitors).",
        "extra_judge_note": "",
    }
    return task, truth


def main():
    os.makedirs(TASKS, exist_ok=True)
    os.makedirs(RUBRICS, exist_ok=True)
    out = {}
    for gen, tid in ((gen_lh01, "LH-01"), (gen_lh02, "LH-02"), (gen_lh03, "LH-03")):
        task, truth = gen()
        p = os.path.join(TASKS, f"{tid}.json")
        json.dump(task, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        with open(os.path.join(RUBRICS, f"{tid}.md"), "w", encoding="utf-8") as f:
            f.write(f"# Judge rubric — {tid}\n\nDeterministic checks only; rubric reserved for LLM-judge mode.\n")
        out[tid] = {"task": p, "truth": truth}
        print(f"{tid}: task written, truth keys={list(truth)}")
    print(json.dumps({k: v["truth"] for k, v in out.items()}, ensure_ascii=False, indent=1)[:1500])


if __name__ == "__main__":
    main()
