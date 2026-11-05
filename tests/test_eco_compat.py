# -*- coding: utf-8 -*-
"""v3.1.6 生态兼容(一):
1. AGENTS.md/CLAUDE.md 项目指令注入(预算 3000 字符,截尾保后;无文件不注入);
2. SKILL.md 标准技能文件夹(agentskills.io):发现进列表(渐进披露第一段,
   只露 name+description)/按目录名与 frontmatter name 查找/加载剥 frontmatter;
   旧扁平格式行为完全不变。"""
import importlib.util
import os
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "ollama_agent", os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"))
sys.argv = ["test"]
_mod = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
except SystemExit:
    pass
A = _mod


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(A, "_TASK_WORKDIR", None)
    monkeypatch.setattr(A, "_child_sandbox", None)
    yield


# ---------------- AGENTS.md / CLAUDE.md ----------------

def test_agents_md_injected(tmp_path, monkeypatch, capsys):
    (tmp_path / "AGENTS.md").write_text("统一用 4 空格缩进。", encoding="utf-8")
    monkeypatch.setattr(A, "_TASK_WORKDIR", str(tmp_path))
    sp = A.system_prompt()
    assert "统一用 4 空格缩进。" in sp
    assert "AGENTS.md" in sp
    assert "已注入项目指令" in capsys.readouterr().out


def test_claude_md_fallback_only_when_no_agents(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("用 ruff 格式化。", encoding="utf-8")
    monkeypatch.setattr(A, "_TASK_WORKDIR", str(tmp_path))
    assert "用 ruff 格式化。" in A.system_prompt()
    (tmp_path / "AGENTS.md").write_text("AGENTS 优先。", encoding="utf-8")
    sp = A.system_prompt()
    assert "AGENTS 优先。" in sp and "用 ruff 格式化。" not in sp


def test_agents_md_truncated_tail_kept(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("A" * 4000 + "\nTAIL_RULE_KEEP\n", encoding="utf-8")
    monkeypatch.setattr(A, "_TASK_WORKDIR", str(tmp_path))
    sp = A.system_prompt()
    assert "TAIL_RULE_KEEP" in sp          # 截尾保后:后面的硬规则保留
    assert "A" * 4000 not in sp
    assert "前文已截断" in sp


def test_no_project_file_no_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_TASK_WORKDIR", str(tmp_path))
    assert "项目指令" not in A.system_prompt()


# ---------------- SKILL.md 标准文件夹 ----------------

def _mk(base, rel, content):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_skill_folder_discovered_and_listed(tmp_path):
    sk = tmp_path / "skills"
    sk.mkdir()
    _mk(sk, "pdf-report/SKILL.md",
        "---\nname: pdf-report\ndescription: 生成 PDF 报告\n---\n\n正文:先跑 pandoc。")
    _mk(sk, "legacy.md", "---\ndescription: 旧格式技能\n---\n\n旧正文。")
    listing = A.list_skills(str(tmp_path))
    assert "pdf-report" in listing and "生成 PDF 报告" in listing   # 只露 name+desc
    assert "先跑 pandoc" not in listing                              # 正文不进列表
    assert "legacy" in listing


def test_load_skill_folder_strips_frontmatter(tmp_path):
    sk = tmp_path / "skills"
    sk.mkdir()
    _mk(sk, "pdf/SKILL.md", "---\nname: pdf\ndescription: d\n---\n\nSTEP1 run pandoc")
    out = A.load_skill("pdf", str(tmp_path))
    assert "STEP1 run pandoc" in out
    assert "name: pdf" not in out          # frontmatter 是元数据,不进正文
    assert out.startswith("### SKILL: pdf")


def test_find_skill_by_frontmatter_name_mismatch_dir(tmp_path):
    sk = tmp_path / "skills"
    sk.mkdir()
    _mk(sk, "weirddir/SKILL.md", "---\nname: nice-name\ndescription: d\n---\nbody")
    assert A.find_skill("nice-name", str(tmp_path)).endswith("SKILL.md")
    assert "body" in A.load_skill("nice-name", str(tmp_path))


def test_flat_skills_unchanged(tmp_path):
    sk = tmp_path / "skills"
    sk.mkdir()
    _mk(sk, "legacy.md", "---\ndescription: 旧\n---\n旧正文全文")
    out = A.load_skill("legacy", str(tmp_path))
    assert "旧正文全文" in out
    assert "description" in out            # 旧格式不剥 frontmatter,行为不变
