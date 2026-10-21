# -*- coding: utf-8 -*-
"""v3.0.0 平台感知(Platform-Aware)测试:platform_profile 单一事实源 + agent/GUI 接线。

范围对应 2026-10-21 调研报告 P0-1(平台信息块)/P0-2(exec_env 收敛)/
P0-3b(参数类型校正回喂)/P1-4(profile 数据化)/P1-6(reg 危险面)/P1-7(命令输出精简)。
静态 SYSTEM 常量与出厂 prefill 钉子(1250)不受影响——平台块是动态注入行。"""

import importlib
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SRC_OA = open(os.path.join(_HERE, "ollama_agent.py"), encoding="utf-8").read()
SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()


@pytest.fixture
def fresh_appconfig(monkeypatch, tmp_path):
    """干净 MINGBIRD_HOME + 重载 appconfig(命令输出精简读配置层,必须隔离真机 config)。"""
    monkeypatch.setenv("MINGBIRD_HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_SLIM_OUTPUT", raising=False)
    import appconfig
    importlib.reload(appconfig)
    yield appconfig
    appconfig._cache = None


# ================= ① platform_profile 单一事实源 =================

def test_profile_detection_windows_real():
    import platform_profile as pp
    p = pp.detect()
    assert p["id"] in ("windows", "macos", "linux")
    assert p["path_sep"] == ("\\" if p["id"] == "windows" else "/")
    assert p["shell"] == ("cmd.exe" if p["id"] == "windows" else "/bin/sh")


def test_prompt_block_full_content():
    import platform_profile as pp
    pp._PROFILE = None   # 重置缓存,按本机真实平台生成
    b = pp.prompt_block(full=True)
    lines = b.split("\n")
    assert len(lines) == 3
    assert "平台:" in lines[0] and "shell=" in lines[0] and "&&" in lines[0]
    assert "命令对照:" in lines[1]
    assert "沙箱外" in lines[2] and "确认" in lines[2]


def test_prompt_block_platform_commands_match_os():
    """命令对照必须与本机平台一致(Windows 教 dir/findstr,POSIX 教 ls/grep)。"""
    import platform_profile as pp
    pp._PROFILE = None
    b = pp.prompt_block(full=True)
    if os.name == "nt":
        assert "搜索文本=findstr" in b and "列目录=dir" in b
        assert "搜索文本=grep" not in b
    else:
        assert "搜索文本=grep" in b and "列目录=ls" in b
        assert "findstr" not in b


def test_prompt_block_simulated_macos():
    import platform_profile as pp
    pp._PROFILE = {"id": "macos", "shell": "/bin/sh", "path_sep": "/"}
    try:
        b = pp.prompt_block(full=True)
        assert "macOS" in b and "列目录=ls" in b and "看文件=cat" in b
        mini = pp.prompt_block(full=False)
        assert "\n" not in mini and "macOS" in mini and "/" in mini
    finally:
        pp._PROFILE = None


def test_prompt_block_unattended_wording():
    """无人值守下是硬拒不是确认——提示词不能教模型"继续干活即可"。"""
    import platform_profile as pp
    b = pp.prompt_block(full=True, unattended=True)
    assert "无人值守" in b and "拒绝" in b
    assert "用户确认" not in b


def test_prompt_block_minimal_is_single_line():
    import platform_profile as pp
    pp._PROFILE = None
    assert len(pp.prompt_block(full=False).split("\n")) == 1
    assert "命令对照" not in pp.prompt_block(full=False)


def test_exec_env_utf8_and_no_mutation():
    import platform_profile as pp
    base = {"PATH": "x"}
    env = pp.exec_env(base)
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"
    assert base == {"PATH": "x"}                       # 不改入参
    pre = pp.exec_env({"PYTHONUTF8": "0"})             # setdefault:已有值不覆盖
    assert pre["PYTHONUTF8"] == "0"


def test_open_cmds_delegate_by_os():
    import platform_profile as pp
    if os.name == "nt":
        assert pp.open_folder_cmd("C:/x")[0] == "explorer"
        assert pp.open_doc_cmd("C:/x/a.txt")[0] == "notepad"
    else:
        assert pp.open_folder_cmd("/tmp")[0] in ("open", "xdg-open")


# ================= ② agent 接线:平台块 + exec_env 收敛 =================

def test_system_prompt_carries_platform_block():
    import ollama_agent as A
    sp = A.system_prompt()
    assert "平台:" in sp and "命令对照:" in sp          # 动态注入生效
    assert "命令对照" not in A.SYSTEM                    # 静态常量未被污染


def test_prefill_pin_unchanged_by_platform_block():
    """出厂 prefill 钉子:SYSTEM+CORE_TOOLS 估算仍为 1250(平台块是动态行)。
    计量口径与 v191 相同:真实主目录先还原成 {USER_HOME} 占位符,跨机器可复现。"""
    import ollama_agent as A
    _home = os.path.expanduser("~") or "~"
    msgs = [{"role": "system", "content": A.SYSTEM.replace(_home, "{USER_HOME}")}]
    assert A._estimate_messages_tokens(msgs, A.CORE_TOOLS) == 1250


def test_exec_env_converged_in_source():
    """run_bash/run_python 的内联 UTF-8 环境拼装已全部收敛到 platform_profile。"""
    assert SRC_OA.count('_pp.exec_env()') == 2
    assert '_env.setdefault("PYTHONUTF8", "1")' not in SRC_OA


def test_qa_branch_single_line_platform():
    assert "_pp.prompt_block(full=False)" in SRC_OA


# ================= ③ 参数类型校正(P0-3b,PydanticAI 式回喂) =================

def test_coerce_string_number_to_int_float():
    import ollama_agent as A
    out, err = A._coerce_args("todo", {"action": "update", "index": "1", "done": "true"})
    assert err is None
    assert out["index"] == 1 and isinstance(out["index"], int)
    assert out["done"] is True
    out2, err2 = A._coerce_args("read_file", {"path": "x", "start_line": "5", "end_line": "9.5"})
    assert err2 is None
    assert out2["start_line"] == 5 and out2["end_line"] == 9.5


def test_coerce_passthrough_correct_types_and_none():
    import ollama_agent as A
    out, err = A._coerce_args("todo", {"action": "list", "index": 2, "done": False})
    assert err is None and out == {"action": "list", "index": 2, "done": False}
    out2, err2 = A._coerce_args("read_file", {"path": "a", "start_line": None})
    assert err2 is None and out2["start_line"] is None


def test_coerce_bad_type_structured_error():
    import ollama_agent as A
    out, err = A._coerce_args("todo", {"action": "update", "index": "第一名"})
    assert err and "[tool error:" in err and "index" in err and "number" in err
    assert out == {"action": "update", "index": "第一名"}   # 出错时返回原 args 不动


def test_coerce_boolean_garbage_errors_symmetrically():
    """boolean 收到解析不了的字符串必须报错——静默放行会让工具侧按字符串真值
    误判(审查发现的 number/boolean 不对称问题)。"""
    import ollama_agent as A
    out, err = A._coerce_args("todo", {"action": "update", "index": 1, "done": "完成"})
    assert err and "done" in err and "boolean" in err
    # 大小写宽容:"True"/"FALSE" 一样能校正
    out2, err2 = A._coerce_args("todo", {"action": "update", "index": 1, "done": "FALSE"})
    assert err2 is None and out2["done"] is False


def test_coerce_empty_optional_number_passthrough():
    """可选数值参数填空串 = 未提供(v2.1.5 行为):不得报错。"""
    import ollama_agent as A
    out, err = A._coerce_args("read_file",
                              {"path": "x", "start_line": "", "end_line": ""})
    assert err is None
    assert out["start_line"] == "" and out["end_line"] == ""


def test_coerce_accepts_one_zero_and_plus_numbers():
    """布尔 "1"/"0" 与 +N / 下划线数字是常见编码,三态复核后纳入。"""
    import ollama_agent as A
    out, err = A._coerce_args("todo", {"action": "update", "index": "+1", "done": "1"})
    assert err is None and out["index"] == 1 and out["done"] is True
    out2, err2 = A._coerce_args("todo", {"action": "update", "index": "1_000", "done": "0"})
    assert err2 is None and out2["index"] == 1000 and out2["done"] is False


def test_coerce_unknown_tool_untouched():
    import ollama_agent as A
    args = {"anything": "1"}
    out, err = A._coerce_args("mcp_servers.tool_x", args)
    assert err is None and out is args


def test_coerce_list_passthrough():
    """todo 的 index 运行时支持批量列表(schema 未表达)——非标量必须放行不报错。"""
    import ollama_agent as A
    out, err = A._coerce_args("todo", {"action": "update", "index": [1, 3]})
    assert err is None
    assert out["index"] == [1, 3]


def test_run_tool_read_file_with_string_range(tmp_path):
    """端到端:start_line/end_line 传字符串,经校正后按数字区间读取成功。"""
    import ollama_agent as A
    f = tmp_path / "lines.txt"
    f.write_text("l1\nl2\nl3\nl4\n", encoding="utf-8")
    res = A.run_tool("read_file", {"path": "lines.txt", "start_line": "2", "end_line": "3"}, str(tmp_path))
    assert "l2" in str(res) and "l4" not in str(res)


# ================= ④ 危险面:注册表写入(reg add/delete/import) =================

def test_env_mutate_now_covers_registry(tmp_path):
    import ollama_agent as A
    assert A._ENV_MUTATE_RE.search("reg add HKCU\\Software\\X /v y /t REG_SZ /d z")
    assert A._ENV_MUTATE_RE.search("REG DELETE HKLM\\Bad /f")
    assert not A._ENV_MUTATE_RE.search("reg query HKCU\\Software\\X")   # 只读查询放行
    assert A._ENV_MUTATE_RE.search("setx PATH C:\\x")                   # 旧面不回退


def test_risk_classify_registry_confirms_or_blocks(tmp_path, monkeypatch):
    """无人值守下 reg add 走默认拒绝;AGENT_ALLOW_ENV_MUTATION=1 放行。"""
    import ollama_agent as A
    monkeypatch.setenv("AGENT_ALLOW_ENV_MUTATION", "0")
    monkeypatch.setattr(A, "_UNATTENDED", True)
    r = A._risk_classify("reg add HKCU\\Software\\X /v y /t REG_SZ /d z", str(tmp_path))
    assert r and "安全垫" in r
    monkeypatch.setenv("AGENT_ALLOW_ENV_MUTATION", "1")
    assert A._risk_classify("reg add HKCU\\Software\\X /v y", str(tmp_path)) is None


def test_gate_registry_reaches_risk_ring(tmp_path, monkeypatch):
    """reg add/delete 此前已在 _DANGER_CMD 里被硬拒,新分级环永远看不到
    (v3.0.0 复审 P1-1)。现在应与 setx 同门:无人值守拒、允许开关放行。"""
    import ollama_agent as A
    monkeypatch.setenv("AGENT_ALLOW_ENV_MUTATION", "0")
    monkeypatch.setattr(A, "_UNATTENDED", True)
    r = A._gate_check("run_bash",
                      {"command": "reg add HKCU\\Software\\X /v y /t REG_SZ /d z"},
                      str(tmp_path))
    assert r and "安全垫" in r and "命令含危险操作" not in r
    r2 = A._gate_check("run_bash", {"command": "reg delete HKLM\\Bad /f"},
                       str(tmp_path))
    assert r2 and "安全垫" in r2 and "命令含危险操作" not in r2
    monkeypatch.setenv("AGENT_ALLOW_ENV_MUTATION", "1")
    assert A._gate_check("run_bash",
                         {"command": "reg add HKCU\\Software\\X /v y"},
                         str(tmp_path)) is None


# ================= ⑤ 命令输出精简(P1-7 一期:上下文紧张触发,含手动开关) =================

def test_slim_output_default_auto(fresh_appconfig):
    # None = 自动:≤32K 才开。三态是 v3.0.0 复审后的修复。
    assert fresh_appconfig.slim_output_mode() is None


def test_slim_output_env_and_config(fresh_appconfig, monkeypatch):
    for v, want in (("1", True), ("0", False), ("true", True), ("off", False)):
        monkeypatch.setenv("AGENT_SLIM_OUTPUT", v)
        fresh_appconfig._cache = None
        assert fresh_appconfig.slim_output_mode() is want, v
    monkeypatch.setenv("AGENT_SLIM_OUTPUT", "")
    cfg = fresh_appconfig.load_config()
    for v, want in (("on", True), ("off", False), ("auto", None),
                    (True, True), (False, None)):
        cfg["slim_output"] = v
        fresh_appconfig.save_config(cfg)
        fresh_appconfig._cache = None
        assert fresh_appconfig.slim_output_mode() is want, v


def test_agent_loop_pins_slim_output_wiring():
    """三态:auto(≤32K)/强制开/强制关;不按模型大小自动。≤4B 的 edit_file
    等协议降级仍由 _small_model 驱动,与输出瘦身解耦。"""
    assert "_slim_pref = appconfig.slim_output_mode()" in SRC_OA
    assert ("_SLIM_OUTPUT_MODE = (CTX_BUDGET <= 32768 if _slim_pref is None else _slim_pref)"
            in SRC_OA)
    assert "bool(_small_model) or appconfig.slim_output_mode()" not in SRC_OA


def test_slim_output_effective_three_state(fresh_appconfig):
    """auto:≤32K 开、大档位关;显式 on/off 覆盖档位(基准可复现旧数据)。"""
    import ollama_agent as A
    saved = A.CTX_BUDGET
    def eff(pref, ctx):
        return (ctx <= 32768 if pref is None else pref)
    try:
        A.CTX_BUDGET = 32768
        assert eff(fresh_appconfig.slim_output_mode(), A.CTX_BUDGET) is True
        A.CTX_BUDGET = 131072
        assert eff(fresh_appconfig.slim_output_mode(), A.CTX_BUDGET) is False
        assert eff(True, A.CTX_BUDGET) is True       # 强制开
        assert eff(False, A.CTX_BUDGET) is False     # 强制关
        A.CTX_BUDGET = 16384
        assert eff(False, A.CTX_BUDGET) is False     # 小档位也能关(旧版关不掉)
    finally:
        A.CTX_BUDGET = saved


# ================= ⑥ GUI 接线钉子 =================

def test_gui_delegates_platform_cmds():
    assert "platform_profile.open_folder_cmd(path)" in SRC_GUI
    assert "platform_profile.open_doc_cmd(path)" in SRC_GUI
    # 便携模式:MINGBIRD_HOME 下 GUI 与 agent 必须读同一个 home
    assert "AGENT_HOME = appconfig.AGENT_HOME" in SRC_GUI
    # 会话侧边栏不得把 .todo.json 快照当成一个会话列出来
    assert 'f.endswith((".meta.json", ".todo.json"))' in SRC_GUI


def test_gui_slim_output_tristate_and_i18n():
    assert "命令输出精简" in SRC_GUI
    assert '_slim_map = {None: _t("自动(≤32K)"), True: _t("开"), False: _t("关")}' in SRC_GUI
    assert '_cfg["slim_output"] = ("auto" if _slim_pick is None' in SRC_GUI
    assert '_T["自动(≤32K)"] = "Auto (≤32K)"' in SRC_GUI
