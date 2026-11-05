# -*- coding: utf-8 -*-
"""测试用假 MCP stdio 服务器(broker 测试的对手盘)。
行分隔 JSON-RPC:initialize / tools/list / tools/call。
每次进程启动向 $FAKE_MCP_COUNT 文件追加一行 start(供测试数 spawn 次数);
设 $FAKE_MCP_LOG 时把收发/崩溃写进该文件。
**stdio 全走二进制层**:CI runner 的 python 子进程文本层编码不保证 UTF-8,
含中文的请求/响应在文本层直接 UnicodeDecodeError 崩溃(11-05 两轮 CI 实锤:
ASCII 参数全过、中文参数必死)——生产 _StdioSession/_probe_stdio 本就是
bytes 管道,fixture 与之对齐。"""
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


try:
    while True:
        _raw = sys.stdin.buffer.readline()
        if not _raw:
            break
        _ln = _raw.decode("utf-8", "replace")
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
                    "content": [{"type": "text",
                                 "text": "echo:" + json.dumps(a, ensure_ascii=False)}]}}
            else:
                out = {"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32602, "message": f"unknown tool {p.get('name')}"}}
        else:
            out = {"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"unknown method {m}"}}
        _s = json.dumps(out, ensure_ascii=False)
        _dbg("SEND", _s[:200])
        sys.stdout.buffer.write((_s + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
except Exception as _e:
    _dbg("CRASH", f"{type(_e).__name__} {_e}")
    raise
