# 🐦 Mingbird

**A local-first agent harness that gets real work out of 2–9B models on integrated graphics.**

It targets Windows + Ollama (experimental Linux/macOS builds) and the models most people can actually run: **2–9B parameters, integrated graphics, 16–32 GB of RAM** (measured up to 35B). No cloud, no account, no telemetry — no outbound connections at all beyond the Ollama/search endpoints you explicitly configure.

[中文版](README_zh.md) · Apache-2.0 · Windows 10/11 · Linux & macOS (experimental) · Offline-first

![Mingbird screenshot](docs/assets/screenshot-app.png)

## The problem we set out to solve

Mainstream agent frameworks are designed for large cloud models. Feed them a 2B local model and everything from the demo videos falls apart: full-tool prefill blows the context, the model cannot self-correct, it loops on tool calls, or quietly gives up halfway through.

**Our claim: these are harness defects, not model defects.** Small models usually know what to do — what they cannot do is reliably output and execute it, step by step. Mingbird is the harness that fills exactly that gap: the same model that only chats elsewhere delivers artifacts here.

## What it can do

- **Real tasks**: write code and run the tests, organize files, web research, analyze data, call MCP tools.
- **Streaming output + visible thinking** — the delivery streams; the thinking folds away once the run is done.
- **Drag-and-drop / paste attachments** — drop a file into the chat or press Ctrl+V: clipboard files and screenshots become attachments on the spot, sent along with your instruction.
- **Voice input out of the box** — the installer bundles a local STT model (pure CPU, ~20× real time) that stops automatically when you stop talking.
- **Task time-box (off by default)** — type `40` / `1.5h` / `half an hour` into the box, or write "限时 40 分钟" (or "timebox 40 minutes") right in the task description (auto-detected, highest priority); the harness nudges the run to wind down as the deadline approaches. Local-model users care about wall-clock time.
- **Session memory** — history persists locally; searchable and replayable.
- **Model auto-detection** — whatever you pulled in Ollama is what you use, up to 256K context.
- **Skills & MCP** — markdown skills load on demand; MCP servers are plain JSON config.
- Bilingual UI (English / 中文).
- **Web UI (experimental)** — the same agent in your browser, local-only, 127.0.0.1 only ([guide](docs/webui.md)).
- **One-click installer**, or run from source.

## What makes it different

Every mechanism comes from "small models can't do X, so the harness does it for them":

| Small models can't… | Mingbird does it for them |
|---|---|
| …self-debug | the harness runs the tests itself and feeds back exact failures (`file:line` + the original error text) |
| …edit code safely | every change is auto-backed up (`.bak`); rollback is one command |
| …escape tool-demo loops | Q&A/task layering (chat answers once and stops) + signature-level anti-loop with an escalating ladder: nudge → hard reset → graceful exit |
| …fit all tools in context | flat prefill loads by category; factory prefill is exactly 797 tokens, and CI fails any change that grows it by a single byte |
| …emit a large file in one call | per-call output cap is 8192 (was 2048); when truncation still bites, the model gets "write the skeleton, then append" chunked feedback instead of an empty-turn spiral |
| …stop crawling through huge files | crawl guard v2 works on a byte budget (2× file size, clamped to 64KB–512KB) — it never refuses |
| …stay on target in long tasks | delivery self-check gate: before claiming done, it re-reads the original task and verifies its work |
| …resist destructive impulses | a five-ring safety net catches them (see [Safety](#safety)) |

Nothing is hardcoded: the Ollama address, executable, GPU environment variables, and model aliases are detected at runtime or configured in `~/.ollama_agent/config.json` (see [AGENTS.md](AGENTS.md)). The quality floor is held up by 441 tests in v1.6.0, the prefill zero-growth assertion included.

## Measured: same model, different harness

Layer 1 is the whole picture in four lines; layer 2 gives the design, the table, and the caveat for each benchmark; layer 3 points at the raw data.

**Layer 1 — at a glance:**

| Benchmark | Run by | Result in one line |
|---|---|---|
| LRAB-288 | us (self-built) | overall 0.886 vs goose 0.631 / opencode 0.479 / agent-mini 0.405 |
| τ²-bench, 3 domains | Sierra Research (external) | retail 0.763 / airline 0.740 / telecom 1.000 — first everywhere; goose re-run in progress |
| Ablations (v1.5.0 code) | us | removing `finish_gate` costs the most: −0.098 |

### LRAB-288 (our benchmark)

4 harnesses (Mingbird / goose / agent-mini / opencode, all stock) × 4 open models (gemma4:e2b 2B · qwen3.5:4b 4B · gemma4:12b 12B · ornith-1.5:35b 35B) × 18 real tasks = 288 cells. Same machine, same budgets (workflow 90 min / long-horizon 180 min), deterministic artifact scoring, timeouts score 0.

![By model size](docs/assets/lrab_by_model.png)

| Harness | 2B | 4B | 12B | 35B | **overall** |
|---|---|---|---|---|---|
| **Mingbird** | **0.821** | **0.876** | **0.906** | **0.941** | **0.886** |
| goose | 0.271 | 0.801 | 0.772 | 0.679 | 0.631 |
| agent-mini | 0.246 | 0.706 | 0.576 | 0.092 | 0.405 |
| opencode | 0.017 | 0.465 | 0.539 | 0.896 | 0.479 |

- **The 2B column is the story**: 0.821 vs 0.017–0.271 — of the four harnesses, the only one with no small-model cliff, and 2B is the size an iGPU laptop runs comfortably.
- **Significance** (Holm-corrected Wilcoxon, paired by task): the edge over all three competitors is significant on 2B and 12B; at 4B only opencode separates (goose closes to 0.801 with thinking off, p=0.33), and at 35B goose and agent-mini separate while opencode (0.896) does not. We state both directions.
- On the 3 long-horizon tasks (LH-01…03, 180-minute budget each), Mingbird leads as well (0.827 vs 0.484 / 0.394 / 0.354).

*All four arms run under one protocol — temperature 0 with thinking off, pinned at the transport layer; goose/opencode re-shot 2026-09-18..20 with their binaries untouched. Self-built benchmark, 18 tasks — the task set, scoring code, and per-cell data are all public; rerun it yourself.*

### τ²-bench, three domains (external)

Sierra Research's [τ²-bench](https://github.com/sierra-research/tau2-bench), all three domains, under the same unified protocol as LRAB: temperature 0 with thinking off (pinned at the transport layer, verified end-to-end). The agent is the same local `qwen3.5:4b` (Ollama), pass^1, error cells score 0, and scoring checks the final database state — an agent that fakes tool calls fails the DB replay.

![tau2](docs/assets/tau2_headline.png)

| Harness | retail (114) | airline (50) | telecom (114) |
|---|---|---|---|
| **Mingbird** | **0.763** | **0.740** | **1.000** |
| τ² native agent | 0.675 | 0.740 | 0.930 |
| opencode | 0.588 | 0.500 | 0.991 |
| goose | re-run in progress | — | — |

The completed arms finished with zero errored trials. The thinking configuration moves these numbers a lot (opencode's telecom is 0.298 thinking-on vs 0.991 thinking-off) — itself a harness-level effect. The goose column is being re-collected under the unified protocol and will land here when done.

*The user simulator is cloud `qwen3.8-flash`, identical for every harness — not the official gpt-4o user setup, so these runs are not comparable with the official τ² leaderboard.*

### Ablations: which mechanism pays for itself (v1.5.0 code)

18 LRAB tasks, `gemma4:e2b`, one mechanism disabled per variant via the `AGENT_ABLATION` environment gate; baseline = the same-code all-mechanisms arm (0.821).

| Variant | total (18 tasks) | Δ vs baseline |
|---|---|---|
| all mechanisms on (baseline) | 0.821 | — |
| − finish_gate | 0.723 | **−0.098** |
| − verify_feedback | 0.772 | −0.048 |
| − anti_loop | 0.805 | −0.015 |
| − flat_prefill | 0.818 | −0.003 |

Two mechanisms carry most of the effect (`finish_gate`, the verify-feedback loop); the other two are cheap insurance — anti-loop and flat prefill (the latter is neutral at 2B).

*Each arm is 18 cells, so read this as directional. The 0.821 baseline is not a separate control: it is the 2B column of the LRAB-288 table above — same 18 cells, same v1.5.0 code, one batch.*

**Layer 3 — verify it yourself.** All raw data is public in [benchmarks/](benchmarks/README.md):

- [`benchmarks/lrab_scores.csv`](benchmarks/lrab_scores.csv) — all 288 cells (harness, task, model, score, wall time)
- [`benchmarks/tau2/`](benchmarks/tau2) — per-trial manifests, all three τ² domains
- [`benchmarks/ablation/`](benchmarks/ablation) — ablation per-cell scores (5 arms × 18 tasks)

## Hardware

Measured on real machines, not estimated:

| Tier | Hardware | Models | Experience |
|---|---|---|---|
| Entry | AMD 680M iGPU · 16 GB RAM | 2–4B | streaming, near raw-Ollama speed |
| Base | Intel Arc B390 iGPU · 32 GB RAM | 2–35B | 35B long tasks run end-to-end |

An integrated GPU or an entry-level discrete GPU is enough; higher-end cards work too. The only thing Mingbird adds to the model is its own static text: 797 tokens.

## Getting started

Mingbird runs in **four ways** — same engine everywhere, pick what fits:

| You want | How |
|---|---|
| Windows desktop client | `Mingbird-v1.6.0-EN-Setup.exe` / `-CN-Setup.exe` from [Releases](https://github.com/Mingbird/Mingbird-agent/releases) |
| Linux / macOS desktop client (experimental) | CI-built tarballs from Releases → `sh install-unix.sh` |
| From source (desktop GUI) | `pip install -r requirements.txt` → `python agent_gui.py` |
| **Web UI in your browser** (experimental) | `pip install -r requirements.txt` → `python webui/server.py` → open http://127.0.0.1:8765 — [guide](docs/webui.md) |

All of them share sessions, skills, MCP servers and settings.

1. Install [Ollama](https://ollama.com) and pull a model:
   ```bash
   ollama pull gemma4:e2b      # small and fast
   ollama pull qwen3.5:4b      # 4B, the benchmark workhorse
   ```
2. Grab `Mingbird-v1.6.0-EN-Setup.exe` (or `-CN` for the Chinese UI) from [Releases](https://github.com/Mingbird/Mingbird-agent/releases), install → desktop shortcut.
   Windows may show SmartScreen for an unsigned installer — "More info" → "Run anyway".
3. Launch, pick a model, hand it work.

Linux & macOS (experimental, CI-built): download `mingbird-v1.6.0-linux-x64.tar.gz` or `mingbird-v1.6.0-macos-arm64.tar.gz` from [Releases](https://github.com/Mingbird/Mingbird-agent/releases), extract, run `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`. Ollama must be installed on that machine.

From source: `python agent_gui.py` (GUI) or `python ollama_agent.py --help` (CLI). Python 3.12 recommended.

## Privacy

No telemetry, no account, no outbound connections beyond the Ollama/search endpoints you explicitly configure. Sessions and settings stay in ~/.ollama_agent.

## Safety

> [!WARNING]
> Mingbird reads and writes files on your disk and runs commands. Choose a working directory with care.

v1.6.0 ships a five-ring safety net, because impulsive uninstalls and blanket deletes are observed small-model failure modes, not hypotheticals:

| Ring | What it does |
|---|---|
| 0 · Sub-agent sandbox | parallel sub-agents are default-deny and always hold strictly fewer permissions than the main agent |
| 1 · Irreversible ops refused | `format`, `diskpart`, `vssadmin delete shadows`, `dd` to raw devices, `wsl --unregister`, `dism`, driver uninstall, `userdel` — refused outright |
| 2 · Behavior tiering | software uninstalls / system environment changes: confirm each while attended, deny by default when unattended (`AGENT_ALLOW_ENV_MUTATION=1` to opt in) |
| 3 · Boundary confirmation | recursive deletes stay inside the working directory; out-of-bounds refusals come with a per-file way out |
| 4 · Rollback everywhere | `.bak` before writes; `delete_file` lands in `.mingbird_trash/`; overwriting a large existing file with much shorter content needs an explicit `replace=true` |

Escape hatch: `AGENT_UNSAFE=1` turns the whole net off — at your own risk.

## Honest limits

- A 2B model will not rewrite your entire codebase in one shot — but it handles the bulk of everyday agent work, and when it cannot, it fails loudly instead of failing silently.
- 35B on an iGPU runs end-to-end but is not fast (~26 tok/s at 128K context).
- Linux and macOS packages are experimental CI builds; Windows is the primary platform.
- LRAB is a benchmark we designed ourselves — which is exactly why the tasks, the scoring code and the raw per-cell data are public: rerun it yourself instead of taking our word for it.

## License

Apache-2.0 — free to use, modify, and distribute.
