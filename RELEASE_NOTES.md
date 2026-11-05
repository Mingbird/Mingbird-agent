## 🇨🇳 中文

# 鸣鸟 v3.1.7

工具可得性修复——源自用户反馈：聊天里看得到的工具被判"不可用"。同一处校验也让断网模式留了几个绕行口，一并修掉。桌面 UI 不变。**687 项测试全绿**（672 + 15 新增）。

- **聊天模式的联网搜索与抓网页恢复可用**：派发校验改为按"本轮真正下发的工具表"比对，并计入同一轮 `enable_tools` 刚解锁的工具。
- **断网拦到工具本体**：`web_search` / `web_search_multi` / `batch_tools` / `web_fetch` 在断网时各自返回明确提示，绕过装配层的调用也出不去。
- **断网时不探测、不调用远程 MCP**：manifest 刷新与 `mcp_call` 都不会碰到 url 型服务器。
- **断网拦截不再触发"硬复位上下文"**：配置状态不再按反循环惩罚处理。
- 聊天=只读、任务=按类别装配的差异保持不变：看得见的可以调用，看不见但能出网的一律拒绝。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.7-CN-Setup.exe`（中文）或 `Mingbird-v3.1.7-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.7-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.7-macos-arm64.tar.gz`（Intel 机型用 `mingbird-v3.1.7-macos-x64.tar.gz`），同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.7

Tool-availability fixes from a user report: tools the model could see in chat were refused as "unavailable". The same check also left a few ways around the offline guarantee; both are fixed. Desktop UI unchanged. **687 tests green** (672 + 15 new).

- **Chat-mode web search and page fetch work again**: execution now validates against the tools actually offered that turn, plus anything `enable_tools` unlocked in the same turn.
- **Offline mode is enforced at the tool bodies**: `web_search`, `web_search_multi`, `batch_tools` and `web_fetch` each return a clear message while offline, so a call that bypasses assembly cannot reach the network.
- **Remote MCP servers are not probed or called while offline**: neither the manifest refresh nor `mcp_call` reaches url-type servers.
- **Offline refusals no longer trigger a context hard reset**: a configuration state is no longer handled by the anti-loop ladder.
- Chat stays a read-only subset and task mode stays category-driven: what the model can see it may call, and what it cannot see but could egress is refused.

**Install**

- Windows: download `Mingbird-v3.1.7-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.7-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.7-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.7-macos-arm64.tar.gz` (Intel: `mingbird-v3.1.7-macos-x64.tar.gz`), same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
