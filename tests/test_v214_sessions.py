# -*- coding: utf-8 -*-
"""v2.1.4 会话系统修复的单元测试(用户实报:载入旧对话续聊→上下文爆炸且不触发
压缩,历史取回不完整)。四条根因与对应修复:
①CJK 估算低估(1字=1token,实际1.5~2)→超限请求被放行→首调500→错误路径只
  重试不压缩→重试到死。修复:估算校准为 cjk*2+other/3(宁可高估=提前压缩)。
②上下文超限类错误现在强制 L3 后重试,不再退避空转。
③压缩级别只升不降(_compact_lvl 梯)→上下文回落后二次增长永远不再压缩。
  修复:pt<60% 时重新武装。
④压缩就地改写 messages 且改写后被存盘→用户取回的历史是截断/摘要残缺版。
  修复:transcript.jsonl 完整转录层(消息发生时追加,压缩只作用于模型上下文),
  GUI 从转录渲染;运行中禁止切换会话(防串档)。不联网。"""
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
def tl_state():
    """转录层全局状态隔离:每测复位,测后清空。"""
    A._TL_NEXT, A._TL_SESSION, A._TL_COMPACTED = 0, None, False
    yield
    A._TL_NEXT, A._TL_SESSION, A._TL_COMPACTED = 0, None, False


# ---------------- ① 估算校准 ----------------

def test_estimate_tokens_cjk_calibrated():
    # 10 个汉字:旧口径 10,新口径 21(2/字 + 1)——低估是续跑爆炸的第一环
    assert A._estimate_tokens("一二三四五六七八九十") == 21
    # 纯 ASCII ~3 字符/token
    assert A._estimate_tokens("abcdefghij") == int(10 / 3) + 1
    # 中文占比越高,估算越保守(旧口径差距越大)
    assert A._estimate_tokens("中文内容很长" * 10) >= 120


# ---------------- ②③④ 源码钉子 ----------------

def test_context_overflow_error_forces_compaction_pin():
    assert "prompt is too long" in SRC_OA            # 错误文本识别集
    assert "强制 L3 压缩后重试" in SRC_OA
    assert "_compact_lvl = 0   # v2.1.4:上下文回落→级别重新武装" in SRC_OA


def test_transcript_wiring_pins():
    assert "_transcript_flush(session, messages)   # v2.1.4" in SRC_OA  # 循环顶实时落盘
    assert SRC_OA.count("_tl_mark_compacted()") == 5  # 4 个调用点(压缩L2/L3+两处硬复位)+定义行
    # GUI:转录优先渲染 + 运行中切换防护
    assert "transcript.jsonl" in SRC_GUI
    assert "任务运行中暂不能切换会话" in SRC_GUI


# ---------------- ④ 转录层行为 ----------------

def test_transcript_fresh_append_and_incremental(tl_state, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    msgs = [{"role": "system", "content": "S"},
            {"role": "user", "content": "任务"}]
    A._transcript_flush("s1", msgs)                 # 新会话:从零建账
    p = tmp_path / "s1.transcript.jsonl"
    assert len(p.read_text(encoding="utf-8").splitlines()) == 2
    msgs.append({"role": "assistant", "content": "答"})
    A._transcript_flush("s1", msgs)                 # 增长:只追加新消息
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and json.loads(lines[2])["content"] == "答"


def test_transcript_compact_shrink_writes_summary(tl_state, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    msgs = [{"role": "system", "content": "S"},
            {"role": "user", "content": "旧1"},
            {"role": "assistant", "content": "旧2"},
            {"role": "user", "content": "近1"}]
    A._transcript_flush("s2", msgs)
    p = tmp_path / "s2.transcript.jsonl"
    assert len(p.read_text(encoding="utf-8").splitlines()) == 4
    # 压缩:[S, 摘要, 近1](带旗标的缩短)→ 摘要补写一行,旧消息不丢
    compacted = [msgs[0], {"role": "user", "content": "[先前上下文摘要] xx"}, msgs[3]]
    A._tl_mark_compacted()
    A._transcript_flush("s2", compacted)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5 and "摘要" in lines[4]


def test_transcript_dedupe_shrink_aligns_silently(tl_state, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    msgs = [{"role": "system", "content": "S"},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "留"}]
    A._transcript_flush("s3", msgs)
    p = tmp_path / "s3.transcript.jsonl"
    before = p.read_text(encoding="utf-8")
    A._transcript_flush("s3", msgs[:1] + msgs[2:])   # 无旗标缩短(dedupe):静默对齐
    assert p.read_text(encoding="utf-8") == before   # 不写任何新行


def test_transcript_session_switch_rebaselines(tl_state, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    # 续跑:转录文件已存在 → 载入的消息(哪怕是被压缩过的)视为已在转录中
    msgs = [{"role": "system", "content": "S"},
            {"role": "user", "content": "任务"},
            {"role": "assistant", "content": "答"}]
    A._transcript_flush("s4", msgs)
    A._transcript_flush("s4", msgs)                  # 同会话再 flush:幂等
    p = tmp_path / "s4.transcript.jsonl"
    assert len(p.read_text(encoding="utf-8").splitlines()) == 3
    # 换到另一会话再回来(模拟新进程续跑):已载入消息不重复写
    A._transcript_flush("other", [{"role": "system", "content": "S"}])
    A._transcript_flush("s4", msgs)
    assert len(p.read_text(encoding="utf-8").splitlines()) == 3


def test_save_session_flushes_transcript(tl_state, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "SESSIONS_DIR", str(tmp_path))
    A.save_session("s5", [{"role": "system", "content": "S"},
                          {"role": "user", "content": "hi"}], workdir=None)
    assert (tmp_path / "s5.transcript.jsonl").exists()
    assert (tmp_path / "s5.json").exists()


def test_compact_history_marks_flag(monkeypatch, tl_state):
    monkeypatch.setattr(A, "call_chat",
                        lambda *a, **k: {"message": {"content": "摘要内容"}})
    msgs = [{"role": "system", "content": "S"}] + \
           [{"role": "user", "content": f"u{i}"} for i in range(5)]
    out = A.compact_history("m", msgs, level=3)
    assert len(out) < len(msgs)
    assert A._TL_COMPACTED is True
