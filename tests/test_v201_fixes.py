# -*- coding: utf-8 -*-
"""v2.0.1→v2.0.2 修复的单元测试(2026-10-07 二轮试用反馈):
①spawn 位点全量 CREATE_NO_WINDOW——GUI console=False 打包下,任何裸 spawn 的
  控制台程序都会闪一个终端框再消失(实测"一次闪几十个"),源级扫描钉死回归。
②会话命名改纯程序:首句前 15 字 + 时间后缀(v2.0.1 模型起名实测不出,已下线)。
③思考块按块存档与独立展开折叠(旧版全局单变量导致收尾后点击失灵/展开错块)。
④计划面板纵向扩展 + 滚轮路由(源锚点)。
⑤finish 收尾可见性:GUI 工具行正则兼容 [i|+Ns] 格式 + 裸 finish 兜底收尾调用。
不联网、不调 ollama;思考块用隐藏 Tk,无显示环境自动跳过。
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


# ================= ② 会话命名(纯程序,v2.0.2) =================

def test_first_msg_title():
    import agent_gui as G
    assert G._first_msg_title("修复登录页面的问题") == "修复登录页面的问题"
    # 多行只取首行;文件名非法字符剔除;超 15 字截断
    assert G._first_msg_title("第一行标题\n第二行不取") == "第一行标题"
    assert G._first_msg_title("a/b\\c:d*e?f\"g<h>i|j") == "abcdefghij"
    assert len(G._first_msg_title("长" * 40)) == 15
    assert G._first_msg_title("   ") == ""
    assert G._first_msg_title(None) == ""
    assert G._first_msg_title('以句号结尾.') == "以句号结尾"


def test_programmatic_session_name_pinned():
    # 新会话名 = 首句15字_月日_时分;模型起名链路(v2.0.1)已整体下线
    assert "_first_msg_title(msg)" in SRC_GUI
    assert "gen_session_title" not in SRC_OA and "SESSION_TITLE" not in SRC_OA
    assert '"chat_"' in SRC_GUI


def test_save_session_meta_merge(oa, tmp_path, monkeypatch):
    """meta 合并写:外部(GUI/旧版)写入的字段不被整体覆盖丢失。"""
    monkeypatch.setattr(oa, "SESSIONS_DIR", str(tmp_path))
    msgs = [{"role": "user", "content": "做点事"},
            {"role": "assistant", "content": "done",
             "tool_calls": [{"function": {"name": "finish", "arguments": {}}}]}]
    oa._merge_session_meta("s1", {"title": "外部写入的标题"})
    oa.save_session("s1", msgs, workdir=str(tmp_path))
    m = json.load(open(tmp_path / "s1.meta.json", encoding="utf-8"))
    assert m["title"] == "外部写入的标题" and m["status"] == "done"
    oa._merge_session_meta("s1", {"status": "interrupted"})
    m2 = json.load(open(tmp_path / "s1.meta.json", encoding="utf-8"))
    assert m2["status"] == "interrupted" and m2["title"] == "外部写入的标题"


# ================= ⑤ finish 收尾可见性(v2.0.2) =================

def test_finish_visibility_pinned():
    # agent 打印的是 [i|+Ns] ⚙ …,GUI 旧正则 \[(\d+)\] 永远匹配不上 → 工具卡/
    # finish ✅ 卡从不渲染(用户只能翻思考过程才知道任务结束)。钉住新正则与
    # 裸 finish 兜底收尾调用。
    assert r"\[(\d+)[^\]]*\] ⚙ " in SRC_GUI
    assert r"\[(\d+)[^\]]*\] ✍ " in SRC_GUI
    assert "任务已收尾" in SRC_OA            # 裸 finish 的无工具收尾兜底
    assert "向用户总结成果" in SRC_OA        # 门禁拒绝词要求 summary 总结成果


@ pytest_skip_ci
def test_gui_feed_renders_real_agent_lines():
    """行为级:feed_transcript 吃 agent 实际打印格式([i|+Ns] ⚙ / ✍)必须渲染成
    卡片/气泡——旧正则在这些行上全部失配,finish 完成卡从不出现。"""
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
                pass
            def refresh_sessions(self):
                pass
        d = D()
        d.transcript = tk.Text(root)
        d._think_text = ""; d._think_live = False; d._think_hdr = False
        d._think_store = {}; d._think_seq = 0; d._think_shown = 0
        d._asst_buf = ""; d._asst_shown = 0; d._streaming_asst = False
        d._selecting = False
        d._flush_stream_pending = lambda: None
        d._scroll_transcript = lambda: None

        # finish 工具行(agent 真实格式) → ✅ 完成卡,且不带 [TASK_COMPLETE] 前缀
        d.feed_transcript('[7|+132s] ⚙ finish {"summary":""} -> [TASK_COMPLETE] 已生成 x.md 与结论')
        body = d.transcript.get("1.0", "end")
        assert "✅" in body and "已生成 x.md 与结论" in body
        assert "[TASK_COMPLETE]" not in body

        # 普通工具行 → ⚙ 卡
        d.feed_transcript('[8|+140s] ⚙ create_file {"path":"a.py"} -> ok')
        assert "⚙ create_file" in d.transcript.get("1.0", "end")

        # ✍ 正文行 → 助手气泡缓冲
        d.feed_transcript("[9|+150s] ✍ 任务完成:共处理 3 个文件。")
        assert d._asst_buf == "任务完成:共处理 3 个文件。"
        d._flush_asst()
        assert "任务完成:共处理 3 个文件。" in d.transcript.get("1.0", "end")
    finally:
        try:
            root.destroy()
        except Exception:
            pass


# ================= ③ 思考块按块存档 =================

# v2.0.3:以下两个测试在进程内创建真实 Tk 窗口——GitHub runner 的服务级会话上
# 原生控件不稳定(曾致 pytest 无 FAILED 行即崩);CI 显式跳过,本地与发版前全量照跑。
pytest_skip_ci = pytest.mark.skipif(os.environ.get("GITHUB_ACTIONS") == "true",
                                    reason="真实 Tk 窗口测试不在 CI runner 上跑")


@ pytest_skip_ci
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
