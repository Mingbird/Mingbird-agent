## 🇨🇳 中文

# 鸣鸟 v3.1.11

回复语言跟随用户版：助手回复的语言不再绑定系统界面语言，改为跟随用户消息；任务过程的叙述语言跟随任务指令语言。内置轻量离线语言识别。桌面 UI 不变。**726 项测试全绿**（719 + 7 新增）。

### 🌐 上线

- **回复语言跟随（问答/任务两类会话）**：回复使用用户消息或任务指令的语言；用户换语言，回复跟着换。中文系统下使用其他语言的用户不再被界面语言带偏。
- **内置离线语言识别**：轻量识别模型随安装包分发，本地运行、零出站。识别有把握时在系统提示明确回复语言，没把握时静默不干预——由双语提示兜底。
- **问答提示双语化**：系统提示不再单语，从根上消除"提示语言带偏回复语言"这一类问题。

### 🔧 修复

- 修复一类"回复语言与用户语言不一致"的问题：根因是回复语言此前跟系统界面走，而界面语言≠用户消息语言；本版起语言决策只看用户输入本身。
- 修复非中文任务在中文系统上"交付物与过程叙述语言不一致"的一类问题：交付物语言已跟任务（v3.1.10），本版补齐过程叙述语言。

### 🧱 工程

- 语言相关指令全部改为动态注入：出厂提示词（prefill）保持冻结，不随功能增长。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.11-CN-Setup.exe`（中文）或 `Mingbird-v3.1.11-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.11-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.11-macos-arm64.tar.gz`（Intel 机型用 `mingbird-v3.1.11-macos-x64.tar.gz`），同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.11

Replies now follow the user's language: the reply language is no longer bound to the UI locale — it follows the user's message, and task-mode narration follows the task language. A lightweight offline language identifier ships inside the package. Desktop UI unchanged. **726 tests green** (719 + 7 new).

### 🌐 Added

- **Reply-language following (chat and task sessions)**: replies use the language of the user's message or the task instruction; when the user switches languages, replies switch too. Users of any other language on a Chinese-locale system are no longer dragged along by the UI locale.
- **Built-in offline language identification**: a lightweight model ships with the installer, runs locally, zero outbound traffic. When detection is confident the system prompt names the reply language; otherwise nothing is injected and the bilingual prompt carries it.
- **Bilingual QA prompt**: the system prompt is no longer single-language, removing the whole class of "prompt language drags the reply language" issues at the root.

### 🔧 Fixed

- Fixed the class of "reply language disagrees with the user's language" issues: replies previously followed the system locale, and locale ≠ message language; language decisions now look only at the user's input.
- Fixed the class of "deliverable and narration languages disagree" for non-Chinese tasks on Chinese systems: deliverables already follow the task (v3.1.10); this release completes narration.

### 🧱 Engineering

- All language-related instructions are now dynamic lines: the factory prompt (prefill) stays frozen and does not grow with features.

**Install**

- Windows: download `Mingbird-v3.1.11-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.11-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.11-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.11-macos-arm64.tar.gz` (Intel: `mingbird-v3.1.11-macos-x64.tar.gz`), same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
