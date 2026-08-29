# -*- coding: utf-8 -*-
"""finish 产物核对门禁 + 小模型协议降级 + 持久禁用机制的单元测试。"""
import importlib.util
import os
import sys
import tempfile

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


# ---- _model_params_b:模型名 → 参数量 ----

def test_params_parsing(oa):
    assert oa._model_params_b("gemma4:e2b") == 2.0
    assert oa._model_params_b("qwen3.5:4b") == 4.0
    assert oa._model_params_b("gemma4:12b") == 12.0
    assert oa._model_params_b("ornith-1.5:35b") == 35.0
    assert oa._model_params_b("unknown-model") is None


def test_small_model_boundary(oa):
    is_small = lambda m: (oa._model_params_b(m) or 99.0) <= 4.0
    assert is_small("gemma4:e2b") and is_small("qwen3.5:4b")
    assert not is_small("gemma4:12b") and not is_small("ornith-1.5:35b")
    assert not is_small("unknown-model")   # 解析失败 → 按大模型


# ---- _claimed_missing_files:finish summary 产物核对 ----

def test_claim_missing_detected(oa):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "report.md"), "w").write("x")
    assert oa._claimed_missing_files(
        "已写入 report.md 和 anomalies.md", d) == ["anomalies.md"]


def test_claim_all_exist(oa):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "report.md"), "w").write("x")
    assert oa._claimed_missing_files("已写入 report.md", d) == []


def test_claim_subdir_counts(oa):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "sub"))
    open(os.path.join(d, "sub", "fig1.png"), "w").write("x")
    assert oa._claimed_missing_files("生成 sub/fig1.png", d) == []


def test_claim_chinese_verb_prefix(oa):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "温度分布图.png"), "w").write("x")
    assert oa._claimed_missing_files("生成了温度分布图.png", d) == []


def test_claim_no_false_positive_numbers(oa):
    d = tempfile.mkdtemp()
    assert oa._claimed_missing_files("done, 3.5b params, v1.1.0 e.g. ok", d) == []


def test_claim_input_fixture_mention(oa):
    d = tempfile.mkdtemp()
    open(os.path.join(d, "requirements_doc.md"), "w").write("x")
    assert oa._claimed_missing_files(
        "按 requirements_doc.md 要求完成,产出 report.md", d) == ["report.md"]


# ---- 持久禁用机制:tools_for_categories 不还原被禁工具 ----

def test_disabled_tool_not_reassembled(oa):
    oa._disabled_tools.add("edit_file")
    try:
        ct = oa.tools_for_categories({"文件", "代码"})
        assert "edit_file" not in [t["function"]["name"] for t in ct]
    finally:
        oa._disabled_tools.clear()
    ct2 = oa.tools_for_categories({"文件", "代码"})
    assert "edit_file" in [t["function"]["name"] for t in ct2]
