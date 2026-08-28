#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LRAB full-matrix driver: serial execution of all (agent × model × task) cells.

Single-GPU host: cells MUST run serially (model reload is the bottleneck, parallel
loads thrash shared VRAM). Each cell:
  1. pre-checks Ollama is up (30-60s probe) before launching the cell
  2. runs run_bench.py for the cell
  3. on failure (crash/timeout/no score), retries ONCE and records both attempts
  4. writes/updates MANIFEST.json

Usage:
  python run_matrix.py --agents hummingbird,opencode,agent-mini,goose \
      --models ornith-1.5:35b,gemma4:12b,qwen3.5:4b,gemma4:e2b \
      --tasks-dir tasks --results ~/dev/hummingbird/eval_results \
      --timeout-min 45 --dry-run   # dry-run just prints the plan

Scope default: all 15 LRAB tasks per cell. Use --tasks WF-06 to subset (smoke).
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
LRAB = os.path.dirname(HERE)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def ollama_up(host=OLLAMA_HOST, timeout=15):
    """Probe /api/tags — cheap health check that model list is reachable."""
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def wait_ollama(host=OLLAMA_HOST, max_wait=180):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if ollama_up(host):
            return True
        time.sleep(10)
    return False


def list_tasks(tasks_dir):
    """Return {task_id: task_json_path} for all *.json under tasks_dir (any tier)."""
    out = {}
    for root, _, files in os.walk(tasks_dir):
        for f in files:
            if f.endswith(".json"):
                tid = f[:-5]
                out[tid] = os.path.join(root, f)
    return dict(sorted(out.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default="hummingbird,opencode,agent-mini,goose")
    ap.add_argument("--models", default="ornith-1.5:35b,gemma4:12b,qwen3.5:4b,gemma4:e2b")
    ap.add_argument("--tasks-dir", default=os.path.join(LRAB, "tasks"))
    ap.add_argument("--tasks", default="", help="comma list of task ids to subset (default: all)")
    ap.add_argument("--results", default=os.path.expanduser("~/dev/hummingbird/eval_results"))
    ap.add_argument("--timeout-min", type=int, default=45)
    ap.add_argument("--judge", default="", help="judge model (empty = deterministic only, faster)")
    ap.add_argument("--retries", type=int, default=1, help="retries on failed cell")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", default="", help="skip cells before this key agent:model:task (resume)")
    a = ap.parse_args()

    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    models = [x.strip() for x in a.models.split(",") if x.strip()]
    all_tasks = list_tasks(a.tasks_dir)
    if a.tasks:
        subset = [x.strip() for x in a.tasks.split(",") if x.strip()]
        tasks = {t: p for t, p in all_tasks.items() if t in subset}
    else:
        tasks = all_tasks
    if not tasks:
        print("no tasks found"); sys.exit(1)

    cells = [(ag, md, tk, tp) for ag in agents for md in models for tk, tp in tasks.items()]
    print(f"matrix plan: {len(agents)} agents x {len(models)} models x {len(tasks)} tasks = {len(cells)} cells")

    if a.dry_run:
        for ag, md, tk, _ in cells[:5]:
            print(f"  would run: {ag:12s} {md:20s} {tk}")
        print("  ... (dry-run, not executing)")
        return

    # Ollama up before starting
    if not ollama_up():
        print("Ollama not responding — waiting up to 180s...", flush=True)
        if not wait_ollama():
            print("Ollama still down, aborting."); sys.exit(2)
    print("Ollama up.", flush=True)

    # process-scoped keep-awake: a multi-hour serial matrix must not be
    # interrupted by idle sleep/hibernate (2026-08-28: a 2h hibernate killed
    # a 13-cell batch mid-run). Non-persistent — dies with this process.
    ka = subprocess.Popen([sys.executable, os.path.join(HERE, "keep_awake.py")],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"keep-awake pid={ka.pid}", flush=True)

    attempt_stats = {}
    manifest = {"cells": [], "summary": {}}
    try:
        _run_cells(a, cells, attempt_stats, manifest)
    finally:
        ka.terminate()
        print("keep-awake released.", flush=True)


def _run_cells(a, cells, attempt_stats, manifest):
    for ag, md, tk, tp in cells:
        key = f"{ag}:{md}:{tk}"
        if a.start and key < a.start:
            continue
        print(f"\n=== [{key}] starting ===", flush=True)
        cell_attempts = []
        ok = False
        for attempt in range(a.retries + 1):
            t0 = time.time()
            # probe ollama right before launching
            if not ollama_up():
                print("  [probe] ollama down, waiting 60s...", flush=True)
                wait_ollama(max_wait=60)
            # run_id 用完整模型标识(冒号转下划线), 避免 gemma4:12b/e2b 同形(自省P0-3)
            md_slug = md.replace(':', '_').replace('-', '')
            run_id = f"{ag.replace('-','')}_{tk.replace('-','')}_{md_slug}_m{attempt}_{time.strftime('%m%d_%H%M%S')}"
            cmd = [sys.executable, os.path.join(HERE, "run_bench.py"),
                   "--agent", ag, "--task", tp, "--model", md,
                   "--results", a.results, "--timeout-min", str(a.timeout_min),
                   "--run-id", run_id]
            if a.judge:
                cmd += ["--judge", a.judge]
            print(f"  attempt {attempt+1}: {' '.join(cmd[:8])}...", flush=True)
            r = subprocess.run(cmd, capture_output=False, timeout=(a.timeout_min * 60) + 120)
            wall = time.time() - t0
            cell_attempts.append({"attempt": attempt, "run_id": run_id,
                                  "wall_seconds": round(wall), "returncode": r.returncode})
            # success = score.json exists and not timeout-only
            score_path = os.path.join(a.results, run_id, "score.json")
            if os.path.exists(score_path):
                try:
                    s = json.load(open(score_path, encoding="utf-8"))
                    if s.get("failure_mode") not in ("timeout",) or attempt == a.retries:
                        ok = True
                        cell_attempts[-1]["total"] = s.get("total")
                        break
                except Exception:
                    pass
            if r.returncode != 0 and attempt < a.retries:
                print(f"  [retry] cell failed (rc={r.returncode}), retrying", flush=True)
        if not ok:
            print(f"  !! cell NOT completed after {a.retries+1} attempts", flush=True)
        attempt_stats[key] = {"attempts": len(cell_attempts), "ok": ok}
        manifest.setdefault("cells", []).append({"agent": ag, "model": md, "task": tk,
                                  "attempts": cell_attempts, "ok": ok})

    manifest["summary"] = {
        "total_cells": len(cells),
        "ok": sum(1 for c in manifest["cells"] if c["ok"]),
        "failed": sum(1 for c in manifest["cells"] if not c["ok"]),
    }
    man_path = os.path.join(a.results, "MATRIX_MANIFEST.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n=== matrix done: {manifest['summary']} ===")
    print(f"manifest: {man_path}")


if __name__ == "__main__":
    main()
