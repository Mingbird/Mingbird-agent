#!/usr/bin/env python3
"""288 final-matrix status probe (single source of truth for the MyAgents
Detector). Reads only the driver logs + attempt dirs + process liveness.

Outputs strict JSON on stdout:
  verdict: running | complete | stalled | dead
  cells_started: DISTINCT cell keys seen in ALL matrix_*.log tee logs
                 (union across run-2 / run-3 / resume attempts; reaches 288
                 at completion regardless of how many driver instances ran)
  cells_finished: distinct cells (run-3 window, latest attempt wins) whose
                 latest attempt has a score.json at all (timeout cells have
                 one without a total)
  cells_scored_ok: ...whose latest score.json carries a total
  completion = driver process gone AND cells_finished == 288.
  The end-of-run MATRIX_MANIFEST is NOT trusted for completion anymore:
  the 09-04 resume driver only writes a partial manifest (resumed cells),
  and mid-batch manifests are incremental snapshots (batch-1 lesson).
  stalled requires BOTH the tee log AND the current cell's artifacts to be
  stale: the log only gains a line at cell start/end, so one LH cell is
  silent for up to budget+180s by design (09-02 false alarm).
"""
import glob
import json
import os
import re
import sys
import time

RES = os.path.expanduser("~/dev/hummingbird/eval_results")
LOG = r"C:\Users\99491\logs288\driver_log.txt"
DONE_STAMP = r"C:\Users\99491\logs288\DRIVER_DONE.txt"
TOTAL_EXPECTED = 288
STALL_SEC = 45 * 60
START_RE = re.compile(r"=== \[([^\]]+)\] starting")
NAME_RE = re.compile(
    r"^(hummingbird|goose|opencode|agentmini)_(.+?)_(.+)_m(\d+)_(\d{4})_(\d{6})$")
RUN3_WINDOW = time.mktime(time.strptime("2026-09-02 15:25:15", "%Y-%m-%d %H:%M:%S"))


def live_log():
    """The run_matrix _Tee file is the real live log (PS5.1 Start-Transcript
    does not reliably capture native python stdout). Newest matrix_*.log in
    eval_results/logs; falls back to the transcript path."""
    cands = glob.glob(os.path.join(RES, "logs", "matrix_*.log"))
    if cands:
        return max(cands, key=os.path.getmtime)
    return LOG


def _stamp_ok(mtime):
    """Artifact belongs to this batch: modified today or yesterday."""
    if mtime <= 0:
        return False
    day = time.strftime("%m%d", time.localtime(mtime))
    yday = time.strftime("%m%d", time.localtime(time.time() - 86400))
    return day in (time.strftime("%m%d"), yday)


def _dir_in_run3(name):
    """Attempt dir belongs to the run-3+ era (>= 09-02 15:25:15 launch)."""
    m = NAME_RE.match(name)
    if not m:
        return False
    mmdd, hhmmss = m.group(5), m.group(6)
    try:
        ts = time.mktime(time.strptime(
            "2026-%s-%s %s:%s:%s" % (mmdd[:2], mmdd[2:], hhmmss[:2],
                                     hhmmss[2:4], hhmmss[4:]),
            "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return False
    return ts >= RUN3_WINDOW


def driver_alive():
    try:
        import psutil
        for p in psutil.process_iter(["cmdline"]):
            try:
                cl = " ".join(p.info.get("cmdline") or [])
                if ("matrix288.ps1" in cl or "matrix288_resume.ps1" in cl
                        or ("run_matrix.py" in cl and "--include-tier4" in cl)):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def started_cells():
    """DISTINCT cell keys ever started, unioned across ALL tee logs (run-2,
    run-3, resume). Monotone; reaches 288 at completion."""
    keys = set()
    for p in glob.glob(os.path.join(RES, "logs", "matrix_*.log")):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = START_RE.search(line)
                    if m:
                        keys.add(m.group(1))
        except OSError:
            continue
    return len(keys)


def scored_cells():
    """Distinct run-3-window cells (latest-attempt-wins by attempt number,
    then dir name = timestamp; same-attempt ties broken by timestamp, the
    09-04 resume left a killed m0 dir that must lose to a newer m0).
    Returns (finished, scored_ok, attempted):
      finished  = latest attempt dir has a score.json at all (timeout cells
                  write one without a total - they ARE finished cells)
      scored_ok = ... and it carries a total
    Completion uses `finished`: a completed batch where the last cells
    timed out must still read complete, not dead."""
    latest = {}
    for d in glob.glob(os.path.join(RES, "*")):
        name = os.path.basename(d)
        m = NAME_RE.match(name)
        if not m or not os.path.isdir(d) or not _dir_in_run3(name):
            continue
        key = (m.group(1), m.group(2), m.group(3))
        cur = latest.get(key)
        if cur is None or (int(m.group(4)), name) > (cur[0], cur[1]):
            latest[key] = (int(m.group(4)), name, d)
    finished = scored = 0
    for _key, (_att, _name, d) in latest.items():
        sp = os.path.join(d, "score.json")
        if not os.path.isfile(sp):
            continue
        try:
            s = json.load(open(sp, encoding="utf-8"))
        except Exception:
            continue
        finished += 1
        if s.get("total") is not None:
            scored += 1
    return finished, scored, len(latest)


def log_progress():
    """Newest tee log freshness (staleness signal only; progress comes from
    started_cells/scored_cells)."""
    path = live_log()
    if not os.path.isfile(path):
        return -1.0, path
    age = max(0.0, time.time() - os.path.getmtime(path))
    return age, path


def cell_artifact_age():
    """(age_sec, dir) of the freshest file inside the newest attempt dirs.
    Attempts land in RES/<agent>_<task>_<model>_m<N>_<ts>/workdir/; the agent
    rewrites .agent_state.json every iteration and deliverables as it goes,
    so artifact mtimes are the live liveness signal (the log is not)."""
    now = time.time()
    dirs = [d for d in glob.glob(os.path.join(RES, "*"))
            if os.path.isdir(d) and _stamp_ok(os.path.getmtime(d))]
    dirs.sort(key=os.path.getmtime, reverse=True)
    newest = 0.0
    for d in dirs[:2]:                     # current cell + just-finished cell
        for root, _ds, files in os.walk(d):
            for f in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    continue
    if newest <= 0:
        return None, None
    return now - newest, dirs[0]


def newest_manifest():
    """Newest timestamped MATRIX_MANIFEST copy (informational only since the
    09-04 resume: completion no longer depends on it)."""
    cands = [p for p in glob.glob(os.path.join(RES, "MATRIX_MANIFEST_*.json"))
             if _stamp_ok(os.path.getmtime(p))]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def runner_cpu_dead(sample_sec=8.0):
    """True if ollama/llama-server processes exist but burn no CPU over the
    sample window (hung-runner fingerprint: alive + spinning = decoding if
    delta>0, dead = gone). 09-04 lesson: goose writes artifacts only at the
    END, so a healthy 61min goose WF cell is silent the whole time - the
    dual-age signal alone false-positives on every long goose cell. CPU
    delta is THE runner-life criterion. None = no runner processes found
    (between cells / fresh restart) or sampling failed."""
    import psutil
    targets = ("ollama", "llama-server")

    def snap():
        total = 0.0
        found = False
        for p in psutil.process_iter(["name"]):
            try:
                nm = (p.info["name"] or "").lower()
                if any(t in nm for t in targets):
                    found = True
                    c = p.cpu_times()
                    total += c.user + c.system
            except Exception:
                continue
        return found, total

    try:
        found, t0 = snap()
        if not found:
            return None
        time.sleep(sample_sec)
        found2, t1 = snap()
        if not found2:
            return None
        return (t1 - t0) < 0.3
    except Exception:
        return None


def main():
    alive = driver_alive()
    started = started_cells()
    finished, scored, attempted = scored_cells()
    log_age, log_path = log_progress()
    art_age, cell_dir = cell_artifact_age()
    man_path = newest_manifest()
    man_total, man_ok, man_failed = 0, 0, 0
    if man_path:
        try:
            s = json.load(open(man_path, encoding="utf-8"))
            man_total = int(s.get("summary", {}).get("total_cells", 0))
            man_ok = int(s.get("summary", {}).get("ok", 0))
            man_failed = int(s.get("summary", {}).get("failed", 0))
        except Exception:
            man_path = None
    stamp_exists = os.path.isfile(DONE_STAMP)
    # Batch complete = driver gone AND every planned cell attempted AND the
    # driver wrote its DONE stamp. finished alone can cap at 287 when a
    # deliberate post-batch heal cell (no run-3 attempt yet) is pending, so
    # "all started + stamp" is the authoritative end-of-run signal.
    complete = (not alive) and stamp_exists and started >= TOTAL_EXPECTED
    dual_stale = log_age > STALL_SEC and (art_age is None or art_age > STALL_SEC)
    cpu_dead = runner_cpu_dead() if (alive and dual_stale) else None
    if complete:
        verdict = "complete"
    elif not alive:
        verdict = "dead"
    elif dual_stale and (cpu_dead is True or cpu_dead is None):
        # CPU-dead confirmed (or unmeasurable -> conservative dual-age call)
        verdict = "stalled"
    else:
        verdict = "running"
    print(json.dumps({
        "verdict": verdict,
        "cells_started": started,
        "cells_finished": finished,
        "cells_scored_ok": scored,
        "cells_attempted": attempted,
        "cells_total_expected": TOTAL_EXPECTED,
        "manifest": {"path": man_path, "total_cells": man_total,
                     "ok": man_ok, "failed": man_failed},
        "done_stamp_exists": stamp_exists,
        "driver_alive": alive,
        "log": log_path, "log_age_sec": round(log_age, 1),
        "artifact_age_sec": round(art_age, 1) if art_age is not None else None,
        "runner_cpu_dead": cpu_dead,
        "cell_dir": cell_dir,
    }))


if __name__ == "__main__":
    main()
