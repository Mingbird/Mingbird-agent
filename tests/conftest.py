# -*- coding: utf-8 -*-
"""套件级确定性护栏。

issue #7 修复(2026-11-18)给 appconfig 加了 local_open:回环 URL 且存在代理来源
(环境变量或 Windows 注册表系统代理)时绕过代理直连。直连 opener 不经过测试
monkeypatch 的 urllib.request.urlopen 桩——这意味着套件结果取决于"跑测试那一刻
系统代理是否开启"(开着 Clash 系统代理的机器上,26 个桩测试会真连 127.0.0.1
拒连而挂)。autouse 把门控钉死为 False:所有测试恒走 urlopen 桩路径,与运行
环境无关;需要真实直连分支的测试(test_issue7_loopback)用 monkeypatch 显式
覆盖回真函数。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import appconfig   # noqa: E402  必须与被测模块共享同一 sys.modules 实例


@pytest.fixture(autouse=True)
def _tests_never_take_proxy_branch(monkeypatch):
    # raising=True(默认):_proxies_active 若被重构改名,conftest 必须大声失败,
    # 否则护栏静默失效,套件又变回"结果取决于系统代理状态"。
    monkeypatch.setattr(appconfig, "_proxies_active", lambda: False)
