# -*- coding: utf-8 -*-
"""v3.1.4 六连修回归钉(修"类"不修"例",全部源自一次真实会话的事后解剖):
1. 转录游标=文件实际行数(--append 的追问不再被吞进基线消失);
2. 假完成门:qa 豁免 + 实质性 summary 算交付;
3. 六道 finish 门拒绝/暂缓时回填中性结果,绝不携带 [TASK_COMPLETE];
4. 交付自查回注的"原文"=最近一条真实用户输入,不是会话第一条;
5. "工具不存在"与"反循环禁用"话术分离;
6. MAX ITERATIONS 只在 200 轮真耗尽时打印(for-else)。"""
import importlib.util
import json
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

SRC_OA = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
              encoding="utf-8").read()


@pytest.fixture
def tl_reset(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    monkeypatch.setattr(A, "_TL_SESSION", None)
    monkeypatch.setattr(A, "_TL_NEXT", 0)
    monkeypatch.setattr(A, "_TL_COMPACTED", False)


# ---- 1. 转录:续跑追加的消息必须落盘 ----

def test_transcript_resume_keeps_appended_user_msg(tl_reset, tmp_path):
    run1 = [{"role": "system", "content": "S"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀"}]
    A._transcript_flush("s", run1)
    p = tmp_path / "s.transcript.jsonl"
    assert sum(1 for _ in open(p, encoding="utf-8")) == 3

    # 模拟第二个进程:load_session(3条) + --append 追加的新用户消息(主循环前拼入)
    A._TL_SESSION, A._TL_NEXT = None, 0
    run2 = run1 + [{"role": "user", "content": "你有哪些能力"}]
    A._transcript_flush("s", run2)
    lines = [json.loads(l) for l in open(p, encoding="utf-8")]
    assert len(lines) == 4                      # 旧代码:游标=len(run2)=4 → 追加消息被吞
    assert lines[3]["content"] == "你有哪些能力"

    run2.append({"role": "assistant", "content": "我能帮你…"})
    A._transcript_flush("s", run2)
    assert sum(1 for _ in open(p, encoding="utf-8")) == 5


def test_transcript_keeps_longer_history_on_compacted_resume(tl_reset, tmp_path):
    """压缩后续跑:转录(50 行)> 上下文(8 条)——完整历史必须保住,新消息续写尾部。"""
    p = tmp_path / "c.transcript.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for i in range(50):
            f.write(json.dumps({"role": "user", "content": f"m{i}"}) + "\n")
    A._TL_SESSION, A._TL_NEXT = None, 0
    compacted = [{"role": "system", "content": "S"},
                 {"role": "user", "content": "[先前上下文摘要] …"}]
    A._transcript_flush("c", compacted)          # 首帧:短于文件 → 静默对齐,不删行
    compacted.append({"role": "assistant", "content": "新回答"})
    A._transcript_flush("c", compacted)
    lines = [json.loads(l) for l in open(p, encoding="utf-8")]
    assert len(lines) == 51                       # 50 行历史 + 1 条新回答
    assert lines[-1]["content"] == "新回答"


# ---- 2/3. 门禁:qa 豁免 + summary 算交付 + 拒绝回填中性 ----

def _fin(summary="", content="", name="finish"):
    return {"message": {"content": content, "tool_calls": [
        {"id": "c1", "function": {"name": name, "arguments": {"summary": summary}}}]}}


def _run_loop(monkeypatch, tmp_path, script, user_text, system="S"):
    turns = list(script)
    def fake_chat(model, messages, ctx=None, tools=None, **k):
        return turns.pop(0) if turns else _fin(summary="兜底收尾")
    monkeypatch.setattr(A, "call_chat", fake_chat)
    return A.agent_loop("m", [{"role": "system", "content": system},
                              {"role": "user", "content": user_text}],
                        str(tmp_path), None)


def test_fake_finish_gate_accepts_substantive_summary(monkeypatch, tmp_path, capsys):
    """空正文但有实质性 summary 的 finish 不是假完成(讲解型交付)。"""
    out = _run_loop(monkeypatch, tmp_path,
                    [_fin(summary="已介绍全部 40 项技能:学术写作/文献检索/数据分析等"),
                     _fin(summary="自查通过,再次 finish")],
                    "把下面这段清单提炼成能力介绍")
    joined = json.dumps(out, ensure_ascii=False)
    assert "你还没有做任何实际工作" not in joined      # 第一次 finish 不再被拒
    assert "===== TASK COMPLETE =====" in capsys.readouterr().out


def test_fake_finish_rejection_result_is_neutral(monkeypatch, tmp_path):
    """真被拒(空正文+空 summary):回填必须是中性文本,不得带 [TASK_COMPLETE]。"""
    out = _run_loop(monkeypatch, tmp_path,
                    [_fin(summary=""),                       # 空交付 → 拒
                     _fin(summary="这次真的总结了完整内容,交付实质摘要")],
                    "把下面这段清单整理成文件")
    tool_msgs = [str(m.get("content", "")) for m in out if m.get("role") == "tool"]
    rej = [t for t in tool_msgs if "finish 被拒绝" in t]
    assert rej and all("[TASK_COMPLETE]" not in t for t in rej)


def test_qa_finish_never_hits_productivity_gate(monkeypatch, tmp_path, capsys):
    out = _run_loop(monkeypatch, tmp_path,
                    [_fin(summary="你好,有什么可以帮你")],
                    "你好")
    assert "你还没有做任何实际工作" not in json.dumps(out, ensure_ascii=False)
    cap = capsys.readouterr().out
    assert "===== TASK COMPLETE =====" in cap
    assert "拒绝假 finish" not in cap
    assert "MAX ITERATIONS" not in cap            # 问答收尾≠耗尽


# ---- 4. 交付自查:原文=最近一条真实输入 ----

def test_task_original_text_is_last_real_input():
    msgs = [{"role": "system", "content": "S"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀"},
            {"role": "user", "content": "回答已经足够,用户是在问答。立即调用 finish 结束本轮,不要重复输出。"},
            {"role": "tool", "content": "[TASK_COMPLETE] 已回答"},
            {"role": "user", "content": "已装技能 · 40\nREADME\nacademic_cv_builder…"},
            {"role": "assistant", "content": ""}]
    orig = A._task_original_text(msgs)
    assert orig.startswith("已装技能")            # 旧代码返回 "你好" —— 题面被丢
    assert "回答已经足够" not in orig              # harness 注入消息被跳过


def test_selfcheck_rereads_last_instruction(monkeypatch, tmp_path):
    """自查门回注的原文=最近一条指令,且暂缓回填为中性文本。"""
    out = _run_loop(monkeypatch, tmp_path,
                    [_fin(summary="已按要求完成"),
                     _fin(summary="自查通过:交付满足全部要求")],
                    "把清单整理成报告并写明单位")
    sc = [str(m.get("content", "")) for m in out if "原始任务指令" in str(m.get("content", ""))]
    assert sc and "把清单整理成报告" in sc[0]      # 回注的是本次指令,不是别的
    tool_msgs = [str(m.get("content", "")) for m in out if m.get("role") == "tool"]
    assert any("finish 待自查" in t for t in tool_msgs)
    assert all(not ("finish 待自查" in t and "[TASK_COMPLETE]" in t) for t in tool_msgs)


# ---- 5. 未知工具话术 ----

def test_unknown_tool_says_not_exists_not_disabled(monkeypatch, tmp_path):
    out = _run_loop(monkeypatch, tmp_path,
                    [{"message": {"content": "", "tool_calls": [
                        {"id": "c1", "function": {"name": "create_xlsx",
                                                  "arguments": {"path": "x.xlsx"}}}]}},
                     _fin(summary="已介绍能力清单,交付完毕")],
                    "把下面这段清单提炼成能力介绍")
    tool_msgs = [str(m.get("content", "")) for m in out if m.get("role") == "tool"]
    hit = [t for t in tool_msgs if "create_xlsx" in t]
    assert hit and "不可用" in hit[0]            # 覆盖"未装配/不存在"两种成因
    assert all("连续重复调用保护" not in t for t in hit)


# ---- 6. 源码钉 ----

def test_no_success_semantics_in_rejection_appends():
    """六道 finish 门的拒绝/暂缓回填全部中性化:门禁区不得再出现 content:res。"""
    for kw in ("你还没有做任何实际工作", "summary 点名的文件缺失", "计划点名的产物缺失",
               "计划与实际进度同步", "核对原始任务指令", "测试未全绿"):
        i = SRC_OA.find(kw)
        assert i > 0, kw
        seg = SRC_OA[i:i + 900]
        assert '"role":"tool","content":res' not in seg, f"门禁 {kw} 仍在回填 res"


def test_max_iterations_is_for_else():
    assert 'else:\n        # for-else:只有 200 轮真正耗尽才打此标签' in SRC_OA


def test_all_finish_gates_exempt_qa():
    """全部 finish 门禁必须带问答豁免:聊天会话的交付是对话本身,任何任务级
    门槛(产物/测试/计划/自查)都不该拦一句寒暄的收尾。"""
    assert "not _FG_OFF and not qa and not productive_used" in SRC_OA          # 假完成门
    assert "not qa and not _FG_OFF and finish_claim_warns < 2" in SRC_OA       # 产物核对门
    assert "not qa and not _FG_OFF and glob.glob" in SRC_OA                    # 测试门
    assert "not qa and _child_sandbox is None and not _FG_OFF and plan_gate_warns" in SRC_OA
    assert "not qa and _child_sandbox is None and 'finish_gate_text_only' not in _ABLATION" in SRC_OA
    assert "not qa and _child_sandbox is None and not finish_reread_used" in SRC_OA
