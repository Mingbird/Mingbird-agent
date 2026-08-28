#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LRAB benchmark runner: run one task on one agent runtime, then score.

Usage:
  python run_bench.py --agent hummingbird --task tasks/tier2_synthesis/WF-06.json \
      --model ornith-1.5:35b --results results/

Prepares a clean workdir (copies fixtures, writes task prompt), invokes the
agent CLI, waits, then invokes scoring. Archives transcript + score.
"""
import argparse, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LRAB = os.path.dirname(HERE)                     # bench/lrab
BENCH = os.path.dirname(LRAB)                    # bench
HB_ROOT = os.path.dirname(BENCH)                 # ~/dev/hummingbird


def prepare_workdir(task, base_workdir):
    workdir = os.path.abspath(base_workdir)
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)
    lrab_dir = LRAB
    for rel in task.get("fixtures", []):
        src = os.path.join(lrab_dir, rel)
        if os.path.isfile(src):
            shutil.copy2(src, workdir)
        elif os.path.isdir(src):
            shutil.copytree(src, os.path.join(workdir, os.path.basename(src)), dirs_exist_ok=True)
    with open(os.path.join(workdir, "task_input.txt"), "w", encoding="utf-8") as f:
        f.write(task["prompt"])
    return workdir


def run_hummingbird(task, workdir, model, timeout_min):
    taskfile = os.path.join(workdir, "task_input.txt")
    env = dict(os.environ)
    env.pop("AGENT_STREAM", None)
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HB_ROOT, "ollama_agent.py"), model, taskfile, workdir],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, env=env, cwd=workdir)
    return proc, time.time() - t0


def run_opencode(task, workdir, model, timeout_min):
    t0 = time.time()
    proc = subprocess.run(
        ["opencode", "run", "--model", f"ollama/{model}", task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir)
    return proc, time.time() - t0


def run_agent_mini(task, workdir, model, timeout_min):
    model_tag = model.split("/")[-1]
    t0 = time.time()
    proc = subprocess.run(
        ["agent-mini", "--model", model_tag, task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir, shell=True)
    return proc, time.time() - t0


def run_goose(task, workdir, model, timeout_min):
    t0 = time.time()
    env = dict(os.environ)
    env["GOOSE_PROVIDER"] = "ollama"
    env["GOOSE_MODEL"] = model
    proc = subprocess.run(
        ["goose", "run", "--no-session", task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir, env=env, shell=True)
    return proc, time.time() - t0


RUNNERS = {
    "hummingbird": run_hummingbird,
    "opencode": run_opencode,
    "agent-mini": run_agent_mini,
    "goose": run_goose,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(RUNNERS))
    ap.add_argument("--task", required=True)
    ap.add_argument("--model", default="ornith-1.5:35b")
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--results", default=os.path.join(LRAB, "results"))
    ap.add_argument("--timeout-min", type=int, default=60)
    ap.add_argument("--judge", default="", help="judge model; empty = deterministic only")
    ap.add_argument("--run-id", default="")
    a = ap.parse_args()

    with open(a.task, encoding="utf-8") as f:
        task = json.load(f)
    run_id = a.run_id or f"{a.agent}_{task['id']}_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir = os.path.join(a.results, run_id)
    os.makedirs(out_dir, exist_ok=True)
    workdir = prepare_workdir(task, a.workdir)

    print(f"[{run_id}] agent={a.agent} model={a.model} task={task['id']}", flush=True)
    proc, wall = RUNNERS[a.agent](task, workdir, a.model, a.timeout_min)
    print(f"[{run_id}] agent finished exit={proc.returncode} wall={wall:.0f}s", flush=True)

    with open(os.path.join(out_dir, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stdout or "")
        if proc.stderr:
            f.write("\n--- STDERR ---\n" + proc.stderr)

    sys.path.insert(0, os.path.join(LRAB, "scoring"))
    from score_task import score_task
    score = score_task(a.task, workdir, judge=bool(a.judge),
                       judge_model=a.judge or "ornith-1.5:35b")
    score.update({
        "agent": a.agent, "model": a.model, "wall_seconds": round(wall, 1),
        "exit_code": proc.returncode, "run_id": run_id,
    })
    with open(os.path.join(out_dir, "score.json"), "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: score[k] for k in ("task_id", "agent", "model", "milestone_score",
                                            "final_score", "total", "wall_seconds")}, ensure_ascii=False))
    # snapshot workdir artifacts for the archive
    snap = os.path.join(out_dir, "workdir")
    shutil.copytree(workdir, snap, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "corpus", ".agent_state.json"))


if __name__ == "__main__":
    main()
