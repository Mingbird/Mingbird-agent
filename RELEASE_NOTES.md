## 🇨🇳 中文

# 鸣鸟 v3.1.6

生态兼容 + 还债版。压缩窗口护栏、MCP 常驻 broker、工具参数归一化、AGENTS.md/SKILL.md 生态兼容。桌面 UI 不变。**672 项测试全绿**（642 + 30 新增）。

- **压缩请求不再超自己的窗**：L2/L3 摘要载荷总量封顶（估算 token ≤ 窗口×0.75），截尾保近——最近的决策与产物名保留；长会话的摘要请求此前会被服务端拒绝且完全不可见（611 格实验日志实锤 8~13K token 超窗请求）。
- **压缩失败降级而非装作压过**：摘要调用失败时退回 L1 机械截断，上下文必然实际下降、运行可继续，不再"压完还是原样"。
- **MCP 常驻 broker**：stdio 服务器每任务 spawn+握手一次（此前每调用一次，每次 1.7~5.7s）；tools/list 会话内缓存，manifest 刷新复用活会话；任何失败自动回退旧单次路径，`AGENT_MCP_BROKER=0` 可关闭。
- **工具参数归一化**：坏 JSON 修复（剥 think 泄漏/提取平衡块/修尾逗号与 Python 字面量与单引号），修不好就拒绝执行并回喂原因——告别"静默空参硬跑报 KeyError"。
- **生态兼容**：工作目录 AGENTS.md/CLAUDE.md 项目指令注入；agentskills.io 的 SKILL.md 文件夹技能直接可读（渐进披露：列表只露 name+description）；winget 清单工具就位（提交 winget-pkgs 人工执行）。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.6-CN-Setup.exe`（中文）或 `Mingbird-v3.1.6-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.6-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.6-macos-arm64.tar.gz`，同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.6

Ecosystem-compatibility + debt-repayment release: compaction window guard, MCP resident broker, tool-argument normalization, AGENTS.md/SKILL.md ecosystem compat. Desktop UI unchanged. **672 tests green** (642 + 30 new).

- **Compaction can no longer outgrow its own window**: the L2/L3 summary payload is now capped at an estimated ≤75% of the window with tail-keeping — recent decisions and artifact names survive. Previously a long session's own compaction request was rejected by the server and the failure was invisible (8–13K-token requests in campaign logs).
- **Compaction failure degrades instead of pretending**: on summary failure the harness falls back to L1 mechanical truncation — context always actually shrinks and the run continues.
- **MCP resident broker**: stdio servers spawn and handshake once per task instead of once per call (1.7–5.7s saved each); `tools/list` cached in-session; manifest refreshes reuse live sessions; any failure falls back to the per-call path; `AGENT_MCP_BROKER=0` disables.
- **Tool-argument normalization**: malformed JSON is repaired (think-leak stripping, balanced-block extraction, trailing commas / Python literals / single quotes); unrepairable calls are rejected with the reason fed back — no more silent empty-args runs ending in confusing KeyErrors.
- **Ecosystem compat**: AGENTS.md/CLAUDE.md project instructions injected; agentskills.io SKILL.md folder skills readable directly (progressive disclosure — the list shows name+description only); winget manifest tooling included (winget-pkgs submission is manual).

**Install**

- Windows: download `Mingbird-v3.1.6-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.6-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.6-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.6-macos-arm64.tar.gz`, same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
