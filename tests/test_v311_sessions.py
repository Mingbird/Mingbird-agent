# -*- coding: utf-8 -*-
"""v3.1.1 会话管理:侧栏右键菜单(打开/归档/删除)。归档=文件移入 sessions/_archived
(列表与搜索自动隐去,可手工移回恢复);删除=确认后彻底移除。运行中的当前会话禁操作
(菜单禁用 + 方法内二道守卫)。用 object.__new__ 桩实例测真实文件操作,不依赖 Tk。"""

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()


def _stub_app(monkeypatch, tmp_path, session="s1", running=False):
    """不经过 Tk 的 AgentGUI 桩:只挂文件操作所需的属性。"""
    import agent_gui as G
    monkeypatch.setattr(G, "SESSION_DIR", str(tmp_path))
    app = object.__new__(G.AgentGUI)
    app.session = session
    app.proc = None
    if running:
        class _P:
            def poll(self):
                return None      # 任务运行中
        app.proc = _P()
    calls = []
    app.log_note = calls.append
    app.refresh_sessions = lambda: calls.append("refresh")
    app.new_chat = lambda: calls.append("newchat")
    return app, calls


def test_session_files_collects_sidecars(tmp_path, monkeypatch):
    app, _ = _stub_app(monkeypatch, tmp_path)
    (tmp_path / "s1.json").write_text("[]", encoding="utf-8")
    (tmp_path / "s1.meta.json").write_text("{}", encoding="utf-8")
    (tmp_path / "s1.todo.json").write_text("{}", encoding="utf-8")
    (tmp_path / "other.json").write_text("[]", encoding="utf-8")
    got = [os.path.basename(p) for p in app._session_files("s1")]
    assert sorted(got) == ["s1.json", "s1.meta.json", "s1.todo.json"]


def test_archive_moves_all_and_resets_current(tmp_path, monkeypatch):
    app, calls = _stub_app(monkeypatch, tmp_path, session="s1")
    for ext in (".json", ".meta.json", ".transcript.jsonl"):
        (tmp_path / ("s1" + ext)).write_text("{}", encoding="utf-8")
    app._archive_session("s1")
    arc = tmp_path / "_archived"
    assert sorted(p.name for p in arc.iterdir()) == \
        ["s1.json", "s1.meta.json", "s1.transcript.jsonl"]
    assert not (tmp_path / "s1.json").exists()      # 原位清空
    assert "newchat" in calls and "refresh" in calls  # 当前会话归档→重置+刷新


def test_archive_other_session_keeps_current(tmp_path, monkeypatch):
    app, calls = _stub_app(monkeypatch, tmp_path, session="cur")
    (tmp_path / "old.json").write_text("[]", encoding="utf-8")
    app._archive_session("old")
    assert (tmp_path / "_archived" / "old.json").exists()
    assert "newchat" not in calls                   # 非当前会话不重置


def test_archive_blocked_while_current_task_running(tmp_path, monkeypatch):
    app, calls = _stub_app(monkeypatch, tmp_path, session="s1", running=True)
    (tmp_path / "s1.json").write_text("[]", encoding="utf-8")
    app._archive_session("s1")
    assert (tmp_path / "s1.json").exists()          # 文件未动
    assert any("运行中" in str(c) for c in calls)


def test_delete_removes_all_after_confirm(tmp_path, monkeypatch):
    app, calls = _stub_app(monkeypatch, tmp_path, session="s1")
    for ext in (".json", ".meta.json"):
        (tmp_path / ("s1" + ext)).write_text("{}", encoding="utf-8")
    import tkinter.messagebox as _mb
    monkeypatch.setattr(_mb, "askyesno", lambda *a, **k: True)
    app._delete_session("s1")
    assert not (tmp_path / "s1.json").exists()
    assert not (tmp_path / "s1.meta.json").exists()
    assert "newchat" in calls


def test_delete_cancelled_keeps_files(tmp_path, monkeypatch):
    app, calls = _stub_app(monkeypatch, tmp_path, session="s1")
    (tmp_path / "s1.json").write_text("[]", encoding="utf-8")
    import tkinter.messagebox as _mb
    monkeypatch.setattr(_mb, "askyesno", lambda *a, **k: False)
    app._delete_session("s1")
    assert (tmp_path / "s1.json").exists()


# ================= 源码钉子 =================

def test_pins_context_menu_wiring():
    assert 'c.tag_bind(f"sess{idx}", "<Button-3>",' in SRC_GUI
    assert 'c.tag_bind(f"sess{idx}", "<Button-2>",' in SRC_GUI   # macOS 右键
    assert "def _session_menu(self, name, event):" in SRC_GUI
    assert "def _archive_session(self, name):" in SRC_GUI
    assert "def _delete_session(self, name):" in SRC_GUI
    assert '"_archived"' in SRC_GUI
    # 菜单三项在任务运行中且为当前会话时禁用
    assert 'state="disabled" if (busy and cur) else "normal"' in SRC_GUI
