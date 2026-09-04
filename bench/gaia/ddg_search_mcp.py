#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local stdio MCP server: DuckDuckGo web search via the HTML endpoint.

Why this exists: the npx duckduckgo-mcp-server used during LRAB cannot reach
its upstream from this network (VQD handshake fails; the package ignores
HTTP_PROXY). This wrapper hits the SAME upstream (html.duckduckgo.com) through
urllib, which natively honors HTTP_PROXY/HTTPS_PROXY env vars — so the batch
driver can hand the identical working search tool to all four agents.

MCP surface (kept minimal):
  tool duckduckgo_web_search { query: string, max_results?: int } -> text

Protocol: newline-delimited JSON-RPC 2.0 over stdio (same as the npx server).
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import re

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

TOOLS = [{
    "name": "duckduckgo_web_search",
    "description": "Search the web via DuckDuckGo and return titles, URLs and snippets.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default 6)"}
        },
        "required": ["query"]
    }
}]


def unwrap_href(href):
    """DDG html wraps outbound links in /l/?uddg=<urlencoded> — unwrap."""
    if "/l/?" in href or "uddg=" in href:
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            return urllib.parse.unquote(m.group(1))
    return href


def strip_tags(s):
    import html
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def search(query, max_results=6):
    # kl=us-en pins the SERP region: without it DDG localizes by proxy exit IP
    # (a CN-exit tunnel made "Moon perigee" return Baidu Baike — 09-05 smoke).
    url = ("https://html.duckduckgo.com/html/?q="
           + urllib.parse.quote_plus(query) + "&kl=us-en")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    html = ""
    for attempt in range(2):        # html endpoint throws sporadic empty SERPs
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                html = r.read().decode("utf-8", "replace")
        except Exception as e:
            html = ""
            last_err = "%s: %s" % (type(e).__name__, str(e)[:150])
        if 'class="result__a' in html or "result-link" in html:
            break
        if attempt == 0:
            time.sleep(2)
    blocks = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html, re.S)
    snippets = re.findall(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        html, re.S)
    if not blocks and not html:
        return "Error: search failed (%s)" % last_err
    out = []
    for i, (href, title) in enumerate(blocks[:max_results]):
        snip = strip_tags(snippets[i]) if i < len(snippets) else ""
        out.append("%d. %s\n   %s\n   %s"
                   % (i + 1, strip_tags(title), unwrap_href(href), snip[:300]))
    if not out:
        return "No results found for: %s" % query
    return "\n".join(out)


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ddg-html-search", "version": "1.0.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name != "duckduckgo_web_search":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": "Unknown tool: %s" % name}]}
        }
        try:
            text = search(args.get("query", ""),
                          int(args.get("max_results") or 6))
        except Exception as e:
            text = "Error: %s: %s" % (type(e).__name__, str(e)[:200])
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": text}]}}
    if mid is not None and method:
        return {"jsonrpc": "2.0", "id": mid, "error":
                {"code": -32601, "message": "Method not found: %s" % method}}
    return None


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error":
                    {"code": -32603, "message": str(e)[:200]}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
