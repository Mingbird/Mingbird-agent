## 🇨🇳 中文

# 鸣鸟 v3.1.12

本地引擎与系统代理隔离版：开着系统代理（Clash/v2rayN 等）的机器上，本地推理不再被代理拦截，Ollama 在跑就正常识别；设置面板的引擎与端点信息如实显示。桌面 UI 不变。**730 项测试全绿**（726 + 4 新增）。

### 🔧 修复

- 修复一类"本地引擎在线却被判离线"的问题：开着系统代理时，本地推理请求此前会跟随系统代理，被代理拦下——Ollama 明明在运行仍提示"未能自动启动"，模型列表与对话同样受影响。本地推理流量现一律直连；云端调用不受影响。
- 修复一类"设置面板信息与实际不符"的问题：引擎选 Ollama 时端点框此前显示的是另一款软件的默认地址，看起来像"设置没保存"；现如实显示真实地址，切换引擎时同步刷新。

### 🧱 工程

- 测试套件不再受运行机器的代理状态影响，两种环境下结果一致。

**安装（Install）**

- Windows：下载 `Mingbird-v3.1.12-CN-Setup.exe`（中文）或 `Mingbird-v3.1.12-EN-Setup.exe`（英文），双击安装。安装包未签名，Windows 可能弹出 SmartScreen——点"更多信息"→"仍要运行"。
- Linux（实验性）：下载 `mingbird-v3.1.12-linux-x64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。
- macOS（实验性）：下载 `mingbird-v3.1.12-macos-arm64.tar.gz`（Intel 机型用 `mingbird-v3.1.12-macos-x64.tar.gz`），同上。
- 需本机已装 Ollama 或任何 OpenAI 兼容本地服务（LM Studio、llama.app、llama-server、vLLM 均可）。

完整变更：[CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)

---

## 🇬🇧 English

# Mingbird v3.1.12

Local engines are now isolated from the system proxy: on machines running a system proxy (Clash/v2rayN etc.), local inference is no longer intercepted — a running Ollama is recognized as online — and the settings panel shows the engine and endpoint as they truly are. Desktop UI unchanged. **730 tests green** (726 + 4 new).

### 🔧 Fixed

- Fixed the class of "local engine online but reported offline" issues: with a system proxy on, local-inference requests previously followed it and got intercepted — a running Ollama was still reported as "not started", with the model list and chat equally affected. Local inference traffic now connects directly; cloud calls are unaffected.
- Fixed the class of "settings panel disagrees with reality" issues: with the engine set to Ollama, the endpoint field used to show another product's default address, reading as "settings weren't saved"; it now shows the real address and follows engine switches.

### 🧱 Engineering

- The test suite no longer depends on the running machine's proxy state; results are identical in both environments.

**Install**

- Windows: download `Mingbird-v3.1.12-CN-Setup.exe` (Chinese) or `Mingbird-v3.1.12-EN-Setup.exe` (English) and run it. The installer is unsigned — Windows SmartScreen may warn; choose "More info" → "Run anyway".
- Linux (experimental): download `mingbird-v3.1.12-linux-x64.tar.gz`, extract, `sh install-unix.sh`, launch `~/.local/share/Mingbird/LocalAgent`.
- macOS (experimental): download `mingbird-v3.1.12-macos-arm64.tar.gz` (Intel: `mingbird-v3.1.12-macos-x64.tar.gz`), same steps.
- Requires Ollama or any OpenAI-compatible local server (LM Studio, llama.app, llama-server, vLLM all work) installed on that machine.

Full changelog: [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md)
