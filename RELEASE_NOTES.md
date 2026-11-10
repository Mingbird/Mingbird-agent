## 🇨🇳 中文

# 鸣鸟 v3.1.10

小模型档加固版：堵住两条死循环（解锁→再撞墙、周期 2 读循环）、todo 状态文件不再能被覆写炸格、拒绝词的出路不再被截断吞掉。桌面 UI 不变。**717 项测试全绿**（697 + 20 新增）。

- **禁用话术给出真实出路**：不再推荐 `enable_tools` 解锁。文档类产物直接 `create_file` 写；必须由代码算出的产物仍必须换代码重跑。出路落在前 120 字符内（压缩截断不再吞掉它），快照挪到末尾。
- **解锁变成真恢复**：核心工具被禁后解锁原本回不到工具面、回执也不说——现在解锁重新装配工具并明说；同一工具本次任务内解锁上限 2 次。
- **读循环按签名封禁**：同一读取反复 6 次、或两个读取交替打满 10 次 → 封涉事区间。**换新区间或读其他文件照常放行**（那是进展）；体量与越界梯子按路径兜底。
- **todo.json 不可覆写、不可炸格**：任何形状的计划文件都归一成可读列表；直接写 `todo.json`/`.agent_state.json` 会被拒绝并指路 todo 工具。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.10-CN-Setup.exe`（中文）或 `Mingbird-v3.1.10-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.10-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.10-macos-arm64.tar.gz`（Intel 机型用 `mingbird-v3.1.10-macos-x64.tar.gz`），同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.10

Small-model robustness release: two death loops closed (unlock-and-rewall, period-2 read loops), the harness plan file can no longer be overwritten into a crash, and escape routes no longer get cut off by truncation. Desktop UI unchanged. **717 tests green** (697 + 20 new).

- **The disabled-tool refusal leads somewhere real**: no more unlock advice — `create_file` for documents, a rewritten rerun for computed work, ordered inside the first 120 characters (compaction truncation used to swallow them), snapshot moved to the end.
- **Unlock actually revives the tool**: a disabled core tool could never come back and the `(none)` receipt hid it. Unlock re-assembles the tool and says so; capped at 2 per tool per task.
- **Read loops are banned by signature**: the same read 6 times, or two reads alternating for 10+ calls, bans those signatures — a NEW range or a different file reads normally (that is progress); the volume and past-the-end ladders stay path-level as the backstop.
- **todo.json can't be overwritten into a crash**: every plan-file shape normalizes to a readable list; writing `todo.json`/`.agent_state.json` directly is refused with a pointer to the todo tool.

**Install**

- Windows: download `Mingbird-v3.1.10-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.10-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.10-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.10-macos-arm64.tar.gz` (Intel: `mingbird-v3.1.10-macos-x64.tar.gz`), same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
