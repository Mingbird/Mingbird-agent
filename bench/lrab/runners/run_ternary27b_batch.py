#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serial 18-cell LRAB driver for one model on the Mingbird arm (v16 tree).

Protocol pins (mirrors family_qwen352b campaign):
  AGENT_TEMP=0, AGENT_THINK=0  - unified sampling protocol
  per-cell budget from task JSON max_wall_minutes
  deterministic scoring (no judge)
  GPU serial: strictly one cell at a time
"""
import glob, json, os, subprocess, sys, time

ROOT = r"C:\Users\99491\dev\mingbird-v16"
RUNNER = os.path.join(ROOT, "bench", "lrab", "runners", "run_bench.py")
RESULTS = os.path.join(ROOT, "eval_results", "lrab_museglimmer_2610")
LOG = os.path.join(ROOT, "eval_results", "lrab_museglimmer_2610_batch.log")
MODEL = "muse-glimmer"

TASKS = sorted(
    glob.glob(os.path.join(ROOT, "bench", "lrab", "tasks", "tier*", "*.json")))

env = dict(os.environ)
env["AGENT_TEMP"] = "0"
env["AGENT_THINK"] = "0"

cells = []
for tj in TASKS:
    with open(tj, encoding="utf-8") as f:
        task = json.load(f)
    cells.append((tj, task["id"], task.get("max_wall_minutes", 60)))
assert len(cells) == 18, "expected 18 tasks, got %d" % len(cells)

with open(LOG, "a", encoding="utf-8") as log:
    log.write("=== batch start %s model=%s cells=%d pid=%d ===\n"
              % (time.strftime("%m-%d %H:%M:%S"), MODEL, len(cells), os.getpid()))
    for i, (tj, tid, budget) in enumerate(cells, 1):
        line = "[%d/18] %s budget=%dmin start %s\n" % (
            i, tid, budget, time.strftime("%H:%M:%S"))
        log.write(line); log.flush()
        print(line, end="", flush=True)
        cmd = [sys.executable, RUNNER, "--agent", "mingbird",
               "--task", tj, "--model", MODEL, "--results", RESULTS,
               "--timeout-min", str(budget)]
        proc = subprocess.run(cmd, env=env, cwd=ROOT,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        log.write("[%d/18] %s rc=%d end %s\n%s%s\n" % (
            i, tid, proc.returncode, time.strftime("%H:%M:%S"),
            proc.stdout or "", proc.stderr or ""))
        log.flush()
        print("rc=%d" % proc.returncode, flush=True)
    log.write("=== batch end %s ===\n" % time.strftime("%m-%d %H:%M:%S"))
print("BATCH DONE", flush=True)
