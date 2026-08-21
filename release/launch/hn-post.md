# HN — Show HN 帖子草稿

> 标题是 HN 的生命线。备选标题按强度排序。

## 标题(选一)

1. **Show HN: Hummingbird — an AI agent that runs on the laptop you already own**
2. Show HN: A local AI agent built for small models (0.5–9B) on iGPU laptops
3. Show HN: I built an agent harness that compensates for what small models can't do

## 正文

I built a fully-offline AI agent for Windows that's designed around **small models (0.5–9B) on hardware people actually have** — not cloud APIs, not a $2,000 GPU.

I developed and tested it on a laptop with only an **AMD Radeon 680M integrated GPU and 16 GB of RAM (no dGPU)**. It responds almost instantly — as fast as talking to Ollama directly, no perceptible extra wait. 39 benchmark rounds drove the design.

The honest problem with small models is they can't self-correct. So the harness compensates:

- **Precise test feedback** — the harness runs your tests, parses the real failure (file:line, error), and hands it back. Plus automatic `.bak` rollback when a bad edit makes things worse. A 2B model went from stuck-at-42-iterations to recovering in 19 once it got real failures instead of "that didn't work."
- **Flat prefill** — tools load by category on demand (files/code/web/memory/MCP), not all at once. Cuts prefill context 50%+, speeds up every request.
- **Q&A vs task layering** — a greeting doesn't become a 20-step tool demo. Casual chat answers once and stops; real tasks unlock the full tool arsenal.
- **Safety gate** — blocks `rm -rf` and system-path writes. Duplicate tool calls and near-identical loops are intercepted.

Proven end-to-end: 12 long-task records in the README — a **2B model** built a 19-test library, did cross-category web-research + quicksort, fixed injected bugs; a small MoE built a tool safety gate and model router.

Other bits: streaming with visible thinking that folds away, local STT voice input bundled with the installer (~20× real-time, pure CPU), session memory with search/replay, up to 256K context, skills + MCP extension. No hardcoded models or machine config — everything is configured per-user via `config.json`.

**Honest limits**: a 2B model won't rewrite your codebase in one shot. It reliably does the 80% of everyday agent work — files, research, scripts, tests, organizing — and fails loudly when it can't, instead of silently doing the wrong thing.

Two installers: 蜂鸟 (中文) and Hummingbird (EN). Apache-2.0, no telemetry, no account, no cloud.

Downloads: [GitHub](https://github.com/Gustor-Wang/hummingbird-agent) · Release v1.0.0

Curious what people think — especially anyone who's tried local agents on low-end hardware and hit the "it loops forever / it silently does the wrong thing" wall.

## 发布建议

- 挑北京时间工作日上午 ~23:00 UTC(约 7:00 北京)发,或美东上午。
- 首楼就把截图贴出来(`assets/preview-en.png`)。
- 作者在正文下方第一评论补充 1–2 条技术细节(扁平 prefill 如何做上下文路由),显示深度。
