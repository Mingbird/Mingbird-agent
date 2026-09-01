#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LRAB batch liveness probe (stdlib only, safe to run while a batch is in flight).

Answers one question: is the 64-cell matrix batch still making progress?

Evidence used (no process-listing needed):
  1. cell count      - eval_results/<run_id>_m0_<date>_*/score.json files (target from --target)
  2. artifact age    - newest mtime among batch run dirs (transcripts update every turn)
  3. ollama activity - GET /api/ps, a loaded model means a cell is being served

Verdicts: running | stalled | complete | idle
Exit code: 0 always (probe, not a gate). Print JSON for the 3h self-review task.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]          # repo root (eval_results lives at ~/dev/hummingbird/)
EVAL = HERE / "eval_results"
STALE_WARN_SEC = 600      # no writes for 10 min -> suspicious
STALE_ALERT_SEC = 1500    # no writes for 25 min -> stalled (budget is 40 min/cell,
                          # but a live cell writes its transcript every turn)


def batch_cells(patterns):
    """Count batch cells (dedup across retry attempts m0/m1/...).

    run_id format: <agent>_<TASK>_<model>_m<attempt>_<MMDD_HHMMSS>. The cell's
    authoritative result is its LATEST attempt THAT WROTE score.json, ordered
    by (timestamp, attempt) - 2026-09-01: raw-name max() let instant-fail husk
    dirs (e.g. *_m1_0901_153624) shadow later real runs. Progress = cells with
    at least one scored attempt; artifact age scans ALL dirs so an in-flight
    unscored attempt still proves freshness.
    """
    import re
    runs = sorted(set(d for pat in patterns for d in EVAL.glob(pat)))
    cell_re = re.compile(r"^(.+)_m(\d+)_(\d{4}_\d{6})$")
    started, scored = set(), {}
    for d in runs:
        m = cell_re.match(d.name)
        if not m:
            continue
        key, order = m.group(1), (m.group(3), int(m.group(2)))
        started.add(key)
        if (d / "score.json").exists():
            prev = scored.get(key)
            if prev is None or order > prev[0]:
                scored[key] = (order, d)
    newest_dir, newest_age = None, None
    now = time.time()
    for d in runs:
        for f in d.rglob("*"):
            if f.is_file():
                age = now - f.stat().st_mtime
                if newest_age is None or age < newest_age:
                    newest_age, newest_dir = age, str(f)
    return len(started), len(scored), newest_dir, newest_age


def ollama_active():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=5) as r:
            models = json.load(r).get("models", [])
        return bool(models), [m.get("model") for m in models]
    except Exception:
        return False, []


def chain_procs_alive():
    """Count live chain processes (run_matrix / run_bench / driver ps1).

    2026-09-01: artifact-age alone is a lagging, ambiguous signal (a hung cell
    looks like deep work; a 2-second husk cascade resets the clock). A healthy
    chain ALWAYS has its driver or run_matrix alive, so:
      >0  -> chain in flight (verdict running regardless of artifact age)
      ==0 -> tree dead before target -> stalled immediately
      -1  -> probe infrastructure error -> fall back to the age heuristic
    Pattern must stay in sync with driver naming (batch1_resume*).
    """
    import base64
    import subprocess
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='powershell.exe'\" | "
          "Where-Object { $_.CommandLine -match 'run_matrix\\.py|run_bench\\.py|batch1_resume' } | "
          "Measure-Object | Select-Object -ExpandProperty Count")
    enc = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc],
                           capture_output=True, text=True, timeout=25)
        return int((r.stdout or "0").strip() or 0)
    except Exception:
        return -1


def load_watch_config():
    """Optional batch_watch.json next to this probe selects the ACTIVE batch:
    {"patterns": [...], "target": N}. Every watcher (detector, 3h audit) then
    follows a new batch by editing that one file instead of code. Falls back
    to the canonical 64-cell batch (0829 + goose 0830 tail)."""
    cfg = Path(__file__).resolve().parent / "batch_watch.json"
    try:
        c = json.loads(cfg.read_text(encoding="utf-8"))
        global STALE_ALERT_SEC
        STALE_ALERT_SEC = int(c.get("stale_alert_sec", STALE_ALERT_SEC))
        return list(c.get("patterns") or []), int(c.get("target", 64))
    except Exception:
        return [
            "*_WF01_*_0829_*", "*_WF03_*_0829_*",
            "*_WF09_*_0829_*", "*_WF15_*_0829_*",
            "goose_WF01_*_0830_*", "goose_WF03_*_0830_*",
            "goose_WF09_*_0830_*", "goose_WF15_*_0830_*",
        ], 64


def main():
    # CLI args win: argv[1] = comma patterns, argv[2] = target.
    # Without args, follow batch_watch.json (active batch) or the canonical default.
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    target = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if arg:
        patterns = arg.split(",")
    else:
        patterns, cfg_target = load_watch_config()
        if target is None:
            target = cfg_target
    if target is None:
        target = 64
    total, done, newest, age = batch_cells(patterns)
    loaded, models = ollama_active()
    procs = chain_procs_alive()
    paused = False
    try:
        paused = bool(json.loads((Path(__file__).resolve().parent / "batch_watch.json")
                                 .read_text(encoding="utf-8")).get("paused", False))
    except Exception:
        pass
    if paused and done < target:
        verdict = "paused"
    elif done >= target:
        verdict = "complete"
    elif age is None:
        verdict = "idle"          # no batch dirs at all
    elif procs > 0:
        verdict = "running"       # driver/runner alive: a cell may legitimately
                                  # sit silent inside its 40-min budget
    elif procs == 0:
        verdict = "stalled"       # tree dead before target: immediate, no lag
    elif age < STALE_WARN_SEC:
        verdict = "running"       # procs unknown (-1): legacy age heuristic
    elif age < STALE_ALERT_SEC and loaded:
        verdict = "running"       # quiet stretch but GPU busy
    else:
        verdict = "stalled"
    print(json.dumps({
        "verdict": verdict,
        "cells_done": done,
        "cells_started": total,
        "target": target,
        "newest_artifact": newest,
        "newest_age_sec": round(age) if age is not None else None,
        "ollama_models_loaded": models,
        "chain_procs": procs,
        "patterns": patterns,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
