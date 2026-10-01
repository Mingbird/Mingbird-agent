## 🇨🇳 中文

### 🌍 六个通用技能:不止写代码
- 此前内置的 11 个技能全是编码向(代码审查、重构、TDD……),日常电脑活没有对应手册。v1.9.1 加入六个通用技能:**整理文件夹**(归类/批量重命名/查重)、**联网调研并写成报告**(多查询检索+交叉验证)、**长文速读**(摘要+要点+行动项)、**Word 文档生成与读取**、**Excel/CSV 表格处理**、**图片批量处理**。技能仍是渐进式加载:模型平时只看到名字和一行描述,用到才载全文——出厂 prefill 一字未变。

### 🎤 语音输入:中英双语,开箱即用
- 旧版只内置中文模型,英文语音要自己在 Ollama 里拉 whisper。v1.9.1 把英文流式模型(en-20M)也打进安装包,麦克风旁新增 **中/EN 切换**,选择会记住。转写仍在纯 CPU 上本地完成,录音不出机器。

### 🐍 新工具 run_python:用户机器不用装 Python
- 办公/图片技能的执行底座:agent 生成的 Python 代码交给**程序内置的解释器**运行,pandas/numpy/PIL 随包可用——用户的电脑不需要装 Python,也不需要装 Office。安全模型与 run_bash 同款:危险命令硬拦、破坏性操作分级、工作目录沙箱、300 秒超时按进程树终止。

### 🧩 技能与 MCP 看得见了
- 技能窗口现在列出技能目录、自装方法(自己的 .md 放进 `~/.ollama_agent/skills/` 即成技能)、以及已配置的 MCP 服务器;`skills/README.md` 写明格式与查找顺序。

### 📦 安装包反而更小
- 内置语音模型改为只带实际加载的 int8 权重(此前打包里躺着一半没人读的 float32):多塞了一个英文模型之后,Windows 安装包反而从 187.4MB 降到 174.5MB。

472 项测试全绿(435 单测 + 26 集成 + 11 项 v1.9.1 新覆盖:run_python 分发与安全门、双语模型解析、int8 打包纪律、通用技能在位)。

### 📦 构建说明
Windows 两包从 v1.9.1 tag 源码构建,并在冻结产物上实测:依赖自检全 OK、`--run-py` 通道实跑通过、GUI 启动存活、stt 双模型仅 int8、17 个技能文件在位;Linux/macOS 三包由 CI 构建并含冒烟步骤;五个资产的 SHA-256 已与本地构建逐字节核对一致。从 v1.8.x 升级直接覆盖安装。完整变更见 [CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)。

## 🇬🇧 English

### 🌍 Six universal skills: beyond coding
- The 11 built-in skills were all coding-oriented (code review, refactoring, TDD...); everyday computer work had no playbook. v1.9.1 adds six universal skills: **file organizing** (sort / batch rename / dedup), **web research with a written report** (multi-query, cross-checked), **long-document digest** (summary + key points + action items), **Word .docx generation and reading**, **Excel/CSV processing**, and **image batch processing**. Skills stay progressive: the model only sees names and one-line descriptions until one is actually loaded — the factory prefill is unchanged byte for byte.

### 🎤 Voice input: Chinese & English, out of the box
- Previously only a Chinese model was bundled; English speech required pulling whisper into Ollama yourself. v1.9.1 bundles an English streaming model (en-20M) too, with a **中/EN toggle** next to the mic (remembered). Transcription still runs locally on pure CPU; your audio never leaves the machine.

### 🐍 New run_python tool: no Python install needed on the user machine
- The execution backbone for the office/image skills: Python code the agent writes runs on the **interpreter bundled inside the app**, with pandas/numpy/PIL available — the user's computer needs neither Python nor Office. Same safety model as run_bash: danger patterns blocked outright, destructive operations classified, workspace sandbox, 300 s timeout with process-tree kill.

### 🧩 Skills & MCP made visible
- The Skills window now lists skill directories, how to install your own (drop a .md into `~/.ollama_agent/skills/`), and the configured MCP servers; `skills/README.md` documents the format and lookup order.

### 📦 The installer actually got smaller
- Bundled voice models now ship only the int8 weights actually loaded (half the previous payload was float32 nobody read): after adding a second model, the Windows installer still shrank from 187.4 MB to 174.5 MB.

472 tests green (435 unit + 26 integration + 11 new v1.9.1 cases: run_python dispatch and safety gates, bilingual model resolution, int8-only packaging rule, universal skills presence).

### 📦 Build note
The two Windows packages were built from the v1.9.1 tag source and verified on the frozen binary: dependency selftest OK, the `--run-py` path exercised for real, GUI launch stays alive, both stt models int8-only, all 17 skill files present. The Linux/macOS packages are built by CI with a smoke step. All five asset SHA-256 digests were verified byte-for-byte against the local builds. Upgrading from v1.8.x is a plain overwrite install. Full changelog in [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md).

---

**Install / 安装**
- Windows: download `Mingbird-v1.9.1-CN-Setup.exe` (中文界面) or `Mingbird-v1.9.1-EN-Setup.exe` (English UI).
- Linux/macOS: experimental tarballs (`mingbird-v1.9.1-linux-x64.tar.gz` / `-macos-arm64.tar.gz` / `-macos-x64.tar.gz`), see `install-unix.sh` inside.
