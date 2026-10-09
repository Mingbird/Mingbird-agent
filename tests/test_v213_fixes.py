# -*- coding: utf-8 -*-
"""v2.1.3 修复的单元测试(用户现场:另一台机器上 E 盘整理任务,模型复读
"工作目录是 C:\\Users\\…"且无法访问 E):
根因三层——①静态 prefill 里唯一绝对路径是主目录({USER_HOME}),工作目录
从未告知模型,小模型把主目录当工作区 ②会话不记工作目录,载入历史对话后
工作目录与该对话无关 ③run_bash 的 cwd 其实一直正确(cwd=workdir 链路无恙)。
修复:①任务级动态注入 _TASK_WORKDIR(不动 SYSTEM 常量,849 钉子不变;
问答分支同样注入) ②save_session 把 workdir 写进会话 meta,GUI 载入历史
会话时恢复 ③新对话仍重置回默认目录(用户定案:本就该重置)。不联网。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_OA = open(os.path.join(_HERE, "ollama_agent.py"), encoding="utf-8").read()
SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()


@pytest.fixture
def task_workdir():
    saved = A._TASK_WORKDIR
    yield lambda v: setattr(A, "_TASK_WORKDIR", v)
    A._TASK_WORKDIR = saved


# ---------------- 工作目录注入:任务/问答两条路 ----------------

def test_system_prompt_injects_task_workdir(task_workdir):
    task_workdir(r"E:\整理")
    p = A.system_prompt()
    assert "当前工作目录" in p and r"E:\整理" in p
    # 主目录仍在(保存到桌面等外部路径的既有能力不受影响)
    assert "主目录:" in p


def test_system_prompt_no_injection_when_unset(task_workdir):
    task_workdir(None)
    assert "当前工作目录" not in A.system_prompt()


def test_system_prompt_constant_untouched(task_workdir):
    """动态行绝不进 SYSTEM 常量(出厂 prefill 849 钉子不受影响)。"""
    task_workdir(r"E:\整理")
    A.system_prompt()
    assert "当前工作目录" not in A.SYSTEM
    assert "当前工作目录" not in A._CHILD_SYSTEM


def test_main_and_chat_wiring_pins():
    assert "_TASK_WORKDIR = os.path.abspath(workdir)" in SRC_OA      # main() 装填
    assert 'CHAT_SYSTEM + (f"\\n当前工作目录:{_TASK_WORKDIR}"' in SRC_OA  # 问答分支


# ---------------- 会话绑定工作目录 ----------------

def test_save_session_records_workdir(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    A.save_session("s_wd", [{"role": "user", "content": "整理文件"},
                            {"role": "assistant", "content": "TASK_COMPLETE"}],
                   workdir=str(tmp_path / "ws"))
    meta = json.load(open(tmp_path / "s_wd.meta.json", encoding="utf-8"))
    assert meta["workdir"].endswith("ws")


def test_save_session_without_workdir_keeps_old_field(tmp_path, monkeypatch):
    """无 workdir 的保存不写该字段;已有旧值不覆盖(合并写语义)。"""
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    (tmp_path / "s_old.meta.json").write_text(
        json.dumps({"workdir": r"E:\旧对话", "title": "x"}), encoding="utf-8")
    A.save_session("s_old", [{"role": "user", "content": "hi"}], workdir=None)
    meta = json.load(open(tmp_path / "s_old.meta.json", encoding="utf-8"))
    assert meta["workdir"] == r"E:\旧对话"
    assert meta["title"] == "x"


def test_gui_restore_and_reset_pins():
    # 载入历史会话:meta.workdir 存在且是目录 → 恢复到 wd_var
    assert '_swd = str(_mt.get("workdir", "") or "")' in SRC_GUI
    assert "self.wd_var.set(_swd)" in SRC_GUI
    # 新对话仍重置回默认目录(用户定案:新开的就该重置)——重置行只此一处
    assert SRC_GUI.count("self.wd_var.set(os.path.join(DEFAULT_TASKS") == 1
    # 不做 GUI 级持久化(工作目录属于会话,不属于 GUI 偏好)
    assert 'self.prefs["workdir"]' not in SRC_GUI
