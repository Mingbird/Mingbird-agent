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
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import re

# Each agent invocation spawns a FRESH MCP interpreter, so cross-process
# state (dedup cache, request spacing) can only live on disk. DDG anomaly-
# flags exit IPs on scripted-request volume (09-05: the flag re-formed
# minutes after a healthy ignition and silently emptied every in-cell
# search), so the wrapper caps request rate and dedups identical queries
# across all four agents.
CACHE_DIR = os.environ.get("GAIA_SEARCH_CACHE") or os.path.join(
    os.path.expanduser("~"), ".gaia_search_cache")
CACHE_TTL = 12 * 3600     # SERP drift within half a day is negligible
MIN_SPACING = 4.0         # seconds between LIVE requests, shared via file


def _cache_path(query):
    h = hashlib.sha1((query + "|us-en").encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")


def _cache_get(query, ignore_ttl=False):
    try:
        with open(_cache_path(query), encoding="utf-8") as f:
            d = json.load(f)
        if ignore_ttl or time.time() - d["ts"] <= CACHE_TTL:
            return d["text"]
    except Exception:
        pass
    return None


def _cache_put(query, text):
    try:
        with open(_cache_path(query), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "text": text}, f)
    except Exception:
        pass


def _throttle():
    """Wait until MIN_SPACING has passed since the last live request."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception:
        pass
    lock = os.path.join(CACHE_DIR, ".lastreq")
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            last = os.path.getmtime(lock)
        except OSError:
            break
        wait = MIN_SPACING - (time.time() - last)
        if wait <= 0:
            break
        time.sleep(min(wait, 2.0))


def _stamp():
    try:
        open(os.path.join(CACHE_DIR, ".lastreq"), "w").close()
    except OSError:
        pass

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


def search(query, max_results=6, fresh=False):
    """fresh=True bypasses the cache (driver health probes must hit live)."""
    if not fresh:
        hit = _cache_get(query)
        if hit is not None:
            return hit
    _throttle()
    text = _search_live(query, max_results)
    _stamp()
    if text.startswith(("1.", "2.", "3.", "4.", "5.")):
        _cache_put(query, text)      # only real result sets are cached
    elif text.startswith("Error") and not fresh:
        stale = _cache_get(query, ignore_ttl=True)
        if stale is not None:
            return stale             # degraded upstream: serve stale cache
    return text


def _search_live(query, max_results=6):
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
