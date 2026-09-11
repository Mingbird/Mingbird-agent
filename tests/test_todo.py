# -*- coding: utf-8 -*-
"""todo 管线单元测试:计划工具本身、问答/任务误判修复、计划同步门禁的纯逻辑部分。

背景(2026-09-01 侦查结论):
- 进行中任务的短后续指令(如"你还有别的工具可以读docx 你找找")曾被 _is_qa 的
  "≤40 字无关键词 → 问答"兜底规则误判成寒暄,导致换聊天提示、卸掉 todo 工具、
  拦截写文件/跑命令 —— 用户在 GUI 里因此从没见过计划面板被填充。
- 小模型(e2b)8/8 格建了计划却 0 勾选收尾:列表只靠模型显式 update 才会动。
不依赖网络 / 不调用 ollama。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A


@pytest.fixture
def wd(tmp_path):
    return str(tmp_path)


def _u(text):
    return {"role": "user", "content": text}


def _a_tool(name):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": {}}}]}


# ---------------- _has_task_progress ----------------

class TestHasTaskProgress:
    def test_mutating_tool_counts(self):
        msgs = [_u("帮我看看这个目录"), _a_tool("list_dir"), _a_tool("run_bash")]
        assert A._has_task_progress(msgs) is True

    def test_create_file_counts(self):
        assert A._has_task_progress([_u("x"), _a_tool("create_file")]) is True

    def test_readonly_tools_do_not_count(self):
        msgs = [_u("x"), _a_tool("read_file"), _a_tool("list_dir"), _a_tool("web_search")]
        assert A._has_task_progress(msgs) is False

    def test_mcp_tool_counts(self, monkeypatch):
        monkeypatch.setattr(A, "is_mcp_tool", lambda n: True)
        assert A._has_task_progress([_u("x"), _a_tool("acme.render_docx")]) is True

    def test_empty_conversation(self):
        assert A._has_task_progress([_u("你好")]) is False


# ---------------- _is_qa:误判修复 + 回归 ----------------

class TestIsQa:
    # 匿名化的真实事故样本:长任务句(含任务词"检查")+ 进行中追加的短指令(无关键词)
    REAL_TASK = ("这个目录里保存了一批待处理的数据文件，"
                 "请你帮我好好检查这几个文件有没有低级错误，并逐一核对细节。")
    FOLLOWUP = "你还有别的工具可以读这些文件 你找找"

    def test_followup_after_real_work_is_task(self):
        """核心修复:进行中任务的短后续指令不再被当成寒暄。"""
        msgs = [_u(self.REAL_TASK), _a_tool("run_bash"), _u(self.FOLLOWUP)]
        assert A._is_qa(msgs, has_progress=A._has_task_progress(msgs)) is False

    def test_short_message_without_progress_is_qa(self):
        """无工作历史的短消息仍按问答(保留原兜底,防加戏回归)。"""
        assert A._is_qa([_u(self.FOLLOWUP)], has_progress=False) is True

    def test_explicit_qa_hint_still_wins(self):
        msgs = [_u(self.REAL_TASK), _a_tool("run_bash"), _u("谢谢")]
        assert A._is_qa(msgs, has_progress=True) is True

    def test_explicit_task_hint_still_task(self):
        assert A._is_qa([_u("帮我检查代码里的 bug")]) is False

    def test_english_short_followup_with_progress(self):
        msgs = [_u("please fix the failing tests in app.py"),
                _a_tool("create_file"), _u("now run them")]
        assert A._is_qa(msgs, has_progress=True) is False


# ---------------- todo 工具行为 ----------------

class TestTodoTool:
    def test_create(self, wd):
        out = A.run_tool("todo", {"action": "create", "items": ["step 1", "step 2"]}, wd)
        assert "[ ] 1. step 1" in out and "[ ] 2. step 2" in out
        assert os.path.exists(A.todo_file(wd))

    def test_update_marks_done(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["a", "b"]}, wd)
        out = A.run_tool("todo", {"action": "update", "index": 1}, wd)
        assert "[x] 1. a" in out and "[ ] 2. b" in out

    def test_update_index_list(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["a", "b", "c"]}, wd)
        out = A.run_tool("todo", {"action": "update", "index": [1, 3]}, wd)
        assert "[x] 1. a" in out and "[ ] 2. b" in out and "[x] 3. c" in out

    def test_update_all(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["a", "b"]}, wd)
        A.run_tool("todo", {"action": "update", "index": 1}, wd)
        out = A.run_tool("todo", {"action": "update", "all": True}, wd)
        assert "[ ]" not in out and out.count("[x]") == 2

    def test_update_all_false_leaves_others(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["a", "b"]}, wd)
        out = A.run_tool("todo", {"action": "update", "index": 2, "done": False}, wd)
        assert "[ ] 2. b" in out

    def test_update_invalid_index_gives_actionable_error(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["a", "b"]}, wd)
        out = A.run_tool("todo", {"action": "update", "index": 9}, wd)
        assert "index" in out and "all=true" in out

    def test_update_on_empty_plan_is_actionable(self, wd):
        out = A.run_tool("todo", {"action": "update", "index": 1}, wd)
        assert "todo(action=create" in out

    def test_list(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["only"]}, wd)
        assert "[ ] 1. only" in A.run_tool("todo", {"action": "list"}, wd)

    def test_create_persists_progress(self, wd):
        A.run_tool("todo", {"action": "create", "items": ["a", "b"]}, wd)
        A.run_tool("todo", {"action": "update", "index": 1}, wd)
        done, total = A.todo_progress(A.load_todo(wd))
        assert (done, total) == (1, 2)

    def test_schema_stays_within_prefill_budget(self):
        """prefill 硬约束:todo 工具描述 ≤20 token、schema 字段不增(出厂 prefill 净增 0)。
        all=true / index 数组属于运行时宽容,由 harness 动态消息教,不进 schema。"""
        todo = next(t for t in A.CORE_TOOLS if t["function"]["name"] == "todo")["function"]
        assert A._estimate_tokens(todo["description"]) <= 20
        assert set(todo["parameters"]["properties"]) == {"action", "items", "index", "done"}
        assert todo["parameters"]["properties"]["index"] == {"type": "number"}


# ---------------- 计划压缩保真 ----------------

class TestCompactKeepsPlan:
    def _msgs(self, n=8):
        return [{"role": "system", "content": "SYS"}] + [
            {"role": "assistant", "content": f"turn {k}"} for k in range(n)]

    def test_l3_reinjects_plan(self, monkeypatch):
        monkeypatch.setattr(A, "call_chat",
                            lambda *a, **kw: {"message": {"content": "摘要"}})
        out = A.compact_history("m", self._msgs(), level=3,
                                todo_text="[ ] 1. a\n[x] 2. b")
        joined = "\n".join(str(m.get("content", "")) for m in out)
        assert "[当前计划(todo)" in joined and "[x] 2. b" in joined

    def test_l2_reinjects_plan(self, monkeypatch):
        monkeypatch.setattr(A, "call_chat",
                            lambda *a, **kw: {"message": {"content": "摘要"}})
        out = A.compact_history("m", self._msgs(), level=2,
                                todo_text="[ ] 1. a")
        joined = "\n".join(str(m.get("content", "")) for m in out)
        assert "[ ] 1. a" in joined

    def test_no_plan_no_marker(self, monkeypatch):
        monkeypatch.setattr(A, "call_chat",
                            lambda *a, **kw: {"message": {"content": "摘要"}})
        out = A.compact_history("m", self._msgs(), level=3, todo_text=None)
        joined = "\n".join(str(m.get("content", "")) for m in out)
        assert "[当前计划(todo)" not in joined


# ---------------- 面板文本与进度(GUI 与 harness 同源) ----------------

class TestFormatAndProgress:
    def test_format_lines(self):
        t = [{"item": "a", "done": True}, {"item": "b", "done": False}]
        assert A.format_todo_lines(t) == "[x] 1. a\n[ ] 2. b"

    def test_progress_counts(self):
        t = [{"item": "a", "done": True}, {"item": "b", "done": True},
             {"item": "c", "done": False}]
        assert A.todo_progress(t) == (2, 3)

    def test_progress_empty(self):
        assert A.todo_progress([]) == (0, 0)
        assert A.todo_progress(None) == (0, 0)

    def test_format_missing_keys_tolerated(self):
        assert A.format_todo_lines([{}]) == "[ ] 1. "
