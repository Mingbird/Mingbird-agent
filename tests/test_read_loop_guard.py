# -*- coding: utf-8 -*-
"""读循环守护的单元与回放测试。

背景:三个既有检测(重复拦截/同签名连续/同工具连续)全是邻接比较,A→B→A→B 的
周期 2 循环打不中,0.8B 曾把同一文件反复读 158 次烧尽 200 轮。本文件钉住:
①周期 2 循环 → 封读热点路径(其他文件照常——按路径不按工具);
②越界读取第一次就给明确信号,连续 3 次封读;
③限速梯子:超预算后前两次仍返回内容,3/4 次硬拒绝,5 次起封读;
④豁免红线:顺序精读不同区间、递增窗口、edit→跑命令的合法迭代都不触发。
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


@pytest.fixture()
def clean_state(oa, monkeypatch, tmp_path):
    monkeypatch.setattr(oa, "_active_tools", list(oa.CORE_TOOLS))
    monkeypatch.setattr(oa, "_disabled_tools", set())
    oa._unlock_used.clear()
    oa._SIG_WINDOW.clear()
    oa._CRAWL_BANNED.clear()
    oa._SIG_BANNED.clear()
    monkeypatch.setattr(oa, "_UNATTENDED", True)
    monkeypatch.setattr(oa, "SESSIONS_DIR", str(tmp_path / "sessions"))
    os.makedirs(str(tmp_path / "sessions"), exist_ok=True)
    return tmp_path


def _make_file(workdir, name, n_lines):
    path = os.path.join(workdir, name)
    with open(path, "w", encoding="utf-8") as f:
        for i in range(1, n_lines + 1):
            f.write(f"line {i} of {name}\n")
    return path


# ---- ②越界读取:明确信号 + ×3 封读 ----

def test_oob_read_signals_then_bans_path(oa, clean_state):
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    _make_file(workdir, "timetrack.py", 84)
    r1 = oa.run_tool("read_file", {"path": "timetrack.py", "start_line": 300, "end_line": 320}, workdir)
    assert "读取越界" in r1 and "84 行" in r1 and "不会有新内容" in r1
    oa.run_tool("read_file", {"path": "timetrack.py", "start_line": 320, "end_line": 340}, workdir)
    r3 = oa.run_tool("read_file", {"path": "timetrack.py", "start_line": 340, "end_line": 360}, workdir)
    assert "已封读" in r3
    r4 = oa.run_tool("read_file", {"path": "timetrack.py", "start_line": 1, "end_line": 20}, workdir)
    assert "已被封读" in r4 and "其他文件不受影响" in r4


# ---- ③限速梯子:内容 ×2 → 硬拒 ×2 → 封读 ----

def test_throttle_escalation_ladder(oa, clean_state):
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    _make_file(workdir, "big.txt", 50)
    ck = os.path.normcase(os.path.normpath(os.path.join(workdir, "big.txt")))
    crawl = {ck: [10, 70000, 2, 1, 0, 0]}   # 已超 64KB 预算
    args = {"path": "big.txt"}
    r1 = oa.run_tool("read_file", dict(args), workdir, crawl_state=crawl)
    assert "读取限速中" in r1 and "line 1" in r1          # 仍返回内容
    r2 = oa.run_tool("read_file", dict(args), workdir, crawl_state=crawl)
    assert "读取限速中" in r2                              # 第 2 次仍返回内容
    r3 = oa.run_tool("read_file", dict(args), workdir, crawl_state=crawl)
    assert "硬拦" in r3 and "不返回内容" in r3             # 第 3 次硬拒绝
    r4 = oa.run_tool("read_file", dict(args), workdir, crawl_state=crawl)
    assert "硬拦" in r4                                    # 第 4 次仍拒
    r5 = oa.run_tool("read_file", dict(args), workdir, crawl_state=crawl)
    assert "已被封读" in r5                                # 第 5 次起封读
    assert ck in oa._CRAWL_BANNED


# ---- ④豁免红线 ----

def test_legal_sequential_reads_not_flagged(oa, clean_state):
    """顺序精读同一文件的 5 个不同区间是合法行为:不封读、不拒、不进禁用。"""
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    _make_file(workdir, "long.txt", 500)
    for a, b in ((20, 40), (40, 60), (60, 80), (80, 100), (100, 120)):
        r = oa.run_tool("read_file", {"path": "long.txt", "start_line": a, "end_line": b}, workdir)
        assert "封读" not in r and "越界" not in r
    assert not oa._CRAWL_BANNED
    assert "read_file" not in oa._disabled_tools


# ---- ①周期 2 循环:整链回放(封签名,新区间放行) ----

def test_period2_loop_bans_signatures_new_range_still_readable(oa, clean_state, monkeypatch):
    """stub 交替读同一文件的两个区间(A→B→A→B):两个签名被封后,同区间再读被拒,
    但换一个新区间必须放行(那是进展不是打转——keep_b2 教训:路径级封读把新区间
    一并拒了,把模型推进 run_bash 死胡同),其他文件照常,read_file 不被禁用。"""
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    _make_file(workdir, "timetrack.py", 84)
    _make_file(workdir, "other.txt", 30)
    state = {"n": 0, "i": 0, "stage": "loop",
             "new_res": None, "other_res": None, "created": False}

    def fake_call_chat(model, messages, ctx=None, tools=None, stream=False,
                       on_token=None, on_think=None):
        state["n"] += 1
        assert state["n"] < 80, "回放未在预算内走出死循环"
        last_tool = ""
        for m in reversed(messages):
            if m.get("role") == "tool":
                last_tool = str(m.get("content", ""))
                break

        def resp(name, args):
            tc = {"function": {"name": name, "arguments": args}}
            return {"message": {"content": "", "tool_calls": [tc]}}

        # 先收上一发调用的回执,再决定下一发。阶段:
        # loop(交替读两区间)→ new_wait(已发新区间,收回执)→ other(发其他文件)
        # → other_wait(收回执)→ deliver(create_file → finish)。
        if state["stage"] == "new_wait":
            state["new_res"] = last_tool
            state["stage"] = "other"
        elif state["stage"] == "other_wait":
            state["other_res"] = last_tool
            state["stage"] = "deliver"

        if state["stage"] == "loop":
            if "该区间已被封读" in last_tool:
                state["stage"] = "new_wait"
            else:
                a, b = (40, 60) if state["i"] % 2 else (60, 84)
                state["i"] += 1
                return resp("read_file", {"path": "timetrack.py",
                                          "start_line": a, "end_line": b})
        if state["stage"] == "new_wait":
            return resp("read_file", {"path": "timetrack.py",
                                      "start_line": 1, "end_line": 20})
        if state["stage"] == "other_wait":
            return resp("read_file", {"path": "other.txt", "start_line": 1, "end_line": 10})
        if state["stage"] == "other":
            state["stage"] = "other_wait"
            return resp("read_file", {"path": "other.txt", "start_line": 1, "end_line": 10})
        if not state["created"]:
            state["created"] = True
            return resp("create_file", {"path": "report.md",
                                        "content": "# Report\nDone."})
        return resp("finish", {"summary": "Wrote report.md."})

    monkeypatch.setattr(oa, "call_chat", fake_call_chat)
    messages = [
        {"role": "system", "content": "You are a test agent."},
        {"role": "user", "content": "Fix timetrack.py and write report.md. "
         "Do not access paths outside the workspace."},
    ]
    oa.agent_loop("stub-model", messages, workdir, "replay-readloop")

    assert state["stage"] in ("deliver", "other"), f"回放卡在阶段 {state['stage']}"
    assert state["n"] <= 30, f"封签名来得太晚({state['n']} 轮)"
    assert state["new_res"] is not None and "已被封读" not in state["new_res"] \
        and "timetrack.py" in state["new_res"], "新区间必须放行(那是进展,不是打转)"
    assert state["other_res"] is not None and "已被封读" not in state["other_res"] \
        and "other.txt" in state["other_res"], "封签名不应波及其他文件"
    assert (clean_state / "work" / "report.md").exists()
    assert "read_file" not in oa._disabled_tools, "签名封禁不得升级成工具禁用"
    assert not oa._CRAWL_BANNED, "循环窗口不得使用路径级封禁"


def test_banned_signature_refuses_same_args_only(oa, clean_state):
    """直接单测:同签名的读取被拒,不同区间/不同文件放行,路径不在封读集合。"""
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    _make_file(workdir, "f.py", 100)
    args = {"path": "f.py", "start_line": 40, "end_line": 60}
    sig = ("read_file", __import__("json").dumps(args, sort_keys=True, ensure_ascii=False))
    oa._SIG_BANNED.add(sig)
    r = oa.run_tool("read_file", dict(args), workdir)
    assert "该区间已被封读" in r
    r2 = oa.run_tool("read_file", {"path": "f.py", "start_line": 61, "end_line": 80}, workdir)
    assert "已被封读" not in r2 and "line 61" in r2
    assert not oa._CRAWL_BANNED


def test_run_bash_repetition_not_caught_by_read_window(oa, clean_state, monkeypatch):
    """edit→跑命令的合法迭代红线:同名命令反复执行(run_bash 不入读循环窗口),
    混合不同区间的 read_file,不得触发任何封读/禁用。"""
    workdir = str(clean_state / "work")
    os.makedirs(workdir, exist_ok=True)
    _make_file(workdir, "code.py", 60)
    state = {"n": 0, "bash": 0, "reads": 0, "created": False}

    def fake_call_chat(model, messages, ctx=None, tools=None, stream=False,
                       on_token=None, on_think=None):
        state["n"] += 1
        assert state["n"] < 60, "合法迭代被误伤"

        def resp(name, args):
            tc = {"function": {"name": name, "arguments": args}}
            return {"message": {"content": "", "tool_calls": [tc]}}

        if state["bash"] < 6:
            state["bash"] += 1
            return resp("run_bash", {"command": "echo step"})
        if state["reads"] < 3:
            state["reads"] += 1
            top = 20 * state["reads"]
            return resp("read_file", {"path": "code.py",
                                      "start_line": top - 19, "end_line": top})
        if not state["created"]:
            state["created"] = True
            return resp("create_file", {"path": "report.md", "content": "done"})
        return resp("finish", {"summary": "ok"})

    monkeypatch.setattr(oa, "call_chat", fake_call_chat)
    messages = [
        {"role": "system", "content": "You are a test agent."},
        {"role": "user", "content": "Iterate on code.py and write report.md."},
    ]
    oa.agent_loop("stub-model", messages, workdir, "replay-legal-iterate")
    assert not oa._CRAWL_BANNED
    assert "run_bash" not in oa._disabled_tools
    assert (clean_state / "work" / "report.md").exists()


# ---- no-revive 通道 ----
# (已随签名封禁移除:循环触发封的是签名不是工具,签名封禁天然不经 enable_tools,
#  反循环禁用的解锁封顶见 test_antiloop_escape.py)
