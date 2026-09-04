# -*- coding: utf-8 -*-
"""三分支整合(integ-0901)的交叉语义测试。

覆盖 alt-0901 × todo-0901 × par-0901 的整合点(a-e):
  a. par 的 TodoProvider 工厂注册 todo-0901 的 todo.json 存储适配器
  b. 子 agent(child mode)不受主 agent 的 todo finish 门禁约束
  c. _SMALL_MODEL_MODE 在 child mode 下按子模型参数量置位(子 agent 永不判为问答)
  d. 派发回执消息不污染类别路由/问答判定;恢复场景不双发
  e. 出厂默认全关(不设 env / 不写 config 时行为与 v1.2.0 一致)

不依赖网络 / 不调用 ollama(全部脚本化驱动)。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

import parallel_config as PC
import parallel_todo as PT


@pytest.fixture
def wd(tmp_path):
    return str(tmp_path)


class _StubSandbox:
    """最小子 agent 沙箱替身:只实现 agent_loop 用到的两个方法。"""

    def __init__(self):
        self.terminated = False

    def check_tool(self, name, args):
        return ("allow", "", "")

    def should_terminate(self):
        return self.terminated


@pytest.fixture
def child_mode():
    """把当前进程置为"子 agent 模式"(不真正安装沙箱,只装判定所需的桩)。"""
    saved = (A._child_sandbox, A._SMALL_MODEL_MODE)
    A._child_sandbox = _StubSandbox()
    try:
        yield A._child_sandbox
    finally:
        A._child_sandbox, A._SMALL_MODEL_MODE = saved


def _scripted_loop(workdir, calls, task="修复 m08.py 里的 bug,并运行测试验证。",
                   model="gemma4:12b", system="sys", session=None, capture=None):
    """按脚本驱动 agent_loop(仿 test_guards 的做法),不触网、不调 ollama。
    capture:可选 dict,循环结束后(还原全局开关前)记录 _SMALL_MODEL_MODE 等现场。"""
    saved = (A.call_chat, A.run_tool, A.mcp_manifest, A.mcp_tool_defs)
    it = {"i": 0}

    def fake_call_chat(m, messages, ctx=None, tools=None, stream=False,
                       on_token=None, on_think=None):
        k = it["i"]; it["i"] += 1
        if k < len(calls):
            name, args, _ = calls[k]
            return {"message": {"content": "", "tool_calls": [
                        {"function": {"name": name, "arguments": args}}]},
                    "prompt_eval_count": 500}
        return {"message": {"content": "done", "tool_calls": [
                    {"function": {"name": "finish",
                                  "arguments": {"summary": "all done"}}}]},
                "prompt_eval_count": 500}

    def fake_run_tool(name, args, w):
        for n, a, r in calls:
            if n == name and a == args:
                return r
        if name == "finish":
            return "[TASK_COMPLETE] all done"
        return "[tool error: not scripted]"

    A.call_chat, A.run_tool = fake_call_chat, fake_run_tool
    A.mcp_manifest, A.mcp_tool_defs = (lambda force=False: None), (lambda cats, extra=None: [])
    try:
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": task}]
        out = A.agent_loop(model, msgs, workdir, session)
        if capture is not None:
            capture["small_model_mode"] = A._SMALL_MODEL_MODE
            capture["messages"] = out
        return out
    finally:
        A.call_chat, A.run_tool, A.mcp_manifest, A.mcp_tool_defs = saved
        A._disabled_tools.discard("edit_file")
        A._SMALL_MODEL_MODE = False


# ---------------- a. TodoProvider 工厂注册 todo-0901 的存储适配器 ----------------

class TestProviderFactoryRegistration:
    def test_default_provider_binds_harness_storage(self, wd):
        """默认 Provider 读写都必须走 ollama_agent.load_todo/save_todo 这一条管线。"""
        A.save_todo(wd, [{"item": "a.csv 转成 md", "done": False},
                         {"item": "导出 report", "done": True}])
        p = PT.make_provider(wd)
        assert isinstance(p, PT.JsonTodoProvider)      # 兼容既有契约
        assert isinstance(p, PT.HarnessTodoProvider)   # 且是 harness 管线适配器
        items = p.all_items()
        assert [x.text for x in items] == ["a.csv 转成 md", "导出 report"]
        assert [x.done for x in items] == [False, True]
        assert [x.id for x in items] == ["1", "2"]     # 序号串 id(现格式契约)

    def test_mark_done_goes_through_harness_save(self, wd):
        """provider 落状态后,harness 侧(GUI 计划面板/门禁)必须立刻看见。"""
        A.save_todo(wd, [{"item": "step 1", "done": False},
                         {"item": "step 2", "done": False}])
        p = PT.make_provider(wd)
        assert p.mark_done("2", note="done by child") is True
        t = A.load_todo(wd)
        assert t[1]["done"] is True and t[1].get("note") == "done by child"
        assert t[0]["done"] is False                    # 不重排序/不误伤其余条目
        assert A.format_todo_lines(t).splitlines()[1].startswith("[x] 2.")

    def test_mark_done_is_idempotent(self, wd):
        A.save_todo(wd, [{"item": "only", "done": False}])
        p = PT.make_provider(wd)
        assert p.mark_done("1") is True
        assert p.mark_done("1") is True
        assert len(A.load_todo(wd)) == 1

    def test_set_complexity_persists_via_harness(self, wd):
        A.save_todo(wd, [{"item": "rename files", "done": False}])
        p = PT.make_provider(wd)
        assert p.set_complexity("1", "simple") is True
        assert A.load_todo(wd)[0]["complexity"] == "simple"

    def test_registry_still_serves_legacy_reader(self, wd):
        A.save_todo(wd, [{"item": "x.md 统计行数", "done": False}])
        legacy = PT.make_provider(wd, kind="legacy-json")
        assert type(legacy) is PT.JsonTodoProvider
        assert [x.text for x in legacy.all_items()] == ["x.md 统计行数"]

    def test_register_provider_extends_factory(self, wd):
        class _Custom(PT.JsonTodoProvider):
            pass
        PT.register_provider("custom-test", _Custom)
        try:
            assert isinstance(PT.make_provider(wd, kind="custom-test"), _Custom)
        finally:
            PT._PROVIDER_REGISTRY.pop("custom-test", None)
        assert isinstance(PT.make_provider(wd), PT.HarnessTodoProvider)  # 默认不受影响

    def test_provider_tolerates_missing_and_malformed(self, wd):
        p = PT.make_provider(wd)
        assert p.all_items() == [] and p.pending_items() == []
        assert p.mark_done("1") is False
        with open(os.path.join(wd, "todo.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        assert p.all_items() == []


# ---------------- b. 子 agent 不承受主 agent 的 todo finish 门禁 ----------------

def _rejections(msgs):
    """finish 被门禁拒绝时注入的 user 消息(计划未同步)。"""
    return [m for m in msgs if m.get("role") == "user"
            and "finish 被拒绝" in str(m.get("content", ""))
            and "未标记完成" in str(m.get("content", ""))]


class TestChildFinishGateExemption:
    CALLS = [("create_file", {"path": "out.md", "content": "x"}, "[created out.md]")]

    def test_main_agent_finish_blocked_by_unsynced_plan(self, wd):
        """主 agent:计划未同步 → finish 被拒并给 todo(update, all=true) 出路。"""
        A.save_todo(wd, [{"item": "step 1", "done": True},
                         {"item": "step 2", "done": False}])
        msgs = _scripted_loop(wd, self.CALLS, session=None)
        gates = _rejections(msgs)
        assert gates, "主 agent 的 finish 门禁必须仍然生效"
        assert "all=true" in gates[0]["content"]

    def test_child_agent_finish_not_blocked(self, wd, child_mode):
        """子 agent:同样的未同步计划,finish 直接放行(它的退出契约在派发层核对)。"""
        A.save_todo(wd, [{"item": "step 1", "done": True},
                         {"item": "step 2", "done": False}])
        msgs = _scripted_loop(wd, self.CALLS, session=None)
        assert _rejections(msgs) == []

    def test_child_finish_not_blocked_even_with_fresh_plan(self, wd, child_mode):
        """子 agent 自己建了计划(提示模板建议 todo)也不被门禁卡住。"""
        A.save_todo(wd, [{"item": "把 a 转成 b", "done": False}])
        msgs = _scripted_loop(wd, self.CALLS, session=None)
        assert _rejections(msgs) == []

    def test_main_agent_gate_still_allows_after_two_rejections(self, wd):
        """上限 2 次:防死锁的便宜退出路径必须保留(all=true 提示在回执里)。"""
        A.save_todo(wd, [{"item": "never done", "done": False}])
        msgs = _scripted_loop(wd, [], session=None)   # 脚本空 → 每次都 finish
        assert len(_rejections(msgs)) == 2


# ---------------- c. 子 agent 永不判为问答;_SMALL_MODEL_MODE 按子模型置位 ----------------

class TestChildModeClassification:
    QA_LIKE_TASK = "这是什么?"       # 无任务动词、含问句提示 → 主 agent 会判为问答

    def test_child_qa_like_text_stays_task_mode(self, wd, child_mode):
        """子 agent 的任务文本像问句也不许换聊天提示/卸工具。"""
        msgs = _scripted_loop(wd, [], task=self.QA_LIKE_TASK, system="CHILD-SYS",
                              model="gemma4:e2b", session=None)
        assert msgs[0] == {"role": "system", "content": "CHILD-SYS"}
        assert not any(m.get("role") == "system" and m.get("content") == A.CHAT_SYSTEM
                       for m in msgs)

    def test_small_model_mode_from_child_model_params(self, wd, child_mode):
        cap = {}
        _scripted_loop(wd, [], task=self.QA_LIKE_TASK, model="gemma4:e2b",
                       session=None, capture=cap)
        assert cap["small_model_mode"] is True      # 子模型 2B → 瘦身生效
        _scripted_loop(wd, [], task=self.QA_LIKE_TASK, model="ornith-1.5:35b",
                       session=None, capture=cap)
        assert cap["small_model_mode"] is False     # 子模型 35B → 不瘦身

    def test_small_model_mode_off_for_main_agent_big_model(self, wd):
        cap = {}
        _scripted_loop(wd, [], task=self.QA_LIKE_TASK, model="ornith-1.5:35b",
                       session=None, capture=cap)
        assert cap["small_model_mode"] is False

    def test_main_agent_qa_like_short_text_is_qa(self, wd):
        """对照组:同一句 QA 文本在主 agent 仍按问答处理(todo 分支的行为不被削弱)。"""
        assert A._is_qa([{"role": "user", "content": self.QA_LIKE_TASK}]) is True


# ---------------- d. 派发回执:不污染路由/判定,恢复不双发 ----------------

class TestDispatchNoteIsolation:
    NOTE = A._DISPATCH_NOTE_MARK + " 以下条目已由并行子任务完成,产物文件已写入当前工作目录:"

    def test_routing_text_skips_dispatch_note(self):
        msgs = [{"role": "user", "content": "把 data.csv 转成 markdown 表格"},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": self.NOTE}]
        assert A._task_routing_text(msgs) == "把 data.csv 转成 markdown 表格"

    def test_qa_skips_dispatch_note(self):
        """回执不是真实用户输入:问答判定应回看上一条真实消息。"""
        msgs = [{"role": "user", "content": "这个报错是什么意思?"},
                {"role": "user", "content": self.NOTE}]
        assert A._is_qa(msgs) is True

    def test_routing_text_falls_back_to_empty(self):
        assert A._task_routing_text([{"role": "user", "content": self.NOTE}]) == ""

    def test_dispatch_not_rerun_when_note_already_present(self, wd, monkeypatch):
        """恢复幂等:对话里已有回执但还没有 tool 消息(极端恢复点)→ 不再派第二次。"""
        monkeypatch.setattr(PC, "get_parallel_config",
                            lambda environ=None: dict(PC.DEFAULT_PARALLEL, enabled=True))
        monkeypatch.setattr(A, "_child_sandbox", None)
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "任务"},
                {"role": "user", "content": self.NOTE}]
        out = A._maybe_parallel_dispatch("m", [dict(m) for m in msgs], wd, None)
        assert out == msgs                           # 原样返回,没有第二次派发

    def test_dispatch_off_by_default_returns_messages_identical(self, wd):
        """出厂默认(enabled=False)下 hook 必须原样返回同一对象,零副作用。"""
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "把 data.csv 转成 markdown 表格"}]
        before = json.dumps(msgs, ensure_ascii=False)
        out = A._maybe_parallel_dispatch("m", msgs, wd, None)
        assert out is msgs
        assert json.dumps(out, ensure_ascii=False) == before

    def test_note_marker_prefix_added_by_harness(self, wd, monkeypatch):
        """派发真正发生时,注入的回执必须带标记前缀(供路由/幂等识别)。"""
        import parallel_dispatch as PD
        monkeypatch.setattr(PC, "get_parallel_config",
                            lambda environ=None: dict(PC.DEFAULT_PARALLEL, enabled=True,
                                                      child_model="c"))
        monkeypatch.setattr(A, "_child_sandbox", None)

        class _Plan:
            should = True
            reasons = []
            items = [PT.TodoItem(id="1", text="a.csv 转成 md")]
            capacity = {"max_parallel": 1}

            @property
            def n_items(self):
                return len(self.items)

        class _FakeDispatcher:
            def __init__(self, cfg=None, progress_cb=None):
                pass

            def run(self, items, w, probe, child_model=None, todo_provider=None, **kw):
                res = PD.DispatchResult()
                res.ok = 1
                return res

        class _FakeIntegrator:
            def __init__(self, cfg=None, provider=None):
                pass

            def integrate(self, result, w):
                return ["a.md"], [], []

        monkeypatch.setattr(PD, "ParallelDispatcher", _FakeDispatcher)
        monkeypatch.setattr(PD, "ResultIntegrator", _FakeIntegrator)
        monkeypatch.setattr(PT, "should_dispatch", lambda probe, provider, cfg: _Plan())
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "任务"}]
        out = A._maybe_parallel_dispatch("m", msgs, wd, None)
        assert len(out) == 3
        assert out[-1]["content"].startswith(A._DISPATCH_NOTE_MARK)
        assert "不必重做" in out[-1]["content"]        # par 的回执正文保持不变


# ---------------- e. 出厂默认全关 ----------------

class TestFactoryDefaultsOff:
    def test_parallel_disabled_and_hard_gate(self, monkeypatch):
        monkeypatch.delenv("AGENT_PARALLEL", raising=False)
        cfg = PC.get_parallel_config(config={})
        assert cfg["enabled"] is False               # 总开关默认关
        assert cfg["child_model"] == ""              # 子模型为空 = 功能关
        assert PC.hard_disabled() is False
        assert PC.hard_disabled(environ={"AGENT_PARALLEL": "0"}) is True

    def test_time_budget_default_zero(self, monkeypatch):
        monkeypatch.delenv("AGENT_TIME_BUDGET_SEC", raising=False)
        assert A.BUDGET_SEC == 0
        assert A._budget_nudge(0, 10 ** 9, set()) is None

    def test_small_model_mode_default_false(self):
        assert A._SMALL_MODEL_MODE is False

    def test_dispatch_env_hard_gate_blocks_even_when_enabled(self, wd, monkeypatch):
        monkeypatch.setenv("AGENT_PARALLEL", "0")
        monkeypatch.setattr(PC, "get_parallel_config",
                            lambda environ=None: dict(PC.DEFAULT_PARALLEL, enabled=True,
                                                      child_model="c"))
        monkeypatch.setattr(A, "_child_sandbox", None)
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "任务"}]
        assert A._maybe_parallel_dispatch("m", msgs, wd, None) is msgs

    def test_child_sandbox_blocks_dispatch_defensively(self, wd, child_mode, monkeypatch):
        """深度锁:子 agent 进程内即使配置错写成 enabled,也绝不派发。"""
        monkeypatch.setattr(PC, "get_parallel_config",
                            lambda environ=None: dict(PC.DEFAULT_PARALLEL, enabled=True,
                                                      child_model="c"))
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "任务"}]
        assert A._maybe_parallel_dispatch("m", msgs, wd, None) is msgs
