#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mingbird Web UI (v1.5) — local-only web frontend over the same agent CLI.

Bind 127.0.0.1 only: nothing leaves the machine (offline-first red line).
Line protocol (@@TOK@@/@@THINK@@/@@ASK@@/@@DISPATCH@@/​[ctx: N/M = P%]) is
identical to the Tk frontend; the web layer re-publishes it as SSE events.
Usage: python webui/server.py [--port 8765]

Endpoints:
  GET  /                 single-page frontend
  GET  /api/status       version/busy/models/session/prefs/workdir
  GET  /api/events       SSE event stream
  POST /api/chat         {prompt, model, resume} -> start agent
  POST /api/stop         kill agent tree
  POST /api/ask          {answer} -> stdin to agent approval prompt
  POST /api/newchat      reset session (next chat starts fresh)
  GET  /api/sessions     session list
  GET  /api/plan         plan (todo.json) of the current workdir
  GET/POST /api/prefs    ctx/temp/num_predict/think/sys_enable/sys_text/ui_mode
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)                     # repo root (ollama_agent.py lives here)
AGENT_PY = os.path.join(ROOT, "ollama_agent.py")
import appconfig                # 统一配置层(AGENT_HOME/模型映射/去重规则与 Tk 同源)
STATIC = os.path.join(HERE, "static")
DEFAULT_TASKS = os.path.join(os.path.expanduser("~"), "agent_tasks")
PREFS_FILE = os.path.join(appconfig.AGENT_HOME, "gui_prefs.json")   # 与桌面版共用设置(遵循 MINGBIRD_HOME)

EVENTS = []
EVENTS_MAX = 600          # 定长截断:长任务会产生数万条 tok 事件,无限增长=内存泄漏
EVENT_SEQ = 0             # 全局单调 id:客户端按 id 追进度,截断后不会永久停滞
COND = threading.Condition()
STATE = {"proc": None, "session": None, "ask_pending": False,
         "ask_id": None, "ask_seq": 0, "workdir": None}


def push_event(evt):
    global EVENT_SEQ
    with COND:
        EVENT_SEQ += 1
        evt = dict(evt)
        evt["id"] = EVENT_SEQ
        EVENTS.append(evt)
        if len(EVENTS) > EVENTS_MAX:
            del EVENTS[:len(EVENTS) - EVENTS_MAX]
        COND.notify_all()


def _decode_frame(payload):
    """v3.0.0 起 token 帧是 JSON 字符串(换行不再拆帧);兼容旧版裸文本。"""
    try:
        v = json.loads(payload)
        return v if isinstance(v, str) else payload
    except Exception:
        return payload


def _prefs_load():
    # v1.7.0 采样三态:temp/think 为 None = 未设置 = 请求不带字段,用 ollama 默认。
    # prefver 迁移与桌面版 load_prefs 同口径:旧版(无标记)文件的 temp=0.0 /
    # think=True 是隐藏默认值而非用户显式选择,一次性迁为未设置。
    d = {"ui_mode": "auto", "ctx": 131072, "temp": None, "num_predict": 2048,
         "think": None, "sys_enable": False, "sys_text": "", "prefver": 2}
    try:
        j = json.load(open(PREFS_FILE, encoding="utf-8"))
        d.update(j)
        if "prefver" not in j:
            if d.get("temp") in (0, 0.0):
                d["temp"] = None
            if d.get("think") is True:
                d["think"] = None
    except Exception:
        pass
    return d


def _prefs_save(p):
    p.setdefault("prefver", 2)   # 迁移标记:落盘后不再把显式 0/关 当作旧默认抹掉
    os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
    tmp = PREFS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREFS_FILE)


def _workdir():
    return STATE.get("workdir") or os.path.join(DEFAULT_TASKS, "work")


def _session_meta(sd, name):
    try:
        return json.load(open(os.path.join(sd, name + ".meta.json"), encoding="utf-8"))
    except Exception:
        return {}


def _first_user_text(fp, limit=60):
    """侧栏标题:优先 meta.title,没有就从首条用户消息截一句。"""
    try:
        msgs = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(msgs, list):
        return ""
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = " ".join(str(m.get("content") or "").split())
        if not c:
            continue
        if c.startswith(("Continue: keep making", "⚠️ 交付前自查", "[时间预算]")):
            continue
        return c[:limit] + ("…" if len(c) > limit else "")
    return ""


def _cloud_public():
    """前端可见的云端配置(不回传 api_key,只报是否已保存)。"""
    c = appconfig.load_config().get("cloud") or {}
    return {"enabled": bool(c.get("enabled")),
            "base_url": str(c.get("base_url") or ""),
            "model": str(c.get("model") or ""),
            "has_key": bool(c.get("api_key"))}


def _session_rows(limit=60):
    sd = os.path.join(appconfig.AGENT_HOME, "sessions")
    if not os.path.isdir(sd):
        return []
    files = [f for f in os.listdir(sd)
             if f.endswith(".json") and not f.endswith((".meta.json", ".todo.json"))]
    files.sort(key=lambda n: -os.path.getmtime(os.path.join(sd, n)))
    rows = []
    for f in files[:limit]:
        name = f[:-5]
        fp = os.path.join(sd, f)
        meta = _session_meta(sd, name)
        title = str(meta.get("title") or "").strip() or _first_user_text(fp)
        rows.append({
            "name": name,
            "title": title or name,
            "mtime": int(os.path.getmtime(fp)),
            "status": str(meta.get("status") or ""),
            "task": str(meta.get("task") or "")[:80],
        })
    return rows


def _model_map():
    import appconfig
    return appconfig.model_map()


def _apply_time_budget(env, task):
    m = re.search(r"(?:限时|within|in under|time limit[: ]*)?(\d+(?:\.\d+)?)\s*(分钟|分钟内|min(?:ute)?s?|hours?|小时|h)\b", task, re.I)
    if m:
        v = float(m.group(1))
        if re.match(r"h|hour|小时", m.group(2), re.I):
            v *= 60
        env["AGENT_TIME_BUDGET_SEC"] = str(int(v * 60))


def start_agent(prompt, model_key, resume):
    import appconfig
    mmap = _model_map()
    # 下拉里选的名字就是发给 ollama 的模型;配置映射只做"显示名→tag"的正向翻译,
    # 查不到时用原值——绝不静默回退到"第一个配置项"(那会选 A 跑 B)。
    model = mmap.get(model_key, model_key)
    workdir = _workdir()
    os.makedirs(workdir, exist_ok=True)
    taskfile = os.path.join(workdir, "task_input.txt")
    with open(taskfile, "w", encoding="utf-8") as f:
        f.write(prompt)
    STATE["ask_pending"] = False
    STATE["ask_id"] = None
    if not resume:
        for stale in (".agent_state.json", "todo.json"):
            p = os.path.join(workdir, stale)
            if os.path.exists(p):
                os.remove(p)
    prefs = _prefs_load()
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["AGENT_STREAM"] = "1"
    # 采样三态(v1.7.0):未设置 → 从 env 删掉继承值,agent 载荷即不带
    # temperature/think 字段(ollama 默认);显式选择(含 0/关)才透传。
    tv = prefs.get("think")
    if tv is None:
        env.pop("AGENT_THINK", None)
    else:
        env["AGENT_THINK"] = "1" if tv else "0"
    env["AGENT_CTX"] = str(prefs.get("ctx", 131072))
    tp = prefs.get("temp")
    if tp is None:
        env.pop("AGENT_TEMP", None)
    else:
        env["AGENT_TEMP"] = str(tp)
    env["AGENT_NUMPREDICT"] = str(prefs.get("num_predict", 2048))
    sys_en = prefs.get("sys_enable")
    sys_file = os.path.join(os.path.expanduser("~"), ".ollama_agent", "system_override.txt")
    if sys_en and os.path.isfile(sys_file):
        env["AGENT_SYSTEM_FILE"] = sys_file
    args = [sys.executable, AGENT_PY, model, taskfile, workdir]
    session = STATE.get("session") or ("chat_" + time.strftime("%m%d_%H%M%S"))
    STATE["session"] = session
    if resume:
        args += ["--session", session, "--append"]
    _apply_time_budget(env, prompt)
    push_event({"type": "note", "data": "====== start · " + model + " ======"})
    _kw = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=env, bufsize=1, cwd=workdir,
                            **_kw)
    STATE["proc"] = proc
    threading.Thread(target=_reader, args=(proc,), daemon=True).start()
    threading.Thread(target=_wait_exit, args=(proc,), daemon=True).start()


def _reader(proc):
    ctx_re = re.compile(r"\[ctx: (\d+)/(\d+) = (\d+)%\]")
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        if line.startswith("@@TOK@@"):
            push_event({"type": "tok",
                        "data": _decode_frame(line[len("@@TOK@@"):])})
        elif line.startswith("@@THINK@@"):
            push_event({"type": "think",
                        "data": _decode_frame(line[len("@@THINK@@"):])})
        elif line.startswith("@@ASK@@"):
            try:
                req = json.loads(line[len("@@ASK@@"):])
            except Exception:
                req = {"question": line[len("@@ASK@@"):]}
            with COND:
                STATE["ask_seq"] = int(STATE.get("ask_seq") or 0) + 1
                ask_id = "ask_%d" % STATE["ask_seq"]
                STATE["ask_pending"] = True
                STATE["ask_id"] = ask_id
            push_event({"type": "ask", "data": req, "ask_id": ask_id})
        elif line.startswith("@@DISPATCH@@"):
            push_event({"type": "dispatch", "data": line[len("@@DISPATCH@@"):]})
        else:
            m = ctx_re.search(line)
            if m:
                push_event({"type": "ctx", "data": {"used": int(m.group(1)),
                                                    "total": int(m.group(2)),
                                                    "pct": int(m.group(3))}})
            elif line.strip():
                push_event({"type": "log", "data": line})
    push_event({"type": "exit", "data": proc.poll()})


def _wait_exit(proc):
    proc.wait()
    time.sleep(0.4)
    push_event({"type": "exit", "data": proc.poll()})


def kill_tree():
    proc = STATE.get("proc")
    if proc and proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import signal
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.kill()
    STATE["ask_pending"] = False
    STATE["ask_id"] = None


# ---------------- HTTP ----------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            p = os.path.join(STATIC, "index.html")
            return self._send(200, open(p, "rb").read(), "text/html; charset=utf-8")
        if u.path.startswith("/static/"):
            fp = os.path.join(STATIC, os.path.basename(u.path[len("/static/"):]))
            if os.path.isfile(fp):
                ct = "text/css" if fp.endswith(".css") else "application/javascript"
                return self._send(200, open(fp, "rb").read(), ct + "; charset=utf-8")
            return self._send(404, "{}")
        if u.path == "/api/status":
            proc = STATE.get("proc")
            prefs = _prefs_load()
            # 动态识别:ollama /api/tags 实际安装的模型(digest 去重,与 Tk 同一规则)
            # + config 友好名。离线时返回空清单,不拿陈旧配置冒充可用(会让用户选到跑不起来的模型)
            # 注意:appconfig 用模块级导入;在此处局部 import 会把整个 do_GET 的
            # appconfig 变成局部名,导致其他分支 UnboundLocalError
            import urllib.request as _ur
            cfg_map = _model_map()
            tag_to_display = {v: k for k, v in cfg_map.items()}
            entries = []
            ollama_ok = False
            try:
                _lb = appconfig.backend_openai()
                if _lb:
                    # v2.1.1 OpenAI 兼容引擎:GET /models(OpenAI 形态)→ 归一成 tags 形态
                    r = json.loads(_ur.urlopen(_lb["base_url"] + "/models", timeout=3).read())
                    entries = [{"name": x.get("id")} for x in (r.get("data") or []) if x.get("id")]
                else:
                    host = appconfig.ollama_host().rstrip("/")
                    r = json.loads(_ur.urlopen(host + "/api/tags", timeout=3).read())
                    entries = r.get("models", [])
                ollama_ok = True
            except Exception:
                entries = []
            models = [d for d, _t in appconfig.dedupe_model_entries(entries, tag_to_display)] \
                if ollama_ok else []
            return self._send(200, json.dumps({
                "version": _version(), "busy": bool(proc and proc.poll() is None),
                "models": models, "ollama_ok": ollama_ok,
                "session": STATE.get("session"), "workdir": _workdir(),
                "offline": bool(appconfig.offline_mode()),
                "cloud": _cloud_public(),
                "ask_pending": STATE.get("ask_pending", False),
                "prefs": {k: prefs.get(k) for k in ("ctx", "temp", "num_predict", "think", "sys_enable", "sys_text", "ui_mode")},
            }, ensure_ascii=False))
        if u.path == "/api/sessions":
            return self._send(200, json.dumps({"sessions": _session_rows()},
                                              ensure_ascii=False))
        if u.path == "/api/session":
            from urllib.parse import parse_qs
            qs = parse_qs(u.query)
            name = (qs.get("name") or [""])[0]
            safe = os.path.basename(name)
            fp = os.path.join(appconfig.AGENT_HOME, "sessions", safe + ".json")
            try:
                msgs = json.load(open(fp, encoding="utf-8"))
            except Exception:
                msgs = []
            return self._send(200, json.dumps({"name": safe, "messages": msgs}, ensure_ascii=False))
        if u.path == "/api/plan":
            wd = _workdir()
            p = os.path.join(wd, "todo.json")
            try:
                plan = json.load(open(p, encoding="utf-8"))
            except Exception:
                plan = []
            return self._send(200, json.dumps({"plan": plan}, ensure_ascii=False))
        if u.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            # 只推连接之后的新事件;按单调 id 追进度。旧实现用列表下标,
            # EVENTS 截断后 idx 永远 >= len(EVENTS),SSE 永久静默(v3 复审 P0)。
            with COND:
                last_id = EVENTS[-1].get("id", 0) if EVENTS else 0
            self.wfile.write(b"retry: 3000\n\n")
            while True:
                with COND:
                    new = [e for e in EVENTS if e.get("id", 0) > last_id]
                    if not new:
                        COND.wait(timeout=15)
                        new = [e for e in EVENTS if e.get("id", 0) > last_id]
                if new:
                    last_id = new[-1].get("id", last_id)
                    for evt in new:
                        self.wfile.write(("data: " + json.dumps(evt, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        return self._send(404, "{}")

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        if u.path == "/api/chat":
            proc = STATE.get("proc")
            if proc and proc.poll() is None:
                return self._send(409, json.dumps({"error": "busy"}))
            start_agent(str(body.get("prompt", "")), str(body.get("model", "")),
                        bool(body.get("resume", True)))
            return self._send(200, "{}")
        if u.path == "/api/stop":
            kill_tree()
            return self._send(200, "{}")
        if u.path == "/api/ask":
            # 只接受当前待答请求的回复:否则任何时刻预置的 "allow" 会在下一次
            # 越界请求时被 agent 直接读走,等于绕过确认框(v3 复审 P1-8)。
            if not STATE.get("ask_pending") \
                    or str(body.get("id") or "") != str(STATE.get("ask_id") or ""):
                return self._send(409, json.dumps({"error": "no pending ask"}))
            proc = STATE.get("proc")
            ans = str(body.get("answer", "deny"))
            if proc and proc.poll() is None:
                try:
                    proc.stdin.write(ans + "\n")
                    proc.stdin.flush()
                except Exception:
                    pass
            STATE["ask_pending"] = False
            STATE["ask_id"] = None
            return self._send(200, "{}")
        if u.path == "/api/newchat":
            STATE["session"] = None
            return self._send(200, "{}")
        if u.path == "/api/offline":
            cfg = dict(appconfig.load_config())
            cl = cfg.get("cloud") or {}
            wants_off = bool(body.get("offline"))
            if wants_off and cl.get("enabled") and cl.get("base_url") and cl.get("model"):
                return self._send(409, json.dumps(
                    {"error": "cloud_requires_network"}, ensure_ascii=False))
            cfg["offline_mode"] = wants_off
            appconfig.save_config(cfg)
            return self._send(200, json.dumps({
                "offline": bool(appconfig.offline_mode())}, ensure_ascii=False))
        if u.path == "/api/cloud":
            cfg = dict(appconfig.load_config())
            c = dict(cfg.get("cloud") or {})
            for k in ("base_url", "model", "api_key"):
                if k in body:
                    v = str(body.get(k) or "").strip()
                    if k == "api_key" and not v:
                        continue          # 空 = 不修改已保存的密钥
                    c[k] = v.rstrip("/") if k == "base_url" else v
            if "enabled" in body:
                c["enabled"] = bool(body.get("enabled"))
            c["enabled"] = bool(c.get("enabled") and c.get("base_url") and c.get("model"))
            if c["enabled"]:
                cfg["offline_mode"] = False   # 云端只能联网
            cfg["cloud"] = c
            appconfig.save_config(cfg)
            return self._send(200, json.dumps({"cloud": _cloud_public()},
                                              ensure_ascii=False))
        if u.path == "/api/session":
            # 载入历史会话:设置 STATE["session"],下一次发送即以 --append 续跑该会话
            name = os.path.basename(str(body.get("name", "")))
            if not name:
                return self._send(400, json.dumps({"error": "name required"}))
            STATE["session"] = name
            return self._send(200, json.dumps({"session": name}))
        if u.path == "/api/prefs":
            prefs = _prefs_load()
            for k in ("ctx", "temp", "num_predict", "think", "sys_enable", "sys_text", "ui_mode"):
                if k in body:
                    prefs[k] = body[k]
            _prefs_save(prefs)
            return self._send(200, json.dumps({"prefs": prefs}))
        return self._send(404, "{}")


def _version():
    try:
        return open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except Exception:
        return ""


def main():
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mingbird Web UI {_version() or 'v1.7.0'}: http://127.0.0.1:{port}  (local only · 仅本机访问)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
