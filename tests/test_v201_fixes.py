# -*- coding: utf-8 -*-
"""v2.0.1 四项修复的单元测试(2026-10-07 试用反馈):
①spawn 位点全量 CREATE_NO_WINDOW——GUI console=False 打包下,任何裸 spawn 的
  控制台程序都会闪一个终端框再消失(实测"一次闪几十个"),源级扫描钉死回归。
②会话标题:起名小调用/清洗/meta 合并写/标题不丢。
③思考块按块存档与独立展开折叠(旧版全局单变量导致收尾后点击失灵/展开错块)。
④计划面板纵向扩展 + 滚轮路由(源锚点)。
不联网、不调 ollama;③用隐藏 Tk,无显示环境自动跳过。
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_OA = open(os.path.join(_HERE, "ollama_agent.py"), encoding="utf-8").read()
SRC_GUI = open(os.path.join(_HERE, "agent_gui.py"), encoding="utf-8").read()


@pytest.fixture
def oa():
    return A


# ================= ① 灭闪框:spawn 位点全量隐藏 =================

def _spawn_statements(src):
    """提取每个 subprocess.run(/Popen( 的完整调用语句(括号配平到闭合)。"""
    out = []
    for m in re.finditer(r"subprocess\.(run|Popen)\(", src):
        j = m.end(); depth = 1
        while j < len(src) and depth:
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
            j += 1
        out.append(src[m.start():j])
    return out


# 白名单:文件管理器/文档打开器(explorer/open/xdg-open/notepad 是 GUI 程序,
# 本就无控制台;直接调用与经 _file_manager_cmd/_open_doc_cmd 封装两种写法都放行)、
# POSIX 专属 pkill、agent 子进程本身(bufsize=1 管道读流那条;窗口化 exe 继承
# 父进程,均不新开终端框)。
_SPAWN_WHITELIST = ("explorer", '"open"', "xdg-open", "pkill", "sys.executable, AGENT_PY",
                    "_file_manager_cmd", "_open_doc_cmd", "bufsize=1")


def test_all_console_spawns_hidden():
    bad = []
    for st in _spawn_statements(SRC_OA) + _spawn_statements(SRC_GUI):
        if any(k in st for k in _SPAWN_WHITELIST):
            continue
        if "creationflags" not in st:
            bad.append(st.splitlines()[0].strip())
    assert not bad, "存在会闪终端框的 spawn(缺 creationflags): " + " | ".join(bad)


def test_nowin_constant_pinned():
    assert 'NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)' in SRC_OA


# ================= ② 会话标题 =================

def test_sanitize_title(oa):
    assert oa.sanitize_title("《材料调研》") == "材料调研"
    assert oa.sanitize_title("  标题：修复登录bug \n第二行不要") == "修复登录bug"
    assert oa.sanitize_title('"写周报"') == "写周报"
    assert len(oa.sanitize_title("长" * 40)) == 16
    assert oa.sanitize_title("") == ""
    assert oa.sanitize_title(None) == ""


def test_gen_session_title_roundtrip(oa, monkeypatch):
    captured = {}

    class FakeResp:
        def read(self):
            return json.dumps({"message": {"content": "《材料调研》"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return FakeResp()

    monkeypatch.setattr(oa.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("AGENT_LANG", "zh")
    t = oa.gen_session_title("m", "整理实验数据并生成图表周报")
    assert t == "材料调研"
    p = captured["payload"]
    assert p["options"]["num_predict"] == 48     # 旁路小调用,预算钉死
    assert p["keep_alive"] == oa.KEEP_ALIVE      # 不把模型踢回 5 分钟卸载
    assert p["stream"] is False
    assert p["messages"][0]["role"] == "user"


def test_gen_session_title_failure_silent(oa, monkeypatch):
    def boom(req, timeout=None):
        raise OSError("ollama down")

    monkeypatch.setattr(oa.urllib.request, "urlopen", boom)
    assert oa.gen_session_title("m", "任何任务") == ""


def test_save_session_preserves_title(oa, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "SESSIONS_DIR", str(tmp_path))
    oa.SESSION_TITLE["v"] = "示例标题"
    try:
        msgs = [{"role": "user", "content": "做点事"},
                {"role": "assistant", "content": "done",
                 "tool_calls": [{"function": {"name": "finish", "arguments": {}}}]}]
        oa.save_session("s1", msgs, workdir=str(tmp_path))
        m = json.load(open(tmp_path / "s1.meta.json", encoding="utf-8"))
        assert m["title"] == "示例标题" and m["status"] == "done"
        # 换一个没起过标题的进程再存:合并写不许清掉已有标题
        oa.SESSION_TITLE["v"] = ""
        oa.save_session("s1", msgs, workdir=str(tmp_path))
        m2 = json.load(open(tmp_path / "s1.meta.json", encoding="utf-8"))
        assert m2.get("title") == "示例标题"
        # merge 辅助:改状态不动标题
        oa._merge_session_meta("s1", {"status": "interrupted"})
        m3 = json.load(open(tmp_path / "s1.meta.json", encoding="utf-8"))
        assert m3["status"] == "interrupted" and m3["title"] == "示例标题"
    finally:
        oa.SESSION_TITLE["v"] = ""


def test_title_protocol_pinned():
    # agent 侧发协议行(GUI 模式),GUI 侧接收并换会话栏/列表显示(标题前缀)
    assert '@@TITLE@@' in SRC_OA and '"@@TITLE@@"' in SRC_GUI
    assert "session_title" in SRC_GUI
    assert 'disp = f"{title}·{name} {tag}"' in SRC_GUI


# ================= ③ 思考块按块存档 =================

def test_think_blocks_independent_toggle():
    tk = pytest.importorskip("tkinter")
    import agent_gui as G
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("无显示环境,跳过 Tk 界面测试")
    root.withdraw()
    try:
        class D(G.AgentGUI):
            def __init__(self):
                pass   # 绕开完整 GUI 构建,只挂方法链所需的最小属性
        d = D()
        d.transcript = tk.Text(root)
        d._think_store = {}; d._think_seq = 0
        d._think_text = ""; d._think_live = False; d._think_hdr = False
        d._think_shown = 0; d._asst_buf = ""; d._asst_shown = 0
        d._streaming_asst = False; d._selecting = False
        d._flush_stream_pending = lambda: None
        d._scroll_transcript = lambda: None

        def _live(text):
            d._think_text = text; d._think_live = True; d._think_hdr = True
            d.transcript.config(state="normal")
            d.transcript.insert("end", "思考中…\n", ("think_region", "think_live"))
            d.transcript.config(state="disabled")

        # 两块先后流式 → 折叠
        _live("第一块思考" * 5); d._collapse_think(); uid1 = f"thinkmk{d._think_seq}"
        _live("第二块思考" * 5); d._collapse_think(); uid2 = f"thinkmk{d._think_seq}"
        assert uid1 != uid2
        body = d.transcript.get("1.0", "end")
        assert "第一块思考" not in body and "第二块思考" not in body   # 都在折叠态

        # 展开块一:必须是块一自己的内容(旧版 bug:展开的是全局最后一块)
        d._toggle_think(uid1)
        body = d.transcript.get("1.0", "end")
        assert "第一块思考" in body and "第二块思考" not in body

        # 收回块一,展开块二:互不干扰;新任务清空 _think_text 后旧标记仍可点开
        d._toggle_think(uid1)
        d._think_text = ""   # 模拟任务结束/新对话(旧版此时点击直接 return,没反应)
        d._toggle_think(uid2)
        body = d.transcript.get("1.0", "end")
        assert "第二块思考" in body and "第一块思考" not in body

        # 空思考块不留"0 字"标记
        seq = d._think_seq
        _live(""); d._collapse_think()
        assert d._think_seq == seq
    finally:
        try:
            root.destroy()
        except Exception:
            pass


# ================= ④ 计划面板滚动 =================

def test_plan_panel_scroll_pinned():
    assert 'pf.pack(fill="both", expand=True)' in SRC_GUI
    assert "_route_wheel" in SRC_GUI and "plan_txt.yview_scroll" in SRC_GUI
