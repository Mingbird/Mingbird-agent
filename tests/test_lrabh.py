# -*- coding: utf-8 -*-
"""LRAB-H (tier4 long-horizon) scoring-thickening tests.

Covers the new deterministic check kinds (contains_groups / contains_ordered /
script_pass), LH task-JSON integrity, and the red-green proof that thickened
checks separate shortcut workdirs from real-work workdirs.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LRAB = os.path.join(ROOT, "bench", "lrab")
sys.path.insert(0, os.path.join(LRAB, "scoring"))
sys.path.insert(0, os.path.join(LRAB, "runners"))

from score_task import check_one, score_group, score_task  # noqa: E402

KNOWN_KINDS = {"exists", "contains_any", "contains_groups", "contains_ordered",
               "not_contains", "min_words", "structure", "python_compiles",
               "script_pass", "file_min_bytes", "min_urls", "image_valid"}
LH_IDS = ["LH-01", "LH-02", "LH-03"]


def lh_path(tid):
    return os.path.join(LRAB, "tasks", "tier4_longhorizon", f"{tid}.json")


def load_lh(tid):
    with open(lh_path(tid), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- check kinds
def test_contains_groups_full_and_partial(tmp_path):
    p = tmp_path / "out.json"
    p.write_text('{"a": 1263.1, "b": 1230.2}', encoding="utf-8")
    chk = {"check": "contains_groups",
           "params": {"groups": [["1263", "1263.1"], ["1230", "1230.2"]],
                      "min_ratio": 1.0}}
    sc, detail = check_one(chk, str(tmp_path), p.name)
    assert sc == 1.0
    chk["params"]["groups"].append(["9999", "9,999"])
    sc, detail = check_one(chk, str(tmp_path), p.name)
    assert 0.0 < sc < 1.0          # graded ratio, capped below 1.0
    assert "2/3" in detail


def test_contains_groups_min_ratio_gate(tmp_path):
    p = tmp_path / "out.txt"
    p.write_text("only one", encoding="utf-8")
    chk = {"check": "contains_groups",
           "params": {"groups": [["one"], ["two"], ["three"]], "min_ratio": 0.99}}
    sc, _ = check_one(chk, str(tmp_path), p.name)
    assert sc < 0.5                # 1/3 ratio, gated below 1.0


def test_contains_ordered(tmp_path):
    p = tmp_path / "report.md"
    p.write_text("leader B08 then runner-up B01 and tail B06", encoding="utf-8")
    ok = {"check": "contains_ordered", "params": {"ordered": ["B08", "B01", "B06"]}}
    sc, _ = check_one(ok, str(tmp_path), p.name)
    assert sc == 1.0
    bad = {"check": "contains_ordered", "params": {"ordered": ["B06", "B08"]}}
    sc, detail = check_one(bad, str(tmp_path), p.name)
    assert sc == 0.0               # B06 appears before B08


def test_script_pass(tmp_path):
    (tmp_path / "t.py").write_text("print('3 passed, 0 failed')", encoding="utf-8")
    chk = {"check": "script_pass",
           "params": {"command": f'"{sys.executable}" t.py',
                      "expect_stdout": "3 passed, 0 failed", "timeout_s": 60}}
    sc, detail = check_one(chk, str(tmp_path), "t.py")
    assert sc == 1.0, detail
    chk["params"]["expect_stdout"] = "all green"
    sc, _ = check_one(chk, str(tmp_path), "t.py")
    assert sc == 0.0


# ------------------------------------------------------------ task integrity
@pytest.mark.parametrize("tid", LH_IDS)
def test_lh_task_json_integrity(tid):
    task = load_lh(tid)
    assert task["id"] == tid
    assert task["milestones"] and task["final_artifacts"]
    for entry in task["milestones"] + task["final_artifacts"]:
        assert entry["check"] in KNOWN_KINDS, f"{tid}: unknown kind {entry['check']}"
        assert entry.get("artifact")
    for rel in task.get("fixtures", []):
        assert os.path.exists(os.path.join(LRAB, rel)), f"{tid}: fixture {rel} missing"
    rubric = os.path.join(LRAB, task["judge_rubric"])
    assert os.path.exists(rubric), f"{tid}: rubric missing"
    text = open(rubric, encoding="utf-8").read()
    assert "reserved for LLM-judge mode" not in text, f"{tid}: rubric still placeholder"
    assert len(text) > 1000, f"{tid}: rubric too thin"


def test_lh03_declares_kill_resume():
    task = load_lh("LH-03")
    assert task.get("kill_at_pct") == 50
    assert task.get("resume_test") is True
    kinds = {e["check"] for e in task["final_artifacts"]}
    assert "script_pass" in kinds   # end-to-end green gate


def test_lh01_truth_embedded_in_checks():
    task = load_lh("LH-01")
    cv_groups = [e for e in task["final_artifacts"]
                 if e["artifact"] == "cross_validation.json"
                 and e["check"] == "contains_groups"]
    assert len(cv_groups) == 1 and len(cv_groups[0]["params"]["groups"]) == 8
    # anomaly (B06 @ 675C) must be checked in the report
    anomaly = [e for e in task["final_artifacts"]
               if e["artifact"] == "master_report.md" and e["check"] == "contains_groups"]
    assert any("B06" in g for grp in anomaly for g in grp["params"]["groups"])


# ------------------------------------------------------------------ helpers
def _group_score(workdir, group):
    sc, _ = score_group(workdir, group)
    return sc


# ------------------------------------------------------- LH-01 red vs green
def _lh01_red_workdir(tmp_path):
    """Satisfies the OLD weak checks (files exist, report long) but does no real
    work: empty slices, empty cross-validation, filler report with no truth."""
    task = load_lh("LH-01")
    for b in range(1, 9):
        (tmp_path / f"slice_stats_B{b:02d}.md").write_text("", encoding="utf-8")
    (tmp_path / "slice_aggregate.py").write_text("print('todo')\n", encoding="utf-8")
    (tmp_path / "cross_validation.json").write_text("{}", encoding="utf-8")
    filler = ("This report summarizes the multi-batch analysis. " * 90)
    (tmp_path / "master_report.md").write_text(filler, encoding="utf-8")
    (tmp_path / "revision_notes.md").write_text(
        "Checked all slice files against the aggregate; nothing to correct.", encoding="utf-8")
    return task


def test_lh01_red_green_separation(tmp_path):
    task = _lh01_red_workdir(tmp_path)
    red = score_task(lh_path("LH-01"), str(tmp_path), judge=False)
    # OLD weak protocol on the same red workdir: exists-only milestones +
    # exists/length final would have scored ~1.0 (the gap this thickening closes)
    old_ms = [{"artifact": f"slice_stats_B{b:02d}.md", "check": "exists"}
              for b in range(1, 9)]
    old_final = [{"artifact": "cross_validation.json", "check": "exists"},
                 {"artifact": "master_report.md", "check": "min_words",
                  "params": {"min_words": 400}}]
    old_total = (0.4 * _group_score(str(tmp_path), old_ms)
                 + 0.3 * _group_score(str(tmp_path), old_final)) / 0.7
    assert old_total >= 0.99, "red workdir should have passed the OLD checks"
    assert red["milestone_score"] == 0.0          # empty slices carry no truth
    assert red["total"] < 0.35, red["total"]

    # GREEN: same artifacts with real values (variants taken from task JSON)
    peak = {"B01": "1263.1", "B02": "1230.2", "B03": "1231.5", "B04": "1139.4",
            "B05": "1241.4", "B06": "1124.0", "B07": "1260.1", "B08": "1302.3"}
    for b, v in peak.items():
        (tmp_path / f"slice_stats_{b}.md").write_text(
            f"peak UTS = {v} MPa\n", encoding="utf-8")
    (tmp_path / "cross_validation.json").write_text(
        json.dumps({"peaks": peak,
                    "ranking": ["B08", "B01", "B07", "B05", "B03", "B02", "B04", "B06"]}),
        encoding="utf-8")
    (tmp_path / "master_report.md").write_text(
        "Ranking: B08 (1302.3) first, B01 second, B07 third. Anomaly: batch B06 "
        "at 675 C shows a 90 MPa dip. " +
        "Recommendation: re-run B06 homogenization and validate the 675 C step. " * 12 +
        "Spread across batches spans about 178 MPa from B06 to B08. " * 25,
        encoding="utf-8")
    (tmp_path / "revision_notes.md").write_text(
        "Cross-checked every slice_stats file against cross_validation.json; all "
        "eight peak values match, ranking order confirmed, no corrections needed. "
        "Slice peaks reproduce the aggregate exactly.",
        encoding="utf-8")
    green = score_task(lh_path("LH-01"), str(tmp_path), judge=False)
    assert green["milestone_score"] == 1.0
    assert green["final_score"] == 1.0
    assert green["total"] - red["total"] > 0.4


# ------------------------------------------------------- LH-02 red vs green
def test_lh02_red_green_separation(tmp_path):
    task = load_lh("LH-02")
    (tmp_path / "build_index.py").write_text("print('todo')\n", encoding="utf-8")
    (tmp_path / "freq_index.json").write_text('{"top": []}', encoding="utf-8")
    (tmp_path / "dedup_report.md").write_text("method " * 200, encoding="utf-8")
    (tmp_path / "corpus_summary.md").write_text(
        "## topic\nlines per topic listed\n## duplicate\n5 duplicates\n71,867 words",
        encoding="utf-8")
    red = score_task(lh_path("LH-02"), str(tmp_path), judge=False)
    assert red["milestone_score"] == 0.0      # top-4 real words absent
    assert red["total"] < 0.45, red["total"]

    top8 = {"stress": 3726, "grain": 3717, "time": 3662, "test": 3635,
            "the": 3610, "fraction": 3609, "structure": 3609, "rate": 3599}
    (tmp_path / "freq_index.json").write_text(json.dumps(
        {"top8": top8, "total_words": 71867}), encoding="utf-8")
    green = score_task(lh_path("LH-02"), str(tmp_path), judge=False)
    assert green["milestone_score"] == 1.0
    assert green["final_score"] == 1.0
    assert green["total"] - red["total"] > 0.4


# ------------------------------------------------------- LH-03 red vs green
FIXED_BODIES = {
    "calc_mean": "return sum(values) / len(values)",
    "calc_median": ("vs = sorted(values)\n    n = len(vs)\n"
                    "    return vs[n//2] if n % 2 else (vs[n//2-1] + vs[n//2]) / 2"),
    "calc_variance": ("m = sum(values) / len(values)\n"
                      "    return sum((v - m) ** 2 for v in values) / (len(values) - 1)"),
    "calc_slope": ("n = len(values)\n    mx = (n - 1) / 2\n    my = sum(values) / n\n"
                   "    den = sum((i - mx) ** 2 for i in range(n))\n"
                   "    return sum((i - mx) * (v - my) for i, v in enumerate(values)) / den"),
    "calc_interp": ("out = []\n    for i in range(len(values) - 1):\n"
                    "        out.append(values[i] + (values[i + 1] - values[i]) * factor)\n"
                    "    return out"),
    "calc_smooth": ("out = []\n    for i in range(len(values)):\n        if i == 0:\n"
                    "            out.append(values[0])\n        else:\n"
                    "            out.append((values[i] + values[i - 1]) / 2)\n    return out"),
    "calc_normalize": "mx = max(values)\n    return [v / mx for v in values]",
    "calc_integrate": ("total = 0.0\n    for i in range(len(values) - 1):\n"
                       "        total += (values[i] + values[i + 1]) / 2\n    return total"),
    "calc_roots": ("lo = 0\n    for i, v in enumerate(values):\n"
                   "        if v < factor:\n            lo = i + 1\n    return lo"),
    "calc_fit": ("n = len(values)\n    mx = (n - 1) / 2\n    my = sum(values) / n\n"
                 "    den = sum((i - mx) ** 2 for i in range(n))\n"
                 "    slope = sum((i - mx) * (v - my) for i, v in enumerate(values)) / den\n"
                 "    return my - slope * mx"),
}
MODULE_FUNCS = [("m01", "calc_mean"), ("m02", "calc_median"), ("m03", "calc_variance"),
                ("m04", "calc_slope"), ("m05", "calc_interp"), ("m06", "calc_smooth"),
                ("m07", "calc_normalize"), ("m08", "calc_integrate"),
                ("m09", "calc_roots"), ("m10", "calc_fit")]


def _stage_lh03_workdir(tmp_path, fixed):
    task = load_lh("LH-03")
    for rel in task["fixtures"]:
        src = os.path.join(LRAB, rel)
        dst = tmp_path / os.path.basename(rel)
        dst.write_text(open(src, encoding="utf-8").read(), encoding="utf-8")
    if fixed:
        for mod, fn in MODULE_FUNCS:
            (tmp_path / f"{mod}.py").write_text(
                f"def {fn}(values, factor=1.0):\n    {FIXED_BODIES[fn]}\n", encoding="utf-8")
        for mod, _ in MODULE_FUNCS:
            (tmp_path / f"fix_log_{mod}.md").write_text(
                f"### {mod}\nbug, root cause, fix (test log).\n", encoding="utf-8")
    return task


def test_lh03_red_green_separation(tmp_path):
    # RED: fixtures as shipped (10 bugs) — logs exist but suite cannot go green
    _stage_lh03_workdir(tmp_path, fixed=False)
    (tmp_path / "fix_log.md").write_text("words " * 120, encoding="utf-8")
    (tmp_path / "integration_report.md").write_text(
        "## all tests\n10 failed\n## regression\nnone\n", encoding="utf-8")
    red = score_task(lh_path("LH-03"), str(tmp_path), judge=False)
    gate = [d for d in red["final_details"] if d["check"] == "script_pass"][0]
    assert gate["score"] == 0.0, "buggy fixtures must fail the green gate"
    assert red["total"] < 0.6, red["total"]

    # GREEN: all 10 modules actually fixed — hard gate passes
    green_dir = tmp_path.parent / (tmp_path.name + "_green")
    green_dir.mkdir()
    _stage_lh03_workdir(green_dir, fixed=True)
    (green_dir / "fix_log.md").write_text("words " * 120, encoding="utf-8")
    (green_dir / "integration_report.md").write_text(
        "## all tests\n10 passed, 0 failed\n## regression\nnone\n", encoding="utf-8")
    green = score_task(lh_path("LH-03"), str(green_dir), judge=False)
    gate = [d for d in green["final_details"] if d["check"] == "script_pass"][0]
    assert gate["score"] == 1.0, gate["detail"]
    assert green["total"] - red["total"] > 0.3


# ------------------------------------------------- run_bench kill-resume bits
def test_make_cmd_contract(tmp_path):
    import run_bench as rb
    task = {"id": "X", "prompt": "p"}
    wd = str(tmp_path / "wd")
    for agent in ("hummingbird", "opencode", "agent-mini", "goose"):
        cmd, env, cwd, cleanup = rb._make_cmd(agent, task, wd, "m")
        assert cmd and all(isinstance(c, str) for c in cmd)
        assert isinstance(env, dict) and cwd
    cmd, _, _, _ = rb._make_cmd("hummingbird", task, wd, "m")
    assert "--new" not in cmd          # checkpoint resume must stay reachable


def test_tree_kill_terminates_child():
    import run_bench as rb
    p = rb._spawn([sys.executable, "-c", "import time; time.sleep(120)"],
                  env=dict(os.environ), cwd=os.getcwd())
    assert p.poll() is None
    rb._tree_kill(p)
    rc = p.wait(timeout=30)
    assert rc is not None and rc != 0
