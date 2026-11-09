## 🇨🇳 中文

# 鸣鸟 v3.1.8

产物质量修复——补上三处门禁缺口：被拒的模型有路可走，收尾的运行交不出读不了的文件。桌面 UI 不变。**697 项测试全绿**（687 + 10 新增）。

- **计算型工具被禁后有真实出路**：`run_bash`/`run_python` 被反循环守卫禁用时，话术改为"改写代码重跑，或 `enable_tools` 解锁"，不再建议直接写产物文件（对计算型任务那是教模型手写本该由脚本算出的结果）。
- **无人值守的越界拒绝给出工作目录与替代做法**：附真实工作目录 + `list_dir(path=".")` / 相对路径读文件，被拒的模型不再原地重试。
- **finish 门禁查内容**：`*.json` 交付物必须能解析才算数，两段 JSON 首尾相接这类坏文件会被打回并要求用脚本重新生成；`AGENT_CONTENT_GATE=0` 可关闭。
- **交付物语言跟任务走**：英文任务出英文交付物、中文任务出中文交付物，与界面语言无关。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.8-CN-Setup.exe`（中文）或 `Mingbird-v3.1.8-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.8-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.8-macos-arm64.tar.gz`（Intel 机型用 `mingbird-v3.1.8-macos-x64.tar.gz`），同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.8

Artifact-quality fixes: three gate gaps closed so that a refused model has something to do, and a finished run cannot deliver files no program can read. Desktop UI unchanged. **697 tests green** (687 + 10 new).

- **Disabled compute tools get a real way forward**: when the anti-loop guard disables `run_bash`/`run_python`, the refusal says "rewrite the code and rerun, or `enable_tools` to unlock" — no more blanket advice to write the deliverable by hand.
- **Unattended path denials state the workdir and alternatives**: the refusal includes the real working directory plus `list_dir(path=".")` / relative-path reads, so a refused model stops retrying the same out-of-bounds path.
- **The finish gate checks content**: `*.json` deliverables must parse — two concatenated JSON objects are bounced back with "regenerate with a script"; turn it off with `AGENT_CONTENT_GATE=0`.
- **Deliverable language follows the task**: English task → English deliverables, Chinese task → Chinese deliverables, regardless of the UI language.

**Install**

- Windows: download `Mingbird-v3.1.8-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.8-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.8-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.8-macos-arm64.tar.gz` (Intel: `mingbird-v3.1.8-macos-x64.tar.gz`), same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
