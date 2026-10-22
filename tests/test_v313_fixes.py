# -*- coding: utf-8 -*-
"""v3.1.3 两连修的回归钉:
1. L2/L3 压缩摘要调用不得另设 num_ctx——ollama 按 (模型,options) 起 runner,
   ctx=8000 会让每次压缩多载一份模型(v1.4.0 遗产);摘要必须骑主循环同 ctx 的
   resident runner;
2. 压缩失败必须留痕(调用方无论成败都消耗压缩阶梯,静默失败="超上下文但不触发
   压缩"的无声复发)。"""
import importlib.util
import os
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "ollama_agent", os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"))
sys.argv = ["test"]

_mod = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
except SystemExit:
    pass
A = _mod


@pytest.fixture
def tl_state(monkeypatch):
    monkeypatch.setattr(A, "_TL_COMPACTED", False)


def _msgs(n=8):
    return ([{"role": "system", "content": "S"}] +
            [{"role": "user", "content": f"u{i}"} for i in range(n)])


def test_compact_summary_rides_main_ctx(monkeypatch, tl_state):
    """L2/L3 摘要调用的 ctx 形参必须是 None(落 call_chat 默认=CTX_BUDGET),
    不得钉任何独立 num_ctx——否则 ollama 另起一个 runner。"""
    seen = []
    def fake_chat(model, req, ctx=None, tools=None, **k):
        seen.append(ctx)
        return {"message": {"content": "摘要"}}
    monkeypatch.setattr(A, "call_chat", fake_chat)
    A.compact_history("m", _msgs(10), level=2)
    A.compact_history("m", _msgs(10), level=3)
    assert seen == [None, None]          # 两级都不带独立 ctx


def test_no_divergent_num_ctx_left_in_src():
    """源码钉:压缩路径不再出现 ctx=8000 之类的固定小 ctx。"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
               encoding="utf-8").read()
    assert "ctx=8000" not in src
    # 摘要调用形如 call_chat(model, req, tools=[]) —— 不带 ctx 形参
    assert 'call_chat(model, req, tools=[])' in src


def test_compact_failure_is_logged_not_silent(monkeypatch, tl_state, capsys):
    """摘要调用抛错:返回原消息(行为不变)但必须打一行失败原因。"""
    def boom(*a, **k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(A, "call_chat", boom)
    msgs = _msgs(10)
    out = A.compact_history("m", msgs, level=3)
    assert out is msgs                       # 原样返回,不丢消息
    err = capsys.readouterr().out
    assert "L3 失败" in err and "RuntimeError" in err and "connection refused" in err
    out2 = A.compact_history("m", msgs, level=2)
    assert out2 is msgs
    assert "L2 失败" in capsys.readouterr().out
