# Hummingbird / 蜂鸟 v1.0.0 — Release Notes

## What is it
A local, small-model-first AI agent for Windows. Runs fully offline on Ollama models (0.5–9B), tuned for modest hardware (AMD Radeon 680M iGPU, 16 GB RAM).

## Highlights
- **Flat prefill architecture**: tools loaded by category on demand → 50%+ context reduction, faster every request.
- **Q&A vs task layering**: casual chat answers instantly; real tasks get full tools. No more "greeting → 20-step tool demo" loops.
- **Resilient harness**: `.bak` rollback, precise test-failure feedback, duplicate-call interception, safety gate (blocks rm -rf / system-path writes).
- **Streaming output + visible thinking** (auto-folding reasoning).
- **Voice input** (local STT ~20× real-time, bundled with the installer), model auto-detection, context up to 256K.
- **VAD auto-stop voice**: just speak — recording ends ~1.2s after you stop talking. No need to click stop.
- **Fully bilingual**: clean English UI in the EN build, clean Chinese UI in the ZH build (no mixed languages).

## Install
1. Install [Ollama](https://ollama.com), pull a model (e.g. `ollama pull gemma4:e2b`).
2. Run the setup.exe → "Hummingbird" desktop shortcut.
3. Launch, pick a model, chat or assign a task.

## Languages
- **EN**: `Hummingbird-v1.0.0-EN-Setup.exe` (English UI)
- **ZH**: `Hummingbird-v1.0.0-ZH-Setup.exe` (中文界面)

## Docs
- `AGENTS.md` — full manual for AI agents (install skills / MCP / model selection)
- `README_EN.md` / `README.md`

## License
Apache-2.0
