# -*- coding: utf-8 -*-
"""v3.0.0 输入快捷键(与主流对齐):Enter=发送,Shift+Enter=换行;Ctrl+Enter 保留为
发送别名。桌面(Tk)与 Web 两端同标准;Web 端必须带 IME 组合保护(isComposing),
中文输入法回车确认候选词不得误发。"""

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()
SRC_WEB = open(os.path.join(_HERE, "webui", "static", "index.html"), encoding="utf-8").read()
SRC_AGENTS = open(os.path.join(_HERE, "AGENTS.md"), encoding="utf-8").read()


# ================= ① 桌面端 =================

def test_desktop_enter_send_shift_enter_newline():
    """输入框绑定 <Return> 到 _on_enter_key;Shift 位走默认换行,发送路径 break。"""
    assert 'self.input.bind("<Return>", self._on_enter_key)' in SRC_GUI
    assert "def _on_enter_key(self, e):" in SRC_GUI
    assert "if e.state & 0x0001:" in SRC_GUI          # Shift 位检测
    assert 'return "break"' in SRC_GUI.split("def _on_enter_key")[1].split("def ")[0]


def test_desktop_ctrl_enter_kept_as_send_alias():
    assert 'self.input.bind("<Control-Return>", lambda e: (self.send_chat(), "break")[1])' in SRC_GUI


def test_desktop_hint_texts_updated():
    assert "输入任务或对话…(Enter 发送 · Shift+Enter 换行)" in SRC_GUI
    assert "Ctrl+Enter 发送" not in SRC_GUI           # 旧提示不得残留


# ================= ② Web 端 =================

def test_web_enter_send_with_ime_guard():
    """Enter 发送须排除 Shift 与 IME 组合(isComposing),Shift+Enter 走默认换行。"""
    seg = SRC_WEB.split('addEventListener("keydown"')[1][:300]
    assert "shiftKey" in seg and "isComposing" in seg
    assert "e.preventDefault(); send();" in seg


def test_web_no_stale_ctrl_enter():
    assert "Ctrl+Enter" not in SRC_WEB


# ================= ③ 文档口径 =================

def test_agents_md_shortcut_line():
    assert "`Enter` 发送 · `Shift+Enter` 换行" in SRC_AGENTS
