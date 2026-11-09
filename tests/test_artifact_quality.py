# -*- coding: utf-8 -*-
"""产物质量加固的单元测试:反循环禁用话术分叉 / 无人值守拒绝给出路 / finish
内容门禁 / 交付物语言跟任务文本。

背景(写进测试防止回归):计算型工具(run_bash/run_python)被反循环禁用后,
旧话术让模型"用 create_file 写产出文件"——对计算型任务这就是教模型手写伪造
本应由脚本算出的结果;无人值守的越界拒绝不给工作目录和替代做法,小模型把拒绝
当瞬时失败原样重试到工具被禁;finish 门只查文件存在,两段 JSON 首尾相接的
坏产物也能放行;英文任务的交付物跟着界面语言变成了中文。
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


# ---- 缺陷 A:计算型工具被禁用的话术 ----

def test_disabled_compute_tool_does_not_advise_handwriting(oa):
    """run_python/run_bash 被禁用时,拒绝话术不得建议用 create_file 写产物,
    并且必须给出 enable_tools 这条真实的解锁通道(禁用消息承诺的出路必须存在)。"""
    for tool in ("run_python", "run_bash"):
        msg = oa._disabled_tool_message(tool)
        assert "create_file 写产出文件" not in msg
        assert "enable_tools" in msg


def test_disabled_read_tool_message_still_points_at_output(oa):
    """非计算工具被禁用时,话术仍可指向产出文件,但不给 enable_tools
    (不在场景里承诺解锁,避免空头支票)。"""
    msg = oa._disabled_tool_message("todo")
    assert "create_file" in msg
    assert "enable_tools" not in msg


def test_hard_reset_tail_forked_by_tool_type(oa):
    """源钉:硬复位尾句按工具类型分叉,计算型不得再出现'手写产物'话术。"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
               encoding="utf-8").read()
    assert "不要用手写文件代替计算" in src
    # 旧的合一话术(对计算型工具也建议手写)必须整体消失
    assert "直接用 create_file 写产出文件,或已有信息足够就调用 finish" not in src
    assert src.count("_disabled_tool_message(") >= 2   # 定义 + 调用


# ---- 缺陷 B:无人值守拒绝必须给出路 ----

def test_unattended_denial_states_workdir(oa, tmp_path, monkeypatch):
    """无人值守的越界拒绝必须给出真实工作目录和相对路径替代做法——
    没有出路的小模型会把拒绝当瞬时失败原样重试。"""
    monkeypatch.setattr(oa, "_UNATTENDED", True)
    allow, allow_all, msg = oa._ask_user_confirm(
        "read_file", str(tmp_path / "x"), str(tmp_path))
    assert allow is False and allow_all is False
    assert os.path.abspath(str(tmp_path)) in msg
    assert "相对路径" in msg


# ---- 缺陷 C:finish 内容门禁 ----

def test_content_gate_flags_concatenated_json(oa, tmp_path):
    """两段 JSON 首尾相接不是合法 JSON,必须被打回(存在性通过 ≠ 产物可用)。"""
    (tmp_path / "index.json").write_text('{"a":1}{"b":2}', encoding="utf-8")
    problems = oa._artifact_content_problems(str(tmp_path))
    assert len(problems) == 1 and problems[0][0] == "index.json"


def test_content_gate_ignores_harness_files(oa, tmp_path):
    """harness/评分器自己的文件(todo.json/.agent_state.json/score.json)
    不参与内容核对——它们不是模型的交付物。"""
    (tmp_path / "todo.json").write_text("not json", encoding="utf-8")
    (tmp_path / ".agent_state.json").write_text("not json", encoding="utf-8")
    (tmp_path / "score.json").write_text("not json", encoding="utf-8")
    assert oa._artifact_content_problems(str(tmp_path)) == []


def test_content_gate_passes_valid_json(oa, tmp_path):
    (tmp_path / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.json").write_text('[1, 2]', encoding="utf-8")
    assert oa._artifact_content_problems(str(tmp_path)) == []


def test_content_gate_only_checks_json(oa, tmp_path):
    """只查 .json:.jsonl/.csv/.md 可能合法地"不是单个 JSON 对象",不核。"""
    (tmp_path / "log.jsonl").write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    (tmp_path / "t.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "r.md").write_text("# 报告\n不是 json", encoding="utf-8")
    assert oa._artifact_content_problems(str(tmp_path)) == []


# ---- 缺陷 D:交付物语言跟任务文本 ----

def test_task_language_detection(oa):
    assert oa._task_output_language("Write a syllabus for a research software course.") == "en"
    assert oa._task_output_language("设计一门研究软件课,排十周模块,写前两次课详案。") == "zh"
    assert oa._task_output_language("") == "en"
    assert oa._task_output_language(None) == "en"


def test_language_pin_follows_task_not_env(oa):
    """源钉:语言钉取自任务文本推断;AGENT_LANG(GUI 按系统语言自动写入)
    不得参与交付物语言判定——中文界面跑英文任务必须仍得到英文钉。"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
               encoding="utf-8").read()
    assert "_out_lang = _task_output_language(task)" in src
    assert 'os.environ.get("AGENT_LANG", "") or _task_output_language' not in src
