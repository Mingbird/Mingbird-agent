# -*- coding: utf-8 -*-
"""压缩窗口护栏(v3.1.6):
1. L2/L3 摘要载荷总量封顶——单条 400 字符×条数无上界,长会话的摘要请求自己
   就能超窗被服务端 400 拒绝(Paper B 611 格日志实锤 8~13K token 请求);
2. 封顶=截尾保近(最近的决策/产物名才有摘要价值)+前置省略标记;
3. 预算=min(CTX_BUDGET,32768)×0.75,估算沿用 CJK 2 token/字的保守估算器。"""
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


@pytest.fixture(autouse=True)
def tl_state(monkeypatch):
    monkeypatch.setattr(A, "_TL_COMPACTED", False)


def _long_msgs(rounds=60, per=1200):
    msgs = [{"role": "system", "content": "S"}]
    for i in range(rounds):
        msgs.append({"role": "assistant", "content": f"决定{i}_中" * (per // 8)})
        msgs.append({"role": "tool", "content": "工具输出" * (per // 8)})
    return msgs


def _budget():
    return max(int(min(A.CTX_BUDGET, 32768) * 0.75), 2048)


def test_cap_summary_text_trims_tail(monkeypatch, capsys):
    monkeypatch.setattr(A, "CTX_BUDGET", 131072)
    text = "".join(f"[assistant]: 决定{i}_" + "很长的中文内容" * 100 + "\n"
                   for i in range(80))
    out = A._cap_summary_text(text)
    assert out.startswith("[更早的消息已省略]\n")
    assert A._estimate_tokens(out) <= _budget() + 30
    assert "决定79" in out and "决定0" not in out        # 截尾保近
    assert "截尾保近" in capsys.readouterr().out          # 封顶动作可见


def test_cap_summary_text_respects_small_ctx_budget(monkeypatch):
    monkeypatch.setattr(A, "CTX_BUDGET", 8192)
    out = A._cap_summary_text("汉" * 100000)
    assert out.startswith("[更早的消息已省略]\n")
    assert A._estimate_tokens(out) <= max(int(8192 * 0.75), 2048) + 30


def test_cap_summary_text_small_payload_passthrough(monkeypatch):
    monkeypatch.setattr(A, "CTX_BUDGET", 131072)
    text = "[user]: 短消息"
    assert A._cap_summary_text(text) == text            # 不超预算原样通过


def test_l3_summary_request_payload_is_capped(monkeypatch):
    captured = {}
    def fake_chat(model, req, ctx=None, tools=None, **k):
        captured["req"] = req
        return {"message": {"content": "摘要"}}
    monkeypatch.setattr(A, "call_chat", fake_chat)
    msgs = _long_msgs()
    out = A.compact_history("m", msgs, level=3)
    payload = captured["req"][1]["content"]
    assert payload.startswith("[更早的消息已省略]\n")
    assert A._estimate_tokens(payload) <= _budget() + 30
    assert "决定58" in payload                            # 尾部在场
    assert "决定0_" not in payload                        # 头部已弃
    assert len(out) < len(msgs)


def test_l2_summary_request_payload_is_capped(monkeypatch):
    captured = {}
    def fake_chat(model, req, ctx=None, tools=None, **k):
        captured["req"] = req
        return {"message": {"content": "摘要"}}
    monkeypatch.setattr(A, "call_chat", fake_chat)
    msgs = _long_msgs()
    A.compact_history("m", msgs, level=2)
    payload = captured["req"][1]["content"]
    assert payload.startswith("[更早的消息已省略]\n")
    assert A._estimate_tokens(payload) <= _budget() + 30


def test_l1_and_guards_untouched():
    """护栏不改变既有守卫:≤4 条不动,L1 行为不变。"""
    msgs = [{"role": "user", "content": "hi"}]
    assert A.compact_history("m", msgs, level=3) == msgs
