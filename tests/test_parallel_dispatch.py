"""派发器与整合器测试:全部 mock spawn,不启动真实模型/子进程树。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import parallel_dispatch as PD
import parallel_todo as PT
from parallel_config import get_parallel_config


def cfg(**over):
    c = get_parallel_config(config={"parallel": {}})
    c.update(over)
    return c


class StubProbe:
    def __init__(self, max_parallel=2):
        self.mp = max_parallel

    def plan_capacity(self, model, cfg):
        return {"max_parallel": self.mp, "reasons": [], "snapshot": {}}


class FakeProc:
    def __init__(self, returncode=None):
        self.pid = 4242
        self.returncode = returncode
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def _fake_child_ok(child_dir, artifact="out.md", summary=None, extra=None):
    """模拟一个成功收尾的子 agent:写产物 + agent.log + 检查点。
    summary 与产物名必须一致(_claimed_missing 会核对声称与实际)。"""
    summary = summary if summary is not None else "created " + artifact
    with open(os.path.join(child_dir, artifact), "w", encoding="utf-8") as f:
        f.write("# report\n\nhello\n")
    with open(os.path.join(child_dir, "agent.log"), "w", encoding="utf-8") as f:
        f.write("[0] ⚙ create_file ...\n===== TASK COMPLETE =====\n" + summary + "\n")
    json.dump([{"role": "assistant", "content": "[TASK_COMPLETE] " + summary}],
              open(os.path.join(child_dir, ".agent_state.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    if extra:
        extra(child_dir)


def make_items(n, text="把 data{}.csv 转成 markdown 表格"):
    return [PT.TodoItem(id=str(i + 1), text=text.format(i + 1)) for i in range(n)]


class Recorder:
    def __init__(self):
        self.spawns = []
        self.envs = []


def success_dispatcher(rec=None, **kw):
    """spawn_fn 同步模拟子 agent 成功收尾。每个子任务产出独立命名的产物
    (设计约束:子 agent 之间绝不共写同一个父目录文件)。"""
    def spawn(cmd, env, cwd, log_path):
        if rec is not None:
            rec.spawns.append(cmd)
            rec.envs.append(dict(env))
        _fake_child_ok(cwd, artifact="out_%s.md" % os.path.basename(cwd))
        logf = open(log_path, "a", encoding="utf-8")
        logf.write("x")
        return FakeProc(0), logf
    return PD.ParallelDispatcher(cfg=cfg(hard_cap=2), spawn_fn=spawn,
                                 progress_cb=lambda ev: None, **kw)


# ---------------- 成功路径 ----------------
class TestHappyPath:
    def test_children_env_and_command(self, tmp_path):
        rec = Recorder()
        d = success_dispatcher(rec)
        d.run(make_items(2), str(tmp_path), StubProbe(), child_model="gemma4:e2b", run_id="r1")
        env = rec.envs[0]
        assert env["AGENT_CHILD_SANDBOX"] == "1"
        assert env["AGENT_PARALLEL"] == "0"
        assert env["MINGBIRD_DEPTH"] == "1"
        assert "HUMMINGBIRD_DEPTH" not in env  # 旧名不得残留,防止新旧值打架
        assert "AGENT_STREAM" not in env
        # 出队顺序在线程池下是竞态:按集合断言,不依赖 task01/task02 先后
        assert {c[4].rsplit(chr(92), 1)[-1] for c in rec.spawns} == {"task01", "task02"}
        for cmd in rec.spawns:
            assert cmd[2] == "gemma4:e2b"
            assert "--session" in cmd and cmd[cmd.index("--session") + 1].startswith("disp_r1_")

    def test_child_env_strips_parent_time_budget(self, tmp_path):
        # 2026-09-01 整合遗留①:A2 的 AGENT_TIME_BUDGET_SEC 是主任务总预算,
        # 子任务的真实时限是派发层 per_task_timeout_s——继承会让子 agent
        # 按错误的钟收到 50/75/90% 收尾提示,必须在 _child_env 里剥掉。
        parent_env = dict(os.environ)
        parent_env["AGENT_TIME_BUDGET_SEC"] = "5400"
        d = PD.ParallelDispatcher(cfg=cfg(hard_cap=2), spawn_fn=None,
                                  progress_cb=lambda ev: None, environ=parent_env)
        env = d._child_env(0)
        assert "AGENT_TIME_BUDGET_SEC" not in env
        assert env["AGENT_CHILD_SANDBOX"] == "1" and env["AGENT_PARALLEL"] == "0"

    def test_three_items_all_ok_and_collected(self, tmp_path):
        provider = PT.JsonTodoProvider(str(tmp_path))
        json.dump([{"item": "把 data.csv 转成 markdown 表格", "done": False}] * 3,
                  open(tmp_path / "todo.json", "w", encoding="utf-8"), ensure_ascii=False)
        d = success_dispatcher()
        res = d.run(make_items(3), str(tmp_path), StubProbe(), child_model="gemma4:e2b",
                    todo_provider=provider, run_id="r1")
        assert res.total == 3 and res.ok == 3 and res.failed == 0
        integ = PD.ResultIntegrator(cfg=cfg(), provider=provider)
        integrated, conflicts, notes = integ.integrate(res, str(tmp_path))
        assert len(integrated) == 3 and not conflicts
        for name in integrated:
            assert os.path.isfile(tmp_path / name)
        assert all(i["done"] for i in json.load(open(tmp_path / "todo.json", encoding="utf-8")))

    def test_progress_events_emitted(self, tmp_path):
        events = []

        def spawn(cmd, env, cwd, log_path):
            _fake_child_ok(cwd)
            return FakeProc(0), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(), spawn_fn=spawn, progress_cb=events.append)
        d.run(make_items(2), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        phases = [e["phase"] for e in events]
        assert phases[0] == "start" and phases[-1] == "done"
        assert events[-1]["ok"] == 2

    def test_dispatch_protocol_line_format(self, capsys):
        PD.emit_progress_line({"phase": "start", "total": 2})
        out = capsys.readouterr().out
        assert out.startswith("@@DISPATCH@@") and '"total": 2' in out.replace("total", "total")


# ---------------- 失败 / 重试 / 回退 ----------------
class TestFailureModes:
    def test_retry_then_success(self, tmp_path):
        calls = {"n": 0}

        def spawn(cmd, env, cwd, log_path):
            calls["n"] += 1
            if os.path.basename(cwd).endswith("_retry1"):
                _fake_child_ok(cwd)
                return FakeProc(0), open(log_path, "a", encoding="utf-8")
            # 第一次尝试:没写产物、没收尾
            return FakeProc(0), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=1), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 1 and calls["n"] == 2
        assert os.path.isdir(tmp_path / "_dispatch" / "r1" / "task01_retry1")

    def test_retry_exhausted_falls_back(self, tmp_path):
        def spawn(cmd, env, cwd, log_path):
            return FakeProc(0), open(log_path, "a", encoding="utf-8")   # 永不收尾

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=1), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(2), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 0 and len(res.fallback) == 2
        assert all("no_task_complete" in why for _, why in res.fallback)

    def test_missing_artifact_rejected(self, tmp_path):
        def spawn(cmd, env, cwd, log_path):
            # 声称写了 missing.md 但没写
            _fake_child_ok(cwd, summary="created missing.md and out.md")
            return FakeProc(0), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=0), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 0 and "missing_artifacts" in res.fallback[0][1]

    def test_no_artifact_rejected(self, tmp_path):
        def spawn(cmd, env, cwd, log_path):
            # 收尾了但分区目录里没有任何产物文件(声称里也没提文件)
            _fake_child_ok(cwd, summary="done")
            os.remove(os.path.join(cwd, "out.md"))
            return FakeProc(0), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=0), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 0 and "no_artifacts" in res.fallback[0][1]

    def test_timeout_kills_child(self, tmp_path):
        now = {"t": 1000.0}
        proc_holder = {}

        def spawn(cmd, env, cwd, log_path):
            p = FakeProc(None)
            proc_holder["p"] = p
            return p, open(log_path, "a", encoding="utf-8")

        killed = []
        d = PD.ParallelDispatcher(cfg=cfg(per_task_timeout_s=5, poll_interval_s=1.0,
                                          max_retries=0),
                                  spawn_fn=spawn, progress_cb=lambda e: None,
                                  kill_fn=lambda p: (killed.append(p.pid) or p.kill() or True),
                                  clock=lambda: now["t"], sleeper=lambda s: now.__setitem__(
                                      "t", now["t"] + s))
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 0 and res.fallback[0][1].startswith("hard_timeout")
        assert proc_holder["p"].killed and killed

    def test_abort_before_run_spawns_nothing(self, tmp_path):
        rec = Recorder()
        d = success_dispatcher(rec)
        d.abort()
        res = d.run(make_items(3), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.aborted and not rec.spawns and len(res.fallback) == 3

    def test_capacity_lost_before_spawn_falls_back(self, tmp_path):
        rec = Recorder()
        d = success_dispatcher(rec)
        res = d.run(make_items(2), str(tmp_path), StubProbe(max_parallel=0),
                    child_model="m", run_id="r1")
        assert not rec.spawns and len(res.fallback) == 2

    def test_spawn_exception_does_not_crash_dispatcher(self, tmp_path):
        def spawn(cmd, env, cwd, log_path):
            raise RuntimeError("no such interpreter")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=0), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 0 and "spawn_error" in res.fallback[0][1]

    def test_all_failed_falls_back_to_parent(self, tmp_path):
        def spawn(cmd, env, cwd, log_path):
            return FakeProc(1), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=0), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(2), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.ok == 0 and len(res.fallback) == 2
        note = PD.summary_for_parent(res, [])
        assert "需要你按原计划自己完成" in note


# ---------------- 安全集成:严重违规 / OOM ----------------
class TestSafetyIntegration:
    def test_severe_violation_no_retry_and_fallback(self, tmp_path):
        calls = {"n": 0}

        def spawn(cmd, env, cwd, log_path):
            calls["n"] += 1
            with open(os.path.join(cwd, "audit.log"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"verdict": "severe", "kind": "write",
                                    "target": "C:\\Windows\\x", "severity": "severe",
                                    "reason": "sensitive_path(\\windows\\)"}) + "\n")
            return FakeProc(53), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=2), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.severe_violations == 1 and res.ok == 0
        assert calls["n"] == 1          # severe 不重试
        assert "severe" in res.fallback[0][1]

    def test_audit_severe_found_while_running_kills(self, tmp_path):
        now = {"t": 0.0}

        def spawn(cmd, env, cwd, log_path):
            # 子 agent 没退,但审计文件已经出现 severe
            with open(os.path.join(cwd, "audit.log"), "w", encoding="utf-8") as f:
                f.write(json.dumps({"verdict": "severe", "kind": "write",
                                    "target": "\\\\wsl$\\Ubuntu", "severity": "severe",
                                    "reason": "sensitive_path(\\\\wsl$)"}) + "\n")
            return FakeProc(None), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(per_task_timeout_s=600, poll_interval_s=0.1,
                                          audit_poll_interval_s=0.2, max_retries=0),
                                  spawn_fn=spawn, progress_cb=lambda e: None,
                                  kill_fn=lambda p: (p.kill() or True),
                                  clock=lambda: now["t"], sleeper=lambda s: now.__setitem__(
                                      "t", now["t"] + s))
        res = d.run(make_items(1), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.severe_violations == 1

    def test_load_failure_aborts_whole_batch(self, tmp_path):
        spawns = {"n": 0}

        def spawn(cmd, env, cwd, log_path):
            spawns["n"] += 1
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("Error: model 'nope' not found, try pulling it first\n")
            return FakeProc(1), open(log_path, "a", encoding="utf-8")

        d = PD.ParallelDispatcher(cfg=cfg(max_retries=0, hard_cap=1), spawn_fn=spawn,
                                  progress_cb=lambda e: None)
        res = d.run(make_items(3), str(tmp_path), StubProbe(), child_model="m", run_id="r1")
        assert res.fallback and "load_failure" in res.fallback[0][1]
        assert spawns["n"] == 1          # OOM/加载失败 → 立即中止整批,不再派


# ---------------- 整合:冲突与不覆盖 ----------------
class TestIntegrator:
    def test_conflict_never_overwrites_by_default(self, tmp_path):
        provider = PT.JsonTodoProvider(str(tmp_path))
        json.dump([{"item": "t", "done": False}],
                  open(tmp_path / "todo.json", "w", encoding="utf-8"), ensure_ascii=False)
        (tmp_path / "out.md").write_text("# original user file", encoding="utf-8")
        res = PD.DispatchResult(total=1, ok=1)
        ct = PD.ChildTask(item=PT.TodoItem(id="1", text="t"), index=0, status="ok",
                          child_dir=str(tmp_path / "_dispatch" / "r1" / "task01"),
                          files=["out.md"])
        res.children = [ct]
        os.makedirs(ct.child_dir, exist_ok=True)
        open(os.path.join(ct.child_dir, "out.md"), "w", encoding="utf-8").write("# child")
        integ = PD.ResultIntegrator(cfg=cfg(), provider=provider)
        integrated, conflicts, notes = integ.integrate(res, str(tmp_path))
        assert integrated == [] and conflicts == ["out.md"]
        assert (tmp_path / "out.md").read_text(encoding="utf-8") == "# original user file"
        assert ct.status == "failed"

    def test_overwrite_allowed_when_configured(self, tmp_path):
        (tmp_path / "out.md").write_text("# original", encoding="utf-8")
        res = PD.DispatchResult(total=1, ok=1)
        ct = PD.ChildTask(item=PT.TodoItem(id="1", text="t"), index=0, status="ok",
                          child_dir=str(tmp_path / "c"), files=["out.md"])
        res.children = [ct]
        os.makedirs(ct.child_dir, exist_ok=True)
        open(os.path.join(ct.child_dir, "out.md"), "w", encoding="utf-8").write("# child")
        integ = PD.ResultIntegrator(cfg=cfg(allow_overwrite_existing=True))
        integrated, conflicts, _ = integ.integrate(res, str(tmp_path))
        assert integrated == ["out.md"] and conflicts == []

    def test_harness_files_not_copied_back(self, tmp_path):
        d = os.path.join(str(tmp_path), "c")
        os.makedirs(d, exist_ok=True)
        for f in (".agent_state.json", "todo.json", "task.md", "agent.log", "audit.log"):
            open(os.path.join(d, f), "w", encoding="utf-8").write("x")
        open(os.path.join(d, "real.md"), "w", encoding="utf-8").write("content")
        assert PD._artifact_files(d) == ["real.md"]

    def test_verify_cmd_must_pass_blacklist(self, tmp_path):
        integ = PD.ResultIntegrator(cfg=cfg())
        assert integ.verify_cmd_allowed("python -m pytest -q") is True
        assert integ.verify_cmd_allowed("wsl --unregister Ubuntu") is False
        assert integ.verify_cmd_allowed("rm -rf x") is False


# ---------------- 给主模型的注入消息 ----------------
class TestParentSummary:
    def test_summary_lists_done_and_fallback(self, tmp_path):
        res = PD.DispatchResult(total=2, ok=1, failed=1)
        it_ok = PT.TodoItem(id="1", text="a.csv 转成 md")
        it_bad = PT.TodoItem(id="2", text="b.csv 转成 md")
        res.children = [PD.ChildTask(item=it_ok, index=0, status="ok", files=["a.md"]),
                        PD.ChildTask(item=it_bad, index=1, status="failed",
                                     reason="missing_artifacts(b.md)")]
        res.fallback = [(it_bad, "missing_artifacts(b.md)")]
        note = PD.summary_for_parent(res, ["a.md"])
        assert "a.md" in note and "b.csv 转成 md" in note
        assert "不必重做" in note and "自己完成" in note

    def test_empty_when_nothing(self):
        assert PD.summary_for_parent(PD.DispatchResult(), []) == ""

    def test_gui_protocol_marker_wired(self):
        """GUI 侧应解析 @@DISPATCH@@ 行(接线冒烟检查)。"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "agent_gui.py"), encoding="utf-8").read()
        assert "@@DISPATCH@@" in src and "_on_dispatch" in src
