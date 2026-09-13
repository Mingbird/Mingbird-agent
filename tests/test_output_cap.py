# -*- coding: utf-8 -*-
"""输出上限(8192)+ 截断死亡反馈 + 空轮防护梯修复 的单元测试。

锚定 2026-09-13 WF-08/4b 三次超时验尸结论:
1. 2048 帽子下单轮工具调用装不下 300 行文件 → 截断螺旋;默认提至 8192;
2. 截断空轮(done_reason=length 且语义空)必须给"分块交付"针对性反馈,
   通用"别输出空文本"无效;
3. 未闭合 <think>(长度截断吞掉闭合标签)必须判空轮,否则空轮计数器被
   残骸轮清零,>=3 纠正/6 硬复位全部不可达(70 连空轮零复位实证)。
"""
import importlib.util
import os
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "ollama_agent", os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"))
sys.argv = ["test"]


@pytest.fixture(scope="module")
def oa():
    mod = importlib.util.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


# ---- 1. 默认输出上限 ----

def test_num_predict_default_8192(oa):
    assert oa.NUM_PREDICT == 8192


def test_num_predict_env_override(oa, monkeypatch):
    spec2 = importlib.util.spec_from_file_location(
        "ollama_agent_ovr", os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"))
    monkeypatch.setenv("AGENT_NUMPREDICT", "4096")
    mod2 = importlib.util.module_from_spec(spec2)
    try:
        spec2.loader.exec_module(mod2)
    except SystemExit:
        pass
    assert mod2.NUM_PREDICT == 4096


# ---- 2. 未闭合 think = 截断残骸 = 空轮 ----

def test_semantically_empty_unclosed_think(oa):
    assert oa._semantically_empty("<think>\nI need to continue implementing app.py")  # m0 实锤残骸
    assert oa._semantically_empty("  <think>partial thought, cut off by length")
    # 有正文在前的不算空(正文是实质内容)
    assert not oa._semantically_empty("先写计划 <think>再想想细节")
    # 闭合形态口径不变(回归锚)
    assert oa._semantically_empty("<think>\n\n</think>")
    assert oa._semantically_empty("<think>只有思考没有答案</think>")
    assert oa._semantically_empty("")


# ---- 3. 截断反馈与硬复位可达性(脚本化 agent_loop) ----

def _run_scripted(oa, tmp_path, responder):
    saved = (oa.call_chat, oa.run_tool, oa.mcp_manifest, oa.mcp_tool_defs)
    saved_tools = (list(oa._active_tools), set(oa._disabled_tools))
    oa.call_chat = responder
    oa.run_tool = (lambda name, args, wd, crawl_state=None:
                   "[TASK_COMPLETE] ok" if name == "finish" else "[ok]")
    oa.mcp_manifest = lambda force=False: None
    oa.mcp_tool_defs = lambda cats, extra=None: []
    try:
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "写一个大文件并验证。"}]
        return oa.agent_loop("gemma4:12b", msgs, str(tmp_path), None)
    finally:
        oa.call_chat, oa.run_tool, oa.mcp_manifest, oa.mcp_tool_defs = saved
        oa._active_tools[:] = saved_tools[0]
        oa._disabled_tools.clear()
        oa._disabled_tools.update(saved_tools[1])


def _debris(n=[0]):
    n[0] += 1
    return {"message": {"content": "<think>\nI need to write the whole app.py now",
                        "tool_calls": None},
            "done_reason": "length", "eval_count": 8192}


def test_truncation_feedback_injected_once(oa, tmp_path):
    state = {"n": 0}
    def responder(m, messages, ctx=None, tools=None, stream=False, on_token=None, on_think=None):
        state["n"] += 1
        if state["n"] == 1:
            return _debris()                      # 截断空轮
        if state["n"] == 2:
            return {"message": {"content": "", "tool_calls": [
                {"function": {"name": "create_file",
                              "arguments": {"path": "app.py", "content": "print(1)"}}}]}}
        return {"message": {"content": "done", "tool_calls": [
            {"function": {"name": "finish", "arguments": {"summary": "all done"}}}]}}
    out = _run_scripted(oa, tmp_path, responder)
    advice = [m for m in out if m.get("role") == "user" and "append_file 逐段追加" in str(m.get("content", ""))]
    assert len(advice) == 1                        # 针对性分块反馈,恰好一次
    assert "8192" in advice[0]["content"]          # 带实际上限值


def test_hard_reset_reachable_after_six_empties(oa, tmp_path):
    state = {"n": 0}
    def responder(m, messages, ctx=None, tools=None, stream=False, on_token=None, on_think=None):
        state["n"] += 1
        if state["n"] <= 6:
            return _debris()                       # 6 连截断空轮(m0 同款签名)
        return {"message": {"content": "done", "tool_calls": [
            {"function": {"name": "finish", "arguments": {"summary": "all done"}}}]}}
    out = _run_scripted(oa, tmp_path, responder)
    joined = " ".join(str(m.get("content", "")) for m in out)
    assert "上下文已重置" in joined                 # 硬复位真实触发(旧代码此路不可达)
    # 复位后最小工作集包含原始任务
    assert any("写一个大文件并验证" in str(m.get("content", "")) for m in out)
