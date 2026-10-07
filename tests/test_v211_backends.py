# -*- coding: utf-8 -*-
"""v2.1.1 多本地引擎(OpenAI 兼容:LM Studio/llama.app/llama-server/Jan/vLLM)单元测试。
不联网、不调任何真实后端:urlopen 全部 monkeypatch 假响应。
覆盖:①appconfig.local_backend 归一化 ②行内 <think> 剥离(非流式正则+流式状态机,
含跨 chunk 撕裂标签) ③OpenAI 消息归一(工具参数 str/dict/坏 JSON 三态) ④载荷形状
(无 keep_alive/num_ctx/think;max_tokens 映射;-1 省略;api_key 才带 Bearer)
⑤SSE 流式(token/思考回调顺序、工具增量按 index 拼装、[DONE]、usage)
⑥call_chat 引擎分发 ⑦ollama 专属逻辑门禁(500 重启自愈/_model_can_think)。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import appconfig
import ollama_agent as A


@pytest.fixture
def lb_cache():
    """直接操纵 appconfig 模块级缓存(避免写真实 config.json),测完还原。"""
    saved = appconfig._cache
    yield lambda cfg: setattr(appconfig, "_cache", dict(cfg))
    appconfig._cache = saved
    A._THINK_CAP_CACHE.clear()


LB_OPENAI = {"local_backend": {"type": "openai",
                               "base_url": "http://127.0.0.1:1234/v1",
                               "api_key": ""}}
LB_OLLAMA = {"local_backend": {"type": "ollama"}}


# ---------------- appconfig.local_backend 归一化 ----------------

def test_local_backend_default_is_ollama(lb_cache):
    lb_cache({})
    assert appconfig.local_backend() == {"type": "ollama"}
    assert appconfig.backend_openai() is None
    assert appconfig.engine_display_name() == "Ollama"


def test_local_backend_openai_normalizes_trailing_slash(lb_cache):
    lb_cache({"local_backend": {"type": "openai",
                                "base_url": "http://127.0.0.1:9931/v1/",
                                "api_key": "sk-x"}})
    lb = appconfig.local_backend()
    assert lb["type"] == "openai"
    assert lb["base_url"] == "http://127.0.0.1:9931/v1"
    assert lb["api_key"] == "sk-x"
    assert appconfig.backend_openai() == lb
    assert appconfig.engine_display_name() == "OpenAI 兼容"


def test_local_backend_openai_without_base_url_falls_back(lb_cache):
    lb_cache({"local_backend": {"type": "openai", "base_url": "   "}})
    assert appconfig.local_backend() == {"type": "ollama"}
    lb_cache({"local_backend": "垃圾值"})
    assert appconfig.local_backend() == {"type": "ollama"}


# ---------------- 行内 <think> 剥离:非流式 ----------------

def test_split_inline_thinking_complete_tags():
    body, think = A._split_inline_thinking("<think>推理</think>\n\n正文")
    assert body == "正文"
    assert think == "推理"


def test_split_inline_thinking_multiple_and_none():
    body, think = A._split_inline_thinking("<think>a</think>x<think>b</think>y")
    assert body == "xy"
    assert think == "ab"
    assert A._split_inline_thinking("没有标签") == ("没有标签", "")
    assert A._split_inline_thinking("") == ("", "")


def test_split_inline_thinking_unclosed_tail():
    body, think = A._split_inline_thinking("<think>没说完就被截断")
    assert body == ""
    assert "截断" in think


# ---------------- 行内 <think> 剥离:流式状态机 ----------------

def test_inline_think_splitter_basic_routing():
    sp = A._InlineThinkSplitter()
    b1, t1 = sp.feed("<think>推理中")
    assert b1 == "" and t1 == "推理中"
    b2, t2 = sp.feed("继续</think>正文来了")
    assert b2 == "正文来了" and t2 == "继续"
    b3, t3 = sp.finish()
    assert b3 == "" and t3 == ""


def test_inline_think_splitter_torn_tag_across_chunks():
    sp = A._InlineThinkSplitter()
    b1, t1 = sp.feed("正文前半<th")       # 半个开标签:扣住不下发
    assert b1 == "正文前半" and t1 == ""
    b2, t2 = sp.feed("ink>思考</thin")
    assert b2 == "" and t2 == "思考"
    b3, t3 = sp.feed("k>正文后半")
    assert b3 == "正文后半" and t3 == ""


def test_inline_think_splitter_lone_lt_is_body():
    sp = A._InlineThinkSplitter()
    b1, t1 = sp.feed("a < b 且 3<5")
    assert b1 == "a < b 且 3<5" and t1 == ""
    b2, t2 = sp.finish()
    assert b2 == "" and t2 == ""


def test_inline_think_splitter_unclosed_at_finish():
    sp = A._InlineThinkSplitter()
    b1, t1 = sp.feed("开头<think>思考没")
    assert b1 == "开头" and t1 == "思考没"
    b2, t2 = sp.finish()
    assert b2 == "" and t2 == ""


# ---------------- OpenAI 消息归一 ----------------

def test_openai_normalize_merges_reasoning_and_inline_think():
    om = A._openai_normalize_message({
        "role": "assistant",
        "content": "<think>行内</think>答案",
        "reasoning_content": "字段态"})
    assert om["content"] == "答案"
    assert om["thinking"] == "字段态行内"


def test_openai_normalize_tool_args_str_and_dict_and_broken():
    om = A._openai_normalize_message({"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "function": {"name": "run_bash",
                                   "arguments": '{"cmd": "ls"}'}},
        {"id": "c2", "function": {"name": "read_file", "arguments": {"path": "x"}}},
        {"id": "c3", "function": {"name": "t", "arguments": "{坏 JSON"}}]})
    assert om["tool_calls"][0]["function"]["arguments"] == {"cmd": "ls"}
    assert om["tool_calls"][1]["function"]["arguments"] == {"path": "x"}
    assert om["tool_calls"][2]["function"]["arguments"]["_raw"] == "{坏 JSON"


# ---------------- 载荷形状与响应归一(非流式) ----------------

class _FakeResp:
    def __init__(self, body):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _capture_urlopen(monkeypatch, resp_obj):
    """捕获 urllib.request.Request → 假响应;记录 (url, headers, body)。"""
    seen = []
    def _fake(req, timeout=None):
        seen.append((req.full_url, dict(req.headers),
                     json.loads(req.data.decode())))
        return resp_obj
    monkeypatch.setattr("urllib.request.urlopen", _fake)
    return seen


MSGS = [{"role": "user", "content": "hi"}]


def test_call_openai_local_payload_shape(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    body = {"choices": [{"message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
    seen = _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", 1024)
    monkeypatch.setattr(A, "TEMP", None)
    res = A._call_openai_local(appconfig.backend_openai(), "qwen", MSGS, [], False, None, None)
    url, headers, payload = seen[0]
    assert url == "http://127.0.0.1:1234/v1/chat/completions"
    assert "Authorization" not in headers          # 空 key 不带 Bearer(严格服务会 401)
    assert payload["model"] == "qwen"
    assert payload["max_tokens"] == 1024
    assert payload["stream"] is False
    for absent in ("keep_alive", "options", "num_ctx", "think", "enable_thinking"):
        assert absent not in payload
    assert res["message"]["content"] == "ok"
    assert res["prompt_eval_count"] == 11 and res["eval_count"] == 7


def test_call_openai_local_unlimited_omits_max_tokens(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    body = {"choices": [{"message": {"role": "assistant", "content": "x"}}]}
    seen = _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", -1)      # 不限 → 省略字段用服务端默认
    A._call_openai_local(appconfig.backend_openai(), "m", MSGS, [], False, None, None)
    assert "max_tokens" not in seen[0][2]


def test_call_openai_local_api_key_header(monkeypatch, lb_cache):
    lb_cache({"local_backend": {"type": "openai",
                                "base_url": "http://127.0.0.1:9931/v1",
                                "api_key": "sk-local"}})
    body = {"choices": [{"message": {"role": "assistant", "content": "x"}}]}
    seen = _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", 0)
    A._call_openai_local(appconfig.backend_openai(), "m", MSGS, [], False, None, None)
    assert seen[0][1]["Authorization"] == "Bearer sk-local"


def test_call_openai_local_tools_passthrough(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    body = {"choices": [{"message": {"role": "assistant", "content": "",
                                     "tool_calls": [{"id": "c1", "function": {
                                         "name": "run_bash",
                                         "arguments": "{\"cmd\": \"dir\"}"}}]},
                         "finish_reason": "tool_calls"}]}
    seen = _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", 0)
    tools = [{"type": "function", "function": {"name": "run_bash",
                "description": "d", "parameters": {"type": "object", "properties": {}}}}]
    res = A._call_openai_local(appconfig.backend_openai(), "m", MSGS, tools, False, None, None)
    assert seen[0][2]["tools"] == tools
    assert seen[0][2]["tool_choice"] == "auto"
    assert res["message"]["tool_calls"][0]["function"]["arguments"] == {"cmd": "dir"}
    assert res["done_reason"] == "tool_calls"


def test_call_openai_local_fires_callbacks_once(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    body = {"choices": [{"message": {"role": "assistant",
                                     "content": "<think>t</think>答案",
                                     "reasoning_content": "r"}}]}
    _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", 0)
    toks, thinks = [], []
    res = A._call_openai_local(appconfig.backend_openai(), "m", MSGS, [], False,
                               toks.append, thinks.append)
    assert toks == ["答案"]
    assert thinks == ["rt"]                        # 字段态在前、行内剥离在后
    assert res["message"]["thinking"] == "rt"


# ---------------- SSE 流式 ----------------

class _FakeSSE:
    def __init__(self, lines):
        self._lines = lines
    def __iter__(self):
        return iter(self._lines)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _sse(chunks):
    return [f"data: {json.dumps(c)}".encode() for c in chunks] + [b"data: [DONE]"]


def test_call_openai_local_stream_tokens_and_think(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    chunks = [
        {"choices": [{"delta": {"content": "<th"}}]},
        {"choices": [{"delta": {"content": "ink>思考</think>你"}}]},
        {"choices": [{"delta": {"reasoning_content": "字段思考"}}]},
        {"choices": [{"delta": {"content": "好"}}],
         "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
    ]
    seen = _capture_urlopen(monkeypatch, _FakeSSE(_sse(chunks)))
    monkeypatch.setattr(A, "NUM_PREDICT", 0)
    toks, thinks = [], []
    res = A._call_openai_local(appconfig.backend_openai(), "m", MSGS, [], True,
                               toks.append, thinks.append)
    assert seen[0][2]["stream"] is True
    assert toks == ["你", "好"]                     # 行内思考不进正文流
    assert "".join(thinks) == "思考字段思考"
    assert res["message"]["content"] == "你好"
    assert res["message"]["thinking"] == "思考字段思考"
    assert res["prompt_eval_count"] == 5


def test_call_openai_local_stream_tool_call_assembly(monkeypatch, lb_cache):
    """OpenAI 流式口径:工具调用按 index 增量,name/参数字符串都可能跨 delta 撕裂。"""
    lb_cache(LB_OPENAI)
    _frag_a = '{"cmd": "di'      # 参数 JSON 被撕成两半
    _frag_b = 'r"}'
    chunks = [
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "call_1", "function": {"name": "run_", "arguments": ""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"name": "bash", "arguments": _frag_a}}]}}]},
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": _frag_b}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    _capture_urlopen(monkeypatch, _FakeSSE(_sse(chunks)))
    monkeypatch.setattr(A, "NUM_PREDICT", 0)
    res = A._call_openai_local(appconfig.backend_openai(), "m", MSGS, [], True, None, None)
    tc = res["message"]["tool_calls"][0]
    assert tc["id"] == "call_1"
    assert tc["function"]["name"] == "run_bash"
    assert tc["function"]["arguments"] == {"cmd": "dir"}


# ---------------- call_chat 分发与 ollama 专属逻辑门禁 ----------------

def test_call_chat_routes_to_openai_backend(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    body = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    seen = _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", 0)
    A.call_chat("qwen", MSGS, tools=[])
    assert seen[0][0].endswith("/v1/chat/completions")


def test_call_chat_still_uses_ollama_by_default(monkeypatch, lb_cache):
    lb_cache(LB_OLLAMA)
    body = {"message": {"role": "assistant", "content": "ok"}, "done": True}
    seen = _capture_urlopen(monkeypatch, _FakeResp(json.dumps(body).encode()))
    monkeypatch.setattr(A, "NUM_PREDICT", 512)
    A.call_chat("qwen", MSGS, tools=[], stream=False)
    assert seen[0][0].endswith("/api/chat")
    assert seen[0][2]["options"]["num_predict"] == 512


def test_model_can_think_skipped_on_openai_backend(monkeypatch, lb_cache):
    lb_cache(LB_OPENAI)
    def _boom(req, timeout=None):
        raise AssertionError("OpenAI 引擎下不应探测 /api/show")
    monkeypatch.setattr("urllib.request.urlopen", _boom)
    assert A._model_can_think("qwen") is None


def test_probe_openai_backend(lb_cache, monkeypatch):
    lb_cache(LB_OPENAI)
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: _FakeResp(b"{}"))
    assert A.probe_openai_backend() is True
    def _fail(req, timeout=None):
        raise OSError("down")
    monkeypatch.setattr("urllib.request.urlopen", _fail)
    assert A.probe_openai_backend() is False
    lb_cache(LB_OLLAMA)
    assert A.probe_openai_backend() is False      # 非 openai 引擎恒 False


def test_500_restart_gate_mentions_openai(monkeypatch, lb_cache):
    """500 重启自愈是 ollama 专属:源码钉子(OpenAI 引擎我们无权重启)。"""
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "ollama_agent.py"), encoding="utf-8").read()
    assert "_restarts < 3 and not appconfig.backend_openai()" in src


# ---------------- GUI/WebUI 接线钉子(CI 安全,不实例化 Tk) ----------------

def test_gui_wiring_pins():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gui = open(os.path.join(here, "agent_gui.py"), encoding="utf-8").read()
    # 引擎预设四家 + 自定义;保存写 config.json 的 local_backend 段
    assert "ENGINE_PRESETS" in gui
    for port in ("1234", "9931", "8080"):
        assert port in gui
    assert '"local_backend"] = {"type": "openai"' in gui
    # 模型列举/状态灯都有 OpenAI 分支(启动探测走 probe_openai_backend 封装)
    assert gui.count('_lb["base_url"] + "/models"') >= 2
    wsr = open(os.path.join(here, "webui", "server.py"), encoding="utf-8").read()
    assert '_lb["base_url"] + "/models"' in wsr
