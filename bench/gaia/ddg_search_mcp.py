#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local stdio MCP server: web search for the GAIA matrix (free, no key).

Why this exists: the npx duckduckgo-mcp-server used during LRAB cannot reach
its upstream from this network (VQD handshake fails; the package ignores
HTTP_PROXY). This wrapper hits free HTML search endpoints through urllib,
which natively honors HTTP_PROXY/HTTPS_PROXY env vars — so the batch driver
can hand the identical working search tool to all four agents.

Upstream chain (09-05): Bing HTML primary, DuckDuckGo HTML fallback. The
VPN provider's whole IP pool got anomaly-flagged by DDG (202 challenge even
for real browsers, across two country ranges) while Bing served clean
English-market results from the same exits. Same upstream chain for every
agent; market pinned to en-US on both (setmkt / kl).

Each agent invocation spawns a FRESH MCP interpreter, so cross-process state
(dedup cache, request spacing) lives on disk: DDG anomaly-flags exit IPs on
scripted-request volume, and Bing will too eventually — the cache cuts
request volume by an order of magnitude and the spacing smooths bursts.

MCP surface (kept minimal):
  tool web_search { query: string, max_results?: int } -> text

Protocol: newline-delimited JSON-RPC 2.0 over stdio.
"""
import base64
import hashlib
import html as _html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

TOOLS = [{
    "name": "web_search",
    "description": "Search the web and return titles, URLs and snippets.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer",
                            "description": "Max results (default 6)"}
        },
        "required": ["query"]
    }
}]

CACHE_DIR = os.environ.get("GAIA_SEARCH_CACHE") or os.path.join(
    os.path.expanduser("~"), ".gaia_search_cache")
CACHE_TTL = 12 * 3600     # SERP drift within half a day is negligible
MIN_SPACING = 4.0         # seconds between LIVE requests, shared via file

# Self-sufficient proxy: GAIA_PROXY must win even when only the driver
# exports it. Bing is reachable DIRECTLY from CN (cn.bing.com) — without
# this, a missing proxy env would silently degrade to regionalized SERPs
# instead of erroring.
_proxy = os.environ.get("GAIA_PROXY", "").strip()
if _proxy and not os.environ.get("HTTPS_PROXY"):
    os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = _proxy
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"


# ---------- disk state (cache + cross-process spacing) ----------

def _proxied():
    """Whether live requests currently egress via the proxy. Regionalized
    SERPs (cn.bing direct) must never be served to proxied runs or vice
    versa, so entries are mode-tagged and cross-mode hits are refused."""
    return bool(os.environ.get("HTTPS_PROXY") or os.environ.get("http_proxy"))


def _cache_path(query):
    h = hashlib.sha1((query + "|en-US").encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, h + ".json")


def _cache_get(query, ignore_ttl=False):
    try:
        with open(_cache_path(query), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("proxied") != _proxied():
            return None                   # different egress: not the same SERP
        if ignore_ttl or time.time() - d["ts"] <= CACHE_TTL:
            return d["text"]
    except Exception:
        pass
    return None


def _cache_put(query, text):
    try:
        with open(_cache_path(query), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "text": text,
                       "proxied": _proxied()}, f)
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


# ---------- upstreams ----------

def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    last_err = "unknown"
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, str(e)[:150])
            if attempt == 0:
                time.sleep(2)
    return ""


def _strip_tags(s):
    return _html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _unwrap_bing(href):
    """Bing wraps outbound links as /ck/a?...&u=a1<base64url> — unwrap."""
    href = _html.unescape(href)
    m = re.search(r"[?&]u=a1([A-Za-z0-9_\-]+)", href)
    if m:
        b64 = m.group(1)
        b64 += "=" * (-len(b64) % 4)
        try:
            return base64.urlsafe_b64decode(b64).decode("utf-8", "replace")
        except Exception:
            pass
    return href


def _unwrap_ddg(href):
    """DDG html wraps outbound links in /l/?uddg=<urlencoded> — unwrap."""
    if "/l/?" in href or "uddg=" in href:
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            return urllib.parse.unquote(m.group(1))
    return href


def _format(blocks, unwrap):
    out = []
    for i, (href, title, snip) in enumerate(blocks):
        out.append("%d. %s\n   %s\n   %s"
                   % (i + 1, _strip_tags(title), unwrap(href), snip[:300]))
    return "\n".join(out)


def _search_bing(query, max_results):
    url = ("https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
           + "&setmkt=en-US&setlang=en&count=%d" % max(6, max_results))
    page = _fetch(url)
    if not page:
        return None                       # network error: try next upstream
    items = re.findall(r'<li class="b_algo".*?</li>', page, re.S)
    blocks = []
    for b in items[:max_results]:
        m = re.search(r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        s = re.search(r'<div class="b_caption[^"]*"[^>]*>\s*<p[^>]*>(.*?)</p>',
                      b, re.S) or re.search(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', b, re.S)
        snip = _strip_tags(s.group(1)) if s else ""
        blocks.append((m.group(1), m.group(2), snip))
    if not blocks:
        return None    # challenge/consent page or zero organic results
    return _format(blocks, _unwrap_bing)


def _search_ddg(query, max_results):
    # kl=us-en pins the SERP region: without it DDG localizes by proxy exit IP
    url = ("https://html.duckduckgo.com/html/?q="
           + urllib.parse.quote_plus(query) + "&kl=us-en")
    page = _fetch(url)
    if not page:
        return None
    items = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        page, re.S)
    snippets = re.findall(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
        page, re.S)
    if not items:
        return None
    blocks = []
    for i, (href, title) in enumerate(items[:max_results]):
        snip = _strip_tags(snippets[i]) if i < len(snippets) else ""
        blocks.append((href, title, snip))
    return _format(blocks, _unwrap_ddg)


def search(query, max_results=6, fresh=False):
    """fresh=True bypasses the cache (driver health probes must hit live)."""
    if not fresh:
        hit = _cache_get(query)
        if hit is not None:
            return hit
    _throttle()
    text = None
    for fetcher in (_search_bing, _search_ddg):
        try:
            text = fetcher(query, max_results)
        except Exception as e:
            text = None
        if text:
            _stamp()
            _cache_put(query, text)       # only real result sets are cached
            return text
        time.sleep(1)                     # breathe before the next upstream
    _stamp()
    if not fresh:
        stale = _cache_get(query, ignore_ttl=True)
        if stale is not None:
            return stale                  # degraded upstream: serve stale
    return ("Error: no upstream returned results (last: %s)"
            % (str(text)[:80] if text else "network error"))


# ---------- MCP stdio loop ----------

def handle(msg):
    mid = msg.get("id")
    method = msg.get("method", "")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "web-search", "version": "1.1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name != "web_search":
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
