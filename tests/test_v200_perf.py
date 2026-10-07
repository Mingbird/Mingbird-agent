# -*- coding: utf-8 -*-
"""v2.0.0 性能与生命周期修复的单元测试(2026-10-06 现场复盘):
①keep_alive 下发 ②bash 超时可配 ③MCP 探测:手写 stdio 探测器/超时进程树硬杀/
失败用旧缓存兜底且 TTL 压短 ④todo 会话快照。不依赖网络 / 不调用 ollama / 不起 GUI。
"""
import json
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

FAKE_MCP = r'''
import json, sys
for ln in sys.stdin:
    try: msg = json.loads(ln)
    except Exception: continue
    if msg.get("id") == 1:
        print(json.dumps({"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",
              "capabilities":{},"serverInfo":{"name":"fake","version":"1"}}}), flush=True)
    elif msg.get("method") == "tools/list":
        print(json.dumps({"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"fake_tool",
              "description":"d","inputSchema":{"type":"object","properties":{"q":{"type":"string"}},
              "required":["q"]}}]}}), flush=True)
'''

FAKE_MCP_HANG = r'''
import os, sys, time
open(sys.argv[1], "w").write(str(os.getpid()))
time.sleep(300)
'''


@pytest.fixture
def oa():
    return A


def test_probe_stdio_returns_tools(oa, tmp_path):
    srv = tmp_path / "fake_mcp.py"
    srv.write_text(FAKE_MCP, encoding="utf-8")
    tools = oa._probe_stdio({"command": sys.executable, "args": [str(srv)]}, timeout=20)
    assert tools is not None
    assert [t["name"] for t in tools] == ["fake_tool"]
    assert tools[0]["schema"]["properties"]["q"]["type"] == "string"


def test_probe_stdio_timeout_kills_tree(oa, tmp_path):
    srv = tmp_path / "hang.py"
    srv.write_text(FAKE_MCP_HANG, encoding="utf-8")
    pidfile = tmp_path / "pid.txt"
    t0 = time.time()
    # timeout=20:给解释器冷启动留足余量(CI 全新 runner 上首启扫描可达十几秒,
    # timeout=6 曾出现在杀进程时 pidfile 还没写出来→断言误炸;本测试验证的是
    # "超时→进程树硬杀",放宽冷启动窗口不改变验证强度)
    r = oa._probe_stdio({"command": sys.executable,
                         "args": [str(srv), str(pidfile)]}, timeout=20)
    assert r is None
    assert time.time() - t0 < 35
    # 进程树必须被硬杀:pid 不再存活。
    # (注意:中文 Windows 的 tasklist 输出 GBK,text=True 按 utf-8 解码会让读取
    # 线程崩溃、stdout 变 None——这里用 ctypes OpenProcess 探活,绕开编码坑。)
    deadline = time.time() + 10
    while time.time() < deadline and not pidfile.exists():
        time.sleep(0.1)
    assert pidfile.exists(), "fake server 未写入 pidfile"
    pid = pidfile.read_text(encoding="utf-8").strip()
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        alive = False
        for _ in range(4):            # 终止中的进程句柄可能短暂可开,重试确认
            h = k32.OpenProcess(0x1000, False, int(pid))
            alive = bool(h)
            if h:
                k32.CloseHandle(h)
            if not alive:
                break
            time.sleep(0.5)
        assert not alive, f"探测超时后进程 {pid} 仍在存活(进程树未被硬杀)"
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)


def test_keep_alive_and_ctx_in_payload(oa, monkeypatch):
    monkeypatch.setattr(oa.appconfig, "cloud_provider", lambda: None)
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps({"message": {"content": "ok"},
                               "prompt_eval_count": 1, "eval_count": 1}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(oa.urllib.request, "urlopen", fake_urlopen)
    oa.call_chat("m", [{"role": "user", "content": "hi"}])
    p = captured["payload"]
    assert p["keep_alive"] == oa.KEEP_ALIVE          # v2.0.0:顶层字段,防 5 分钟卸载重载
    assert p["options"]["num_ctx"] == oa.CTX_BUDGET
    assert p["options"]["num_predict"] == oa.NUM_PREDICT


def test_run_python_docx_importable(oa, tmp_path):
    """v2.0.0:run_python 环境必须能 import docx(当晚实录:模型两次因缺库炸掉,
    被迫用 zipfile 手搓 docx XML;通用技能里 Word 生成/读取是卖点)。"""
    out = oa.run_tool("run_python", {"code": "import docx\nprint('docx-ok')"}, str(tmp_path))
    assert "[exit 0]" in out and "docx-ok" in out


def test_bash_timeout_default(oa):
    assert oa.BASH_TIMEOUT == 120                     # v2.0.0:300 → 120


def test_save_session_todo_snapshot(oa, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "SESSIONS_DIR", str(tmp_path))
    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "todo.json").write_text(json.dumps([{"item": "a", "done": False}]),
                                  encoding="utf-8")
    oa.save_session("s1", [{"role": "user", "content": "t"}], str(wd))
    snap = tmp_path / "s1.todo.json"
    assert snap.exists()
    assert json.loads(snap.read_text(encoding="utf-8"))[0]["item"] == "a"
    # 无 todo 的会话保存 → 旧快照被清,防串档
    wd2 = tmp_path / "wd2"
    wd2.mkdir()
    oa.save_session("s1", [{"role": "user", "content": "t2"}], str(wd2))
    assert not snap.exists()


def test_manifest_stale_merge_and_short_ttl(oa, tmp_path, monkeypatch):
    cache_f = tmp_path / "mcp_manifest_cache.json"
    monkeypatch.setattr(oa, "_MCP_CACHE_FILE", str(cache_f))
    monkeypatch.setattr(oa, "_MCP_CACHE", {"t": 0, "data": None})
    monkeypatch.setattr(oa, "load_mcp_servers", lambda: {"slow": {"command": "x"}})
    # 磁盘旧缓存(已过期,但 slow 有旧工具):探测失败时应兜底,而非缓存成空
    cache_f.write_text(json.dumps({"ts": time.time() - 400, "data": {"slow": {
        "categories": ["MCP"], "tools": [{"name": "old_tool", "desc": "", "schema": {},
                                           "categories": ["MCP"], "expose": "auto"}]}}}),
                       encoding="utf-8")
    monkeypatch.setattr(oa, "_probe_server", lambda cfg: None)
    m = oa.mcp_manifest(force=True)
    assert m["slow"]["tools"][0]["name"] == "old_tool"
    assert oa._MCP_CACHE["t"] <= time.time() - 240       # 失败 → TTL 压到 60s 后重试

    # 成功路径:全量 TTL
    monkeypatch.setattr(oa, "_probe_server", lambda cfg: [])
    m2 = oa.mcp_manifest(force=True)
    assert m2["slow"]["tools"] == []
    assert oa._MCP_CACHE["t"] >= time.time() - 5
