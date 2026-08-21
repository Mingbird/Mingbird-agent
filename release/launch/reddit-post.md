# Reddit 发布稿

> 分两个 sub 发,措辞差异化:r/LocalLLaMA(技术向)、r/selfhosted(自托管向)。
> 建议错开 24h 发,避免双发被降权。

## r/LocalLLaMA 版 —— 技术向

**标题**: I built an agent harness for small models on iGPU laptops — and it fixed the "my 2B model loops forever" problem

**正文**:

Spent months building a local agent for small models (0.5–9B) on a laptop with only an AMD Radeon 680M integrated GPU and 16 GB of RAM (no dGPU, no cloud). It responds almost instantly — as fast as talking to Ollama directly.

The whole design came out of one recurring failure mode: **small models don't debug their own code.** They hit an error, guess, and either loop or silently produce garbage. So the harness does the compensating:

1. **The harness runs the tests itself**, parses the real failure (`FAILED test_x.py::f — File "x", line N, E ...`), and injects it back as a precise instruction. Plus `.bak` rollback — every edit is backed up, so a "recovery" is one restore away. In one experiment a 2B model was stuck past 42 iterations without it, and recovered in 19 with it.
2. **Flat prefill by category.** Tools are tagged 文件/代码/网络/记忆/MCP. A task routes to its relevant categories and only those tools load — ~8–12 tools instead of 17+. Prefill context drops by half, requests get faster. Skills are progressively disclosed (name + one line only, full text loaded on demand).
3. **Q&A vs task classification.** This killed the classic "greeting → 20-step tool demo" death spiral. Chat system prompt + read-only tools, answer once, force-finish. Tasks get the full arsenal.

Other stuff: safety gate that blocks `rm -rf` / system-path writes, duplicate-call interception, streaming with folding thinking, bundled local STT (sherpa-onnx, ~20× real-time), sessions with search + replay, up to 256K context, skills + MCP extensibility. No hardcoded models — the GUI lists whatever you have in Ollama, and per-machine config lives in `config.json`.

Validated with a 39-round benchmark (V1–V39): each version is a real task run end-to-end. 12 successful long-task records are in the README — including a **2B model** building a 19-test library, doing cross-category web research + quicksort, and fixing injected bugs.

Repo + Windows installers (蜂鸟 中文 / Hummingbird EN): https://github.com/Gustor-Wang/hummingbird-agent — Apache-2.0, no telemetry.

Happy to talk about the harness design — especially the force-finish heuristics and what "precise failure injection" looks like in practice. What do people here do when their local models go into tool-call loops?

---

## r/selfhosted 版 —— 自托管向

**标题**: Fully-offline AI agent that runs on an iGPU laptop — no GPU, no cloud, no telemetry

**正文**:

Self-hosting the *model* is easy. Self-hosting an *agent that does real work* on modest hardware is the hard part — everything out there assumes a dGPU or a cloud API.

Made a Windows agent that runs entirely on Ollama, built and tested on a laptop with only an AMD Radeon 680M integrated GPU and 16 GB of RAM. It responds almost instantly — no perceptible extra wait vs. talking to Ollama directly. Zero data leaves the machine. No account. No telemetry.

What it does: writes code and runs tests, manages files, researches the web, uses MCP tools. Streaming output with visible thinking that folds away. Local voice input (STT model ships with the installer). Sessions persist, are searchable, replayable. No hardcoded models — it auto-detects what you've pulled in Ollama; per-machine config (Ollama address, GPU env vars, model names) lives in `config.json`.

Built for models 0.5–9B (recommendations in the README). Skills + MCP extension documented in `AGENTS.md`.

Repo: https://github.com/Gustor-Wang/hummingbird-agent · Apache-2.0 · EN + 中文 installers.

Anyone else running agents on iGPUs? Curious what your failure modes are.
