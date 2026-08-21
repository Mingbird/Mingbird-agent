# 🐦 Hummingbird · Local AI Assistant

**An AI agent that runs on the laptop you already own.**

[中文版](README_zh.md) · Apache-2.0 · Windows 10/11

![preview](https://raw.githubusercontent.com/Gustor-Wang/hummingbird-agent/main/assets/preview-en.png)

Most agent frameworks assume you have a cloud API or a $2,000 GPU. Hummingbird is the opposite: a **capable, fully-offline agent built for small models (0.5–9B) on modest hardware** — the kind most people actually own. We built and tested it on a laptop with an **AMD Radeon 680M integrated GPU and 16 GB of system RAM (no discrete GPU)** — and it responds almost instantly, as fast as talking to Ollama directly, with no perceptible extra wait.

## The problem we set out to solve

**1–4B local models simply cannot run in a traditional agent.** We found this out the hard way: mainstream agent frameworks (built for cloud-scale models) choke on a 2B model — the full tool prefill blows the context budget, the model can't self-correct, and it spins into tool-call loops. And the few agents that *are* tuned for small models turned out, in our testing, to have **no reliable long-task capability** — they either "demo" tools instead of doing real work, or silently die on multi-step tasks.

**Our main contribution: ultra-small models (0.5–9B) can now reliably complete long, complex tasks.** Not by pretending small models are big models, but by building a harness that compensates for exactly what they can't do — run the tests for them and feed back precise failures (`file:line`), roll back bad edits automatically (`.bak`), stop tool-demo loops before they start (Q&A/task layering), and load only the tools each task needs (flat prefill, −50%+ context).

This isn't a wrapper. It's an agent **harness designed around what small models can and can't do**, proven across **39 benchmark rounds (V1–V39)** — every version is a real task run end-to-end on real models.

## Proven: 12 successful long-task records

Every row below is a **real task completed end-to-end on a model in the 2–4B range** (or a small MoE), with tests actually passing:

| # | Model | Task (what was done) | Result |
|---|---|---|---|
| 1 | **qwen3.5:2b** (2B) | From a blank folder, built a data-analysis utilities library (mean / median / std-dev / mode / etc.), wrote 19 unit tests, ran them until green | ✅ 19/19 tests pass, full report |
| 2 | **qwen3.5:2b** (2B) | Same library, but under **flat prefill** (only the relevant tool categories loaded) | ✅ 23/23 tests pass — flat prefill works |
| 3 | **qwen3.5:2b** (2B) | **Cross-category long task**: researched quicksort algorithms online (5 real web searches), then implemented the sort and its tests | ✅ 10/10 tests pass |
| 4 | **qwen3.5:2b** (2B) | Fixed **4 deliberately injected bugs** in a provided program (with `.bak` auto-rollback as safety net) | ✅ 4/4 tests green |
| 5 | **gemma4:e2b** (4B) | Built the data-analysis utilities library, wrote 15 unit tests, ran them to green | ✅ 15/15 pass, full report |
| 6 | **gemma4:e2b** (4B) | Web research: performed 3 real searches, synthesized a 2.9 KB report with sources | ✅ report complete |
| 7 | **gemma4:e2b** (4B) | Fixed **4 injected bugs** (with `.bak` safety net) | ✅ 4/4 tests green |
| 8 | **Mellum2** (small MoE) | Built the data-analysis utilities library, 11 unit tests | ✅ 11/11 pass |
| 9 | **Mellum2** (small MoE) | **Memory relay**: stored 3 facts in one session, recalled all 3 in a later turn | ✅ 3/3 recalled, report |
| 10 | **Mellum2** (small MoE) | Implemented a **tool safety gate** that blocks destructive commands (`rm -rf`, system-path writes) | ✅ 9/9 tests pass |
| 11 | **Mellum2** (small MoE) | Implemented a **model router** that routes a task to the right model by category | ✅ 9/9 tests pass |
| 12 | **qwen3.5:4b** (4B) | Performance optimization: rewrote an O(N²) sort to O(N log N) | ✅ ~2000× faster, 10 tests pass |

## Why small models deserve a real agent

Small models are honest about their limits — and the harness compensates for them:

- **They can't debug their own code.** So the harness runs your tests, parses the exact failure (file/line/error), and feeds it back. Automatic `.bak` rollback if a bad edit makes things worse.
- **Context is precious.** So tools are loaded *by category, on demand* (files / code / web / memory / MCP) instead of all-at-once. This cuts prefill context by 50%+ and speeds up every request.
- **They demo instead of doing.** A casual "hello" can spiral into a 20-step tool-call loop. So Q&A is detected and kept light — answer once, stop — while real tasks unlock the full tool arsenal.
- **They repeat themselves.** Duplicate tool calls and near-identical loops are intercepted and force-finished.

## What it does

- **Fully offline** — your data never leaves the machine. No account, no telemetry, no cloud.
- **Near-instant responses** — flat prefill + Q&A layering keep overhead so low that answers stream at nearly the speed of talking to Ollama directly.
- **Real tasks**: write code and run tests, manage files, research the web, analyze data, run MCP tools.
- **Streaming + visible thinking** — you watch it reason, then the reasoning folds away and the answer streams.
- **Voice input, bundled** — a local STT model ships with the installer (~20× real-time, pure CPU).
- **Session memory** — conversations persist, are searchable, and can be replayed.
- **Model auto-detection** — picks up whatever models you've pulled in Ollama, up to 256K context.
- **Extensible** — install skills (markdown → the model loads them on demand) and MCP servers. `AGENTS.md` is a how-to written for other agents.

## Getting started

1. Install [Ollama](https://ollama.com) and pull a model:
   ```
   ollama pull gemma4:e2b      # 4B, fast
   ollama pull qwen3.5:2b      # 2B, 256K context
   ```
2. Run the setup (`Hummingbird-v1.0.0-EN-Setup.exe`) → desktop shortcut.
3. Launch, pick a model, and just talk — or give it a task.

> **No hardcoded models or machine config.** Everything is detected at runtime or configured in `~/.ollama_agent/config.json` (see `AGENTS.md` §4.1): Ollama address, ollama executable, GPU acceleration env vars, and friendly model names — you set it up for *your* machine.

## Picking a model for your hardware

| Machine | Recommended |
|---|---|
| Entry (8 GB RAM, CPU-only) | `qwen3:0.6b` / `gemma3:1b` |
| Mainstream (iGPU laptop) | `gemma4:e2b` (fast) / `qwen3.5:2b` (long context) |
| More RAM / a dGPU | larger MoE models also run fine |

Small models benefit most from **long context** — it's their memory.

## Installing skills & MCP

- **Skills**: drop a markdown file with `---` frontmatter into `skills/` (next to the exe, or `~/.ollama_agent/skills/`). The agent loads only the summary until a skill is actually needed.
- **MCP**: add a server to `~/.ollama_agent/mcp.json` — plain JSON, documented in `AGENTS.md`.

`AGENTS.md` is written for AI agents and walks through both, with format examples.

## Architecture (the short version)

```
AgentGUI (ttkbootstrap, i18n EN/中文)
   │  AGENT_STREAM=1
   ▼
ollama_agent.py — the loop
   ├─ classify: Q&A (chat system + read-only tools, answer once)
   │             vs task (full harness)
   ├─ route: task → categories (文件/代码/网络/记忆/MCP) → load only those tools
   ├─ execute: tool calls with schema validation
   ├─ verify: run tests → parse real failures (file:line) → feed back
   ├─ guard: safety gate (blocks rm -rf / system paths), duplicate-call interception
   └─ persist: sessions + checkpoints for resume
```

## Development

```
pip install -r requirements.txt
python ollama_agent.py --help     # CLI
python agent_gui.py               # GUI
```

## Honest limits

A 2B model will not rewrite your codebase in one shot. It will reliably do the 80% of everyday agent work — and fail loudly (instead of silently wrong) when it can't.

## License

Apache-2.0 — free to use, modify, and redistribute.
