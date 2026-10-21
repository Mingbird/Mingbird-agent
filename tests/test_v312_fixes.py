# -*- coding: utf-8 -*-
"""v3.1.1 源码审计三连修的回归钉:
1. AGENT_UNATTENDED=1 → _ask_user_confirm 所有通道(含 AGENT_STREAM 的 @@ASK@@
   分支)一律直接拒,不再出现"无人值守却挂 120s 等确认"的组合;
2. crawl guard 预算与消耗统一字节口径(预算=getsize 字节,原消耗=len() 字符,
   中文文件实际拿到约 3× 额度)。
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


def test_ask_user_confirm_denies_when_unattended(oa, tmp_path, monkeypatch):
    """无人值守 + 流式监听同时在:无人在环,直接拒而非弹 @@ASK@@ 等 120s。"""
    monkeypatch.setenv("AGENT_STREAM", "1")
    monkeypatch.setattr(oa, "_UNATTENDED", True)
    ok, allok, msg = oa._ask_user_confirm("read_file", "/etc/hosts",
                                          str(tmp_path), "读取")
    assert ok is False and allok is False
    assert "无人值守" in msg
    assert "@@ASK@@" not in msg


def test_crawl_guard_counts_bytes_not_chars(oa, tmp_path, monkeypatch):
    """中文文件按字节计量:同预算下,字符口径 15 次读不完额度,字节口径
    约第 6 次即限速(每读 6000 字符=18000 字节,预算=2×48000 字节)。"""
    monkeypatch.setattr(oa, "_CRAWL_BUDGET_FLOOR", 4096, raising=False)
    p = tmp_path / "zh.txt"
    p.write_text("鸣鸟测试中文内容" * 2000, encoding="utf-8")   # 16000 字=48000B
    state = {}
    hit = None
    r = ""
    for i in range(1, 16):
        r = oa.run_tool("read_file", {"path": "zh.txt"}, str(tmp_path),
                        crawl_state=state)
        if "crawl-guard" in r:
            hit = i
            break
    assert hit is not None and hit <= 8       # 旧字符口径:15 次内永不触限
    assert "字节" in r                          # 提示口径同为字节
