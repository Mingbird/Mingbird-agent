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

## Layout

The browser UI mirrors the desktop app: a conversation sidebar on the left,
chat and composer in the centre, and a plan drawer on the right.

- **Conversation sidebar** — past sessions grouped by Today / Yesterday /
  Earlier, with instant search. Click one to load it (the next message appends
  to that session), or use **New chat** for a fresh one.
- **Chat** — choose a model from the header pill, type a task, and press
  `Enter` (`Shift+Enter` for a new line; IME composition is guarded). Output streams token by token; thinking is
  visible in a collapsible block and folds away when the answer starts.
  **Stop** kills the run; **Resume** continues the interrupted task.
- **Header pills** — model, thinking (default/on/off), online/offline, and the
  plan chip. The plan chip only appears when the agent has a todo list; click
  it to open the right-hand drawer with progress and the current item.
- **Settings** — a modal with context window, temperature (empty = Ollama
  default), output limit, thinking selector, custom system prompt, and the
  optional **Cloud API** protocol. Prefs are stored in
  `~/.ollama_agent/gui_prefs.json` (shared with the desktop app); the engine and
  cloud provider live in `config.json` and are shared too.
- **Cloud API (optional)** — Settings → Cloud API: endpoint, API key and model
  name for any OpenAI-compatible service. Cloud and local models are mutually
  exclusive; when a cloud model is active the offline toggle is disabled,
  because cloud inference needs the network. The `☁` pill switches back.
- **Themes & language** — auto/light/dark and English/中文 in the sidebar
  footer, remembered locally.
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
| Model list wrong or duplicated | The server process predates the fix — restart `python webui/server.py` and hard-refresh the page (Ctrl+F5). Fresh builds show exactly the installed models. |
| Chat repeats old content after reconnect | Old builds replayed the event backlog; current builds stream only new events — update. |
| Settings changed in browser don't affect the desktop app | Both read the same file at *next task start*; a running task keeps its settings. |

## Where things live

| Data | Location |
|---|---|
| Sessions | `~/.ollama_agent/sessions/*.json` |
| Settings (both frontends) | `~/.ollama_agent/gui_prefs.json` |
| Engine & cloud provider (both) | `~/.ollama_agent/config.json` |
| Task working directory | `~/agent_tasks/work` (per-run switching is desktop-only for now; the Web UI always uses the default) |
