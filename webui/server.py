#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mingbird Web UI (v1.5) — local-only web frontend over the same agent CLI.

Bind 127.0.0.1 only: nothing leaves the machine (offline-first red line).
Line protocol (@@TOK@@/@@THINK@@/@@ASK@@/@@DISPATCH@@) is identical to the
Tk frontend; the web layer just re-publishes it as SSE events.
Usage: python webui/server.py [--port 8765]
"""
import json
import os
import queue
import shutil
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
STATIC = os.path.join(HERE, "static")
DEFAULT_TASKS = os.path.join(os.path.expanduser("~"), "agent_tasks")

STATE = {"proc": None, "events": [], "cond": None, "session": None,
         "ask_pending": False, "clients": 0}
_lock = threading.Lock()
_cond = threading.Condition()


def push_event(evt):
    with _cond:
        STATE["events"].append(evt)
        _cond.notify_all()


def start_agent(prompt, model_key, time_limit, resume):
    import appconfig
    model = appconfig.model_map().get(model_key, next(iter(appconfig.model_map().values()), model_key))
    workdir = os.path.join(DEFAULT_TASKS, "work")
    os.makedirs(workdir, exist_ok=True)
    task = prompt
    taskfile = os.path.join(workdir, "task_input.txt")
    with open(taskfile, "w", encoding="utf-8") as f:
        f.write(task)
    if not resume:
        for stale in (".agent_state.json", "todo.json"):
            p = os.path.join(workdir, stale)
            if os.path.exists(p):
                os.remove(p)
    prefs = _load_prefs()
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
    _apply_time_budget(env, task)
    push_event({"type": "note", "data": "====== start · " + model + " ======"})
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=env, bufsize=1,
                            cwd=workdir)
    STATE["proc"] = proc
    threading.Thread(target=_reader, args=(proc,), daemon=True).start()
    threading.Thread(target=_wait_exit, args=(proc,), daemon=True).start()


def _apply_time_budget(env, task):
    import re
    m = re.search(r"(?:限时|时间限制|within|in under|time limit[: ]*)?(\d+(?:\.\d+)?)\s*(分钟|分钟内|min(?:ute)?s?|hours?|小时|h)\b", task, re.I)
    if m:
        v = float(m.group(1))
        if re.match(r"h|hour|小时", m.group(2), re.I):
            v *= 60
        env["AGENT_TIME_BUDGET_SEC"] = str(int(v * 60))


def _reader(proc):
    for line in proc.stdout:
        line = line.rstrip("\r\n")
        if line.startswith("@@TOK@@"):
            push_event({"type": "tok", "data": line[len("@@TOK@@"):]})
        elif line.startswith("@@THINK@@"):
            push_event({"type": "think", "data": line[len("@@THINK@@"):]})
        elif line.startswith("@@ASK@@"):
            try:
                req = json.loads(line[len("@@ASK@@"):])
            except Exception:
                req = {"question": line[len("@@ASK@@"):]}
            STATE["ask_pending"] = True
            push_event({"type": "ask", "data": req})
        elif line.startswith("@@DISPATCH@@"):
            push_event({"type": "dispatch", "data": line[len("@@DISPATCH@@"):]})
        elif line.strip():
            push_event({"type": "log", "data": line})
    push_event({"type": "exit", "data": proc.poll()})


def _wait_exit(proc):
    proc.wait()
    time.sleep(0.5)
    push_event({"type": "exit", "data": proc.poll()})


def kill_tree():
    proc = STATE.get("proc")
    if proc and proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()


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
            import appconfig
            models = list(appconfig.model_map().keys())
            proc = STATE.get("proc")
            return self._send(200, json.dumps({
                "version": _version(), "busy": bool(proc and proc.poll() is None),
                "models": models, "session": STATE.get("session"),
                "ask_pending": STATE.get("ask_pending", False),
                "prefs": _prefs_public(),
            }, ensure_ascii=False))
        if u.path == "/api/sessions":
            import glob
            sd = os.path.join(os.path.expanduser("~"), ".ollama_agent")
            sd = os.path.join(sd, "") if os.path.isdir(sd) else sd
            files = sorted(glob.glob(os.path.join(os.path.expanduser(os.path.join("~", ".ollama_agent")), "*.json")),
                           key=os.path.getmtime, reverse=True)[:60]
            names = [os.path.basename(f)[:-5] for f in files if not f.endswith(".meta.json")]
            return self._send(200, json.dumps({"sessions": names}))
        if u.path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            idx = max(0, len(STATE["events"]) - 200)
            self.wfile.write(b"retry: 3000\n\n")
            while True:
                with _cond:
                    while idx >= len(STATE["events"]):
                        _cond.wait(timeout=15)
                    new = STATE["events"][idx:]
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
            if STATE.get("proc") and STATE["proc"].poll() is None:
                return self._send(409, json.dumps({"error": "busy"}))
            start_agent(str(body.get("prompt", "")), str(body.get("model", "")),
                        body.get("time_limit"), bool(body.get("resume", True)))
            return self._send(200, "{}")
        if u.path == "/api/stop":
            kill_tree()
            return self._send(200, "{}")
        if u.path == "/api/ask":
            proc = STATE.get("proc")
            ans = str(body.get("answer", "deny"))
            STATE["ask_pending"] = False
            if proc and proc.poll() is None:
                try:
                    proc.stdin.write(ans + "\n")
                    proc.stdin.flush()
                except Exception:
                    pass
            return self._send(200, "{}")
        return self._send(404, "{}")


def _version():
    try:
        return open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except Exception:
        return ""


def _prefs_public():
    prefs = _load_prefs()
    return {"ctx": prefs.get("ctx", 131072), "temp": prefs.get("temp", 0.0),
            "num_predict": prefs.get("num_predict", 2048), "ui_mode": prefs.get("ui_mode", "auto")}


def _load_prefs():
    pf = os.path.join(os.path.expanduser("~"), ".ollama_agent", "gui_prefs.json")
    d = {"ui_mode": "auto", "ctx": 131072, "temp": 0.0, "num_predict": 2048, "think": True}
    try:
        d.update(json.load(open(pf, encoding="utf-8")))
    except Exception:
        pass
    return d


def main():
    port = 8765
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mingbird Web UI: http://127.0.0.1:{port}  (local only · 仅本机访问)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
