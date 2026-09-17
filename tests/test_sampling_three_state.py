# -*- coding: utf-8 -*-
"""v1.7.0 采样三态语义测试:温度/思考 未设置=请求不带字段(ollama 默认),
显式设置(含 0/关)=显式下发。直接对 /api/chat 载荷构造断言,不发真实网络请求
(urlopen 被替换,载荷从捕获的请求体解析)。
"""
import importlib.util
import io
import json
import os
import sys
import urllib.error

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


class FakeResp:
    """非流式 /api/chat 假响应。"""
    def __init__(self, body): self._b = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self._b


class FakeStreamResp:
    """流式假响应:可迭代的 NDJSON 行(思考+正文)。"""
    def __init__(self, lines): self._lines = lines
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __iter__(self): return iter(self._lines)


def _capture_urlopen(captured, resp=None):
    """替换 urlopen:记录请求体,返回固定响应。"""
    def fake(req, timeout=10):
        captured.append(json.loads(req.data))
        return resp
    return fake


# ---- 环境变量解析:三态入口 ----

def test_parse_temp_env_three_states(oa):
    assert oa._parse_temp_env(None) is None          # 未设置 → None
    assert oa._parse_temp_env("") is None            # 空串 → None
    assert oa._parse_temp_env("  ") is None
    assert oa._parse_temp_env("0") == 0.0            # 显式 0 = 用户选择,不是未设置
    assert oa._parse_temp_env("0.7") == 0.7
    assert oa._parse_temp_env("abc") is None         # 非法按未设置处理(不崩)


def test_parse_think_env_three_states(oa):
    assert oa._parse_think_env(None) is None         # 未设置 → None
    assert oa._parse_think_env("") is None
    assert oa._parse_think_env("1") is True          # 显式开
    assert oa._parse_think_env("0") is False         # 显式关


# ---- 载荷构造:未设置 = 完全不带字段 ----

def test_unset_omits_temperature_and_think(oa, monkeypatch):
    """用户未设置 → options 无 temperature 字段、顶层无 think 字段(ollama 默认)。"""
    captured = []
    monkeypatch.setattr(oa.urllib.request, "urlopen",
                        _capture_urlopen(captured, FakeResp(
                            b'{"message":{"role":"assistant","content":"ok"}}')))
    monkeypatch.setattr(oa, "TEMP", None)
    monkeypatch.setattr(oa, "THINK", None)
    oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    p = captured[0]
    assert "temperature" not in p["options"]
    assert "think" not in p
    assert p["options"]["num_ctx"] == 1024           # 其余 options 不受影响


def test_explicit_temp_zero_is_sent(oa, monkeypatch):
    """显式 0 是用户选择:必须显式下发 temperature=0,不得当作未设置。"""
    captured = []
    monkeypatch.setattr(oa.urllib.request, "urlopen",
                        _capture_urlopen(captured, FakeResp(
                            b'{"message":{"role":"assistant","content":"ok"}}')))
    monkeypatch.setattr(oa, "TEMP", 0.0)
    monkeypatch.setattr(oa, "THINK", None)
    oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    p = captured[0]
    assert p["options"]["temperature"] == 0.0
    assert "think" not in p


def test_explicit_temp_value_is_sent(oa, monkeypatch):
    captured = []
    monkeypatch.setattr(oa.urllib.request, "urlopen",
                        _capture_urlopen(captured, FakeResp(
                            b'{"message":{"role":"assistant","content":"ok"}}')))
    monkeypatch.setattr(oa, "TEMP", 0.7)
    monkeypatch.setattr(oa, "THINK", None)
    oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    assert captured[0]["options"]["temperature"] == 0.7


# ---- 载荷构造:think 显式开/关(顶层字段) ----

def test_explicit_think_true_is_top_level(oa, monkeypatch):
    captured = []
    monkeypatch.setattr(oa.urllib.request, "urlopen",
                        _capture_urlopen(captured, FakeResp(
                            b'{"message":{"role":"assistant","content":"ok"}}')))
    monkeypatch.setattr(oa, "TEMP", None)
    monkeypatch.setattr(oa, "THINK", True)
    oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    p = captured[0]
    assert p["think"] is True
    assert "think" not in p["options"]               # 顶层字段,放 options 会被 ollama 丢弃


def test_explicit_think_false_is_top_level(oa, monkeypatch):
    captured = []
    monkeypatch.setattr(oa.urllib.request, "urlopen",
                        _capture_urlopen(captured, FakeResp(
                            b'{"message":{"role":"assistant","content":"ok"}}')))
    monkeypatch.setattr(oa, "TEMP", None)
    monkeypatch.setattr(oa, "THINK", False)
    oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    p = captured[0]
    assert p["think"] is False
    assert "think" not in p["options"]


def test_non_thinking_model_400_retry_drops_think(oa, monkeypatch):
    """非 thinking 模型拒收 think 字段(400)→ 去参重试一次;重试载荷无 think。"""
    captured = []
    calls = {"n": 0}

    def flaky(req, timeout=10):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError("http://x", 400, "bad", {}, io.BytesIO(b""))
        captured.append(json.loads(req.data))
        return FakeResp(b'{"message":{"role":"assistant","content":"ok"}}')

    monkeypatch.setattr(oa.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(oa, "TEMP", None)
    monkeypatch.setattr(oa, "THINK", False)
    r = oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    assert calls["n"] == 2
    assert "think" not in captured[0]
    assert r["message"]["content"] == "ok"


def test_think_unset_400_does_not_retry(oa, monkeypatch):
    """未设置 think 时 400 不应触发去参重试(载荷本就无 think,重试无意义)。"""
    calls = {"n": 0}

    def boom(req, timeout=10):
        calls["n"] += 1
        raise urllib.error.HTTPError("http://x", 400, "bad", {}, io.BytesIO(b""))

    monkeypatch.setattr(oa.urllib.request, "urlopen", boom)
    monkeypatch.setattr(oa, "TEMP", None)
    monkeypatch.setattr(oa, "THINK", None)
    with pytest.raises(urllib.error.HTTPError):
        oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[])
    assert calls["n"] == 1


# ---- 思考非空、正文为空:如实上报,按正常空响应路径处理 ----

def test_stream_thinking_only_response_carries_thinking(oa, monkeypatch):
    """thinking 模型裸请求(未设置)下思考烧光预算 → 流式返回携带 thinking、
    content 为空;主循环据此计空轮进防护梯,不崩、不死循环。"""
    lines = [
        json.dumps({"message": {"role": "assistant", "thinking": "让我想想…"},
                    "done": False}),
        json.dumps({"message": {"role": "assistant", "content": ""},
                    "done_reason": "length", "done": True,
                    "prompt_eval_count": 10, "eval_count": 500}),
    ]
    captured = []
    monkeypatch.setattr(oa.urllib.request, "urlopen",
                        _capture_urlopen(captured, FakeStreamResp(lines)))
    monkeypatch.setattr(oa, "TEMP", None)
    monkeypatch.setattr(oa, "THINK", None)
    toks, thinks = [], []
    r = oa.call_chat("m", [{"role": "user", "content": "hi"}], ctx=1024, tools=[],
                     stream=True, on_token=toks.append, on_think=thinks.append)
    assert thinks == ["让我想想…"]                    # 思考流实时回调不丢
    assert r["message"]["content"] == ""
    assert r["message"]["thinking"] == "让我想想…"    # 思考随返回结构上交,可记录
    assert oa._semantically_empty(r["message"]["content"])   # 计空轮,防护梯接管
