# -*- coding: utf-8 -*-
"""工具可得性校准(v3.1.7):执行校验的唯一事实源 = 本轮真正下发给模型的工具表。

回归靶心(用户实机 + 源码双向实锤):
1. 假阴性——问答模式 _chat_tool_defs() 下发 read_file/list_dir/web_search/web_fetch,
   但校验比对 _active_tools(初始=CORE_TOOLS,不含 web_search/web_fetch)
   → 模型看得到、调用被判"当前不可用",搜索/抓网页永远发不出去;
2. 假阳性——离线模式把它们剔出下发列表,但 tools_for_categories 先把名字 append
   进 _active_tools 再过滤 → 校验放行 → 断网模式下真的发请求(零出站破功);
3. 同轮 enable_tools 解锁后立刻使用必须仍然可用(不能把这条正常路径卡死)。
"""
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


def _tool_msg_text(msgs):
    return " ".join(str(m.get("content", "")) for m in msgs if m.get("role") == "tool")


def _loop(tmp_path, calls, task, finish_content="done", finish_summary="all done"):
    """脚本化 agent_loop。calls=[(name, args, result)];enable_tools 走真实实现。"""
    saved = (A.call_chat, A.run_tool, A.mcp_manifest, A.mcp_tool_defs)
    saved_tools = (list(A._active_tools), set(A._disabled_tools))
    it = {"i": 0}

    def fake_chat(model, messages, ctx=None, tools=None, stream=False, on_token=None, on_think=None):
        k = it["i"]; it["i"] += 1
        if k < len(calls):
            name, args, _ = calls[k]
            return {"message": {"content": "", "tool_calls": [
                {"function": {"name": name, "arguments": args}}]}, "prompt_eval_count": 500}
        return {"message": {"content": finish_content, "tool_calls": [
            {"function": {"name": "finish", "arguments": {"summary": finish_summary}}}]},
            "prompt_eval_count": 500}

    def fake_run_tool(name, args, wd, crawl_state=None):
        if name == "enable_tools":
            return A.enable_advanced_tools(args.get("tools", []))   # 真实实现(会改 _active_tools)
        for n, a, r in calls:
            if n == name and a == args:
                return r
        if name == "finish":
            return "[TASK_COMPLETE] all done"
        return "[tool error: not scripted]"

    A.call_chat, A.run_tool = fake_chat, fake_run_tool
    A.mcp_manifest, A.mcp_tool_defs = (lambda force=False: None), (lambda cats, extra=None: [])
    try:
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": task}]
        return A.agent_loop("gemma4:12b", msgs, str(tmp_path), None, budget_sec=None)
    finally:
        A.call_chat, A.run_tool, A.mcp_manifest, A.mcp_tool_defs = saved
        A._active_tools[:] = saved_tools[0]
        A._disabled_tools.clear()
        A._disabled_tools.update(saved_tools[1])


def _web_search_def():
    return next(t for t in A.ADVANCED_TOOLS if t["function"]["name"] == "web_search")


def test_qa_mode_web_search_is_executed(tmp_path, monkeypatch):
    """问答模式:web_search 在下发表里 → 必须真的执行,不得判"不可用"。"""
    monkeypatch.delenv("AGENT_OFFLINE", raising=False)
    monkeypatch.setattr(A.appconfig, "offline_mode", lambda: False)
    calls = [("web_search", {"query": "魔塔社区 是什么"},
              "[search results] 魔塔社区是 ModelScope 的中文名。")]
    msgs = _loop(tmp_path, calls, "魔塔社区是什么？")
    txt = _tool_msg_text(msgs)
    assert "ModelScope" in txt            # 脚本结果回来了 = 真的执行了
    assert "当前不可用" not in txt
    assert "断网模式" not in txt


def test_qa_mode_web_fetch_is_executed(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_OFFLINE", raising=False)
    monkeypatch.setattr(A.appconfig, "offline_mode", lambda: False)
    calls = [("web_fetch", {"url": "https://example.com"}, "[fetched] hello")]
    msgs = _loop(tmp_path, calls, "这个网页讲什么？")
    txt = _tool_msg_text(msgs)
    assert "hello" in txt and "当前不可用" not in txt


def test_offline_mode_blocks_polluted_active_tool(tmp_path, monkeypatch):
    """离线模式:即便 _active_tools 被污染(装配 append 泄漏),未下发的联网工具也不得执行。"""
    monkeypatch.setenv("AGENT_OFFLINE", "1")
    A._active_tools.append(_web_search_def())      # 复现 tools_for_categories 的 append 泄漏
    calls = [("web_search", {"query": "x"}, "[SHOULD_NOT_RUN]")]
    msgs = _loop(tmp_path, calls, "魔塔社区是什么？")
    txt = _tool_msg_text(msgs)
    assert "SHOULD_NOT_RUN" not in txt             # 没有真的跑
    assert "断网模式" in txt                        # 且话术说明是断网所致(不是"工具不存在")


def test_enable_then_use_same_turn_still_works(tmp_path, monkeypatch):
    """同一轮先 enable_tools 解锁、随后调用:必须仍然可用(不能把正常路径卡死)。"""
    monkeypatch.delenv("AGENT_OFFLINE", raising=False)
    monkeypatch.setattr(A.appconfig, "offline_mode", lambda: False)
    A._active_tools[:] = [t for t in A._active_tools
                          if t["function"]["name"] != "web_search"]   # 确保初始未解锁
    calls = [("enable_tools", {"tools": ["web_search"]}, "[enabled tools: web_search]"),
             ("web_search", {"query": "q"}, "[search] ok")]
    msgs = _loop(tmp_path, calls, "搜索一下 mingbird 的版本，写成报告。")
    txt = _tool_msg_text(msgs)
    assert "[search] ok" in txt
    assert "当前不可用" not in txt


def test_guard_reads_offered_list_not_global():
    """源码钉:可得性闸必须保留"本轮下发"口径(修假阴性+断网红线),不得回退裸 _active_tools。"""
    src = open(os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"),
               encoding="utf-8").read()
    assert 'name not in [t["function"]["name"] for t in _active_tools]' not in src
    assert "_offered = ({t[\"function\"][\"name\"] for t in ct} if ct is not None" in src
    assert "_offered |= ({t[\"function\"][\"name\"] for t in _active_tools}" in src
    assert "_active_snapshot = {t[\"function\"][\"name\"] for t in _active_tools}" in src
    # 断网红线:离线时联网工具必须"本轮下发"才放行
    assert "_offline_blk = (appconfig.offline_mode() and name in _ONLINE_TOOLS" in src
    assert "_blocked = name in _disabled_tools or name not in _allowed or _offline_blk" in src


def test_qa_finish_not_blocked_by_new_gate(tmp_path, monkeypatch, capsys):
    """回归钉:问答模式收尾(finish 不在 _chat_tool_defs 里)不得被新闸误判"不可用"。
    注:被接受的 finish 其 tool 结果不进返回的 messages(v3.1.4 同款坑),故查 stdout。"""
    monkeypatch.delenv("AGENT_OFFLINE", raising=False)
    monkeypatch.setattr(A.appconfig, "offline_mode", lambda: False)
    _loop(tmp_path, [], "魔塔社区是什么？")     # 脚本为空 → 直接 finish
    out = capsys.readouterr().out
    assert "当前不可用" not in out
    assert "TASK_COMPLETE" in out


def test_chat_tool_defs_are_advanced_tools():
    """事实钉:web_search/web_fetch 属 ADVANCED(不在 CORE)——正是旧校验假阴性的根因。"""
    core = {t["function"]["name"] for t in A.CORE_TOOLS}
    adv = {t["function"]["name"] for t in A.ADVANCED_TOOLS}
    chat = {t["function"]["name"] for t in A._chat_tool_defs()}
    assert {"web_search", "web_fetch"} <= chat
    assert "web_search" in adv and "web_search" not in core


# ---------------- 第二层:断网友好闸在工具本体(纵深防御) ----------------

@pytest.mark.parametrize("call", [
    lambda: A.web_search("q"),
    lambda: A.web_search_multi(["q"]),
    lambda: A.web_fetch("https://example.com"),
    lambda: A.batch_tools([{"tool": "web_search", "args": {"query": "q"}}], "."),
])
def test_offline_refuses_inside_network_tool_bodies(call, monkeypatch):
    """绕过装配层直接调用联网工具本体,断网时也必须拒绝(零出站不依赖装配过滤)。"""
    monkeypatch.setenv("AGENT_OFFLINE", "1")
    out = call()
    assert "断网模式" in out
    assert "零出站" in out


def test_online_mode_still_reaches_tool_body(monkeypatch):
    """反证:非断网时本体不拦(把请求函数打桩,验证确实走进去而不是被闸挡在外面)。"""
    monkeypatch.delenv("AGENT_OFFLINE", raising=False)
    monkeypatch.setattr(A.appconfig, "offline_mode", lambda: False)
    monkeypatch.setattr(A, "_search_backends", lambda: [])
    out = A.web_search("q")
    assert "断网模式" not in out


# ---------------- 审计追加:远程 MCP 的两条出站路径 ----------------

def _mcp_cfg(tmp_path, monkeypatch, servers):
    import json as _json
    p = tmp_path / "mcp.json"
    p.write_text(_json.dumps(servers, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(A, "MCP_CONFIG", str(p))
    monkeypatch.setattr(A, "_MCP_CACHE", {"t": 0, "data": None})
    monkeypatch.setattr(A, "_MCP_CACHE_FILE", str(tmp_path / "cache.json"))


def test_offline_blocks_remote_mcp_call(tmp_path, monkeypatch):
    """断网时直接调 url 型 MCP:必须在 mcp_call 本体拦下(派发闸对 MCP 是豁免的)。"""
    _mcp_cfg(tmp_path, monkeypatch, {"remote": {"url": "https://example.com/mcp"}})
    monkeypatch.setenv("AGENT_OFFLINE", "1")
    out = A.mcp_call("remote", "search", {"q": "x"})
    assert "断网模式" in out and "零出站" in out


def test_offline_manifest_does_not_probe_remote(tmp_path, monkeypatch):
    """断网时 manifest 刷新不得探测 url 型服务器(探测本身就是出站,且发生在启动预热)。"""
    _mcp_cfg(tmp_path, monkeypatch,
             {"local": {"command": "python", "args": ["-c", "pass"]},
              "remote": {"url": "https://example.com/mcp"}})
    monkeypatch.setenv("AGENT_OFFLINE", "1")
    probed = []
    monkeypatch.setattr(A, "_probe_server", lambda cfg: probed.append(cfg.get("url") or "stdio") or [])
    A.mcp_manifest(force=True)
    assert probed == ["stdio"]           # 只探了本地 stdio,remote 一次都没碰


def test_offline_repeat_calls_do_not_hard_reset_context(tmp_path, monkeypatch, capsys):
    """断网拦截不计入反循环梯:连续 11 次也不得硬复位上下文(那不是模型滥用)。"""
    monkeypatch.setenv("AGENT_OFFLINE", "1")
    calls = [("web_search", {"query": f"q{i}"}, "x") for i in range(11)]
    _loop(tmp_path, calls, "搜索一下 mingbird 的版本，写成报告。")
    out = capsys.readouterr().out
    assert "硬复位上下文" not in out
    assert "断网模式下不可用" in out
