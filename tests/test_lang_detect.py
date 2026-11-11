# -*- coding: utf-8 -*-
"""回复语言检测三层(2026-11-11,用户裁决内置 fastText LID):①脚本层确定性
②问候/客套闭集表整句精确匹配 ③fastText lid.176.ftz 句子级 0.9 严进。
产出=动态注入一行指名语言(_lang_line),不进出厂 prefill 钉,用户消息零改写。

背景(写进测试防止回归):中文问答提示让英文"hello"得到中文回答(用户实机
hello/what-can-you-do 全翻车);双语平衡提示修好旗舰但对地板模型(≤2b)的裸
问候词仍无效。统计 LID 对裸词全部失明("hello" fasttext en@0.39 / lingua
it@0.33——短词信息量不足是硬底)且会误标("Guten Tag…" fasttext en@0.81),
所以裸词只能闭集表、句子级才交给 fastText,阈值 0.9 宁缺毋滥(检测不出就
什么都不注入,双语提示里的镜像行兜底)。"""
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


# ---- 层①:脚本层,文字系统与语言一一对应,确定性 ----

def test_script_tier_unique_scripts(oa):
    assert oa._detect_lang("你好") == "zh"
    assert oa._detect_lang("帮我写个周报") == "zh"          # 纯汉字短句(fasttext 曾返回空)
    assert oa._detect_lang("こんにちは、何ができる？") == "ja"   # 有假名=日语
    assert oa._detect_lang("レポートを作成して") == "ja"
    assert oa._detect_lang("안녕하세요") == "ko"
    assert oa._detect_lang("Καλημέρα") == "el"
    assert oa._detect_lang("שלום") == "he"
    assert oa._detect_lang("สวัสดี") == "th"


# ---- 层②:问候闭集表,整句精确匹配(归一化大小写/变音符/标点) ----

def test_greeting_table_exact_whole_message(oa, monkeypatch):
    # 层③关掉,只验层①②的确定性:整句命中才给码,不是整句不猜
    monkeypatch.setattr(oa, "_lid_model", lambda: None)
    assert oa._detect_lang("hello") == "en"        # 统计 LID 失明的裸词,闭集表管
    assert oa._detect_lang("Hello!") == "en"       # 标点归一
    assert oa._detect_lang("HELLO !") == "en"      # 大小写+空格归一
    assert oa._detect_lang("hi there") == "en"
    assert oa._detect_lang("bonjour") == "fr"
    assert oa._detect_lang("ça va") == "fr"        # 变音符归一(ç→c)
    assert oa._detect_lang("Guten Tag") == "de"
    assert oa._detect_lang("привет") == "ru"
    assert oa._detect_lang("hola, ¿qué tal?") is None   # 不是表内整句=不猜(交给层③/镜像行)


# ---- 层③:fastText 句子级,0.9 严进(只钉实测过的格子) ----

def test_fasttext_tier_sentence_level(oa):
    if oa._lid_model() is None:
        pytest.skip("lid.176.ftz 不在本机(源码树未下模型)——降级路径由上一层测试覆盖")
    assert oa._detect_lang("Schreibe mir einen Wochenbericht") == "de"   # 实测 1.00
    assert oa._detect_lang("Bonjour, tu fais quoi ?") == "fr"            # 实测 0.96
    assert oa._detect_lang("Напиши мне отчёт") == "ru"                   # 实测 1.00(西里尔不进脚本层)


def test_fasttext_low_confidence_stays_silent(oa, monkeypatch):
    """曾实锤的误标面必须保持不注入:"Guten Tag, was machst du?" 被判 en@0.81
    (<0.9 拒),问候表无此句(带问号非整句)→ None,镜像行兜底(德语镜像双模型
    探针全对)。宁可不注入,不注错。"""
    if oa._lid_model() is None:
        pytest.skip("lid.176.ftz 不在本机")
    assert oa._detect_lang("Guten Tag, was machst du?") is None


# ---- 降级:依赖/模型缺失时静默降级,脚本层与问候表照常工作 ----

def test_degradation_model_missing(oa, monkeypatch):
    monkeypatch.setattr(oa, "_lid_model", lambda: None)
    assert oa._detect_lang("Schreibe mir einen Wochenbericht") is None   # 不抛异常
    assert oa._detect_lang("你好") == "zh"                                # 脚本层不受影响
    assert oa._detect_lang("hello") == "en"                              # 问候表不受影响


# ---- 注入行与门 ----

def test_lang_line_injection_and_gate(oa, monkeypatch):
    assert oa._lang_line("qa", "hello") == "[回复语言] Respond in English."
    assert oa._lang_line("task", "帮我写个周报") == "[回复语言] Chat with the user in Chinese."
    assert oa._lang_line("qa", "") == ""            # 空=什么都不注
    monkeypatch.setenv("AGENT_LANG", "en")
    assert oa._lang_line("qa", "hello") == ""       # v2.0.3 显式英文契约优先


# ---- 铁律:检测绝不改写用户输入(语言钉事故的根) ----

def test_detect_never_mutates_input(oa):
    s = "Hello! 你好"
    oa._detect_lang(s)
    assert s == "Hello! 你好"
    s2 = "Écris-moi un poème"
    oa._lang_line("qa", s2)
    assert s2 == "Écris-moi un poème"
