"""Recompute the comparison study's tables from the raw cells and compare.

Nine checks, added over two sessions as each table got one: the span table, the
contrast table, the failure forms, the mechanism gradient, both panels of the
ladder, the served-model metadata, the task declarations, the discrimination
counts the study states as instrument properties, and the check-type census.

Everything except `tab:bmodels` is a function of the published cells or the task
files alone, so it can be recomputed without any of the analysis code, and that
is what this does. `tab:bmodels` reads the live server instead, because the
caption says those numbers come from the served artifacts.

What it caught the first time it ran:

- `tab:span` printed 0.382 for the 1.9B best gap where the cells give 0.3814.
  Because goose is the strongest arm at that rung, the best gap must equal the
  goose gap, which the same table printed as 0.381. The wrong value came from
  the revision plan and had been copied into the table and the text.
- `tab:bgradient` was missing a whole row. Fifty-four cells at 3.7B had been
  collected after the design section was written, and the section still said the
  ablation "does not run at 3.7B". Checking a table means checking how many rows
  it should have, not only whether the rows it has are right. The gradient is
  checked here too.

Bootstrap intervals are not recomputed. They need the block-resampling code in
`analyze_comparison.py`, and re-implementing it here would be a second method with
the same assumptions rather than an independent one. What this rules out is the
cheaper failure: a table that drifted from the cells.

The `_` prefix filter is load-bearing. Directories beginning with an underscore
hold superseded attempts; counting them once produced a 396 against the study's
395 and sent a wrong correction into the study.

    python -I experiments/scripts/verify_tables.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import math
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

# Set COMPARISON_ROOT to point at a tree holding experiments/results/; the default
# is the layout this script was developed in, two directories above its own.
ROOT = os.path.abspath(os.environ.get("COMPARISON_ROOT")
                       or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MATRIX = os.path.join(ROOT, "experiments", "results", "b_matrix")
GRADIENT = os.path.join(ROOT, "experiments", "results", "b_gradient")
TASKS = os.path.join(ROOT, "experiments", "tasks_heldout")
TOL = 0.0006  # tables print three decimals

LADDER = {"qwen3.5:0.8b": "0.75", "qwen3.5:2b": "1.9",
          "granite4.2:3b": "3.7", "qwen3.5:4b": "4.7"}
ARMS = ("mingbird", "pi", "opencode", "goose", "mini")


def load_matrix() -> dict:
    rows = collections.defaultdict(dict)
    for p in glob.glob(os.path.join(MATRIX, "*", "score.json")):
        if os.path.basename(os.path.dirname(p)).startswith("_"):
            continue
        j = json.load(open(p, encoding="utf-8"))
        model, arm, task = j.get("model"), j.get("agent"), j.get("task_id")
        if not (model and arm and task):
            continue
        v = j.get("total")
        rows[(model, arm)][task] = float(v) if isinstance(v, (int, float)) else 0.0
    return rows


def mean(d: dict) -> float:
    return sum(d.values()) / len(d)


def check_span(rows: dict) -> int:
    """tab:span: span, goose gap, best gap, and the saturated count per rung."""
    exp = [("0.75", 0.441, 0.386, 0.314, 0), ("1.9", 0.747, 0.381, 0.381, 2),
           ("3.7", 0.774, 0.707, 0.564, 0), ("4.7", 0.904, 0.196, 0.146, 10)]
    print("tab:span — span, gaps, and tasks both Mingbird and goose solve")
    print(f"  {'rung':5s} {'span':>7s} {'exp':>7s} {'goose':>7s} {'exp':>7s} "
          f"{'best':>7s} {'exp':>7s} {'sat':>4s} {'exp':>4s}")
    bad = 0
    for rung, e_span, e_goose, e_best, e_sat in exp:
        model = next(m for m, r in LADDER.items() if r == rung)
        means = {a: mean(rows[(model, a)]) for a in ARMS if rows.get((model, a))}
        span = max(means.values()) - min(means.values())
        goose = means["mingbird"] - means["goose"]
        best = means["mingbird"] - max(v for a, v in means.items() if a != "mingbird")
        mb, go = rows[(model, "mingbird")], rows[(model, "goose")]
        sat = sum(1 for t in mb if mb[t] >= 1 - 1e-9 and go.get(t, 0) >= 1 - 1e-9)
        flags = [f"{n} {g:+.4f}!={e:+.4f}" for g, e, n in
                 ((span, e_span, "span"), (goose, e_goose, "goose"),
                  (best, e_best, "best")) if abs(g - e) > TOL]
        if sat != e_sat:
            flags.append(f"saturated {sat}!={e_sat}")
        if flags:
            bad += 1
        print(f"  {rung:5s} {span:7.3f} {e_span:7.3f} {goose:+7.3f} {e_goose:+7.3f} "
              f"{best:+7.3f} {e_best:+7.3f} {sat:4d} {e_sat:4d}"
              + ("   MISMATCH " + "; ".join(flags) if flags else ""))
    return bad


def check_contrast(rows: dict) -> int:
    """tab:contrast, deployment reading: mean paired difference per rung."""
    exp = {
        "0.75": {"pi": 0.314, "opencode": 0.441, "goose": 0.386, "mini": 0.441},
        "1.9": {"pi": 0.448, "opencode": 0.437, "goose": 0.381, "mini": 0.747},
        "3.7": {"pi": 0.564, "opencode": 0.774, "goose": 0.707, "mini": 0.766},
        "4.7": {"pi": 0.146, "opencode": 0.397, "goose": 0.196, "mini": 0.904},
    }
    print("\ntab:contrast — paired difference against each baseline")
    bad = 0
    for model, rung in LADDER.items():
        mb = rows[(model, "mingbird")]
        for arm in ("pi", "opencode", "goose", "mini"):
            other = rows[(model, arm)]
            common = sorted(set(mb) & set(other))
            d = sum(mb[t] - other[t] for t in common) / len(common)
            e = exp[rung][arm]
            if abs(d - e) > TOL:
                bad += 1
                print(f"  {rung:5s} {arm:9s} {d:+.4f} != {e:+.3f}   MISMATCH")
    print(f"  16 point estimates checked, {bad} mismatched")
    return bad


def check_failures(rows: dict) -> int:
    """tab:bfailures: artefact state and termination, per harness."""
    declared = {}
    for p in glob.glob(os.path.join(TASKS, "*", "*.json")):
        j = json.load(open(p, encoding="utf-8"))
        names = [a["artifact"] for a in j.get("final_artifacts", [])]
        names += [a["artifact"] for a in j.get("milestones", [])]
        declared[j["id"]] = names

    agg = collections.defaultdict(collections.Counter)
    for p in glob.glob(os.path.join(MATRIX, "*", "score.json")):
        cell = os.path.basename(os.path.dirname(p))
        if cell.startswith("_"):
            continue
        j = json.load(open(p, encoding="utf-8"))
        if j.get("model") not in LADDER:
            continue
        names = declared.get(j.get("task_id"), [])
        if not names:
            continue
        wd = os.path.join(os.path.dirname(p), "workdir")
        n = sum(1 for a in names if os.path.isfile(os.path.join(wd, a)))
        a = agg[j.get("agent")]
        a["complete" if n == len(names) else ("none" if n == 0 else "partial")] += 1
        if n == 0:
            mode = j.get("failure_mode")
            a["finished" if mode == "completed"
              else ("budget" if mode == "timeout" else "other")] += 1

    exp = {"mingbird": (49, 18, 5, 5, 0, 0), "pi": (30, 20, 22, 18, 1, 3),
           "opencode": (13, 20, 39, 27, 12, 0), "goose": (19, 21, 32, 22, 8, 2),
           "mini": (1, 17, 54, 34, 11, 9)}
    print("\ntab:bfailures — complete / partial / none, and how the empty cells ended")
    print(f"  {'harness':10s} {'C':>3s}{'P':>4s}{'N':>4s} {'fin':>4s}{'bud':>4s}{'oth':>4s}")
    bad = 0
    for arm in ARMS:
        a = agg[arm]
        got = (a["complete"], a["partial"], a["none"],
               a["finished"], a["budget"], a["other"])
        if got != exp[arm]:
            bad += 1
        print(f"  {arm:10s} {got[0]:3d}{got[1]:4d}{got[2]:4d} "
              f"{got[3]:4d}{got[4]:4d}{got[5]:4d}"
              + ("   MISMATCH" if got != exp[arm] else ""))
    return bad


def check_gradient() -> int:
    """tab:bgradient: four rungs, three arms, and the guards difference."""
    exp = {"0.75": (0.470, 0.317, 0.181, 0.152, 0.136),
           "1.9": (0.723, 0.574, 0.619, 0.149, -0.045),
           "3.7": (0.977, 0.875, 0.811, 0.101, 0.064),
           "4.7": (0.929, 0.928, 0.955, 0.001, -0.027)}
    rows = collections.defaultdict(dict)
    for p in glob.glob(os.path.join(GRADIENT, "g_*", "score.json")):
        if os.path.basename(os.path.dirname(p)).startswith("_"):
            continue
        j = json.load(open(p, encoding="utf-8"))
        rid = j.get("run_id", "")
        var = rid[2:].rsplit("_", 2)[0] if rid.startswith("g_") else "?"
        # run ids are g_<variant>_<model>_<task>; the model carries a hyphen
        for v in ("guards_off", "text_only", "full"):
            if rid.startswith(f"g_{v}_"):
                var = v
                break
        v = j.get("total")
        rows[(j.get("model"), var)][j.get("task_id")] = \
            float(v) if isinstance(v, (int, float)) else 0.0

    print("\ntab:bgradient — three arms and the guards difference per rung")
    print(f"  {'rung':5s} {'full':>6s} {'guard':>6s} {'text':>6s} "
          f"{'guards':>7s} {'remind':>7s}")
    bad = 0
    for model, rung in LADDER.items():
        f, g, t = rows[(model, "full")], rows[(model, "guards_off")], rows[(model, "text_only")]
        tasks = sorted(set(f) & set(g) & set(t))
        full, guards, text = mean(f), mean(g), mean(t)
        d_guards = sum(f[x] - g[x] for x in tasks) / len(tasks)
        d_rem = sum(g[x] - t[x] for x in tasks) / len(tasks)
        e = exp[rung]
        got = (full, guards, text, d_guards, d_rem)
        flags = [f"{n} {a:+.3f}!={b:+.3f}" for a, b, n in
                 zip(got, e, ("full", "guard", "text", "guards", "remind"))
                 if abs(a - b) > TOL]
        if flags:
            bad += 1
        print(f"  {rung:5s} {full:6.3f} {guards:6.3f} {text:6.3f} "
              f"{d_guards:+7.3f} {d_rem:+7.3f}"
              + ("   MISMATCH " + "; ".join(flags) if flags else ""))
    return bad


def check_ladder(rows: dict) -> int:
    """tab:ladder: both panels, 40 arm means and eight spans.

    The upper panel is the one the rest of the study reads. The lower one keeps
    the archived working directory of the 30 cells that were stopped at the wall
    budget while already holding artifacts, and scores those directories with
    the same checker; the rescored values come from
    `experiments/analysis/comparison_timeout_rescore.json`.

    The deployment panel also exposes a rounding trap worth knowing about: the
    published gaps are computed from unrounded means, and at 1.9B subtracting
    the two printed values (0.776 - 0.394) gives 0.382 where the same table's
    span gives 0.381. The exact difference is 0.38146. That is a caption
    problem, not a table problem, and the caption now says so.
    """
    deploy = {"0.75": (0.470, 0.156, 0.029, 0.084, 0.029, 0.441),
              "1.9": (0.776, 0.328, 0.338, 0.394, 0.029, 0.747),
              "3.7": (0.830, 0.266, 0.056, 0.123, 0.064, 0.774),
              "4.7": (0.988, 0.842, 0.591, 0.792, 0.084, 0.904)}
    rescored = {"0.75": (0.470, 0.215, 0.029, 0.084, 0.029, 0.441),
                "1.9": (0.776, 0.403, 0.338, 0.394, 0.029, 0.747),
                "3.7": (0.830, 0.772, 0.200, 0.226, 0.144, 0.685),
                "4.7": (0.988, 0.858, 0.635, 0.792, 0.084, 0.904)}
    rs = {}
    rpath = os.path.join(ROOT, "experiments", "analysis", "comparison_timeout_rescore.json")
    if os.path.isfile(rpath):
        for r in json.load(open(rpath, encoding="utf-8")):
            rs[(r["model"], r["harness"], r["task"])] = float(r["total"])
    else:
        print("\ntab:ladder (rescored panel) — SKIPPED, no timeout rescore file")

    print("\ntab:ladder — five arm means and the span per rung, both panels")
    bad = 0
    for model, rung in LADDER.items():
        for label, exp, use_rs in (("deploy", deploy, False), ("rescore", rescored, True)):
            if use_rs and not rs:
                continue
            means = {}
            for a in ARMS:
                tasks = rows.get((model, a), {})
                if not tasks:
                    continue
                vals = [rs.get((model, a, t), v) if use_rs else v for t, v in tasks.items()]
                means[a] = sum(vals) / len(vals)
            if len(means) != len(ARMS):
                bad += 1
                print(f"  {rung:5s} {label:8s} only {len(means)} arms present  MISMATCH")
                continue
            span = max(means.values()) - min(means.values())
            e = exp[rung]
            flags = [f"{a} {means[a]:.4f}!={e[i]:.3f}" for i, a in enumerate(ARMS)
                     if abs(means[a] - e[i]) > TOL]
            if abs(span - e[5]) > TOL:
                flags.append(f"span {span:.4f}!={e[5]:.3f}")
            if flags:
                bad += 1
            print(f"  {rung:5s} {label:8s} " + " ".join(f"{means[a]:.4f}" for a in ARMS)
                  + f"  span {span:.4f}"
                  + ("   MISMATCH " + "; ".join(flags) if flags else ""))
    print(f"  40 means and 8 spans checked, {bad} mismatched")
    return bad


def check_models() -> int:
    """tab:bmodels: five served artifacts against what the server reports.

    The caption says the parameter counts, quantisation and file sizes are read
    from the served artifacts rather than from model names, so the check reads
    them the same way. Needs a live server on 11437; without one it prints
    SKIPPED rather than passing, because a green run that never looked at a
    model would be the most misleading result this script could produce.
    """
    exp = {  # tag: (params, quant, family, size GB, expert count, experts used)
        "qwen3.5:0.8b": ("752.39M", "Q8_0", "qwen35", 1.3, None, None),
        "qwen3.5:2b": ("1.9B", "Q8_0", "qwen35", 2.7, None, None),
        "granite4.2:3b": ("3.7B", "Q4_K_M", "granite", 2.2, None, None),
        "qwen3.5:4b": ("4.7B", "Q4_K_M", "qwen35", 3.4, None, None),
        "ornith-1.5:35b": ("35.5B", "Q4_K_M", "qwen35moe", 22.6, 256, 8),
    }
    try:
        tags = json.load(urllib.request.urlopen("http://127.0.0.1:11437/api/tags", timeout=8))
    except Exception:
        print("\ntab:bmodels — SKIPPED, no server on 11437")
        return 0
    sizes = {m["name"]: m["size"] / 1e9 for m in tags.get("models", [])}
    print("\ntab:bmodels — parameter count, quantisation, family and file size")
    bad = 0
    for tag, (params, quant, fam, gb, n_exp, n_used) in exp.items():
        if tag not in sizes:
            print(f"  {tag:18s} MISSING from the server")
            bad += 1
            continue
        req = urllib.request.Request(
            "http://127.0.0.1:11437/api/show",
            data=json.dumps({"model": tag}).encode(),
            headers={"Content-Type": "application/json"})
        info = json.load(urllib.request.urlopen(req, timeout=15))
        det, mi = info.get("details", {}), info.get("model_info", {})
        flags = []
        if det.get("parameter_size") != params:
            flags.append(f"params {det.get('parameter_size')}!={params}")
        if det.get("quantization_level") != quant:
            flags.append(f"quant {det.get('quantization_level')}!={quant}")
        if det.get("family") != fam:
            flags.append(f"family {det.get('family')}!={fam}")
        if abs(sizes[tag] - gb) > 0.05:
            flags.append(f"size {sizes[tag]:.2f}!={gb}")
        if n_exp is not None:
            got = [v for k, v in mi.items() if k.endswith("expert_count")]
            got = got[0] if got else None
            use = [v for k, v in mi.items() if k.endswith("expert_used_count")]
            use = use[0] if use else None
            if got != n_exp or use != n_used:
                flags.append(f"experts {got}/{use}!={n_exp}/{n_used}")
        if flags:
            bad += 1
        print(f"  {tag:18s} {params:>8s} {quant:7s} {fam:10s} {sizes[tag]:5.2f} GB"
              + ("   MISMATCH " + "; ".join(flags) if flags else ""))
    print(f"  5 artifacts checked, {bad} mismatched")
    return bad


TIER_DIR = {"Retrieval": "tier1_retrieval", "Synthesis": "tier2_synthesis",
            "Workflow": "tier3_workflow", "Long horizon": "tier4_longhorizon"}


def check_tasks() -> int:
    """tab:btasks: tier, fixture count and check count, read from the task files.

    The table is prose-shaped, so this parses the .tex rather than restating it:
    whatever the table says is what gets compared, which is the only way the
    check can catch an edit that quietly changes a row.
    """
    tex = os.environ.get("TABLES_TEX") or os.path.join(
        ROOT, "report", "tables", "btasks.tex")
    if not os.path.isfile(tex):
        print("\ntab:btasks — SKIPPED, table not found")
        return 0
    declared = {}
    for d in os.listdir(TASKS):
        for p in glob.glob(os.path.join(TASKS, d, "*.json")):
            j = json.load(open(p, encoding="utf-8"))
            names = [a["artifact"] for a in j.get("milestones", [])]
            names += [a["artifact"] for a in j.get("final_artifacts", [])]
            declared[j["id"]] = {
                "tier": d,
                "fixtures": len(j.get("fixtures", [])),
                "checks": len(j.get("milestones", [])) + len(j.get("final_artifacts", [])),
                "artifacts": names,
            }

    print("\ntab:btasks — tier, fixtures and declarative checks per task")
    bad = 0
    seen = 0
    for line in open(tex, encoding="utf-8"):
        if "&" not in line or "\\\\" not in line:
            continue
        cells = [c.strip() for c in line.split("&")]
        tid = cells[0]
        if not re.fullmatch(r"H(?:WF|LH)-\d\d", tid):
            continue
        seen += 1
        want = declared.get(tid)
        if not want:
            bad += 1
            print(f"  {tid} not on disk  MISMATCH")
            continue
        flags = []
        if TIER_DIR.get(cells[1]) != want["tier"]:
            flags.append(f"tier {cells[1]}!={want['tier']}")
        if cells[3].rstrip("\\ ").strip() != str(want["fixtures"]):
            flags.append(f"fixtures {cells[3]}!={want['fixtures']}")
        checks = cells[5].rstrip("\\ ").strip()
        if checks != str(want["checks"]):
            flags.append(f"checks {checks}!={want['checks']}")
        first = cells[4].split(",")[0].strip().replace("\\_", "_").rstrip(".")
        if not first.startswith("$") and first not in want["artifacts"]:
            flags.append(f"deliverable {first} not declared")
        if flags:
            bad += 1
            print(f"  {tid} MISMATCH " + "; ".join(flags))
    print(f"  {seen} rows checked, {bad} mismatched")
    return bad


def check_instrument(rows: dict) -> int:
    """Section 'What the instrument can measure': separation and dead tasks.

    The study states these as the instrument's own measurement properties, so
    they are claims about the cells too: a task separates a rung if the five
    arms do not all land on the same score, and a dead task is zero for every
    arm.
    """
    exp = {"0.75": (15, ["HLH-01", "HWF-13", "HWF-15"]),
           "1.9": (18, []),
           "3.7": (17, ["HWF-08"]),
           "4.7": (18, [])}
    print("\n§instrument — tasks that separate the arms, and tasks nobody solves")
    bad = 0
    for model, rung in LADDER.items():
        tasks = sorted({t for (m, a) in rows if m == model for t in rows[(m, a)]})
        sep, dead = 0, []
        for t in tasks:
            vals = [rows[(model, a)].get(t) for a in ARMS]
            if any(v is None for v in vals):
                continue
            if len(set(vals)) > 1:
                sep += 1
            if all(v == 0 for v in vals):
                dead.append(t)
        e_sep, e_dead = exp[rung]
        ok = sep == e_sep and sorted(dead) == sorted(e_dead)
        if not ok:
            bad += 1
        print(f"  {rung:5s} {sep:2d}/18 separate  dead={sorted(dead)}"
              + ("" if ok else f"   MISMATCH expected {e_sep}/18 dead={e_dead}"))
    print(f"  4 rungs checked, {bad} mismatched")
    return bad


def check_checks() -> int:
    """tab:bchecks: 117 checks in eleven types, counted from the task files.

    The caption makes a claim the count alone cannot support — that an `exists`
    check cannot tell a correct artifact from a plausible one — so this verifies
    the arithmetic and the type names, not the argument.
    """
    exp = {"exists": 44, "contains_any": 25, "python_compiles": 18,
           "min_words": 13, "contains_groups": 5, "structure": 3,
           "image_valid": 3, "min_urls": 3, "not_contains": 1,
           "spec_pytest": 1, "script_pass": 1}
    count = collections.Counter()
    for p in glob.glob(os.path.join(TASKS, "*", "*.json")):
        j = json.load(open(p, encoding="utf-8"))
        for a in j.get("milestones", []) + j.get("final_artifacts", []):
            count[a.get("check")] += 1
    print("\ntab:bchecks — check types and their counts")
    bad = 0
    for k in sorted(set(list(count) + list(exp))):
        got, want = count.get(k, 0), exp.get(k, 0)
        if got != want:
            bad += 1
            print(f"  {k:18s} {got:3d} != {want:3d}  MISMATCH")
    total = sum(count.values())
    if total != 117:
        bad += 1
        print(f"  total {total} != 117  MISMATCH")
    print(f"  117 checks in {len(count)} types, {bad} mismatched")
    return bad


def check_anchor() -> int:
    """The 35.5B anchor: both arms saturate the six-task subset.

    The six are defined by the design as the tasks with the fewest final
    deliverables, ties broken by task id. That rule is applied here rather than
    the task list being hard-coded, so a change to a task's deliverables count
    would move the subset and this check would notice.
    """
    nfa = {}
    for p in glob.glob(os.path.join(TASKS, "*", "*.json")):
        j = json.load(open(p, encoding="utf-8"))
        nfa[j["id"]] = len(j.get("final_artifacts", []))
    six = sorted(nfa, key=lambda t: (nfa[t], t))[:6]
    rows = {}
    for p in glob.glob(os.path.join(MATRIX, "*ornith*", "score.json")):
        if os.path.basename(os.path.dirname(p)).startswith("_"):
            continue
        j = json.load(open(p, encoding="utf-8"))
        rows[(j.get("agent"), j.get("task_id"))] = j.get("total")
    print("\nupper anchor — the six-task subset at 35.5B")
    print(f"  subset: {six}")
    bad = 0
    for t in six:
        pair = (rows.get(("mingbird", t)), rows.get(("goose", t)))
        sat = all(isinstance(v, (int, float)) and v >= 1 - 1e-9 for v in pair)
        if not sat:
            bad += 1
        print(f"  {t}: mingbird={pair[0]} goose={pair[1]}" + ("" if sat else "  NOT SATURATED"))
    print(f"  6 tasks checked, {bad} not saturated")
    return bad


def check_slopes(rows: dict) -> int:
    """tab:span lower panel: four slopes on log10 parameters, two scopes.

    The upper panel was checked from the start and this one was not, which is
    the more exposed half: eight fitted values with no cells behind them that a
    reader could recount. The point estimates are recomputed here; the intervals
    are not, for the same reason the contrast intervals are not — rebuilding the
    block bootstrap in this file would be a second implementation of the same
    assumption, not an independent check.

    A tolerance of 0.002 is allowed because the x axis is a parameter count and
    0.752 against 0.75 for the smallest rung moves the third decimal.
    """
    params = {"qwen3.5:0.8b": 0.752, "qwen3.5:2b": 1.9,
              "granite4.2:3b": 3.7, "qwen3.5:4b": 4.7}
    pts = []
    for model, par in params.items():
        mu = {a: mean(rows[(model, a)]) for a in ARMS if rows.get((model, a))}
        if len(mu) != len(ARMS):
            print("\ntab:span slopes — SKIPPED, a rung is incomplete")
            return 0
        no_mini = [v for a, v in mu.items() if a != "mini"]
        pts.append((math.log10(par),
                    max(mu.values()) - min(mu.values()),
                    max(no_mini) - min(no_mini),
                    mu["mingbird"] - mu["goose"],
                    mu["mingbird"] - max(v for a, v in mu.items() if a != "mingbird")))
    exp = [("span", 0.528, 0.582), ("span -mini", 0.153, -0.055),
           ("goose gap", 0.025, -0.236), ("best gap", -0.011, -0.210)]
    def slope(xs, ys):
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den

    print("\ntab:span slopes — on log10 parameters, all four rungs and Qwen only")
    print(f"  {'quantity':11s} {'all four':>9s} {'report':>7s} {'Qwen':>8s} {'report':>7s}")
    bad = 0
    for i, (name, e_all, e_q) in enumerate(exp, start=1):
        xs = [p[0] for p in pts]
        ys = [p[i] for p in pts]
        a = slope(xs, ys)
        qx = [p[0] for p in pts if p[0] != math.log10(3.7)]
        qy = [p[i] for p in pts if p[0] != math.log10(3.7)]
        q = slope(qx, qy)
        flags = []
        if abs(a - e_all) > 0.002:
            flags.append(f"all {a:+.3f}!={e_all:+.3f}")
        if abs(q - e_q) > 0.002:
            flags.append(f"qwen {q:+.3f}!={e_q:+.3f}")
        if flags:
            bad += 1
        print(f"  {name:11s} {a:+9.3f} {e_all:+7.3f} {q:+8.3f} {e_q:+7.3f}"
              + ("   MISMATCH " + "; ".join(flags) if flags else ""))
    print(f"  8 slopes checked, {bad} mismatched")
    return bad


def main() -> int:
    rows = load_matrix()
    print(f"matrix cells read: {sum(len(v) for v in rows.values())}\n")
    bad = (check_span(rows) + check_contrast(rows) + check_failures(rows)
           + check_gradient() + check_ladder(rows) + check_models()
           + check_tasks() + check_instrument(rows) + check_checks()
           + check_anchor() + check_slopes(rows))
    print(f"\ntotal mismatched checks: {bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
