# -*- coding: utf-8 -*-
"""v2.1.5 / issue #6:PyInstaller 6 onedir 把 datas 装进 _internal(=sys._MEIPASS),
Windows 安装版 GUI 只扫 EXE 根目录的 skills → 技能列表恒为 0。
本文件锁两层:GUI 扫描目录解析(_skill_scan_dirs)与 agent 侧 _skill_bases 的冻结分支。"""

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()
SRC_OA = open(os.path.join(_HERE, "ollama_agent.py"), encoding="utf-8").read()

_DIST_INTERNAL = os.path.join(_HERE, "dist", "LocalAgent", "_internal")


# ================= ① GUI 扫描目录(#6 主修复) =================

def test_skill_dirs_source_mode_two_entries():
    """源码运行与现状一致:仓库 skills + 用户主目录 skills,恰好两项。"""
    import agent_gui as G
    assert G.SKILL_DIRS == [os.path.join(G.AGENT_DIR, "skills"),
                            os.path.join(G.AGENT_HOME, "skills")]


def test_skill_dirs_frozen_picks_meipass_first():
    """打包运行:sys._MEIPASS(_internal)排第一,根目录/主目录仍在且无重复。"""
    import agent_gui as G
    old = getattr(sys, "_MEIPASS", None)
    sys._MEIPASS = _DIST_INTERNAL
    try:
        dirs = G._skill_scan_dirs()
        assert dirs[0] == os.path.join(_DIST_INTERNAL, "skills")
        assert os.path.join(G.AGENT_DIR, "skills") in dirs
        assert os.path.join(G.AGENT_HOME, "skills") in dirs
        assert len(dirs) == len(set(dirs))
    finally:
        if old is None:
            del sys._MEIPASS
        else:
            sys._MEIPASS = old


def test_skill_scan_finds_bundled_skills_if_built():
    """本机有 PyInstaller 产物时,模拟安装版扫描应能列出内置技能(#6 的复现场景)。"""
    dist_skills = os.path.join(_DIST_INTERNAL, "skills")
    if not os.path.isdir(dist_skills):
        import pytest
        pytest.skip("no local PyInstaller build (dist/LocalAgent/_internal/skills)")
    import agent_gui as G
    old = getattr(sys, "_MEIPASS", None)
    sys._MEIPASS = _DIST_INTERNAL
    try:
        names = set()
        for base in G._skill_scan_dirs():
            if os.path.isdir(base):
                for f in os.listdir(base):
                    if f.endswith((".md", ".txt", ".py")):
                        names.add(f.rsplit(".", 1)[0])
        assert "python_best_practices" in names   # 报告者点名的内置技能
    finally:
        if old is None:
            del sys._MEIPASS
        else:
            sys._MEIPASS = old


# ================= ② Agent 侧技能目录(与 GUI 对齐) =================

def test_skill_bases_source_mode_unchanged():
    import ollama_agent as A
    wd = os.path.join(_HERE, "tasks", "_t215")
    assert A._skill_bases(wd) == [os.path.join(wd, "skills"), A.SKILLS_DIR_HOME,
                                  os.path.join(os.path.dirname(os.path.abspath(A.__file__)), "skills")]


def test_skill_bases_frozen_adds_exe_dir():
    """打包运行:EXE 旁的 skills 也可加载,优先级在主目录之后、内置之前。"""
    import ollama_agent as A
    old_f = getattr(sys, "frozen", None)
    old_ex = sys.executable
    sys.frozen = True
    sys.executable = os.path.join(_HERE, "dist", "LocalAgent", "LocalAgent.exe")
    try:
        bases = A._skill_bases(os.path.join(_HERE, "tasks", "_t215"))
        exe_skills = os.path.join(os.path.dirname(sys.executable), "skills")
        assert bases[2] == exe_skills
        assert len(bases) == 4 and len(set(bases)) == 4
    finally:
        if old_f is None:
            del sys.frozen
        else:
            sys.frozen = old_f
        sys.executable = old_ex


# ================= ③ 源码钉子 =================

def test_pin_gui_skill_scan_dirs_wiring():
    assert "SKILL_DIRS = _skill_scan_dirs()" in SRC_GUI
    assert 'if getattr(sys, "_MEIPASS", ""):' in SRC_GUI


def test_pin_agent_frozen_branch_in_skill_bases():
    seg = SRC_OA.split("def _skill_bases")[1].split("def find_skill")[0]
    assert 'getattr(sys, "frozen", False)' in seg
    assert 'os.path.dirname(sys.executable)' in seg
