# Product Hunt 列表草稿

## 产品名

Hummingbird (蜂鸟)

## Tagline

*An AI agent that runs on the laptop you already own — small models (0.5–9B), smart harness, fully offline.*

备选: *A capable offline agent for laptops without a GPU.*

## 首屏图(第 1 张)

`assets/preview-en.png` — 最大化窗口 UI:欢迎语 + 侧栏 + 流式对话。
备用(选 3–5 张):
2. 任务执行中的日志页(带思考折叠)
3. 会话列表 + 搜索
4. 语音按钮(含已转录示例)
5. 中文界面

## 描述(Description,<=255 字符,英文)

> An AI agent built for small models (0.5–9B) and iGPU laptops. Fully offline. The harness runs your tests, parses real failures, rolls back bad edits, and stops tool-call loops. Skills + MCP. Ships with local STT. Apache-2.0.

## 正文(Description full)

**Most agent frameworks assume a cloud API or a $2,000 GPU. Hummingbird is for the laptop you already own.**

Fully offline, no account, no telemetry. Runs on Ollama with models 0.5–9B — built and tested on a laptop with an **AMD Radeon 680M integrated GPU and 16 GB of RAM**, and it responds almost instantly: as fast as talking to Ollama directly, no extra wait.

**Why it works where small models usually fail:**
- **It runs your tests.** The harness parses the real failure (file:line, error) and feeds it back — plus `.bak` rollback on every edit. A 2B model went from stuck-past-42-iterations to recovering in 19.
- **Flat prefill.** Tools load by category on demand — 50%+ less context, faster every request.
- **Q&A vs tasks.** A greeting answers once and stops. Real tasks unlock the full tool arsenal.
- **Safety gate + loop interception.** `rm -rf` is blocked. Repeating itself gets stopped.

**Proven:** 12 long-task records end-to-end — a 2B model built a 19-test library, did cross-category web research + quicksort, fixed injected bugs; a small MoE built a tool safety gate and model router.

**Extensible:** skills (markdown, loaded on demand) + MCP servers. `AGENTS.md` is a how-to written for other agents. **No hardcoded models** — the GUI auto-detects your Ollama models; per-machine config lives in `config.json`.

**Ships ready:** bundled local voice input (~20× real-time), streaming with folding thinking, session memory with search & replay, up to 256K context.

Open source, Apache-2.0. 中文版:蜂鸟。Windows 10/11.

## First comment(置顶评论,营造讨论)

> I built this because every agent I tried assumed I had a dGPU or a cloud budget. A 2B model won't rewrite your codebase in one shot — but with a harness that feeds it real test failures, stops loops, and rolls back bad edits, it reliably does the 80% of everyday work. Happy to share the 39-round benchmark methodology and the force-finish heuristics. What's your experience running local agents on low-end hardware?

## 话题标签

#AI #DeveloperTools #OpenSource #Productivity #Privacy

## 发布建议

- 选美西周二–周四上午(Product Hunt 最佳)。
- 需要 Launch 页/截图横幅;若账户级别不够,先用 Community 帖预热。
