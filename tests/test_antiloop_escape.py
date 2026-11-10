# -*- coding: utf-8 -*-
"""反循环死锁回归测试。

背景:禁用话术推荐 enable_tools 解锁后,小模型会"解锁 → 原样重发同一条被
安全门拒绝的命令 → 再被禁用 → 再解锁"无限循环烧尽 200 轮;且解锁只清了禁用
集合、没把工具装回工具面(CORE 工具不在 ADVANCED_TOOLS 里),回执"(none)"
让模型读不出已恢复——承诺的恢复是假的。本文件钉住三件事:
①拒绝话术不再推荐解锁,出路是 create_file(文档类)/换代码重跑(计算类);
②解锁真恢复工具面、回执明说,同一工具解锁上限 2 次;
③整条链路用 stub 模型回放:被拒命令循环 → 禁用 → 按话术改写产物 → finish。
"""
import importlib.util
import json
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


@pytest.fixture()
def clean_state(oa, monkeypatch, tmp_path):
    """隔离模块全局状态:工具面/禁用集合/解锁计数/无人值守/会话目录。"""
    monkeypatch.setattr(oa, "_active_tools", list(oa.CORE_TOOLS))
    monkeypatch.setattr(oa, "_disabled_tools", set())
    oa._unlock_used.clear()
    monkeypatch.setattr(oa, "_UNATTENDED", True)
    monkeypatch.setattr(oa, "SESSIONS_DIR", str(tmp_path / "sessions"))
    os.makedirs(str(tmp_path / "sessions"), exist_ok=True)
    return tmp_path


# ---- ②解锁:真恢复 + 明说 + 封顶 ----

def test_unlock_revives_and_says_so(oa, clean_state):
    """解锁必须把工具装回工具面,且回执明说已恢复(旧实现回执 '(none)',
    模型读不出已恢复,只能原样重发被拒命令)。"""
    oa._disabled_tools.add("run_bash")
    r = oa.enable_advanced_tools(["run_bash"])
    assert "run_bash" not in oa._disabled_tools
    assert "run_bash" in [t["function"]["name"] for t in oa._active_tools]
    assert "已解除禁用" in r and "恢复可用" in r


def test_unlock_capped_after_two(oa, clean_state):
    """同一工具解锁 2 次后,第 3 次必须拒绝且不解除禁用——解锁是给
    '换做法'用的,不是给'重发同一条命令'用的。"""
    for _ in range(2):
        oa._disabled_tools.add("run_bash")
        oa.enable_advanced_tools(["run_bash"])
    # 第三次禁用按真实语义同时移出工具面(反循环禁用就是这么做的)
    oa._disabled_tools.add("run_bash")
    oa._active_tools = [t for t in oa._active_tools
                        if t["function"]["name"] != "run_bash"]
    r = oa.enable_advanced_tools(["run_bash"])
    assert "已拒绝再次解锁" in r
    assert "create_file" in r
    assert "run_bash" in oa._disabled_tools          # 保持禁用
    assert "run_bash" not in [t["function"]["name"] for t in oa._active_tools]


def test_unlock_unknown_tool_still_reported(oa, clean_state):
    """不存在的工具名不得混进'已恢复'——回执必须真实(死循环重试的诱因)。"""
    r = oa.enable_advanced_tools(["totally_fake_tool"])
    assert "不存在" in r
    assert "totally_fake_tool 已解除禁用" not in r


# ---- ③整链回放:被拒命令 → 禁用 → 按话术改写 → finish ----

def test_replay_disabled_loop_escapes_to_create_file(oa, clean_state, monkeypatch):
    """stub 模型反复发出同一条越界 mkdir:必须走到禁用话术(含 create_file
    出路、不含 enable_tools 推荐、含进度快照),随后 stub 照话术改写文档产物,
    finish 被接受。这就是 0.8B 烧尽 200 轮的那条链路。"""
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    state = {"n": 0, "refusal": None, "created": False, "finish_seen": 0}

    def fake_call_chat(model, messages, ctx=None, tools=None, stream=False,
                       on_token=None, on_think=None):
        state["n"] += 1
        assert state["n"] < 120, "回放未在预算内走出死循环"
        last_tool = ""
        for m in reversed(messages):
            if m.get("role") == "tool":
                last_tool = str(m.get("content", ""))
                break
        if state["refusal"] is None and "已被禁用" in last_tool:
            state["refusal"] = last_tool

        def resp(name, args):
            tc = {"function": {"name": name, "arguments": args}}
            return {"message": {"content": "", "tool_calls": [tc]}}

        if state["refusal"] is None:
            # 阶段A:同一条越界命令原样重发(POSIX 风格 + 工作区外绝对路径)
            return resp("run_bash", {"command": 'mkdir -p "/Users/nobody/outside"'})
        if not state["created"]:
            # 阶段B:照话术的出路 1) 改写文档类产物
            state["created"] = True
            return resp("create_file", {"path": "report.md",
                                        "content": "# Report\nDone from replay."})
        # 阶段C:finish(交付自查门禁会回注一次任务原文,finish 两次)
        state["finish_seen"] += 1
        return resp("finish", {"summary": "Wrote report.md in the workspace."})

    monkeypatch.setattr(oa, "call_chat", fake_call_chat)
    messages = [
        {"role": "system", "content": "You are a test agent."},
        {"role": "user", "content": "Write report.md in the workspace. "
         "Do not access paths outside the workspace."},
    ]
    oa.agent_loop("stub-model", messages, workdir, "replay-antiloop")

    assert state["refusal"], "从未进入禁用拒绝路径"
    assert "enable_tools" not in state["refusal"], "禁用话术不得推荐解锁"
    assert "create_file" in state["refusal"]
    assert "换一段不同的代码重跑" in state["refusal"]
    assert "当前进度快照" in state["refusal"]
    assert (clean_state / "work" / "report.md").exists(), "模型未按出路改写产物"
    assert state["n"] < 60, f"回放烧了 {state['n']} 轮,死循环没有被打破"


def test_replay_unattended_denial_offers_write_route(oa, clean_state, monkeypatch):
    """安全门拒绝本身必须含写方向出路(create_file)——只有读方向建议时,
    写不出的模型会一直重发同一条命令。"""
    allow, _, msg = oa._ask_user_confirm(
        "run_bash", str(clean_state / "outside"), str(clean_state / "work"))
    assert allow is False
    assert "create_file" in msg
    assert "绝对路径" in msg
