# Web UI guide

Mingbird gives you **two frontends over the same agent core**: the desktop app
(`agent_gui.py`, shipped in the installers) and a **local Web UI**
(`webui/server.py`) that runs in your browser. Both drive the same engine
(`ollama_agent.py`), so sessions, skills, MCP servers and settings are shared.

## Starting the Web UI

Requirements: Python 3.12, [Ollama](https://ollama.com) with at least one model
pulled. From the repository root:

```
pip install -r requirements.txt      # once
python webui/server.py               # serves http://127.0.0.1:8765
python webui/server.py --port 9000   # custom port
```

Open the printed address in your browser. The server binds to **127.0.0.1
only** — nothing is reachable from the network, there is no account and no
telemetry. Do not tunnel or port-forward it: the Web UI has no authentication
and is designed to stay on your machine.

## What works in the browser

- **Chat page** — pick a model, type a task, `Ctrl+Enter` (or `Cmd+Enter`) to
  send. Output streams token by token; thinking is visible in a collapsible
  block and folds away when the answer starts. `Stop` kills the run,
  `Resume` continues the interrupted task, `New chat` starts a fresh session.
- **History page** — lists past sessions; *Load & resume* continues a session
  in the browser (the next message appends to it), *View transcript* shows the
  raw messages.
- **Settings page** — context window, temperature, output limit, thinking
  toggle, custom system prompt. Stored in `~/.ollama_agent/gui_prefs.json`,
  **shared with the desktop app**: change it in one place, the other picks it
  up on the next task.
- **Plan (todo) panel** — the agent's live todo list, same as the desktop
  side panel.
- **Themes & language** — auto/light/dark theme, English/中文 toggle, both
  remembered locally.
- **Time-box** — write "40 minutes" / "限时 40 分钟" in the task text and the
  run steers to wind down on time, same as the desktop.

## What the desktop app has that the Web UI does not (yet)

- Voice input (the bundled STT model is wired into the desktop app only).
- Drag-and-drop / paste-to-attach of files and screenshots.
- The attachments panel; web attachment upload is on the roadmap.

Everything else — tool execution, safety gates, session memory, MCP, skills —
is the same engine, so behavior matches the desktop.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Ollama ✗" red dot, model dropdown greyed | Ollama is not running (`ollama serve`) or has no models (`ollama pull qwen3.5:4b`). It self-heals once Ollama is up. |
| Port already in use | `python webui/server.py --port 9000` |
| Chat repeats old content after reconnect | Old builds replayed the event backlog; current builds stream only new events — update. |
| Settings changed in browser don't affect the desktop app | Both read the same file at *next task start*; a running task keeps its settings. |

## Where things live

| Data | Location |
|---|---|
| Sessions | `~/.ollama_agent/sessions/*.json` |
| Settings (both frontends) | `~/.ollama_agent/gui_prefs.json` |
| Task working directory | `~/agent_tasks/work` (per-run switching is desktop-only for now; the Web UI always uses the default) |
