## 🇨🇳 中文

# 鸣鸟 v3.1.11

回复语言跟随用户版：中文系统下英文"hello"不再得到中文回答。问答回复语言三层检测（独有文字系统 → 问候词闭集 → fastText 语言识别），检测有把握就指名语言，没把握就不注。桌面 UI 不变。**726 项测试全绿**（719 + 7 新增）。

- **修复"英文问候得到中文回答"**：v3.1.10 及之前的问答提示通篇中文，唯一的语言开关只跟系统界面语言走——说其他语言的用户都会被中文提示带偏。
- **三层检测，宁缺毋滥**：文字一一对应的语言直接判（中/日/韩/希腊/希伯来/泰）；问候/客套词整句精确匹配（归一大小写与变音符）；fastText（938KB，离线，176 种语言）只管句子级，置信 ≥0.9 才采纳，检测不出就不注入——双语提示里的"用用户消息的语言回答"兜底。
- **统计识别不碰裸词**：实测"hello"的识别置信只有 0.39、德语句子被误标英语 0.81——裸词交给闭集表，句子才交给模型。
- **任务过程文本跟随任务指令语言**：英文任务不再出现"英文交付物 + 中文过程絮语"。
- **出厂 prefill 钉维持 1319**：语言行全部动态注入，静态面不再为语言功能增长。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.11-CN-Setup.exe`（中文）或 `Mingbird-v3.1.11-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.11-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.11-macos-arm64.tar.gz`（Intel 机型用 `mingbird-v3.1.11-macos-x64.tar.gz`），同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.11

Replies now follow the user's language: on a Chinese-locale machine, an English "hello" no longer gets a Chinese answer. Three-tier reply-language detection (unique-script ranges → greeting/courtesy table → fastText language ID) names the language when confident and injects nothing when not. Desktop UI unchanged. **726 tests green** (719 + 7 new).

- **"English greeting, Chinese answer" is fixed**: through v3.1.10 the QA prompt was Chinese-only and the only language switch followed the UI locale — speakers of any other language got dragged along.
- **Three tiers, silence over a wrong guess**: unique scripts decide outright (Chinese/Japanese/Korean/Greek/Hebrew/Thai); greetings are whole-message exact matches (case and diacritics normalized); fastText (938KB, offline, 176 languages) judges sentences only at confidence ≥ 0.9 — otherwise nothing is injected and the bilingual prompt's "reply in the user's language" line carries it.
- **Statistical ID never touches bare words**: "hello" measures 0.39 confidence and a German sentence once scored en=0.81 — bare words go to the closed table, sentences go to the model.
- **Task-mode process text follows the task language**: an English task no longer gets English deliverables with Chinese status chatter.
- **The factory prefill pin stays at 1319**: language lines are all dynamic; the static face no longer grows for language features.

**Install**

- Windows: download `Mingbird-v3.1.11-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.11-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.11-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.11-macos-arm64.tar.gz` (Intel: `mingbird-v3.1.11-macos-x64.tar.gz`), same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
