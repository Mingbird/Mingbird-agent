"""配置层测试:深合并、环境变量覆盖、非法值回退、类型收敛。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import parallel_config as PC


def test_defaults_are_strict():
    d = PC.DEFAULT_PARALLEL
    assert d["enabled"] is False
    assert d["child_model"] == ""            # 零硬编码:模型名必须显式配置
    assert d["hard_cap"] == 2
    assert d["allow_parent_eviction"] is False
    assert d["allow_overwrite_existing"] is False
    assert d["child_allow_commands"] is False
    assert d["retry_on_severe"] is False
    assert d["max_depth"] == 1
    assert "run_bash" not in d["child_allowed_tools"]
    assert "enable_tools" not in d["child_allowed_tools"]


def test_user_config_overrides_defaults():
    c = PC.get_parallel_config(config={"parallel": {"enabled": True, "hard_cap": 3,
                                                    "child_model": "gemma4:e2b"}})
    assert c["enabled"] is True and c["hard_cap"] == 3 and c["child_model"] == "gemma4:e2b"


def test_other_config_keys_ignored():
    c = PC.get_parallel_config(config={"ollama_host": "x", "parallel": {"nonsense": 1}})
    assert "nonsense" not in c and "ollama_host" not in c


def test_env_overrides_config():
    c = PC.get_parallel_config(config={"parallel": {"hard_cap": 3}},
                               environ={"AGENT_PARALLEL_MAX": "1",
                                        "AGENT_PARALLEL_MODEL": "qwen3.5:4b"})
    assert c["hard_cap"] == 1 and c["child_model"] == "qwen3.5:4b"


def test_invalid_values_fall_back_not_crash():
    c = PC.get_parallel_config(config={"parallel": {"hard_cap": "abc", "child_ctx": None,
                                                    "enabled": "yes"}})
    assert isinstance(c["hard_cap"], int) and c["hard_cap"] == 2
    assert c["enabled"] is True
    assert isinstance(c["child_ctx"], int)


def test_kill_switch_and_depth():
    assert PC.hard_disabled({"AGENT_PARALLEL": "0"}) is True
    assert PC.hard_disabled({"AGENT_PARALLEL": "false"}) is True
    assert PC.hard_disabled({}) is False
    assert PC.current_depth({}) == 0
    assert PC.current_depth({"HUMMINGBIRD_DEPTH": "2"}) == 2
    assert PC.current_depth({"HUMMINGBIRD_DEPTH": "garbage"}) == 0


def test_rule_lists_are_data_not_code():
    """安全规则是数据:可以整体替换或追加,出厂默认 = 最严档。"""
    strict = PC.get_parallel_config(config={"parallel": {}})
    assert strict["sensitive_dir_patterns"] == []       # 空 = 用出厂最严默认
    assert strict["dangerous_command_patterns"] == []
    c = PC.get_parallel_config(config={"parallel": {
        "extra_dangerous_command_patterns": ["mycompany_tool"]}})
    assert c["extra_dangerous_command_patterns"][0]["pattern"] == "mycompany_tool"
    c2 = PC.get_parallel_config(config={"parallel": {
        "dangerous_command_patterns": [{"pattern": "foo", "severity": "severe"}]}})
    assert len(c2["dangerous_command_patterns"]) == 1


def test_no_model_name_hardcoded_anywhere():
    """逻辑代码里不得出现任何具体模型 tag(零硬编码)。"""
    for mod in ("parallel_config", "parallel_probe", "parallel_todo",
                "parallel_dispatch", "parallel_safety"):
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                mod + ".py"), encoding="utf-8").read()
        for tag in ("gemma4", "qwen3.5", "ornith"):
            assert tag not in src, f"{mod} 硬编码了 {tag}"
