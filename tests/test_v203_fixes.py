# -*- coding: utf-8 -*-
"""v2.0.3 修复的单元测试(外部用户 issue #3,Fedora/Podman/qwen3.5 2B-9B 实测):
①finish 门拒绝词必须带绝对工作目录(小模型把"工作区"猜成主目录/幻影 /workspace,
  三个尺寸全部原地打转) ②run_bash 就地改写(sed -i/>/cp)前置快照 .bak(补上 shell
  绕开 .bak 安全网的大洞) ③todo schema 标注 index 1-based ④AGENT_LANG=en →
  强制英文应答(中文系统提示会让 Qwen 跟风输出中文) ⑤只读分析任务正文即交付
  (假 finish 门不再拦) ⑥AGENT_APITIMEOUT 超时旋钮。不联网、不调 ollama。"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_OA = open(os.path.join(_HERE, "ollama_agent.py"), encoding="utf-8").read()


@pytest.fixture
def oa():
    return A


# ================= ① finish 门拒绝词带绝对工作目录 =================

def test_ws_note_contains_abs_workdir(oa, tmp_path):
    note = oa._ws_note(str(tmp_path))
    assert "工作目录(绝对路径)" in note
    assert str(tmp_path) in note
    assert 'create_file(path="options.md")' in note


def test_ws_note_wired_into_gates():
    # 假 finish / 产物核对 / 计划核对 三道门的拒绝词都要带上工作目录提示
    assert SRC_OA.count("_ws_note(workdir)") >= 3


# ================= ② run_bash 就地改写前置快照 =================

def test_bash_snapshot_unit(oa, tmp_path):
    (tmp_path / "notes.md").write_text("a", encoding="utf-8")
    (tmp_path / "other.txt").write_text("b", encoding="utf-8")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "x.py").write_text("c", encoding="utf-8")
    # sed -i 命中工作区既有文件
    got = oa._bash_snapshot("sed -i 's/a/b/' notes.md", str(tmp_path))
    assert got == ["notes.md"] and (tmp_path / "notes.md.bak").exists()
    # 子目录文件也要覆盖
    got2 = oa._bash_snapshot("sed -i s/c/d/ sub/x.py", str(tmp_path))
    assert got2 == ["x.py"] and (sub / "x.py.bak").exists()
    # 非改写命令不备份
    assert oa._bash_snapshot("cat notes.md", str(tmp_path)) == []
    assert oa._bash_snapshot("ls -la", str(tmp_path)) == []
    # 工作区之外的文件不碰(绝对路径指向外部)
    outside = tmp_path.parent / "mb_outside_probe.md"
    outside.write_text("x", encoding="utf-8")
    try:
        assert oa._bash_snapshot(f"sed -i s/x/y/ {outside}", str(tmp_path)) == []
        assert not os.path.exists(str(outside) + ".bak")
    finally:
        outside.unlink()


def test_run_bash_snapshot_integration(oa, tmp_path):
    (tmp_path / "data.txt").write_text("old", encoding="utf-8")
    out = oa.run_tool("run_bash", {"command": "echo new> data.txt"}, str(tmp_path))
    assert "[exit 0]" in out and "已自动备份" in out
    assert (tmp_path / "data.txt.bak").read_text(encoding="utf-8").strip("\n ") .startswith("old")
    assert "new" in (tmp_path / "data.txt").read_text(encoding="utf-8")


# ================= ③④⑤⑥ 行为与配置钉子 =================

def test_todo_schema_says_one_based(oa):
    assert "index is 1-based" in str(oa.CORE_TOOLS)


def test_lang_en_forces_english():
    r = subprocess.run([sys.executable, "-c",
                        "import ollama_agent as A;"
                        "assert 'Always respond in English' in A.SYSTEM;"
                        "assert 'Always respond in English' in A.CHAT_SYSTEM;print('EN_OK')"],
                       env={**os.environ, "AGENT_LANG": "en"},
                       capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert "EN_OK" in r.stdout, r.stderr[-400:]


def test_lang_default_untouched():
    r = subprocess.run([sys.executable, "-c",
                        "import os; os.environ.pop('AGENT_LANG', None);"
                        "import ollama_agent as A;"
                        "assert 'Always respond in English' not in A.SYSTEM;print('DEF_OK')"],
                       capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert "DEF_OK" in r.stdout, r.stderr[-400:]


def test_api_timeout_env_knob():
    r = subprocess.run([sys.executable, "-c",
                        "import ollama_agent as A;"
                        "assert A.API_TIMEOUT_OPEN == 300, A.API_TIMEOUT_OPEN;print('T_OK')"],
                       env={**os.environ, "AGENT_APITIMEOUT": "300"},
                       capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert "T_OK" in r.stdout, r.stderr[-400:]


def test_readonly_finish_passes_fake_gate_condition():
    # 正文非空的 finish 不再被"假完成"门拦:分析/讲解类任务的交付就是正文
    assert "not productive_used and _semantically_empty(content)" in SRC_OA
    assert "分析/讲解类任务" in SRC_OA


# ================= ⑦ 输出上限:16k/32k/不限(v2.0.4) =================

def test_output_limit_unlimited_local_payload(oa, monkeypatch):
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps({"message": {"content": "ok"},
                               "prompt_eval_count": 1}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(oa.appconfig, "cloud_provider", lambda: None)
    monkeypatch.setattr(oa, "NUM_PREDICT", -1)
    monkeypatch.setattr(oa.urllib.request, "urlopen", fake_urlopen)
    oa.call_chat("m", [{"role": "user", "content": "hi"}])
    assert captured["payload"]["options"]["num_predict"] == -1   # ollama:无限生成


def test_output_limit_unlimited_cloud_payload_omits_max_tokens(oa, monkeypatch):
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}],
                               "usage": {}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(oa.appconfig, "cloud_provider",
                        lambda: {"base_url": "https://x/v1", "api_key": "k", "model": "m"})
    monkeypatch.setattr(oa, "NUM_PREDICT", -1)
    monkeypatch.setattr(oa.urllib.request, "urlopen", fake_urlopen)
    oa.call_chat("m", [{"role": "user", "content": "hi"}])
    # OpenAI 兼容端点无负值语义:"不限"=省略 max_tokens,用 provider 默认
    assert "max_tokens" not in captured["payload"]


def test_output_limit_settings_options_pinned():
    # 设置面板输出上限:512..32k + 不限(-1)
    assert "16384, 32768, _t(\"不限\")" in SRC_GUI
    assert 'prefs["num_predict"] = -1 if _np_raw' in SRC_GUI
