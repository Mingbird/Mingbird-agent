# -*- coding: utf-8 -*-
"""issue #7(2026-11-17,Win11+代理):本地推理链路被系统代理拦截。

背景(写进测试防止回归):urllib 默认尊重系统代理/代理环境变量,且
proxy_bypass("127.0.0.1")=False(CPython 的 "<local>" 豁免只匹配不带点的主机名)
——开着 Clash/v2rayN 时,对 127.0.0.1:11434 的探测/模型列表/对话请求全被代理
拦下:Ollama 明明在跑仍被误报"未能自动启动",本地引擎整条链路断,而 curl/netstat
不经代理所以用户看到监听正常。修法=appconfig.local_open:回环 URL 一律绕过代理
直连,非回环(云端/自定义远程端点)保持 urllib 默认。"""
import http.server
import importlib.util
import os
import socket
import sys
import threading
import urllib.request

import pytest

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "appconfig", os.path.join(_here, "..", "appconfig.py"))
appconfig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(appconfig)


# ---- 回环判定 ----

def test_is_loopback_url_truth_table():
    assert appconfig.is_loopback_url("http://127.0.0.1:11434/api/tags")
    assert appconfig.is_loopback_url("http://localhost:11434/api/chat")
    assert appconfig.is_loopback_url("http://[::1]:11434/v1/models")   # IPv6 字面量
    assert appconfig.is_loopback_url("http://LOCALHOST:9931/v1")       # 大小写
    assert not appconfig.is_loopback_url("http://192.168.1.5:11434")
    assert not appconfig.is_loopback_url("https://api.openai.com/v1")
    assert not appconfig.is_loopback_url("not a url")


# ---- 决定性实验:同一回环地址,代理毒化环境下 urlopen 挂、local_open 通 ----

def test_local_open_bypasses_proxy(monkeypatch):
    """起真实回环 HTTP 服务;把 http_proxy/https_proxy 指到一个必然拒连的端口。
    裸 urlopen 必须失败(根因复现),local_open 必须成功(修复)。跨平台:拒连端口
    用一个已绑定但 backlog 关闭的 socket 地址,连接立即被拒。"""
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        url = f"http://127.0.0.1:{port}/api/tags"
        # 毒化代理:绑一个立刻关闭监听的端口,连接必被拒(不依赖具体机器环境)
        sink = socket.socket()
        sink.bind(("127.0.0.1", 0))
        sink_port = sink.getsockname()[1]
        sink.close()
        monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{sink_port}")
        monkeypatch.setenv("https_proxy", f"http://127.0.0.1:{sink_port}")
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{sink_port}")
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{sink_port}")
        # 根因复现:裸 urlopen 走代理 → 拒连(本机代理开着时用户看到的就是这个)
        with pytest.raises(Exception):
            urllib.request.urlopen(url, timeout=5)
        # 修复:local_open 对回环绕过代理直连
        with appconfig.local_open(url, timeout=5) as r:
            assert r.status == 200 and b'"ok"' in r.read()
    finally:
        srv.shutdown()
        srv.server_close()


def test_local_open_non_loopback_keeps_default(monkeypatch):
    """非回环 URL 保持 urllib 默认(带代理环境时仍走代理=云端调用不受影响):
    用毒化代理断言 local_open 对外网地址同样失败(证明它没有全局禁代理)。"""
    sink = socket.socket()
    sink.bind(("127.0.0.1", 0))
    sink_port = sink.getsockname()[1]
    sink.close()
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{sink_port}")
    with pytest.raises(Exception):
        appconfig.local_open("http://192.168.1.5:1/", timeout=3)


# ---- 源钉:调用面收敛,防新增裸 urlopen 回潮 ----

def test_source_no_bare_loopback_urlopen_left():
    """ollama_agent 里裸 urlopen 只允许剩 _call_cloud 一处(云端按设计走代理);
    agent_gui 的探测点全部换用 local_open;端点框 Ollama 模式显示真实地址。"""
    src = open(os.path.join(_here, "..", "ollama_agent.py"), encoding="utf-8").read()
    assert src.count("appconfig.local_open(") >= 12   # 探测3+show1+openai3+probe1+chat6
    # 剩余裸调用仅云端(_call_cloud 内 2711 一处)
    import re
    bare = [l for l in src.splitlines()
            if "urllib.request.urlopen(" in l and "appconfig" not in l
            and not l.strip().startswith("#")]
    assert len(bare) == 1, bare
    gsrc = open(os.path.join(_here, "..", "agent_gui.py"), encoding="utf-8").read()
    assert gsrc.count("appconfig.local_open(") >= 4    # refresh_models×2 + check_ollama×2
    assert "appconfig.ollama_host()))" in gsrc          # 端点框 Ollama 预填真实地址
    assert "(_cur_base or self.ENGINE_PRESETS[1][1])" not in gsrc   # LM Studio 1234 预填已废
