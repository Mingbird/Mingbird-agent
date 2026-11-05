# -*- coding: utf-8 -*-
"""测试用假 MCP stdio 服务器(broker 测试的对手盘)。
行分隔 JSON-RPC:initialize / tools/list / tools/call。
每次进程启动向 $FAKE_MCP_COUNT 文件追加一行 start(供测试数 spawn 次数);
设 $FAKE_MCP_LOG 时把全部收发写进该文件(CI 侧排查 stdio 行为用)。
读循环用 readline() 而非 for-iteration:文件迭代有内部预读,在部分构建上对
管道中段交互不稳(CI Linux 实测 initialize 通、后续请求丢失)。"""
import json
import os
import sys

_cnt = os.environ.get("FAKE_MCP_COUNT")
if _cnt:
    try:
        open(_cnt, "a", encoding="utf-8").write("start\n")
    except Exception:
        pass
_log = os.environ.get("FAKE_MCP_LOG")


def _dbg(tag, s):
    if _log:
        try:
            open(_log, "a", encoding="utf-8").write(f"{tag} {s}\n")
        except Exception:
            pass


while True:
    _ln = sys.stdin.readline()
    if not _ln:
        break
    _dbg("RECV", _ln.strip()[:200])
    try:
        msg = json.loads(_ln)
    except Exception:
        continue
    mid = msg.get("id")
    if mid is None:
        continue
    m = msg.get("method")
    if m == "initialize":
        out = {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake", "version": "0"}}}
    elif m == "tools/list":
        out = {"jsonrpc": "2.0", "id": mid, "result": {"tools": [
            {"name": "echo", "description": "回显参数",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"}},
                             "required": ["text"]}}]}}
    elif m == "tools/call":
        p = msg.get("params") or {}
        if p.get("name") == "echo":
            a = p.get("arguments") or {}
            out = {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": "echo:" + json.dumps(a, ensure_ascii=False)}]}}
        else:
            out = {"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32602, "message": f"unknown tool {p.get('name')}"}}
    else:
        out = {"jsonrpc": "2.0", "id": mid,
               "error": {"code": -32601, "message": f"unknown method {m}"}}
    _s = json.dumps(out, ensure_ascii=False)
    _dbg("SEND", _s[:200])
    sys.stdout.write(_s + "\n")
    sys.stdout.flush()
