#!/usr/bin/env python3
"""fp-0902 verification batch status probe (single source of truth for the
MyAgents Detector). Reads only eval_results dirs + driver process liveness.

Outputs strict JSON on stdout:
  verdict: running | complete | stalled | dead
  cells_done: how many of the 3 (task, model) combos have a final score.json
  cells: [{key, attempt_dir, scored, failure_mode, total}]
  newest_artifact / newest_age_sec: freshness signal across run dirs + log
"""
import glob
import json
import os
import re
import sys
import time

RES = os.path.expanduser("~/dev/hummingbird/eval_results")
LOG = os.path.join(RES, "logs", "fpverify_0902.log")
# cell key -> run-id prefix (attempt wildcard appended)
CELLS = [
    ("WF-05_gemma4:12b", "hummingbird_WF05_gemma4_12b_m"),
    ("WF-08_gemma4:12b", "hummingbird_WF08_gemma4_12b_m"),
    ("WF-08_qwen3.5:4b", "hummingbird_WF08_qwen3.5_4b_m"),
]
STALL_SEC = 45 * 60
# run-id tail: _m<attempt>_<MMdd>_<HHMMSS>. Accept today OR yesterday (a batch
# crossing midnight must stay visible). String containment ("0902_1250" in
# name) was the v1 bug: it matched nothing, so the probe reported 0 cells
# while the whole batch ran and completed.
_STAMP_RE = re.compile(r"_m\d_(\d{4})_(\d{6})$")


def _batch_stamp_ok(dirname):
    m = _STAMP_RE.search(os.path.basename(dirname))
    if not m:
        return False
    yday = time.strftime("%m%d", time.localtime(time.time() - 86400))
    return m.group(1) in (time.strftime("%m%d"), yday)


def driver_alive():
    try:
        import psutil
        for p in psutil.process_iter(["cmdline"]):
            try:
                cl = " ".join(p.info.get("cmdline") or [])
                if "fpverify_0902.ps1" in cl:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def latest_attempt(prefix):
    """Newest run dir for a cell prefix; None if absent."""
    dirs = [d for d in glob.glob(os.path.join(RES, prefix + "*"))
            if os.path.isdir(d) and _batch_stamp_ok(d)]
    if not dirs:
        return None
    return max(dirs, key=os.path.getmtime)


def newest_mtime():
    """Freshness across run dirs (recursive) + driver log. Returns (path, age)."""
    best, best_mt = None, 0.0
    for d in glob.glob(os.path.join(RES, "hummingbird_WF0*")):
        if not os.path.isdir(d) or not _batch_stamp_ok(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                try:
                    mt = os.path.getmtime(os.path.join(root, f))
                except OSError:
                    continue
                if mt > best_mt:
                    best_mt, best = mt, os.path.join(root, f)
    if os.path.isfile(LOG):
        mt = os.path.getmtime(LOG)
        if mt > best_mt:
            best_mt, best = mt, LOG
    age = max(0.0, time.time() - best_mt) if best_mt else -1.0
    return best, age


def main():
    cells, done = [], 0
    for key, prefix in CELLS:
        d = latest_attempt(prefix)
        entry = {"key": key, "attempt_dir": os.path.basename(d) if d else None,
                 "scored": False, "failure_mode": None, "total": None}
        if d:
            sp = os.path.join(d, "score.json")
            if os.path.isfile(sp):
                try:
                    s = json.load(open(sp, encoding="utf-8"))
                    entry["scored"] = True
                    entry["failure_mode"] = s.get("failure_mode")
                    entry["total"] = s.get("total")
                except Exception:
                    pass
        if entry["scored"]:
            done += 1
        cells.append(entry)
    alive = driver_alive()
    art, age = newest_mtime()
    if done == 3:
        verdict = "complete"
    elif not alive:
        verdict = "dead"
    elif age > STALL_SEC:
        verdict = "stalled"
    else:
        verdict = "running"
    print(json.dumps({
        "verdict": verdict, "cells_done": done, "cells": cells,
        "driver_alive": alive, "newest_artifact": art, "newest_age_sec": round(age, 1),
    }))


if __name__ == "__main__":
    main()
