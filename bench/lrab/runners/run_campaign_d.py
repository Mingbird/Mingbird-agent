#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mingbird v1.4.0 current-build campaign on LRAB: plan D.

Stage 1: mingbird 72 cells (4 models x 18 tasks) on main repo HEAD.
Stage 2: ablation - 4 mechanisms x WF subset (30 cells each), qwen3.5:4b.
Chain: stage 1 -> stage 2 automatically; each stage skips cells that already
have a score (manifest resume), so restarts are always safe.

Device discipline:
- competitors' numbers stay from the original batch (stock binaries, pinned);
  only the evolving product (Mingbird) is re-shot - same disclosure model as tau2.
- budgets match the 288 final protocol: WF 90 min, LH 180 min.
- fresh-ollama per attempt, retries=1, latest-attempt-wins, deterministic judge.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # 仓根(runners 上三级)
RUNNERS = os.path.join(HERE)                       # runners 目录本身
RESULTS = os.path.join(REPO, "eval_results")      # 主仓 eval_results(288 同处)
PY = sys.executable

MODELS = ["qwen3.5:4b", "gemma4:e2b", "gemma4:12b", "ornith-1.5:35b"]  # 4b 先行(基准主力),35b 压轴(用户定调)
WF_SUBSET = [f"WF-{i:02d}" for i in range(1, 16)][:10]      # WF-01..WF-10
ABLATION_VARIANTS = ["finish_gate", "anti_loop", "flat_prefill", "verify_feedback"]


def run(cmd, env_extra=None, log=None):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    print("[run]", " ".join(cmd), "| extra-env:", env_extra or "-", flush=True)
    # 实时透传:逐行同时写窗口(Tee 已在管道上)与日志文件。
    # 之前 stdout=lf 把全部输出吞进文件,Tee/窗口只看到 [run] 一行。
    os.makedirs(os.path.dirname(log), exist_ok=True)
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    with open(log, "a", encoding="utf-8") as lf:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            lf.write(line)
    proc.wait()
    return proc.returncode


def stage1(args):
    """mingbird 72 cells on HEAD, 288-final budgets, small-models-first sweep."""
    log = os.path.join(RESULTS, "logs", "mingbird_v140_72.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    return run([PY, os.path.join(RUNNERS, "run_matrix.py"),
                "--agents", "hummingbird",
                "--models", ",".join(MODELS),
                "--include-tier4",
                "--timeout-min", str(args.timeout_min),
                "--sweep", "model",
                "--fresh-ollama",
                "--retries", "1",
                "--results", RESULTS], log=log)


def stage2(args):
    """ablation: 4 mechanisms x WF-01..10 x qwen3.5:4b (plus baseline pass)."""
    log = os.path.join(RESULTS, "logs", "ablation_120.log")
    # baseline pass (no gate) - anchors the comparison on the same day/code
    rc = run([PY, os.path.join(RUNNERS, "run_matrix.py"),
              "--agents", "hummingbird",
              "--models", "qwen3.5:4b",
              "--tasks", ",".join(WF_SUBSET),
              "--timeout-min", str(args.timeout_min),
              "--fresh-ollama",
              "--results", RESULTS], log=log)
    for variant in ABLATION_VARIANTS:
        rc = run([PY, os.path.join(RUNNERS, "run_matrix.py"),
                  "--agents", "hummingbird",
                  "--models", "qwen3.5:4b",
                  "--tasks", ",".join(WF_SUBSET),
                  "--timeout-min", str(args.timeout_min),
                  "--fresh-ollama",
                  "--results", RESULTS],
                 env_extra={"AGENT_ABLATION": variant}, log=log)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-min", type=int, default=90)
    ap.add_argument("--stage", choices=("1", "2", "all"), default="all")
    a = ap.parse_args()
    os.makedirs(RESULTS, exist_ok=True)
    t0 = time.time()
    rc = 0
    if a.stage in ("1", "all"):
        rc = stage1(a)
        print(f"[chain] stage1 rc={rc} elapsed={(time.time()-t0)/3600:.1f}h", flush=True)
    if rc == 0 and a.stage in ("2", "all"):
        rc = stage2(a)
        print(f"[chain] stage2 rc={rc} elapsed={(time.time()-t0)/3600:.1f}h", flush=True)
    print(f"[chain] ALL DONE rc={rc} total={(time.time()-t0)/3600:.1f}h", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
