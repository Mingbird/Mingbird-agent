#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并行派发器 + 结果整合器。

派发:harness spawn N 个 headless ollama_agent 子进程(小模型),每个子 agent 一个独立
分区目录,深度限制 1(子进程 env 双闸:AGENT_CHILD_SANDBOX=1 + AGENT_PARALLEL=0 +
HUMMINGBIRD_DEPTH+1),硬超时,可中止,审计采样。
整合:确定性校验(exit code / TASK COMPLETE / 产物核对 / 审计复核)→ 拷回父目录
(默认不覆盖)→ 失败重试一次 → 再失败回退主模型串行。

prefill 预算:本模块不改主 agent 系统提示,触发/派发/整合全在 harness 代码层;
只在派发发生后给主模型注入一条运行中消息(动态成本,非 prefill 税)。

设计文档: design/2026-09-01-parallel-dispatch.md §3 §4 §5
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from parallel_config import get_parallel_config
from parallel_safety import (ChildSandbox, audit_summary, read_audit,
                             DEFAULT_DANGEROUS_COMMANDS, match_command, norm_command)

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_HARNESS_FILES = (".agent_state.json", "todo.json", "task.md", "agent.log", "audit.log")
_GIB = 1024 ** 3

# 子 agent 专用最小系统提示(子 agent 会话的局部成本,小模型短任务,不计主 prefill)
CHILD_SYSTEM = """You are a sub-agent doing one small mechanical file task.
- Work ONLY inside your current directory. Never touch paths outside it.
- Use create_file to write the result, list_dir/read_file to inspect, todo to plan.
- No commands, no network, no deleting, no editing other files.
- When the output file exists and is correct, call finish(summary=files you created)."""

# 任务文件模板:条目原文 + 明确边界(分区目录即子 agent 的工作目录)
TASK_TEMPLATE = """[simple] {text}

Constraints:
- Create the output file in THIS directory only (relative path, no drive letters, no ..).
- One input/output scope, no cross-file dependencies, do not delete or overwrite anything.
- If you cannot complete it deterministically, call finish(summary="FAILED: reason").
"""


@dataclass
class ChildTask:
    """一条被派发的子任务。"""
    item: object                      # TodoItem
    index: int = 0
    child_dir: str = ""
    attempt: int = 0
    status: str = "pending"           # pending/running/ok/failed/timeout/severe/aborted
    exit_code: int = None
    reason: str = ""
    files: list = field(default_factory=list)
    audit: dict = field(default_factory=dict)
    elapsed_s: float = 0.0


@dataclass
class DispatchResult:
    total: int = 0
    ok: int = 0
    failed: int = 0
    fallback: list = field(default_factory=list)      # [(TodoItem, reason)] 交还主模型
    severe_violations: int = 0
    aborted: bool = False
    elapsed_s: float = 0.0
    children: list = field(default_factory=list)

    @property
    def ok_items(self):
        return [c for c in self.children if c.status == "ok"]


# ---------------- 子进程 spawn(可注入 mock) ----------------

def default_spawn(cmd, env, cwd, log_path):
    """真实 spawn:stdout/stderr 进子目录 agent.log,子进程组可整体杀。"""
    logf = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=logf, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, creationflags=_creation_flags())
    return proc, logf


def _creation_flags():
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def default_kill(proc):
    """杀整棵子进程树(Windows: taskkill /F /T;POSIX: kill)。"""
    try:
        if proc.poll() is not None:
            return True
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=15)
        else:
            proc.kill()
        return True
    except Exception:
        try:
            proc.kill()
        except Exception:
            return False
        return False


# ---------------- 派发器 ----------------

class ParallelDispatcher:
    """spawn N 个 headless 子 agent 并行做简单条目。全程可中止,零硬编码。"""

    def __init__(self, cfg=None, spawn_fn=None, kill_fn=None, progress_cb=None,
                 clock=None, sleeper=None, environ=None):
        self.cfg = cfg or get_parallel_config()
        self._spawn = spawn_fn or default_spawn
        self._kill = kill_fn or default_kill
        self._progress = progress_cb or (lambda ev: None)     # GUI 走 @@DISPATCH@@
        self._clock = clock or time.time
        self._sleep = sleeper or time.sleep
        self._env = environ if environ is not None else os.environ
        self._abort = threading.Event()

    # ---- 生命周期 ----
    def abort(self):
        """全程可中止:置位后,池在每个轮询分片检查并杀掉存活子进程。"""
        self._abort.set()

    @property
    def aborted(self):
        return self._abort.is_set()

    # ---- 目录与任务文件 ----
    def _run_dir(self, parent_workdir, run_id):
        d = os.path.join(parent_workdir, str(self.cfg.get("dispatch_dirname", "_dispatch")),
                         run_id)
        os.makedirs(d, exist_ok=True)
        return d

    def _child_dir(self, run_dir, index, attempt=0):
        name = "task{:02d}".format(index + 1) + ("_retry{}".format(attempt) if attempt else "")
        d = os.path.join(run_dir, name)
        os.makedirs(d, exist_ok=True)
        return d

    def _write_task_file(self, child_dir, text):
        p = os.path.join(child_dir, "task.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(TASK_TEMPLATE.format(text=text))
        return p

    def _child_env(self, depth):
        env = dict(self._env)
        env["AGENT_CHILD_SANDBOX"] = "1"          # 子 agent 安全模型(default-deny)
        env["AGENT_PARALLEL"] = "0"               # 深度闸之二:子 agent 禁止再派
        env["HUMMINGBIRD_DEPTH"] = str(int(depth) + 1)
        env.pop("AGENT_STREAM", None)             # 子进程不开流式(headless)
        # 2026-09-01 整合遗留①:子 agent 不继承主任务的时间预算——A2 的
        # 50/75/90% 档位是按主任务总预算算的,子任务的真实时限是派发层的
        # per_task_timeout_s,继承只会让子 agent 收到错误的收尾节奏。
        env.pop("AGENT_TIME_BUDGET_SEC", None)
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _child_cmd(self, child_model, task_path, child_dir, session):
        entry = os.path.join(_MODULE_DIR, str(self.cfg.get("agent_entry", "ollama_agent.py")))
        return [sys.executable, entry, str(child_model), task_path, child_dir,
                "--session", session, "--new"]

    # ---- 主入口 ----
    def run(self, items, parent_workdir, probe, child_model=None, todo_provider=None,
            depth=0, run_id=None):
        """items: 可派条目列表(TodoItem)。返回 DispatchResult。
        任何派发层异常都被吞掉并降级为"整单交还主模型"(派发层故障不能让主任务失败)。"""
        t0 = self._clock()
        cfg = self.cfg
        model = child_model or cfg.get("child_model") or ""
        run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
        result = DispatchResult(total=len(items))
        try:
            max_par = int(probe.plan_capacity(model, cfg).get("max_parallel", 0))
        except Exception:
            max_par = 0
        if max_par < 1:
            # 容量在触发后被复核为 0(资源已变):整单交还主模型
            for it in items:
                result.fallback.append((it, "capacity_lost_before_spawn"))
                result.failed += 1
            result.elapsed_s = self._clock() - t0
            return result

        cap = min(max_par, int(cfg.get("hard_cap", 2)))
        run_dir = self._run_dir(parent_workdir, run_id)
        self._emit({"phase": "start", "total": result.total, "model": model,
                    "max_parallel": cap, "run_id": run_id})
        try:
            with ThreadPool(cap) as pool:
                futures = []
                for i, it in enumerate(items):
                    result.children.append(ChildTask(item=it, index=i))
                pending = list(result.children)
                inflight = []
                while pending or inflight:
                    if self._abort.is_set():
                        result.aborted = True
                        break
                    while pending and len(inflight) < cap:
                        ct = pending.pop(0)
                        ct.status = "running"
                        pool.submit(self._run_one, ct, run_dir, model, depth, result)
                        inflight.append(ct)
                    time.sleep(0.05)
                    inflight = [c for c in inflight if c.status == "running"]
                # 等待收尾(abort 时 _run_one 会被杀掉并落 status)
                pool.wait()
        except Exception as e:
            for ct in result.children:
                if ct.status in ("pending", "running"):
                    ct.status = "failed"
                    ct.reason = f"dispatcher_error({e})"
                    result.fallback.append((ct.item, ct.reason))
                    result.failed += 1
        for ct in result.children:
            if ct.status == "ok":
                result.ok += 1
            elif ct.status != "ok":
                if ct.status == "severe":
                    result.severe_violations += 1
                if not any(f[0] is ct.item for f in result.fallback):
                    result.fallback.append((ct.item, ct.reason or ct.status))
                    result.failed += 1
        result.elapsed_s = self._clock() - t0
        self._emit({"phase": "done", "total": result.total, "ok": result.ok,
                    "failed": result.failed, "fallback": len(result.fallback),
                    "severe_violations": result.severe_violations,
                    "aborted": result.aborted,
                    "elapsed_s": round(result.elapsed_s, 1)})
        return result

    # ---- 单个子任务(含重试) ----
    def _run_one(self, ct, run_dir, child_model, depth, result):
        try:
            max_retries = int(self.cfg.get("max_retries", 1))
            for attempt in range(0, max_retries + 1):
                if self._abort.is_set():
                    ct.status = "aborted"
                    ct.reason = "aborted_by_user"
                    return
                ct.attempt = attempt
                child_dir = self._child_dir(run_dir, ct.index, attempt)
                ct.child_dir = child_dir          # 整合器据此拷回产物
                task_path = self._write_task_file(child_dir, ct.item.text)
                session = "disp_{}_{:02d}{}".format(
                    os.path.basename(run_dir), ct.index + 1,
                    ("_r{}".format(attempt) if attempt else ""))
                cmd = self._child_cmd(child_model, task_path, child_dir, session)
                env = self._child_env(depth)
                log_path = os.path.join(child_dir, "agent.log")
                try:
                    proc, logf = self._spawn(cmd, env, child_dir, log_path)
                except Exception as e:
                    ct.status = "failed"
                    ct.reason = f"spawn_error({e})"
                    return self._finalize(ct, result)
                status, reason = self._wait(proc, logf, child_dir, ct, result)
                ct.status, ct.reason = status, reason
                ct.exit_code = getattr(proc, "returncode", None)
                if status == "ok":
                    return self._finalize(ct, result)
                # severe 违规:不重试(模型已表现危险倾向),直接回退主模型
                if status == "severe" and not self.cfg.get("retry_on_severe"):
                    return self._finalize(ct, result)
                # OOM/加载失败:立即中止整个批次(重试只会再 OOM)
                if status == "load_failure":
                    self.abort()
                    return self._finalize(ct, result)
            return self._finalize(ct, result)
        except Exception as e:      # 派发层兜底:任何异常都降级为交还主模型
            ct.status = "failed"
            ct.reason = f"child_error({e})"
            return self._finalize(ct, result)

    def _wait(self, proc, logf, child_dir, ct, result):
        """带硬超时/中止/审计采样的等待。返回 (status, reason)。"""
        deadline = self._clock() + float(self.cfg.get("per_task_timeout_s", 900))
        poll = float(self.cfg.get("poll_interval_s", 0.5))
        audit_every = max(1, int(float(self.cfg.get("audit_poll_interval_s", 5.0)) / max(poll, 0.05)))
        i = 0
        while True:
            rc = proc.poll()
            if rc is not None:
                try:
                    logf.close()
                except Exception:
                    pass
                return self._judge(rc, child_dir, ct)
            if self._abort.is_set():
                self._kill(proc)
                try:
                    logf.close()
                except Exception:
                    pass
                return "aborted", "aborted_by_user"
            if self._clock() > deadline:
                self._kill(proc)
                try:
                    logf.close()
                except Exception:
                    pass
                return "timeout", f"hard_timeout({self.cfg.get('per_task_timeout_s')}s)"
            i += 1
            if i % audit_every == 0:
                summ = audit_summary(read_audit(os.path.join(child_dir, "audit.log")))
                ct.audit = summ
                if summ["severes"] > 0:
                    self._kill(proc)      # 审计发现严重违规:立即终止(模型若还没退)
                    try:
                        logf.close()
                    except Exception:
                        pass
                    return "severe", "severe_violation(审计发现危险行为)"
                self._emit({"phase": "progress", "index": ct.index, "total": result.total,
                            "task": ct.item.text[:60], "status": "running",
                            "denies": summ["denies"], "severes": summ["severes"]})
            self._sleep(poll)

    def _judge(self, rc, child_dir, ct):
        """确定性校验(整合器的第一半):exit code / TASK COMPLETE / 审计 / 产物。"""
        # 1) exit code:53 = 子 agent 沙箱严重违规
        if rc == ChildSandbox.SEVERE_EXIT_CODE:
            ct.audit = audit_summary(read_audit(os.path.join(child_dir, "audit.log")))
            return "severe", "severe_violation(子 agent 沙箱熔断,exit 53)"
        if rc != 0:
            ct.audit = audit_summary(read_audit(os.path.join(child_dir, "audit.log")))
            # 加载失败/OOM 的启发信号:进程很快退出且没有产出文件
            if self._looks_like_load_failure(child_dir, rc):
                return "load_failure", f"child_model_load_failure(exit {rc})"
            return "failed", f"child_exit_{rc}"
        # 2) TASK COMPLETE
        log_text = _read_file(os.path.join(child_dir, "agent.log"))
        if "TASK COMPLETE" not in (log_text or ""):
            return "failed", "no_task_complete(子 agent 未正常收尾)"
        # 3) 审计复核
        summ = audit_summary(read_audit(os.path.join(child_dir, "audit.log")))
        ct.audit = summ
        if summ["severes"] > 0:
            return "severe", "severe_violation(审计复核发现危险行为)"
        if summ["denies"] >= int(self.cfg.get("max_denies_per_child", 3)):
            return "failed", f"too_many_denies({summ['denies']})"
        # 4) 产物核对
        summary = _child_summary(child_dir)
        missing = _claimed_missing(summary, child_dir)
        if missing:
            return "failed", f"missing_artifacts({', '.join(missing[:3])})"
        artifacts = _artifact_files(child_dir)
        if not artifacts:
            return "failed", "no_artifacts(分区目录没有任何产物文件)"
        ct.files = artifacts
        return "ok", ""

    @staticmethod
    def _looks_like_load_failure(child_dir, rc):
        """小模型加载失败/OOM 的启发:日志含加载错误,或秒退且无产物。"""
        log_text = (_read_file(os.path.join(child_dir, "agent.log")) or "").lower()
        signals = ("model not found", "does not exist", "failed to load", "out of memory",
                   "oom", "llm runner", "unable to load", "no such model")
        if any(s in log_text for s in signals):
            return True
        return not _artifact_files(child_dir) and len(log_text) < 4000

    def _finalize(self, ct, result):
        if ct.status == "ok":
            self._emit({"phase": "progress", "index": ct.index, "total": result.total,
                        "task": ct.item.text[:60], "status": "ok",
                        "denies": ct.audit.get("denies", 0),
                        "severes": ct.audit.get("severes", 0)})
        else:
            self._emit({"phase": "progress", "index": ct.index, "total": result.total,
                        "task": ct.item.text[:60], "status": ct.status,
                        "reason": ct.reason[:120],
                        "denies": ct.audit.get("denies", 0),
                        "severes": ct.audit.get("severes", 0)})

    def _emit(self, ev):
        try:
            self._progress(ev)
        except Exception:
            pass


# ---------------- 整合器 ----------------

class ResultIntegrator:
    """验收 + 拷回 + todo 落状态。全部确定性检查,不让主模型目测。"""

    def __init__(self, cfg=None, provider=None, copier=None, runner=None, environ=None):
        self.cfg = cfg or get_parallel_config()
        self.provider = provider
        self._copier = copier or shutil.copy2
        self._runner = runner          # (cmd, cwd, timeout) -> CompletedProcess
        self._env = environ if environ is not None else os.environ

    def verify_cmd_allowed(self, cmd):
        """verify 命令也要过危险命令黑名单(它来自条目文本,harness 执行不免检)。"""
        rules = list(self.cfg.get("dangerous_command_patterns") or DEFAULT_DANGEROUS_COMMANDS)
        rules += list(self.cfg.get("extra_dangerous_command_patterns") or [])
        return match_command(norm_command(cmd), rules) is None

    def collect(self, child):
        """子产物拷回父目录。返回 (copied, conflicts)。默认不覆盖已有文件。"""
        parent = child.parent_workdir
        copied, conflicts = [], []
        for rel in child.files:
            src = os.path.join(child.child_dir, rel)
            dst = os.path.join(parent, rel)
            if os.path.exists(dst) and not self.cfg.get("allow_overwrite_existing"):
                conflicts.append(rel)
                continue
            os.makedirs(os.path.dirname(dst) or parent, exist_ok=True)
            self._copier(src, dst)
            copied.append(rel)
        return copied, conflicts

    def integrate(self, result, parent_workdir):
        """整合整个 DispatchResult:拷回 + todo 置 done。返回 (integrated, conflicts, report)。"""
        integrated, conflicts, notes = [], [], []
        for ct in result.ok_items:
            copied, conf = self.collect(ChildView(ct, parent_workdir))
            integrated += copied
            conflicts += conf
            if conf:
                notes.append(f"[{ct.item.id}] 部分产物冲突未覆盖: {', '.join(conf)}")
                ct.status = "failed"
                ct.reason = "overwrite_conflict(父目录已有同名文件,默认不覆盖)"
            else:
                notes.append(f"[{ct.item.id}] 已完成并拷回: {', '.join(copied)}")
                if self.provider:
                    try:
                        self.provider.mark_done(ct.item.id, note="done-by-subagent")
                    except Exception:
                        pass
        for ct in result.children:
            if ct.status not in ("ok",):
                notes.append(f"[{ct.item.id}] 未完成({ct.status}: {ct.reason})由主模型接手")
        return integrated, conflicts, "\n".join(notes)


@dataclass
class ChildView:
    """collect 需要的最小视图(child_dir / parent_workdir / files)。"""
    ct: object
    parent_workdir: str

    @property
    def child_dir(self):
        return self.ct.child_dir

    @property
    def files(self):
        return self.ct.files


def _read_file(path, limit=200000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def _child_summary(child_dir):
    """从子 agent 检查点读 finish summary(最后一条含 TASK COMPLETE 的 assistant 消息)。"""
    state = os.path.join(child_dir, ".agent_state.json")
    try:
        msgs = json.load(open(state, encoding="utf-8"))
    except Exception:
        return ""
    for m in reversed(msgs if isinstance(msgs, list) else []):
        if m.get("role") != "assistant":
            continue
        c = str(m.get("content") or "")
        if "[TASK_COMPLETE]" in c:
            return c.split("[TASK_COMPLETE]", 1)[1].strip()
        for tc in (m.get("tool_calls") or []):
            try:
                if tc.get("function", {}).get("name") == "finish":
                    args = tc["function"].get("arguments") or {}
                    if isinstance(args, str):
                        args = json.loads(args)
                    return str(args.get("summary", ""))
            except Exception:
                continue
    return ""


_CLAIM_RE = re.compile(r"[A-Za-z0-9_\-一-鿿][A-Za-z0-9_\-一-鿿]*\.[A-Za-z0-9]{2,5}")
_CLAIM_EXTS = (".md", ".txt", ".png", ".jpg", ".jpeg", ".csv", ".py", ".json", ".docx",
               ".xlsx", ".pdf", ".html", ".yaml", ".yml", ".svg", ".tex", ".tsv", ".log")


def _claimed_missing(summary, child_dir):
    """子 agent finish summary 声称的产物逐一核对(与主 agent finish 门禁同规则)。"""
    toks = []
    for m in _CLAIM_RE.finditer(summary or ""):
        t = m.group(0)
        if t.lower().endswith(_CLAIM_EXTS) and t not in toks:
            toks.append(t)
    missing = []
    for tok in toks:
        rel = tok.replace("\\", "/").lstrip("./")
        p = os.path.join(child_dir, rel)
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            continue
        base = os.path.basename(rel).lower()
        found = any(b.lower() == base for b in _artifact_files(child_dir))
        if not found:
            missing.append(tok)
    return missing


def _artifact_files(child_dir):
    """分区目录里的非 harness 产物文件(相对路径,递归)。"""
    out = []
    for root, dirs, files in os.walk(child_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for f in files:
            if f in _HARNESS_FILES:
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, child_dir).replace("\\", "/")
            try:
                if os.path.getsize(p) <= 0:
                    continue
            except Exception:
                continue
            out.append(rel)
    return sorted(out)


# ---------------- 给主模型的注入消息(动态成本,非 prefill 税) ----------------

def summary_for_parent(result, integrated):
    """派发结束后给主模型的一条 user 消息。模型此刻才第一次知道有子 agent 这回事。"""
    lines = []
    if result.aborted:
        lines.append("并行派发已被中止。")
    if integrated:
        lines.append("以下条目已由并行子任务完成,产物文件已写入当前工作目录(可直接使用,不必重做):")
        for rel in integrated:
            lines.append(f"- {rel}")
    if result.fallback:
        lines.append("以下条目子任务未完成,需要你按原计划自己完成:")
        seen = set()
        for it, why in result.fallback:
            key = getattr(it, "id", str(it))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- ({key}) {getattr(it, 'text', '')[:120]}  [原因: {why}]")
    if not lines:
        return ""
    lines.append("请核对上述产物与你的计划一致性后继续推进。")
    return "\n".join(lines)


# ---------------- GUI/日志进度行 ----------------

def emit_progress_line(ev, out=None):
    """把进度事件写成 @@DISPATCH@@ 协议行(GUI 按行解析;旧版 GUI 当普通日志丢弃)。"""
    try:
        (out or sys.stdout).write("@@DISPATCH@@" + json.dumps(ev, ensure_ascii=False) + "\n")
        (out or sys.stdout).flush()
    except Exception:
        pass


# ---------------- 线程池(最小实现,避免依赖 concurrent.futures 的语义差异) ----------------

class ThreadPool:
    """固定线程数的简单池:submit 返回句柄,wait 阻塞至全部完成。"""

    def __init__(self, n):
        self.n = max(1, int(n))
        self._workers = []
        self._lock = threading.Lock()
        self._errors = []

    def submit(self, fn, *a, **kw):
        t = threading.Thread(target=self._wrap, args=(fn,) + a, kwargs=kw, daemon=True)
        with self._lock:
            self._workers.append(t)
        t.start()
        return t

    def _wrap(self, fn, *a, **kw):
        try:
            fn(*a, **kw)
        except Exception as e:
            with self._lock:
                self._errors.append(e)

    def wait(self):
        for t in list(self._workers):
            t.join()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.wait()
        return False


# ---------------- CLI:python parallel_dispatch.py plan ----------------

def _cli(argv):
    if not argv or argv[0] != "plan":
        print("用法: python parallel_dispatch.py plan   # 打印本机容量计划(只读,不派发)")
        return 0
    from parallel_probe import ResourceProbe, format_capacity_table
    from parallel_config import get_parallel_config
    import appconfig
    cfg = get_parallel_config()
    host = (appconfig.load_config() or {}).get("ollama_host") or "http://127.0.0.1:11434"
    probe = ResourceProbe(ollama_host=host)
    model = cfg.get("child_model") or "(未配置 child_model)"
    plan = probe.plan_capacity(model, cfg)
    print(format_capacity_table(plan, cfg))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
