# -*- coding: utf-8 -*-
"""v2.1.2 修复的单元测试(外部用户 issue #4,Windows 安装包/无 pytest 环境):
①测试守护不再假定环境有 pytest:缺 pytest → 回退 python -m unittest;
  连 python 都缺 → skip 不拦(其余 finish 门照常)
②判定读 stdout+stderr 合流("No module named pytest" 走 stderr,
  旧版"精确失败"恒空)③拒绝词不再把路指死在 pytest,并披露 3 次上限
④守护内 pytest 超时不再走 pr.returncode 的 AttributeError 崩溃路径
⑤GUI 思考标记点击 lambda 参数容错(e=None)。不联网、不装任何包。"""
import os
import subprocess
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_OA = open(os.path.join(_HERE, "ollama_agent.py"), encoding="utf-8").read()
SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()


def _pr(rc, out="", err=""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


# ---------------- _test_env_broken:缺件 vs 真失败 ----------------

def test_env_broken_no_module_pytest():
    pr = _pr(1, err="C:\\...\\python.exe: No module named pytest")
    assert A._test_env_broken(pr, (pr.stdout + pr.stderr)) is True


def test_env_broken_python_missing():
    assert A._test_env_broken(_pr(9009, err="'python' is not recognized as an internal or external command"), "x") is True
    assert A._test_env_broken(_pr(127, err="python: command not found"), "x") is True


def test_env_broken_real_failure_is_not_env():
    out = "test_leap.py F\nFAILED test_leap.py::test_1900 - AssertionError\n"
    assert A._test_env_broken(_pr(1, out=out), out) is False
    assert A._test_env_broken(_pr(0, out="3 passed"), "3 passed") is False


def test_env_broken_none_pr_is_not_env():
    assert A._test_env_broken(None, "") is False


# ---------------- _run_test_guard:三段降级 ----------------

def _seq(monkeypatch, resps):
    """按序喂 subprocess.run 假返回(元素可为 Exception=抛出);记录调用。"""
    calls = []
    it = iter(resps)
    def _fake(cmd, **kw):
        calls.append((cmd, kw))
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(A.subprocess, "run", _fake)
    return calls


def test_guard_pytest_missing_falls_back_to_unittest_pass(monkeypatch, tmp_path):
    """issue #4 原案:pytest 缺、unittest 风格测试已绿 → 必须放行,不得判失败。"""
    calls = _seq(monkeypatch, [
        _pr(1, err="python.exe: No module named pytest"),
        _pr(0, out="....\n----------------------------------------------------------------------\nRan 4 tests in 0.001s\n\nOK"),
    ])
    v, h = A._run_test_guard(str(tmp_path))
    assert v == "pass"
    assert "unittest" in calls[1][0]           # 回退命令真的是 unittest
    assert calls[0][1]["cwd"] == str(tmp_path)  # 在工作目录跑
    assert calls[0][1]["creationflags"] == A.NOWIN


def test_guard_python_missing_skips(monkeypatch, tmp_path):
    calls = _seq(monkeypatch, [
        _pr(9009, err="'python' is not recognized as an internal or external command"),
        _pr(9009, err="'python' is not recognized as an internal or external command"),
    ])
    v, h = A._run_test_guard(str(tmp_path))
    assert v == "skip"                          # 不可验证 ≠ 失败,不拦
    assert h == ""


def test_guard_pytest_green_no_fallback(monkeypatch, tmp_path):
    calls = _seq(monkeypatch, [_pr(0, out="4 passed in 0.01s")])
    v, _ = A._run_test_guard(str(tmp_path))
    assert v == "pass"
    assert len(calls) == 1                      # pytest 可用就不跑第二段


def test_guard_pytest_red_gives_precise_hint(monkeypatch, tmp_path):
    out = ("FAILED test_leap.py::test_1900 - AssertionError: 1900 不是闰年\n"
           'test_leap.py:12: AssertionError\nE  AssertionError: 1900 不是闰年\n'
           "1 failed, 3 passed in 0.02s\n")
    _seq(monkeypatch, [_pr(1, out=out)])
    v, h = A._run_test_guard(str(tmp_path))
    assert v == "fail"
    assert "test_leap" in h or "AssertionError" in h   # 精确失败非空


def test_guard_pytest_timeout_no_crash(monkeypatch, tmp_path):
    """旧版隐患:超时 pr=None 后仍取 pr.returncode → AttributeError 崩 harness。"""
    _seq(monkeypatch, [subprocess.TimeoutExpired(cmd="x", timeout=300)])
    v, h = A._run_test_guard(str(tmp_path))
    assert v == "fail"
    assert "超时" in h


def test_guard_unittest_fallback_red(monkeypatch, tmp_path):
    _seq(monkeypatch, [
        _pr(1, err="No module named pytest"),
        _pr(1, out="FF\nFAILED (failures=2)\n"),
    ])
    v, h = A._run_test_guard(str(tmp_path))
    assert v == "fail"
    assert "(failures=2)" in h                 # FAILED 行剥离前缀后仍进提示


# ---------------- 拒绝词与计数:源码钉子 ----------------

def test_guard_rejection_wording_pins():
    # 不再把路指死在 pytest;给出环境可用替代;披露 3 次上限
    assert "没有 pytest 就用 python -m unittest" in SRC_OA
    assert "满 3 次后 finish 将放行" in SRC_OA
    # 计数只在 fail 时消耗(旧版跑之前就 +1,通过的运行也烧预算)
    assert 'elif verdict == "fail":' in SRC_OA
    assert "test_guard_warns += 1\n" in SRC_OA


def test_gui_think_lambda_tolerates_no_args():
    """issue #4 附报崩溃:_think_freeze 的点击 lambda 被零参调用时不再 TypeError。"""
    assert "lambda e=None, u=uid: self._toggle_think(u)" in SRC_GUI
