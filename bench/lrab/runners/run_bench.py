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
    # 公平性: 与其他 agent 对齐 num_ctx=32768(自省P0-1, 原默认16384)
    env["AGENT_CTX"] = os.environ.get("AGENT_CTX", "32768")
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
    # 基准隔离: 干净配置(仅 DDG MCP, 无私人 skills)
    env["OPENCODE_CONFIG"] = os.path.expanduser("~/.hummingbird_bench/opencode-config/opencode.json")
    # XDG_CONFIG_HOME 指向空目录: 屏蔽全局 ~/.config/opencode(否则其 7 个学术 MCP
    # 会与基准配置合并, 工具数爆炸压垮小模型 — 这是公平性的关键)
    env["XDG_CONFIG_HOME"] = os.path.join(os.path.dirname(os.path.dirname(workdir)), "oc_xdg")
    os.makedirs(env["XDG_CONFIG_HOME"], exist_ok=True)
    # --auto: 非交互自动批准; --dir: 明确工作目录; 配合 config 里 permission=allow。
    # 注意: 不用 --format json — 实测它会吞掉 position 参数里的 prompt(模型收到空任务),
    # 非 JSON 模式 prompt 正常传递。
    proc = subprocess.run(
        [oc_cmd, "run", "--model", f"ollama/{model}", "--auto", "--dir", workdir,
         task["prompt"]],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout_min * 60, cwd=workdir, env=env)
    return proc, time.time() - t0


def _win_path(p):
    """转为 Windows 原生绝对路径(Git Bash 的 /c/... 或 C:/... 都统一成 C:\\...)。"""
    p = os.path.abspath(p)
    return os.path.normpath(p)


def run_agent_mini(task, workdir, model, timeout_min):
    # agent-mini 的模型只能经 config.json 切换: 运行前写入
    cfg_path = os.path.expanduser("~/.agent-mini/config.json")
    # 自省P1-8: 备份用户真机配置, 跑完还原(基准隔离, 不污染日常使用)
    backup = None
    if os.path.exists(cfg_path):
        try:
            backup = open(cfg_path, encoding="utf-8").read()
        except Exception:
            backup = None
    try:
        cfg = json.loads(backup) if backup else {}
    except Exception:
        cfg = {}
    cfg.setdefault("provider", "ollama")
    cfg.setdefault("providers", {}).setdefault("ollama", {})["baseUrl"] = "http://localhost:11434"
    cfg["providers"]["ollama"]["model"] = model
    cfg["providers"]["ollama"]["num_ctx"] = 32768  # 自省P0-1: 与其他 agent 对齐
    cfg.setdefault("agent", {})["temperature"] = 0.0
    # workspace 指向隔离实例(防止写个人记忆/技能),并覆盖为 Windows 原生路径
    cfg["workspace"] = _win_path(workdir)
    cfg.setdefault("memory", {})["enabled"] = False
    cfg["tools"]["restrictToWorkspace"] = True
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    env = dict(os.environ)
    env["AGENT_MINI_CTX"] = "32768"
    t0 = time.time()
    try:
        proc = subprocess.run(
            ["agent-mini", "chat", "--workspace", _win_path(workdir), "-m", task["prompt"]],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_min * 60, cwd=workdir, env=env)
    finally:
        # 还原用户配置
        if backup is not None:
            try:
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(backup)
            except Exception:
                pass
    return proc, time.time() - t0


def run_goose(task, workdir, model, timeout_min):
    t0 = time.time()
    env = dict(os.environ)
    env["GOOSE_PROVIDER"] = "ollama"
    env["GOOSE_MODEL"] = model
    goose_exe = os.path.expanduser("~/myagents-bin/goose/goose-package/goose.exe")
    # -q: 只输出模型响应(安静); --path: 明确工作目录(否则默认主目录,产物写错地方)
    proc = subprocess.run(
        [goose_exe, "run", "-q", "--path", workdir, "-t", task["prompt"]],
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
    try:
        proc, wall = RUNNERS[a.agent](task, workdir, a.model, a.timeout_min)
    except subprocess.TimeoutExpired:
        # 超时: 记为 timeout, 不判分(避免把环境失败当能力 0 分)
        failure = {"task_id": task["id"], "agent": a.agent, "model": a.model,
                   "wall_seconds": a.timeout_min * 60, "exit_code": None, "run_id": run_id,
                   "failure_mode": "timeout",
                   "failure_note": f"agent exceeded {a.timeout_min} min wall budget"}
        with open(os.path.join(out_dir, "score.json"), "w", encoding="utf-8") as f:
            json.dump(failure, f, ensure_ascii=False, indent=2)
        print(json.dumps({k: failure[k] for k in ("task_id", "agent", "model",
                                                  "wall_seconds", "failure_mode")}), flush=True)
        return
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
    # 失败模式分类: 依据 exit code + 是否产出关键产物
    failure_mode = "completed"
    transcript = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        failure_mode = "crash" if wall < 60 else "error"
    elif score.get("total", 0) == 0:
        # 0 分时区分: 无产物 / 读任务后停滞(stall) / 秒退(early_finish)
        artifacts = [f for f in os.listdir(workdir) if f != "task_input.txt" and f != "aging_data.csv"]
        if not artifacts:
            if "task_input" in transcript and "Read" in transcript:
                failure_mode = "stall"   # 读了任务文件但无后续动作
            elif wall < 30:
                failure_mode = "early_finish"
            else:
                failure_mode = "no_artifacts"
    score.update({
        "agent": a.agent, "model": a.model, "wall_seconds": round(wall, 1),
        "exit_code": proc.returncode, "run_id": run_id, "failure_mode": failure_mode,
    })
    with open(os.path.join(out_dir, "score.json"), "w", encoding="utf-8") as f:
        json.dump(score, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: score[k] for k in ("task_id", "agent", "model", "milestone_score",
                                            "final_score", "total", "wall_seconds")}, ensure_ascii=False))
    # workdir 已在 out_dir 内(run 隔离设计),无需再快照;若 runner 被外部指定了
    # 独立 workdir(旧用法),才复制归档。统一 normcase+abspath 防 Windows 分隔符误判
    wd_norm = os.path.normcase(os.path.abspath(workdir))
    out_norm = os.path.normcase(os.path.abspath(out_dir))
    if os.path.dirname(wd_norm) != out_norm and wd_norm != out_norm:
        snap = os.path.join(out_dir, "workdir_snapshot")
        shutil.copytree(workdir, snap, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "corpus", ".agent_state.json"))


if __name__ == "__main__":
    main()
