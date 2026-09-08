#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GAIA-L1 matrix driver: 4 agents x 2 models (both ends) x 53 tasks = 424 cells.

Model scope (2026-09-05 user decision): two-end anchor -- gemma4:e2b (smallest)
+ ornith-1.5:35b (strongest). The full 4-model gradient is the LRAB 288
matrix's job; disclose GAIA as a two-end external anchor in METHODS.

Protocol mirrors the LRAB 288 matrix (fp_0902 proven parts inlined):
  - sequential, model-outer slices (e2b -> 35b), ollama restart at
    slice boundaries so the previous model's weights are gone before the next;
  - uniform 30 min wall budget, timeout = no total (scored 0 at aggregation);
  - latest-attempt-wins resume via per-cell DONE.json (a restart skips done
    cells, retries unfinished ones);
  - 35b load guard (tiny request forces weights into UMA VRAM before any cell,
    so cold-load time and the ollama runner-rebuild loop burn the guard, not
    the cell budget);
  - keep-awake thread (process-scoped SetThreadExecutionState) so the laptop
    cannot sleep mid-chain;
  - proxy env: GAIA_PROXY from the launcher, propagated to ALL agents via
    dict(os.environ) inheritance in run_bench; NO_PROXY covers ollama.

Usage:
  python run_gaia_matrix.py                 # full plan, resume-aware
  python run_gaia_matrix.py --limit 2       # smoke: first N unfinished cells
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # bench/gaia
BENCH = os.path.dirname(HERE)                              # bench/
HB_ROOT = os.path.dirname(BENCH)                           # ~/dev/hummingbird
RUNNERS = os.path.join(BENCH, "lrab", "runners")
sys.path.insert(0, RUNNERS)
sys.path.insert(0, HERE)

import run_bench as rb            # noqa: E402  (LRAB primitives, untouched)
import gaia_scorer                # noqa: E402

# Two-end anchor (2026-09-05 user decision): smallest + strongest models only.
# The full 4-model gradient lives in the LRAB 288 matrix; GAIA here is an
# external anchor, so both ends suffice for the release narrative. Disclose
# as "two-end L1 anchor" in METHODS -- not a full gradient.
MODELS = ["gemma4:e2b", "qwen3.5:4b", "ornith-1.5:35b"]  # 4b added 2026-09-06 (4-agent discrimination campaign)
AGENTS = ["hummingbird", "opencode", "goose", "agent-mini"]
TASKS_DIR = os.path.join(HERE, "tasks")
BASE = os.path.join(HB_ROOT, "eval_results", "gaia_l1_matrix")
BUDGET_MIN = 60   # 30→60 (2026-09-05 用户定): give stuck cells a fairer window
SEARCH_CHECK_EVERY = 10   # cells between live search-health probes
LOG_PATH = os.path.join(BASE, "driver_log.txt")
PROGRESS_PATH = os.path.join(BASE, "GAIA_PROGRESS.json")
MANIFEST_PATH = os.path.join(BASE, "GAIA_MANIFEST.json")
OLLAMA_HOST = "http://127.0.0.1:11434"

NODE_DIRS = [
    os.path.expandvars(r"%LOCALAPPDATA%\MyAgents\nodejs"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
                       r"\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe"
                       r"\node-v24.19.0-win-x64"),
    os.path.expandvars(r"%APPDATA%\npm"),
]


# ---------- environment prep (schtasks context is minimal) ----------

def prep_env():
    os.environ["PATH"] = os.pathsep.join(NODE_DIRS) + os.pathsep + os.environ.get("PATH", "")
    proxy = os.environ.get("GAIA_PROXY", "").strip()
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
    # Hummingbird's builtin web_search defaults to cn.bing/baidu (CN-market,
    # regionalized) and poisons English GAIA tasks with zhihu/baike noise --
    # the model picking the builtin over the MCP wrapper then gets garbage.
    # Point the builtin at international Bing with an explicit market (without
    # setmkt, Bing geolocates by proxy exit IP -- the current exit is JP and
    # serves Japanese results) so BOTH search tools serve en-US results; same
    # upstream the shared MCP wrapper uses. Run-environment config, not bench
    # state (fairness: equivalent to a user's config file).
    os.environ.setdefault(
        "AGENT_SEARCH_BACKENDS",
        "https://www.bing.com/search?setmkt=en-US&setlang=en&q={query}")
    # Context budget: 128K (2026-09-05 staged test on this machine: 35B MoE
    # decode 26.4 tok/s at 128K vs 1.8 tok/s at 256K = swap thrash). GAIA runs
    # are product-capability probes; the LRAB 288 comparison stays frozen at
    # 32K (run_bench fallback) so the four-harness protocol is untouched.
    os.environ.setdefault("AGENT_CTX", "131072")
    # ollama calls must never try the proxy even when one is set
    no_px = set((os.environ.get("NO_PROXY", "") or "").split(","))
    no_px |= {"localhost", "127.0.0.1"}
    os.environ["NO_PROXY"] = ",".join(sorted(x for x in no_px if x))
    return proxy


def keep_awake_thread():
    """Process-scoped system-awake (same mechanism as fp keep_awake.py)."""
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_AWAYMODE_REQUIRED = 0x80000000, 0x1, 0x40

    def _loop():
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
            log("[keep-awake] system sleep suppressed (process-scoped)")
            while True:
                time.sleep(60)
        except Exception:
            pass

    threading.Thread(target=_loop, daemon=True).start()


# ---------- logging ----------

class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%m-%d %H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass


# ---------- ollama lifecycle (fp_0902 run_matrix protocol) ----------

def ollama_up(timeout=15):
    try:
        with urllib.request.urlopen(OLLAMA_HOST + "/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def wait_ollama(max_wait=300):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if ollama_up():
            return True
        time.sleep(10)
    return False


def restart_ollama():
    log("[ollama] restart: kill + relaunch (Vulkan launcher) + poll")
    subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)
    time.sleep(5)
    launcher = os.environ.get(
        "OLLAMA_LAUNCHER_PS1",
        os.path.expandvars(r"%USERPROFILE%\launch_ollama_0831.ps1"))
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", launcher], capture_output=True, timeout=120)
    return wait_ollama(max_wait=300)


def guard_model_loaded(model, max_wait=900):
    """35b cold load / runner-rebuild guard: tiny request must complete."""
    if "35b" not in model:
        return True
    payload = json.dumps({"model": model, "prompt": "hi", "stream": False,
                          "options": {"num_predict": 1}}).encode()
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                OLLAMA_HOST + "/api/generate", data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=620) as r:
                if json.loads(r.read()).get("done") is True:
                    log("[ollama] 35b load guard passed")
                    return True
        except Exception:
            time.sleep(10)
    return False


def wait_for_search(max_hours=48, interval_min=5):
    """Ignition / health gate: GAIA-L1 is search-dependent; a flagged DDG
    exit node (202 anomaly challenge, IP-bound) poisons cells with honest-
    looking 0s. Probe the REAL path (wrapper via proxy env, fresh=True so
    the probe never reads the cache) and block until it returns results."""
    deadline = time.time() + max_hours * 3600
    attempt = 0
    sys.path.insert(0, HERE)
    import ddg_search_mcp as dsm
    while time.time() < deadline:
        attempt += 1
        try:
            txt = dsm.search("capital of France", 3, fresh=True)
            ok = txt.startswith(("1.", "2.", "3.", "4.", "5.")) or (
                "http" in txt and "Error" not in txt[:60])
        except Exception as e:
            ok, txt = False, "%s: %s" % (type(e).__name__, str(e)[:100])
        if ok:
            log("[gate] search healthy after %d probes -- IGNITION" % attempt)
            return True
        log("[gate] probe #%d blocked (%s) -- retry in %d min"
            % (attempt, txt[:80].replace("\n", " "), interval_min))
        time.sleep(interval_min * 60)
    log("FATAL: search still blocked after %dh -- aborting" % max_hours)
    return False


# ---------- plan / resume / progress ----------

def model_safe(m):
    return m.replace(":", "_").replace(".", "")


def agent_safe(a):
    return a.replace("-", "")


def build_plan():
    tasks = []
    for f in sorted(os.listdir(TASKS_DIR)):
        if f.startswith("GAIA-L1-") and f.endswith(".json"):
            tasks.append(os.path.join(TASKS_DIR, f))
    plan = []
    for model in MODELS:
        for agent in AGENTS:
            for tp in tasks:
                plan.append((model, agent, tp))
    return plan


def cell_paths(model, agent, tp):
    tid = os.path.splitext(os.path.basename(tp))[0]
    cdir = os.path.join(BASE, model_safe(model), agent_safe(agent), tid)
    return cdir, os.path.join(cdir, "DONE.json")


def write_progress(done, total, current, eta_h):
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump({"done": done, "total": total, "current": current,
                       "eta_hours": round(eta_h, 1), "updated_at":
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
    except Exception:
        pass


# ---------- one cell ----------

def run_cell(model, agent, tp):
    task = json.load(open(tp, encoding="utf-8"))
    cdir, done_path = cell_paths(model, agent, tp)
    if os.path.exists(done_path):
        return None                      # resume: already scored
    os.makedirs(cdir, exist_ok=True)
    attempt = os.path.join(cdir, "attempt_" + time.strftime("%m%d_%H%M%S"))
    workdir = os.path.join(attempt, "workdir")
    os.makedirs(workdir, exist_ok=True)
    rb.prepare_workdir(task, workdir)
    log("CELL start %s %s %s" % (model, agent, task["id"]))
    t0 = time.time()
    try:
        proc, wall, meta = rb.run_single(agent, task, workdir, model, BUDGET_MIN)
    except Exception:
        traceback.print_exc()
        raise
    with open(os.path.join(attempt, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stdout or "")
        if proc.stderr:
            f.write("\n--- STDERR ---\n" + proc.stderr)
    try:
        rb.wait_for_quiet(workdir)
    except Exception:
        pass

    score = {"task_id": task["id"], "agent": agent, "model": model,
             "run_id": os.path.basename(attempt),
             "wall_seconds": round(wall, 1), "exit_code": proc.returncode,
             "gaia_task_id": task.get("gaia_task_id"), "level": task.get("level")}
    if meta and meta.get("timed_out"):
        score["failure_mode"] = "timeout"
        score["failure_note"] = "exceeded %d min wall budget" % BUDGET_MIN
        total = None
    elif proc.returncode != 0:
        score["failure_mode"] = "crash" if wall < 60 else "error"
        total = 0.0
    else:
        total, detail = gaia_scorer.score_answer(workdir, task["gold_answer"])
        score["failure_mode"] = ("completed" if not detail.get("error")
                                 else "no_answer")
        score["gaia"] = detail
    if total is not None:
        score["total"] = total
    with open(os.path.join(attempt, "score.json"), "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2)
    with open(done_path, "w", encoding="utf-8") as f:
        json.dump({"run_id": score["run_id"], "total": total,
                   "failure_mode": score["failure_mode"],
                   "wall_seconds": score["wall_seconds"]}, f, indent=1)
    log("CELL done  %s %s %s total=%s fm=%s wall=%.0fs"
        % (model, agent, task["id"], total, score["failure_mode"], wall))
    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="run at most N unfinished cells (smoke mode)")
    ap.add_argument("--models", default="",
                    help="comma-separated model override (subset of MODELS)")
    ap.add_argument("--agents", default="",
                    help="comma-separated agent override (subset of AGENTS)")
    ap.add_argument("--task-sample", type=int, default=0, dest="task_sample",
                    help="keep only N evenly-spaced tasks (probe viability "
                         "before committing to the full run)")
    a = ap.parse_args()

    os.makedirs(BASE, exist_ok=True)
    logfile = open(LOG_PATH, "a", encoding="utf-8", errors="replace")
    sys.stdout = _Tee(sys.__stdout__, logfile)
    sys.stderr = _Tee(sys.__stderr__, logfile)
    proxy = prep_env()
    keep_awake_thread()
    models = ([m.strip() for m in a.models.split(",") if m.strip()]
              if a.models else MODELS)
    log("=== gaia_l1_matrix driver boot | proxy=%s | budget=%dmin | "
        "models=%s ===" % (proxy or "none", BUDGET_MIN, ",".join(models)))

    plan = [c for c in build_plan() if c[0] in models]
    if a.agents:
        agents = {x.strip() for x in a.agents.split(",") if x.strip()}
        plan = [c for c in plan if c[1] in agents]
    if a.task_sample:
        tasks = sorted({tp for _, _, tp in plan})
        step = max(1, len(tasks) // a.task_sample)
        keep = set(tasks[::step][:a.task_sample])
        plan = [c for c in plan if c[2] in keep]
        log("task sample: %d of %d tasks (step %d)"
            % (len(keep), len(tasks), step))
    total = len(plan)
    done = sum(1 for m, ag, tp in plan
               if os.path.exists(cell_paths(m, ag, tp)[1]))
    log("plan: %d cells, %d already done, %d to run" % (total, done, total - done))
    if not a.models and not a.task_sample and total != 424:
        log("WARNING: expected 424 cells, got %d -- task dir mismatch?" % total)

    if not wait_for_search(max_hours=48, interval_min=5):
        sys.exit(1)

    manifest_cells = []
    wall_hist = []
    consecutive_errors = 0
    current_model = None
    ran = 0

    for i, (model, agent, tp) in enumerate(plan):
        cdir, done_path = cell_paths(model, agent, tp)
        if os.path.exists(done_path):
            try:
                d = json.load(open(done_path, encoding="utf-8"))
                manifest_cells.append({"model": model, "agent": agent,
                                       "task_id": os.path.basename(tp)[:-5],
                                       "total": d.get("total"),
                                       "failure_mode": d.get("failure_mode"),
                                       "run_id": d.get("run_id")})
            except Exception:
                pass
            continue
        if a.limit and ran >= a.limit:
            log("smoke limit reached (%d ran) -- exiting cleanly" % ran)
            break

        # model slice boundary: restart ollama so the previous weights are gone
        if model != current_model:
            log("=== model slice %s (fresh ollama) ===" % model)
            if not ollama_up() and not restart_ollama():
                log("FATAL: ollama unreachable after restart -- aborting chain")
                sys.exit(1)
            if not guard_model_loaded(model):
                log("FATAL: load guard failed for %s -- aborting chain" % model)
                sys.exit(1)
            current_model = model

        # per-cell health gate
        if not ollama_up():
            log("[ollama] down before cell -- restarting")
            if not restart_ollama() or not guard_model_loaded(model):
                log("FATAL: ollama unrecoverable -- aborting chain")
                sys.exit(1)

        eta_h = (sum(wall_hist[-20:]) / max(1, len(wall_hist[-20:]))) \
            * max(0, total - done) / 3600.0 if wall_hist else 0.0
        write_progress(done, total, "%s %s %s" % (model, agent,
                                                  os.path.basename(tp)[:-5]),
                       eta_h)
        try:
            run_cell(model, agent, tp)
            consecutive_errors = 0
        except SystemExit:
            raise
        except Exception as e:
            consecutive_errors += 1
            log("CELL ERROR %s %s %s -> %s: %s (consecutive=%d)"
                % (model, agent, os.path.basename(tp)[:-5],
                   type(e).__name__, str(e)[:150], consecutive_errors))
            if consecutive_errors >= 5:
                log("FATAL: 5 consecutive driver errors -- aborting chain")
                sys.exit(1)
            continue

        d = json.load(open(done_path, encoding="utf-8"))
        manifest_cells.append({"model": model, "agent": agent,
                               "task_id": os.path.basename(tp)[:-5],
                               "total": d.get("total"),
                               "failure_mode": d.get("failure_mode"),
                               "run_id": d.get("run_id")})
        wall_hist.append(d.get("wall_seconds") or 0.0)
        done += 1
        ran += 1
        write_progress(done, total, "", eta_h)

        # Continuous search guard. The boot gate only proves health once:
        # on 09-05 the DDG flag re-formed minutes after ignition and every
        # in-cell search silently returned empty pages, poisoning 233 cells
        # with honest-looking 0s while the log kept advancing (invisible to
        # stall/FATAL sentinels). Re-probe live every N cells and PAUSE --
        # not abort -- on degradation.
        if ran % SEARCH_CHECK_EVERY == 0 and not wait_for_search(
                max_hours=24, interval_min=5):
            log("FATAL: search degraded mid-run and did not recover")
            sys.exit(1)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump({"protocol": {"budget_min": BUDGET_MIN, "models": models,
                                "agents": AGENTS, "tasks": "GAIA-L1-01..53",
                                "timeout": "no total key", "resume":
                                "latest-attempt-wins per DONE.json"},
                   "complete": True, "finished_at":
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "cells": manifest_cells}, f, ensure_ascii=False, indent=1)
    scored = [c for c in manifest_cells if c.get("total") is not None]
    mean = sum(c["total"] for c in scored) / len(scored) if scored else 0.0
    log("matrix done {'cells_manifest': %d, 'scored': %d, 'mean_of_scored': %.3f}"
        % (len(manifest_cells), len(scored), mean))
    log("=== gaia_l1_matrix driver exit ===")


if __name__ == "__main__":
    main()
