#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GAIA pilot driver: run one task on one agent, score with the GAIA scorer.

Reuses bench/lrab/runners/run_bench.py primitives (prepare_workdir /
run_single / wait_for_quiet) untouched — LRAB runner stays frozen as the
audited execution truth. Only the scoring step differs (answer.txt vs the
deterministic GAIA question_scorer).

Usage:
  python run_gaia.py --agent hummingbird --task tasks/GAIA-L1-01.json \
      --model gemma4:e2b --timeout-min 30
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)                     # bench/
HB_ROOT = os.path.dirname(BENCH)                  # ~/dev/hummingbird
RUNNERS = os.path.join(BENCH, "lrab", "runners")
sys.path.insert(0, RUNNERS)
sys.path.insert(0, HERE)

import run_bench as rb            # noqa: E402  (LRAB primitives, untouched)
import gaia_scorer                # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="hummingbird")
    ap.add_argument("--task", required=True)
    ap.add_argument("--model", default="gemma4:e2b")
    ap.add_argument("--results", default=os.path.join(HB_ROOT, "eval_results"))
    ap.add_argument("--timeout-min", type=int, default=30)
    ap.add_argument("--run-id", default="")
    a = ap.parse_args()

    with open(a.task, encoding="utf-8") as f:
        task = json.load(f)

    run_id = a.run_id or (
        f"{a.agent}_GA{task['id'].replace('-', '')}_"
        f"{a.model.split(':')[0].replace(':', '').replace('.', '')}_{time.strftime('%m%d_%H%M%S')}")
    out_dir = os.path.join(a.results, run_id)
    os.makedirs(out_dir, exist_ok=True)
    workdir = os.path.join(out_dir, "workdir")
    rb.prepare_workdir(task, workdir)

    print(f"[{run_id}] agent={a.agent} model={a.model} task={task['id']}", flush=True)
    proc, wall, meta = rb.run_single(a.agent, task, workdir, a.model, a.timeout_min)

    with open(os.path.join(out_dir, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stdout or "")
        if proc.stderr:
            f.write("\n--- STDERR ---\n" + proc.stderr)

    rb.wait_for_quiet(workdir)

    score = {"task_id": task["id"], "agent": a.agent, "model": a.model,
             "run_id": run_id, "wall_seconds": round(wall, 1),
             "exit_code": proc.returncode,
             "gaia_task_id": task.get("gaia_task_id"), "level": task.get("level")}

    if meta and meta.get("timed_out"):
        score.update({"failure_mode": "timeout",
                      "failure_note": f"exceeded {a.timeout_min} min wall budget"})
        total = None                      # LRAB convention: timeout carries no total
    elif proc.returncode != 0:
        score.update({"failure_mode": "crash" if wall < 60 else "error"})
        total = 0.0
    else:
        total, detail = gaia_scorer.score_answer(workdir, task["gold_answer"])
        # answer.txt 缺失 = agent 烧到强收尾/退化完成,与"正常完成但答错"分开标注
        score["failure_mode"] = "completed" if not detail.get("error") else "no_answer"
        score["gaia"] = detail
    if total is not None:
        score["total"] = total

    with open(os.path.join(out_dir, "score.json"), "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: score.get(k) for k in
                      ("task_id", "agent", "model", "wall_seconds",
                       "failure_mode", "total")}), flush=True)


if __name__ == "__main__":
    main()
