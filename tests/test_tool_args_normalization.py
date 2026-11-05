# -*- coding: utf-8 -*-
"""v3.1.6 工具参数归一化层:
1. dict 原样通过、合法 JSON 字符串解析、无 note;
2. <think> 泄漏剥离 / 平衡 {} 提取 / 尾逗号与 python 字面量与单引号修复;
3. 修不好 → (None, 原因),派发层拒绝执行并回喂原因(源码钉:静默空 dict 路径已删)。"""
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

N = A._normalize_tool_args


def test_dict_passthrough():
    args, note = N("t", {"a": 1})
    assert args == {"a": 1} and note is None


def test_valid_json_string():
    args, note = N("t", '{"path": "x.txt"}')
    assert args == {"path": "x.txt"} and note is None


def test_empty_string():
    assert N("t", "") == ({}, None)
    assert N("t", "   ") == ({}, None)


def test_think_leak_stripped():
    raw = '<think>用户想要文件……我应该……</think>\n{"path": "a.md"}'
    args, note = N("t", raw)
    assert args == {"path": "a.md"}
    assert note == "已剥离参数外的杂散文本"


def test_balanced_braces_extracted():
    raw = '我用工具创建文件:```json\n{"path": "b.md", "content": "hi {未闭合示例}"}\n``` 完成后继续'
    args, note = N("t", raw)
    assert args == {"path": "b.md", "content": "hi {未闭合示例}"}
    assert note is not None


def test_trailing_comma_repaired():
    args, note = N("t", '{"a": 1, "b": 2,}')
    assert args == {"a": 1, "b": 2}
    assert "已自动修复" in note


def test_python_literals_repaired():
    args, note = N("t", '{"flag": True, "x": None}')
    assert args == {"flag": True, "x": None}
    assert "已自动修复" in note


def test_single_quotes_repaired():
    args, note = N("t", "{'path': 'c.md'}")
    assert args == {"path": "c.md"}
    assert "已自动修复" in note


def test_unrepairable_returns_none_with_reason():
    args, note = N("t", "完全不是 JSON 的胡话")
    assert args is None
    assert "不是合法 JSON" in note


def test_array_is_rejected_with_note():
    args, note = N("t", '[1, 2, 3]')
    assert args is None
    assert "而非 JSON 对象" in note


def test_silent_empty_dict_path_removed_from_src():
    """源码钉:旧"except: args={}"静默空参路径必须不复存在。"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
               encoding="utf-8").read()
    assert "except: args={}" not in src
    assert "_normalize_tool_args(name, args)" in src
    assert "参数解析失败,该调用未执行" in src
