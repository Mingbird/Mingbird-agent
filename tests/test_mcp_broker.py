# -*- coding: utf-8 -*-
"""v3.1.6 MCP 常驻 broker:
1. N 次调用只 spawn 一次(启动计数文件为证)——每调用 spawn 税还清;
2. manifest 强制重探复用常驻会话,不再白 spawn(300s 重探税);
3. AGENT_MCP_BROKER=0 走原单次路径(每调用一 spawn);
4. 会话被杀 → 自动重拉,结果不丢;错误调用回喂期望参数名。"""
import importlib.util
import json
import os
import sys
import time

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

SERVER = os.path.join(os.path.dirname(__file__), "fixtures", "fake_mcp_server.py")


def _setup(tmp_path, monkeypatch):
    cnt = tmp_path / "starts.txt"
    cfgfile = tmp_path / "mcp.json"
    cfgfile.write_text(json.dumps({
        "fake": {"command": sys.executable,
                 "args": ["-u", SERVER],   # -u:子进程 stdio 全不缓冲(CI 稳定性)
                 "env": {"FAKE_MCP_COUNT": str(cnt),
                         "FAKE_MCP_LOG": str(tmp_path / "srv.log")}}}), encoding="utf-8")
    monkeypatch.setattr(A, "MCP_CONFIG", str(cfgfile))
    monkeypatch.setattr(A, "_BROKER_ENABLED", True)
    A._broker_close_all()
    monkeypatch.setattr(A, "_MCP_CACHE", {"t": 0, "data": None})
    monkeypatch.setattr(A, "_MCP_CACHE_FILE", str(tmp_path / "cache.json"))
    return cnt


def _starts(cnt):
    try:
        return len(open(cnt, encoding="utf-8").read().splitlines())
    except Exception:
        return 0


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    A._broker_close_all()


def test_broker_single_spawn_across_calls(tmp_path, monkeypatch):
    cnt = _setup(tmp_path, monkeypatch)
    assert "第一次" in A.mcp_call("fake", "echo", {"text": "第一次"})
    assert "第二次" in A.mcp_call("fake", "echo", {"text": "第二次"})
    assert "第三次" in A.mcp_call("fake", "echo", {"text": "第三次"})
    assert _starts(cnt) == 1            # 三次调用,一次 spawn
    A._broker_close_all()
    time.sleep(0.3)
    assert _starts(cnt) == 1            # 关闭不重启


def test_manifest_reuses_broker_session(tmp_path, monkeypatch):
    cnt = _setup(tmp_path, monkeypatch)
    assert "echo:" in A.mcp_call("fake", "echo", {"text": "x"})   # 建会话
    m = A.mcp_manifest(force=True)                                  # 强制重探
    assert m["fake"]["tools"] and m["fake"]["tools"][0]["name"] == "echo"
    assert _starts(cnt) == 1                                        # 重探没白 spawn


def test_broker_off_falls_back_per_call(tmp_path, monkeypatch):
    if importlib.util.find_spec("mcp") is None:
        pytest.skip("mcp 库未装:单次路径依赖 mcp.ClientSession(CI 不装该依赖)")
    cnt = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(A, "_BROKER_ENABLED", False)
    assert "echo:" in A.mcp_call("fake", "echo", {"text": "a"})
    assert "echo:" in A.mcp_call("fake", "echo", {"text": "b"})
    assert _starts(cnt) == 2           # 单次路径=每调用一 spawn(旧行为基线)


def test_broker_error_surfaces_params_hint(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = A.mcp_call("fake", "nope", {})
    assert "mcp_call error" in r and "期望参数" in r


def test_broker_dead_session_respawns(tmp_path, monkeypatch):
    cnt = _setup(tmp_path, monkeypatch)
    assert "echo:" in A.mcp_call("fake", "echo", {"text": "1"})
    with A._BROKER_LOCK:
        for s in A._BROKER.values():
            s.proc.kill()
    time.sleep(0.2)
    assert "echo:" in A.mcp_call("fake", "echo", {"text": "2"})   # 自动重拉
    assert _starts(cnt) >= 2
