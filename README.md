# 🐦 Mingbird

**Small local models on your laptop that actually finish the job — not just chat.**

Mingbird is a local-first agent harness for Windows + Ollama (experimental Linux/macOS builds), designed for the models most people can actually run: **2–9B parameters on integrated graphics and 16–32 GB of RAM** (measured up to a 35B MoE). No cloud, no account, no telemetry (no outbound connections at all beyond the Ollama/search endpoints you explicitly configure); an integrated or entry-level discrete GPU is all it asks.

[中文版](README_zh.md) · Apache-2.0 · Windows 10/11 · Linux & macOS (experimental) · Offline-first

![Mingbird screenshot](docs/assets/screenshot-app.png)

## The problem we set out to solve

Mainstream agent frameworks are designed for large cloud models. Feed them a 2B local model and everything from the demo videos falls apart: full-tool prefill blows the context, the model cannot self-correct, it loops on tool calls, or quietly gives up halfway through.

**Our position: these are harness defects, not model defects.** Small models usually "know what to do" — what they cannot do is reliably "emit and execute" it. Mingbird is the harness that fills exactly that gap — the same model that only chats elsewhere starts getting work done here.

## What it can do

- **Real tasks**: write code and run the tests, organize files, web research, analyze data, call MCP tools.
- **Streaming output + visible thinking** — watch it reason, then the thinking folds away and the answer flows.
- **Drag-and-drop / paste attachments** — drop a file into the chat or press Ctrl+V: clipboard files and screenshots become attachments on the spot, sent along with your instruction.
- **Voice input out of the box** — the installer bundles a local STT model (pure CPU, ~20× real time) that stops automatically when you stop talking.
- **Task time-box (off by default)** — type `40` / `1.5h` / `half an hour` into the box, or write "限时 40 分钟" (or "timebox 40 minutes") right in the task description (auto-detected, highest priority); the harness nudges the run to wind down as the deadline approaches. Local-model users care about wall-clock time — deadlines are a first-class setting.
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
| …stop crawling through huge files | crawl guard v2 works on a byte budget (2× file size, clamped 64KB–512KB) — it never refuses, progress keeps flowing |
| …stay on target in long tasks | delivery self-check gate: before claiming done, it re-reads the original task and verifies its work |
| …resist destructive impulses | a five-ring safety net catches them (see [Safety](#safety)) |

Zero hardcoding: Ollama address, executable, GPU environment variables, model aliases — all detected at runtime or configured in `~/.ollama_agent/config.json` (see [AGENTS.md](AGENTS.md)). Quality floor: 441 tests in v1.6.0, the prefill zero-growth assertion included.

## Measured: same model, different harness

### LRAB-288 (our benchmark, raw data public)

4 harnesses (Mingbird / goose / agent-mini / opencode, all stock) × 4 open models (gemma4:e2b 2B · qwen3.5:4b 4B · gemma4:12b 12B · ornith-1.5:35b 35B MoE) × 18 real tasks = 288 cells. Same machine, same budgets (workflow 90 min / long-horizon 180 min), deterministic artifact scoring, timeouts score 0.

![By model size](docs/assets/lrab_by_model.png)

| Harness | 2B | 4B | 12B | 35B MoE | **overall** |
|---|---|---|---|---|---|
| **Mingbird** | **0.799** | **0.921** | **0.920** | **0.939** | **0.895** |
| goose | 0.266 | 0.636 | 0.620 | 0.822 | 0.586 |
| agent-mini | 0.246 | 0.706 | 0.576 | 0.092 | 0.405 |
| opencode | 0.017 | 0.404 | 0.140 | 0.776 | 0.334 |

- **The 2B column is the story**: 0.799 vs 0.017–0.266 — the only harness with no small-model cliff, at exactly the size laptops can run. On the 3 long-horizon tasks Mingbird also leads (0.808).
- **Significance** (Holm-corrected Wilcoxon, paired by task): the edge is significant on 2B/4B/12B. At 35B the field compresses — Mingbird vs goose is p=0.085, not significant. We state that bound as-is.
- **Ablations** (v1.5.0 code, same-code baseline 0.821, 18 tasks × 4 variants): remove `finish_gate` → 0.723 (−0.098, the largest single cost) · remove `verify_feedback` → 0.772 (−0.049) · remove `anti_loop` → 0.805 (−0.016) · remove `flat_prefill` → 0.818 (−0.003, neutral at 2B). All four mechanisms are non-negative. (Separate batch from the 0.895 above; the two are not comparable.)

### τ²-bench, three domains, four harnesses (external)

Sierra Research's [τ²-bench](https://github.com/sierra-research/tau2-bench), all three domains, final. Identical setup for every harness: the agent is the same local `qwen3.5:4b` (Ollama), the user simulator is cloud `qwen3.8-flash` for all four, pass^1, error cells score 0, and scoring checks the final database state — an agent that fakes tool calls fails the DB replay.

![tau2](docs/assets/tau2_headline.png)

| Harness | retail (114) | airline (50) | telecom (114) |
|---|---|---|---|
| **Mingbird** | **0.789** | **0.740** | **1.000** |
| τ² native agent | 0.640 | 0.520 | 1.000 |
| goose | 0.588 | 0.460 | 0.377 |
| opencode | 0.246 | 0.460 | 0.298 |

telecom is a saturated domain — the two leaders both take full marks, so it separates nothing; we report it as-is rather than picking a friendlier cut.

### The number we don't like

BFCL v3 multi_turn (800 tasks, same 4B model, official evaluator): **Mingbird 36.25% vs the model's native function-calling channel 46.50%**. On a 4B, a dedicated FC channel beats a general agent loop — the cost of generality, disclosed as-is.

All raw data is public: [`benchmarks/lrab_scores.csv`](benchmarks/lrab_scores.csv) (288 cells), the τ² three-domain manifests, and the BFCL two-arm scoring details — [benchmarks/](benchmarks/README.md).

## Hardware

Measured on real machines, not estimated:

| Tier | Hardware | Models | Experience |
|---|---|---|---|
| Entry | AMD 680M iGPU · 16 GB RAM | 2–4B | streaming, near raw-Ollama speed |
| Base | Intel Arc B390 iGPU · 32 GB RAM | 2–35B (MoE) | 35B long tasks run end-to-end |

An integrated GPU or an entry-level discrete GPU is enough; higher-end cards naturally work too. Mingbird does not wrap or proxy the model — its own static prefill is 797 tokens.

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

- A 2B model will not rewrite your entire codebase in one shot — but it handles the bulk of everyday agent work, and when it cannot, it fails loudly (rather than silently wrong).
- On BFCL multi_turn, the general loop scores below the model's native FC channel (36.25% vs 46.50%).
- 35B on an iGPU runs end-to-end but is not fast (~26 tok/s at 128K context).
- Linux and macOS packages are experimental CI builds; Windows is the primary platform.
- LRAB is a benchmark we designed ourselves — which is exactly why the tasks, the scoring code and the raw per-cell data are public: rerun it yourself instead of taking our word for it.

## License

Apache-2.0 — free to use, modify, and distribute.
