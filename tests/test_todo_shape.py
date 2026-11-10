# -*- coding: utf-8 -*-
"""todo 状态文件加固的测试:形状归一化 + harness 状态文件写保护。

背景:模型曾绕过 todo 工具直接 create_file 覆写 todo.json(写成
{"status":"complete","tasks":[...]}),load_todo 把 dict 放行后,消费方
for x in t 迭代出字符串键,x.get() 直接 AttributeError 终止整个任务。
"""
import importlib.util
import json
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


@pytest.fixture()
def workdir(tmp_path):
    wd = tmp_path / "work"
    wd.mkdir()
    return str(wd)


def _write_todo(workdir, payload):
    with open(os.path.join(workdir, "todo.json"), "w", encoding="utf-8") as f:
        if isinstance(payload, str):
            f.write(payload)                      # 原样写(含非法 JSON)
        else:
            json.dump(payload, f, ensure_ascii=False)


# ---- 形状归一化 ----

def test_normal_list_passthrough(oa, workdir):
    _write_todo(workdir, [{"item": "a", "done": False}, {"item": "b", "done": True}])
    t = oa.load_todo(workdir)
    assert t == [{"item": "a", "done": False}, {"item": "b", "done": True}]


def test_dict_with_tasks_key_normalized(oa, workdir):
    _write_todo(workdir, {"status": "complete", "tasks": [
        {"id": "1", "name": "x", "status": "completed"},
        {"id": "2", "name": "y", "status": "pending"}]})
    t = oa.load_todo(workdir)
    assert t == [{"item": "x", "done": True}, {"item": "y", "done": False}]


def test_string_items_normalized(oa, workdir):
    _write_todo(workdir, ["a", "b"])
    assert oa.load_todo(workdir) == [{"item": "a", "done": False},
                                     {"item": "b", "done": False}]


def test_garbage_shapes_return_empty_no_raise(oa, workdir):
    for payload in ({"foo": 1}, "garbage", "{not json", 42, [{"id": 1}, "ok"]):
        _write_todo(workdir, payload)
        t = oa.load_todo(workdir)
        assert isinstance(t, list)
        for x in t:
            assert isinstance(x, dict) and "item" in x


def test_format_todo_lines_never_raises(oa, workdir):
    for payload in ({"status": "complete", "tasks": [{"name": "x", "status": "done"}]},
                    ["a", "b"], "{not json", {"foo": 1}):
        _write_todo(workdir, payload)
        lines = oa.format_todo_lines(oa.load_todo(workdir))
        assert isinstance(lines, str)


# ---- harness 状态文件写保护 ----

def test_create_file_refused_for_harness_state(oa, workdir):
    todo_path = os.path.join(workdir, "todo.json")
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write('[{"item": "real plan", "done": false}]')
    r = oa.run_tool("create_file", {"path": "todo.json",
                                    "content": '{"status": "complete"}'}, workdir)
    assert "拒绝" in r and "todo(action=create" in r
    with open(todo_path, encoding="utf-8") as f:
        assert json.load(f) == [{"item": "real plan", "done": False}]   # 内容不变


def test_agent_state_and_edit_append_also_blocked(oa, workdir):
    r1 = oa.run_tool("create_file", {"path": ".agent_state.json", "content": "{}"}, workdir)
    r2 = oa.run_tool("edit_file", {"path": "todo.json", "old": "a", "new": "b"}, workdir)
    r3 = oa.run_tool("append_file", {"path": "todo.json", "content": "x"}, workdir)
    assert all("拒绝" in r for r in (r1, r2, r3))


def test_normal_deliverable_unaffected(oa, workdir):
    r = oa.run_tool("create_file", {"path": "todo_notes.md", "content": "ok"}, workdir)
    assert "拒绝" not in r
