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
COND = threading.Condition()
STATE = {"proc": None, "session": None, "ask_pending": False, "workdir": None}


def push_event(evt):
    with COND:
        EVENTS.append(evt)
        if len(EVENTS) > EVENTS_MAX:
            del EVENTS[:len(EVENTS) - EVENTS_MAX]
        COND.notify_all()


def _prefs_load():
    d = {"ui_mode": "auto", "ctx": 131072, "temp": 0.0, "num_predict": 2048,
         "think": True, "sys_enable": False, "sys_text": ""}
    try:
        d.update(json.load(open(PREFS_FILE, encoding="utf-8")))
    except Exception:
        pass
    return d


def _prefs_save(p):
    os.makedirs(os.path.dirname(PREFS_FILE), exist_ok=True)
    tmp = PREFS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PREFS_FILE)


def _workdir():
    return STATE.get("workdir") or os.path.join(DEFAULT_TASKS, "work")


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
    if not resume:
        for stale in (".agent_state.json", "todo.json"):
            p = os.path.join(workdir, stale)
            if os.path.exists(p):
                os.remove(p)
    prefs = _prefs_load()
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["AGENT_STREAM"] = "1"
    env["AGENT_THINK"] = "1" if prefs.get("think", True) else "0"
    env["AGENT_CTX"] = str(prefs.get("ctx", 131072))
    env["AGENT_TEMP"] = str(prefs.get("temp", 0.0))
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
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=env, bufsize=1, cwd=workdir)
    STATE["proc"] = proc
    threading.Thread(target=_reader, args=(proc,), daemon=True).start()
    threading.Thread(target=_wait_exit, args=(proc,), daemon=True).start()


def _reader(proc):
    ctx_re = re.compile(r"\[ctx: (\d+)/(\d+) = (\d+)%\]")
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        if line.startswith("@@TOK@@"):
            push_event({"type": "tok", "data": line[len("@@TOK@@"):]})
        elif line.startswith("@@THINK@@"):
            push_event({"type": "think", "data": line[len("@@THINK@@"):]})
        elif line.startswith("@@ASK@@"):
            STATE["ask_pending"] = True
            try:
                req = json.loads(line[len("@@ASK@@"):])
            except Exception:
                req = {"question": line[len("@@ASK@@"):]}
            push_event({"type": "ask", "data": req})
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
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
    STATE["ask_pending"] = False


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
                "ask_pending": STATE.get("ask_pending", False),
                "prefs": {k: prefs.get(k) for k in ("ctx", "temp", "num_predict", "think", "sys_enable", "sys_text", "ui_mode")},
            }, ensure_ascii=False))
        if u.path == "/api/sessions":
            sd = os.path.join(appconfig.AGENT_HOME, "sessions")
            if not os.path.isdir(sd):
                return self._send(200, json.dumps({"sessions": []}, ensure_ascii=False))
            files = sorted([f for f in os.listdir(sd) if f.endswith(".json") and not f.endswith(".meta.json")],
                           key=lambda n: -os.path.getmtime(os.path.join(sd, n)))[:60]
            return self._send(200, json.dumps({"sessions": files}, ensure_ascii=False))
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
            idx = len(EVENTS)      # 只推连接之后的新事件:回放旧事件会让重连的浏览器整段重复聊天内容
            self.wfile.write(b"retry: 3000\n\n")
            while True:
                with COND:
                    while idx >= len(EVENTS):
                        COND.wait(timeout=15)
                    new = EVENTS[idx:]
                idx += len(new)
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
            proc = STATE.get("proc")
            ans = str(body.get("answer", "deny"))
            if proc and proc.poll() is None:
                try:
                    proc.stdin.write(ans + "\n")
                    proc.stdin.flush()
                except Exception:
                    pass
            return self._send(200, "{}")
        if u.path == "/api/newchat":
            STATE["session"] = None
            return self._send(200, "{}")
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
    print(f"Mingbird Web UI v1.5-alpha: http://127.0.0.1:{port}  (local only · 仅本机访问)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
