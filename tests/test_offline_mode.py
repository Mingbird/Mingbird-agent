# -*- coding: utf-8 -*-
"""v1.8.0 一键断网(offline mode)测试:装配过滤、云禁用、消息映射。
全部离线断言(不发网络请求)。"""
import importlib
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ONLINE_TOOLS = {"web_search", "web_fetch", "web_search_multi", "batch_tools"}


@pytest.fixture
def fresh_appconfig(monkeypatch, tmp_path):
    """干净 MINGBIRD_HOME + 可控 env,重载 appconfig(清缓存)。"""
    monkeypatch.setenv("MINGBIRD_HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_OFFLINE", raising=False)
    import appconfig
    importlib.reload(appconfig)
    yield appconfig
    appconfig._cache = None


def _set_offline(appconfig, monkeypatch, value):
    monkeypatch.setenv("AGENT_OFFLINE", "1" if value else "0")
    appconfig._cache = None


def test_offline_default_off(fresh_appconfig):
    assert fresh_appconfig.offline_mode() is False


def test_offline_env_override(fresh_appconfig, monkeypatch):
    _set_offline(fresh_appconfig, monkeypatch, True)
    assert fresh_appconfig.offline_mode() is True
    _set_offline(fresh_appconfig, monkeypatch, False)
    assert fresh_appconfig.offline_mode() is False


def test_offline_from_config(fresh_appconfig):
    cfg = fresh_appconfig.load_config()
    cfg["offline_mode"] = True
    fresh_appconfig.save_config(cfg)
    fresh_appconfig._cache = None
    assert fresh_appconfig.offline_mode() is True


def test_cloud_disabled_when_offline(fresh_appconfig, monkeypatch):
    cfg = fresh_appconfig.load_config()
    cfg["cloud"] = {"enabled": True, "base_url": "https://example.invalid/v1",
                    "model": "m", "api_key": "k"}
    fresh_appconfig.save_config(cfg)
    fresh_appconfig._cache = None
    assert fresh_appconfig.cloud_provider()["model"] == "m"
    _set_offline(fresh_appconfig, monkeypatch, True)
    assert fresh_appconfig.cloud_provider() == {}      # 断网=云端强制禁用


def test_cloud_requires_full_config(fresh_appconfig):
    cfg = fresh_appconfig.load_config()
    cfg["cloud"] = {"enabled": True, "model": "m"}     # 缺 base_url
    fresh_appconfig.save_config(cfg)
    fresh_appconfig._cache = None
    assert fresh_appconfig.cloud_provider() == {}


def test_filter_offline_tools(fresh_appconfig, monkeypatch):
    import ollama_agent as oa
    defs = [{"type": "function", "function": {"name": n, "parameters": {}}}
            for n in ("read_file", "web_search", "web_fetch", "create_file",
                      "web_search_multi", "batch_tools", "run_bash")]
    _set_offline(fresh_appconfig, monkeypatch, True)
    names = {t["function"]["name"] for t in oa._filter_offline_tools(defs)}
    assert names & ONLINE_TOOLS == set()
    assert {"read_file", "create_file", "run_bash"} <= names
    _set_offline(fresh_appconfig, monkeypatch, False)
    assert len(oa._filter_offline_tools(defs)) == len(defs)


def test_chat_tool_defs_offline(fresh_appconfig, monkeypatch):
    import ollama_agent as oa
    _set_offline(fresh_appconfig, monkeypatch, True)
    names = {t["function"]["name"] for t in oa._chat_tool_defs()}
    assert "web_search" not in names and "web_fetch" not in names
    assert {"read_file", "list_dir"} <= names
    _set_offline(fresh_appconfig, monkeypatch, False)
    names = {t["function"]["name"] for t in oa._chat_tool_defs()}
    assert {"read_file", "list_dir", "web_search", "web_fetch"} <= names


def test_cloud_message_mapping():
    """ollama 形态 → OpenAI 形态:assistant.tool_calls(dict args)→JSON 字符串,
    相邻 tool 消息按序配对 tool_call_id。"""
    import ollama_agent as oa
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "create_file", "arguments": {"path": "a", "content": "x"}}},
            {"function": {"name": "read_file", "arguments": {"path": "b"}}}]},
        {"role": "tool", "content": "ok1"},
        {"role": "tool", "content": "ok2"},
        {"role": "assistant", "content": "done"},
    ]
    out = oa._cloud_to_openai_messages(msgs)
    assert out[0] == {"role": "system", "content": "s"}
    a = out[2]
    assert a["role"] == "assistant" and len(a["tool_calls"]) == 2
    assert json.loads(a["tool_calls"][0]["function"]["arguments"])["path"] == "a"
    t1, t2 = out[3], out[4]
    assert t1["role"] == "tool" and t1["tool_call_id"] == a["tool_calls"][0]["id"]
    assert t2["tool_call_id"] == a["tool_calls"][1]["id"]
    assert out[5] == {"role": "assistant", "content": "done"}
