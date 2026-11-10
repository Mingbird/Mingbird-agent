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


# ---- 缺陷 A:计算型工具被禁用的话术 ----

def test_disabled_compute_message_offers_two_routes(oa, tmp_path):
    """计算型工具被禁的话术必须:给 create_file 这条文档类出路(绝大多数交付物
    本来就是文档);保留'必须由代码算出的产物换代码重跑'的防伪造分支;
    不推荐 enable_tools 解锁(小模型解锁后会原样重发同一条被拒命令,
    死胡同变无限循环);附进度快照让模型重建方向。"""
    msg = oa._disabled_tool_message("run_python", str(tmp_path))
    assert "enable_tools" not in msg
    assert "create_file" in msg
    assert "换一段不同的代码重跑" in msg
    assert "当前进度快照" in msg
    msg2 = oa._disabled_tool_message("run_bash", str(tmp_path))
    assert "enable_tools" not in msg2 and "create_file" in msg2


def test_disabled_read_tool_message_still_points_at_output(oa):
    """非计算工具被禁用时,话术仍可指向产出文件,但不给 enable_tools
    (不在场景里承诺解锁,避免空头支票)。"""
    msg = oa._disabled_tool_message("todo")
    assert "create_file" in msg
    assert "enable_tools" not in msg


def test_escape_routes_survive_120_char_truncation(oa, tmp_path):
    """上下文压缩 L1 把旧 tool 消息截到 120 字符——两条出路必须落在前 120
    字符内(实测:快照在前时,'二选一:'后面被整体截掉,模型原地重发撞帽),
    快照挪到末尾,被截断也不影响出路。"""
    # 600+ 字符的计划 + 若干文件,把快照撑大
    big_plan = [{"item": "这是第 %d 步,包含足够多的中文字符来撑长计划文本。" % i, "done": False}
                for i in range(1, 16)]
    with open(os.path.join(str(tmp_path), "todo.json"), "w", encoding="utf-8") as f:
        json.dump(big_plan, f, ensure_ascii=False)
    for fn in ("design_day.md", "test_day.py", "timetrack.py", "raw.csv", "notes.txt"):
        (tmp_path / fn).write_text("x", encoding="utf-8")
    msg = oa._disabled_tool_message("run_bash", str(tmp_path))
    assert "1)" in msg[:120] and "2)" in msg[:120], "出路被截断在 120 字符之外"
    assert "当前进度快照" in msg and msg.find("当前进度快照") > 120   # 快照在末尾
    assert "换一段不同的代码重跑" in msg


def test_disabled_message_single_source(oa):
    """源钉:三处拒绝点共用一个话术函数(防各自漂移);任何一处都不得再推荐
    enable_tools 解锁;v3.1.7 之前的'一律建议手写'话术必须保持消失。"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
               encoding="utf-8").read()
    assert src.count("_disabled_tool_message(") >= 4   # 定义 + 工具回执 + 三连提示 + 硬复位
    assert "需要恢复该工具" not in src
    assert "直接用 create_file 写产出文件,或已有信息足够就调用 finish" not in src


# ---- 缺陷 B:无人值守拒绝必须给出路 ----

def test_unattended_denial_states_workdir(oa, tmp_path, monkeypatch):
    """无人值守的越界拒绝必须给出真实工作目录和相对路径替代做法(读+写两个方向
    都要有)——没有出路的小模型会把拒绝当瞬时失败原样重试。"""
    monkeypatch.setattr(oa, "_UNATTENDED", True)
    allow, allow_all, msg = oa._ask_user_confirm(
        "read_file", str(tmp_path / "x"), str(tmp_path))
    assert allow is False and allow_all is False
    assert os.path.abspath(str(tmp_path)) in msg
    assert "相对路径" in msg
    assert "create_file" in msg


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
