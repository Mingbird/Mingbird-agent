#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate MANIFEST.json for LRAB run archives.

Scans both archive roots (eval_results/ canonical + bench/lrab/results/ dev smoke),
reads each run's score.json (or marks state), classifies each run by its id pattern,
and writes a single MANIFEST.json so paper/HN data provenance is auditable.

Run-status classification (by run-id prefix):
  - canonical : matrix run via run_bench.py into eval_results/ (no prefix)
  - smoke     : smoke{N}_* / verify_* / m1_* pre-fix dev runs (excluded from published matrix)
  - pre-fix   : runs from before the isolation fix (2631765), marked invalid for publication
"""
import json, os, re, glob, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LRAB = HERE
ROOTS = {
    "eval": os.path.expanduser("~/dev/hummingbird/eval_results"),
    "dev": os.path.join(LRAB, "results"),
}

def classify(run_id, root_key):
    """Best-effort status from run-id + which archive root it lives in.
    Policy: only eval_results/ runs with a scored, non-failure result are
    canonical-publishable; everything else (dev results/, verify/smoke, failures)
    is excluded from the published matrix. Canonical is decided by score content,
    not run-id prefix (fixes self-review P0-3: goose runs were mislabeled, and the
    opencode-e2b fix2 run was excluded while the broken 0.0 run was canonical)."""
    if root_key == "dev":
        return "pre-fix", "dev/pre-isolation run, excluded from published matrix"
    low = run_id.lower()
    # verify_*_fix* 是修复后 adapter 的合法重跑(如 opencode-e2b 0.429), 视为矩阵 run
    if "fix" in low and low.startswith("verify_"):
        return "canonical", "matrix run (post-fix rerun)"
    if low.startswith(("smoke", "verify", "m1_", "oc_", "am_")):
        return "pre-fix", "dev smoke run in eval archive, excluded from published matrix"
    return "canonical", "matrix run"

def classify_score(s):
    """Re-classify a run from its score.json content. Returns (status, note)."""
    fm = s.get("failure_mode", "completed")
    if fm in ("timeout", "stall", "crash", "no_artifacts", "early_finish"):
        return "failed", f"failure_mode={fm}, excluded from published matrix"
    if s.get("total") is None or s.get("total") < 0:
        return "invalid", "missing/invalid total"
    return "canonical", "matrix run"

def scan(root, root_key):
    runs = []
    if not os.path.isdir(root):
        return runs
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if not os.path.isdir(p):
            continue
        score_path = os.path.join(p, "score.json")
        entry = {"run_id": d, "dir": d}
        if os.path.exists(score_path):
            try:
                s = json.load(open(score_path, encoding="utf-8"))
                entry.update({
                    "agent": s.get("agent"), "model": s.get("model"),
                    "task": s.get("task_id"), "milestone_score": s.get("milestone_score"),
                    "final_score": s.get("final_score"), "total": s.get("total"),
                    "wall_seconds": s.get("wall_seconds"), "exit_code": s.get("exit_code"),
                    "failure_mode": s.get("failure_mode", "completed"),
                    "scored": True,
                })
            except Exception as e:
                entry.update({"scored": False, "note": f"score unreadable: {e}"})
        else:
            entry.update({"scored": False, "note": "no score.json (incomplete run)"})
        st, note = classify(d, root_key)
        # 已评分的 run: 用 score 内容精确判定(失败模式 → failed; 正常 → canonical)
        if entry.get("scored") and st == "canonical":
            st, note = classify_score(entry)
        entry["status"] = st
        if st != "canonical" and "note" not in entry:
            entry["note"] = note
        runs.append(entry)
    return runs

def main():
    manifest = {
        "schema": "lrab-manifest-v1",
        "generated_at_local": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "archive_policy": "eval_results/ is canonical; bench/lrab/results/ is dev-only. "
                          "Pre-fix runs are excluded from the published matrix.",
        "runs": {},
    }
    for key, root in ROOTS.items():
        manifest["runs"][key] = scan(root, key)
    out = os.path.join(LRAB, "MANIFEST.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    n = sum(len(v) for v in manifest["runs"].values())
    print(f"MANIFEST.json: {n} runs indexed")
    for key, runs in manifest["runs"].items():
        canon = sum(1 for r in runs if r["status"] == "canonical")
        pref  = sum(1 for r in runs if r["status"] == "pre-fix")
        print(f"  {key:5s}: {len(runs)} total ({canon} canonical, {pref} pre-fix)")

if __name__ == "__main__":
    main()
