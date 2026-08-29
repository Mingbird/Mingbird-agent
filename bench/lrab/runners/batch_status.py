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

    run_id format: <agent>_<TASK>_<model>_m<attempt>_<MMDD_HHMMSS>. A retry
    gets a fresh dir with a bumped attempt number; the cell's authoritative
    result is its LATEST attempt. Progress = cells whose latest attempt has
    score.json.
    """
    import re
    runs = []
    for pat in patterns:
        runs.extend(EVAL.glob(pat))
    cells = {}   # cell key -> latest attempt dir
    for d in sorted(set(runs)):
        m = re.match(r"^(.+)_m(\d+)_(\d{4}_\d{6})$", d.name)
        key = m.group(1) if m else d.name
        if key not in cells or d.name > cells[key].name:
            cells[key] = d
    done = sum(1 for d in cells.values() if (d / "score.json").exists())
    newest_dir, newest_age = None, None
    now = time.time()
    for d in cells.values():
        for f in d.rglob("*"):
            if f.is_file():
                age = now - f.stat().st_mtime
                if newest_age is None or age < newest_age:
                    newest_age, newest_dir = age, str(f)
    return len(cells), done, newest_dir, newest_age


def ollama_active():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=5) as r:
            models = json.load(r).get("models", [])
        return bool(models), [m.get("model") for m in models]
    except Exception:
        return False, []


def main():
    # default: the 64-cell canonical batch (tasks WF-01/03/09/15, launched
    # 2026-08-29 09:17, ran past midnight -> goose tail cells stamped 0830).
    # Pinned per agent+date so later same-day reruns never pollute the count.
    # Comma-separated patterns can be passed to track a different batch.
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    patterns = arg.split(",") if arg else [
        "*_WF01_*_0829_*", "*_WF03_*_0829_*",
        "*_WF09_*_0829_*", "*_WF15_*_0829_*",
        "goose_WF01_*_0830_*", "goose_WF03_*_0830_*",
        "goose_WF09_*_0830_*", "goose_WF15_*_0830_*",
    ]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 64
    total, done, newest, age = batch_cells(patterns)
    loaded, models = ollama_active()
    if done >= target:
        verdict = "complete"
    elif age is None:
        verdict = "idle"          # no batch dirs at all
    elif age < STALE_WARN_SEC:
        verdict = "running"
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
        "patterns": patterns,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
