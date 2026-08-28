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
    # 基准隔离: 干净实例(仅 tavily MCP, 无私人 skills)
    env["HUMMINGBIRD_HOME"] = os.path.expanduser("~/.hummingbird_bench")
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, os.path.join(HB_ROOT, "ollama_agent.py"), model, taskfile, workdir],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, env=env, cwd=workdir)
    return proc, time.time() - t0


def run_opencode(task, workdir, model, timeout_min):
    t0 = time.time()
    oc_cmd = shutil.which("opencode") or os.path.expandvars(
        r"%LOCALAPPDATA%\MyAgents\nodejs\opencode.cmd")
    env = dict(os.environ)
    # 基准隔离: 干净配置(仅 tavily MCP, 无私人 skills)
    env["OPENCODE_CONFIG"] = os.path.expanduser("~/.hummingbird_bench/opencode-config/opencode.json")
    proc = subprocess.run(
        [oc_cmd, "run", "--model", f"ollama/{model}", task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir, env=env)
    return proc, time.time() - t0


def run_agent_mini(task, workdir, model, timeout_min):
    # agent-mini 的模型只能经 config.json 切换: 运行前写入
    cfg_path = os.path.expanduser("~/.agent-mini/config.json")
    try:
        cfg = json.load(open(cfg_path, encoding="utf-8"))
    except Exception:
        cfg = {}
    cfg.setdefault("provider", "ollama")
    cfg.setdefault("providers", {}).setdefault("ollama", {})["baseUrl"] = "http://localhost:11434"
    cfg["providers"]["ollama"]["model"] = model
    cfg.setdefault("agent", {})["temperature"] = 0.0
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    t0 = time.time()
    proc = subprocess.run(
        ["agent-mini", "chat", "--workspace", workdir, "-m", task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir)
    return proc, time.time() - t0


def run_goose(task, workdir, model, timeout_min):
    t0 = time.time()
    env = dict(os.environ)
    env["GOOSE_PROVIDER"] = "ollama"
    env["GOOSE_MODEL"] = model
    goose_exe = os.path.expanduser("~/myagents-bin/goose/goose-package/goose.exe")
    proc = subprocess.run(
        [goose_exe, "run", "--text", task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir, env=env)
    return proc, time.time() - t0


RUNNERS = {
    "hummingbird": run_hummingbird,
    "opencode": run_opencode,
    "agent-mini": run_agent_mini,
    "goose": run_goose,
}


def wait_for_quiet(workdir, quiet_secs=20, max_wait=180):
    """等 workdir 文件集合+大小稳定(被测 agent 可能留下后台子进程继续写盘)。
    连续 quiet_secs 秒无变化即返回;最长等 max_wait 秒。"""
    import time as _t

    def _state():
        st = []
        for root, _, files in os.walk(workdir):
            for f in files:
                try:
                    p = os.path.join(root, f)
                    st.append((p, os.path.getsize(p)))
                except OSError:
                    pass
        return sorted(st)

    deadline = _t.time() + max_wait
    last, since = _state(), _t.time()
    while _t.time() < deadline:
        _t.sleep(5)
        cur = _state()
        if cur != last:
            last, since = cur, _t.time()
        elif _t.time() - since >= quiet_secs:
            return True
    return False


def main():
    # 隔离与归档: 每 run 一个唯一目录(agent_model_task_时间戳), workdir 和产物同放,
    # 归档到 ~/dev/hummingbird/eval_results/ (持久, 论文/HN 数据源, 不互相污染)
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(RUNNERS))
    ap.add_argument("--task", required=True)
    ap.add_argument("--model", default="ornith-1.5:35b")
    ap.add_argument("--results", default=os.path.expanduser("~/dev/hummingbird/eval_results"))
    ap.add_argument("--timeout-min", type=int, default=60)
    ap.add_argument("--judge", default="", help="judge model; empty = deterministic only")
    ap.add_argument("--run-id", default="", help="auto: agent_model_task_timestamp")
    a = ap.parse_args()

    with open(a.task, encoding="utf-8") as f:
        task = json.load(f)
    # 隔离: run-id 强制含时间戳; workdir 在 run 目录内(每 run 完全独立, 互不污染)
    run_id = a.run_id or f"{a.agent}_{task['id'].replace('-', '')}_{model.split(':')[0].replace('-','')}_{time.strftime('%m%d_%H%M%S')}"
    out_dir = os.path.join(a.results, run_id)
    os.makedirs(out_dir, exist_ok=True)
    workdir = os.path.join(out_dir, "workdir")
    prepare_workdir(task, workdir)

    print(f"[{run_id}] agent={a.agent} model={a.model} task={task['id']}", flush=True)
    proc, wall = RUNNERS[a.agent](task, workdir, a.model, a.timeout_min)
    print(f"[{run_id}] agent finished exit={proc.returncode} wall={wall:.0f}s", flush=True)

    with open(os.path.join(out_dir, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(proc.stdout or "")
        if proc.stderr:
            f.write("\n--- STDERR ---\n" + proc.stderr)

    # 等后台子进程写盘完成(agent 主进程退出 ≠ 其派生进程退出),再判分
    wait_for_quiet(workdir)

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
    # workdir 已在 out_dir 内(run 隔离设计),无需再快照;若 runner 被外部指定了
    # 独立 workdir(旧用法),才复制归档
    if os.path.dirname(os.path.abspath(workdir)) != out_dir:
        snap = os.path.join(out_dir, "workdir")
        shutil.copytree(workdir, snap, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "corpus", ".agent_state.json"))


if __name__ == "__main__":
    main()
