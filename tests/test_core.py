"""Unit tests for Hummingbird core modules. No network / no Ollama required."""
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A


# ---------------- path safety (guard system) ----------------
class TestSafePath:
    def test_relative_inside(self, tmp_path):
        real, inside = A._safe_path(str(tmp_path), "sub/file.txt")
        assert inside and real.startswith(str(tmp_path))

    def test_absolute_escape(self, tmp_path):
        _, inside = A._safe_path(str(tmp_path), "C:\\Windows\\system32\\evil.dll")
        assert not inside

    def test_dotdot_escape(self, tmp_path):
        _, inside = A._safe_path(str(tmp_path), "..\\..\\secret.txt")
        assert not inside

    def test_nested_inside(self, tmp_path):
        _, inside = A._safe_path(str(tmp_path), "a/b/c.txt")
        assert inside


class TestSensitivePath:
    def test_ssh_blocked(self, tmp_path):
        real = os.path.join(str(tmp_path), ".ssh", "id_rsa")
        assert A._is_sensitive_path(real)

    def test_env_blocked(self, tmp_path):
        assert A._is_sensitive_path(os.path.join(str(tmp_path), ".env"))

    def test_normal_file_ok(self, tmp_path):
        assert not A._is_sensitive_path(os.path.join(str(tmp_path), "report.md"))


class TestGateCheck:
    def test_dangerous_command_blocked(self, tmp_path):
        msg = A._gate_check("run_bash", {"command": "rm -rf C:/x"}, str(tmp_path))
        assert msg and "危险操作" in msg

    def test_outside_file_tool_blocked_cli(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGENT_STREAM", raising=False)
        msg = A._gate_check("read_file", {"path": "C:\\Windows\\notepad.exe"}, str(tmp_path))
        assert msg and "安全门" in msg or "工作目录" in msg

    def test_inside_file_tool_allowed(self, tmp_path):
        assert A._gate_check("create_file", {"path": "ok.txt"}, str(tmp_path)) is None


# ---------------- batch tools ----------------
class TestBatchTools:
    def test_serial_file_ops_no_race(self, tmp_path):
        calls = [
            {"tool": "create_file", "args": {"path": "a.txt", "content": "AAA"}},
            {"tool": "read_file", "args": {"path": "a.txt"}},
        ]
        out = A.batch_tools(calls, tmp_path)
        assert "AAA" in out

    def test_nested_blocked(self, tmp_path):
        out = A.batch_tools([{"tool": "batch_tools", "args": {}}], tmp_path)
        assert "禁止嵌套" in out

    def test_dangerous_still_blocked(self, tmp_path):
        out = A.batch_tools([{"tool": "run_bash", "args": {"command": "rm -rf /x"}}], tmp_path)
        assert "危险操作" in out

    def test_parallel_search(self, tmp_path):
        calls = [{"tool": "web_search_multi", "args": {"queries": ["x"], "max_results": 1}}]
        out = A.batch_tools(calls, tmp_path)
        assert "### [1]" in out


# ---------------- context compaction ----------------
class TestCompactHistory:
    def _msgs(self):
        return [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "plan"},
            {"role": "tool", "content": "x" * 500},
            {"role": "assistant", "content": "done"},
        ]

    def test_l1_truncates_old_tool_output(self):
        out = A.compact_history("m", self._msgs(), level=1)
        tool = [m for m in out if m.get("role") == "tool"][0]
        assert "已截断" in tool["content"]

    def test_l3_produces_summary(self, monkeypatch):
        # L3 calls the model to summarize: mock call_chat (no ollama in CI)
        monkeypatch.setattr(A, "call_chat", lambda *a, **k: {"message": {"content": "summary"}})
        msgs = self._msgs() * 4
        out = A.compact_history("m", msgs, level=3)
        assert len(out) < len(msgs)
        assert "先前上下文摘要" in out[1]["content"]

    def test_short_history_untouched(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert A.compact_history("m", msgs, level=3) == msgs


# ---------------- category routing ----------------
class TestRouting:
    def test_code_keywords(self):
        cats = A.route_categories("帮我写一个 python 脚本")
        assert "代码" in cats

    def test_default_is_broad(self):
        assert A.route_categories("随便说点什么") == {"文件", "代码", "网络"}

    def test_tools_for_categories_small(self):
        tools = A.tools_for_categories({"网络"})
        names = [t["function"]["name"] for t in tools]
        assert "read_file" in names          # base tools always present
        assert "web_search" in names         # network tools loaded
        assert "run_bash" not in names       # code tools not loaded


# ---------------- token estimation ----------------
class TestEstimation:
    def test_cjk_dense(self):
        assert A._estimate_tokens("钛合金时效处理") >= 7

    def test_english_sparse(self):
        assert A._estimate_tokens("titanium alloy aging") >= 5

    def test_messages_aggregate(self):
        msgs = [{"role": "user", "content": "word " * 100}]
        assert A._estimate_messages_tokens(msgs) > 20


# ---------------- disk cache ----------------
class TestCache:
    def test_roundtrip(self):
        key = A._cache_key("t", "k")
        A._cache_set(key, {"v": 42})
        assert A._cache_get(key) == {"v": 42}

    def test_missing_returns_none(self):
        assert A._cache_get(A._cache_key("nope", "x")) is None


# ---------------- mcp expose parsing ----------------
class TestMcpManifest:
    def test_expose_parser(self):
        per_tool = {"a": ["网络"], "b": {"categories": ["文件"], "expose": "on-demand"}}
        assert A._mcp_expose(per_tool, "a", None) == "auto"
        assert A._mcp_expose(per_tool, "b", None) == "on-demand"
        assert A._mcp_expose({}, "c", "disabled") == "disabled"

    def test_on_demand_excluded_from_default(self, monkeypatch):
        monkeypatch.setattr(A, "_MCP_CACHE", {"t": 0, "data": None})
        defs = A.mcp_tool_defs(["网络"])
        names = [d["function"]["name"] for d in defs]
        assert "playwright.browser_navigate" not in names   # on-demand server


# ---------------- task utilities ----------------
class TestDedupeAssistant:
    def test_merges_trailing_assistants(self):
        msgs = [{"role": "user", "content": "u"},
                {"role": "assistant", "content": "a"},
                {"role": "assistant", "content": "b"}]
        out = A._dedupe_trailing_assistant(msgs)
        assert out[-1]["content"] == "a\nb"
