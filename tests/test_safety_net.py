# -*- coding: utf-8 -*-
"""通用安全垫(小模型破坏性行为防护)单元测试。

锚定 2026-09-14 72 格重跑实证:
- e2b WF-10 用 create_file 把 2354B 完整手册覆盖成 368B 半截稿(91 秒自毁)→ 覆盖保护;
- 用户场景:小模型无故删文件/卸载软件/系统级破坏 → 分级防护。
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
def unattended(oa, monkeypatch):
    monkeypatch.setattr(oa, "_UNATTENDED", True)


def _create(oa, wd, path, content, **extra):
    return oa.run_tool("create_file", {"path": path, "content": content, **extra}, wd)


# ---- 1. 覆盖自毁防护 ----

def test_clobber_blocked_and_replace_escapes(oa, tmp_path):
    wd = str(tmp_path)
    big = "# 手册\n" + "正文段落,内容充足。\n" * 60          # ~1.8KB
    r1 = _create(oa, wd, "doc.md", big)
    assert "created" in r1
    stub = "## 只有第二节\n一点尾巴"                          # ~30B,疑似自毁覆盖
    r2 = _create(oa, wd, "doc.md", stub)
    assert "覆盖防护" in r2 and "replace=true" in r2
    assert len(open(os.path.join(wd, "doc.md"), encoding="utf-8").read()) == len(big)  # 原文未损
    r3 = _create(oa, wd, "doc.md", stub, replace=True)        # 显式确认后放行
    assert "created" in r3
    assert open(os.path.join(wd, "doc.md"), encoding="utf-8").read() == stub


def test_grow_and_new_file_not_blocked(oa, tmp_path):
    wd = str(tmp_path)
    assert "created" in _create(oa, wd, "new.txt", "hello world")
    assert "created" in _create(oa, wd, "new.txt", "hello world, 更长的续写" * 20)  # 变大放行
    small = "a" * 100
    _create(oa, wd, "tiny.txt", small)
    assert "created" in _create(oa, wd, "tiny.txt", "b" * 80)  # 300B 以下小文件不触发


def test_clobber_regression_wf10_shape(oa, tmp_path):
    """WF-10/e2b 实锤形状:2354B 完整手册被 368B'第2节'覆盖。"""
    wd = str(tmp_path)
    manual = "# TimeTrack CLI User Manual\n\n## 1. Introduction\n\n" + "line of manual text.\n" * 80
    _create(oa, wd, "user_manual.md", manual)
    section2 = "## 2. Real Captured Terminal Outputs\n\n```text\nsome output\n```"
    r = _create(oa, wd, "user_manual.md", section2)
    assert "覆盖防护" in r
    assert "Introduction" in open(os.path.join(wd, "user_manual.md"), encoding="utf-8").read()


# ---- 2. delete_file → 回收站 ----

def test_delete_moves_to_trash(oa, tmp_path):
    wd = str(tmp_path)
    p = os.path.join(wd, "precious.txt")
    open(p, "w", encoding="utf-8").write("重要内容")
    r = oa.run_tool("delete_file", {"path": "precious.txt"}, wd)
    assert "mingbird_trash" in r
    assert not os.path.exists(p)                                   # 原位已删
    trashed = os.listdir(os.path.join(wd, ".mingbird_trash"))
    assert len(trashed) == 1 and trashed[0].startswith("precious.txt")
    assert "重要内容" in open(os.path.join(wd, ".mingbird_trash", trashed[0]), encoding="utf-8").read()


def test_delete_missing_still_reports(oa, tmp_path):
    assert "not found" in oa.run_tool("delete_file", {"path": "ghost.txt"}, str(tmp_path))


# ---- 3. 卸载/环境变异分级 ----

def test_uninstall_denied_unattended(oa, tmp_path, unattended):
    r = oa._risk_classify("pip uninstall -y numpy", str(tmp_path))
    assert r and "无人值守" in r and "AGENT_ALLOW_ENV_MUTATION" in r


def test_uninstall_allowed_with_env_flag(oa, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "_UNATTENDED", True)
    monkeypatch.setenv("AGENT_ALLOW_ENV_MUTATION", "1")
    assert oa._risk_classify("pip uninstall -y numpy", str(tmp_path)) is None


def test_env_mutate_denied_unattended(oa, tmp_path, unattended):
    assert oa._risk_classify("setx MINGBIRD_HOME C:\\x", str(tmp_path))
    assert oa._risk_classify("schtasks /create /tn evil /sc daily evil.exe", str(tmp_path))


def test_normal_commands_pass(oa, tmp_path, unattended):
    for cmd in ("python bench.py --run", "pip install requests", "dir",
                "python -m pytest -q", "git status"):
        assert oa._risk_classify(cmd, str(tmp_path)) is None, cmd


# ---- 4. 递归删除:工作目录内放行、目录外拒绝 ----

def test_recursive_delete_inside_workdir_allowed(oa, tmp_path):
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, "sub"))
    assert oa._risk_classify("Remove-Item .\\sub -Recurse -Force", wd) is None
    assert oa._risk_classify("rd /s /q sub", wd) is None


def test_recursive_delete_outside_denied(oa, tmp_path):
    r = oa._risk_classify("Remove-Item C:\\Windows\\Temp -Recurse -Force", str(tmp_path))
    assert r and "工作目录之外" in r
    r2 = oa._risk_classify("del /s /q D:\\data", str(tmp_path))
    assert r2 and "工作目录之外" in r2


# ---- 5. ~ 路径教超 ----

def test_tilde_path_teachback(oa, tmp_path):
    r = oa.run_tool("create_file", {"path": "~/.timetrack/entries.json", "content": "[]"}, str(tmp_path))
    assert "安全垫" in r and "相对路径" in r
    assert not (tmp_path / "~").exists()                           # 没有创建字面 ~ 子目录


# ---- 7. POSIX/macOS 覆盖(2026-09-14 用户纠偏:高危命令不能只防 Windows) ----

def test_posix_recursive_delete_scoped(oa, tmp_path):
    wd = str(tmp_path)
    os.makedirs(os.path.join(wd, "sub"))
    assert oa._risk_classify("rm -r sub", wd) is None
    assert oa._risk_classify("rm --recursive sub", wd) is None
    assert oa._risk_classify("rm -f -r sub", wd) is None
    assert oa._risk_classify("find . -name x -delete", wd) is None
    r = oa._risk_classify("rm -r /home/user/other", wd)
    assert r and "工作目录之外" in r
    r2 = oa._risk_classify("find /etc -name x -delete", wd)
    assert r2 and "工作目录之外" in r2


def test_posix_uninstall_and_services_denied_unattended(oa, tmp_path, unattended):
    for cmd in ("brew uninstall python", "pacman -R python", "zypper remove python",
                "flatpak uninstall org.app", "emerge --unmerge pkg",
                "systemctl stop nginx", "systemctl disable sshd",
                "crontab -r", "launchctl remove com.evil"):
        r = oa._risk_classify(cmd, str(tmp_path))
        assert r and "无人值守" in r, cmd


def test_dd_write_to_device_is_danger(oa, tmp_path, unattended):
    # D 类在 _gate_check 层拦截;此处锚定清单包含 dd 写设备与 shred
    assert "of=/dev/" in oa._DANGER_CMD
    assert "shred " in oa._DANGER_CMD
    assert oa._risk_classify("dd if=a of=b.img", str(tmp_path)) is None  # 普通拷贝放行
