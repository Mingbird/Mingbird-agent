## 🇨🇳 中文

### 🔧 修复:自定义模型目录不再"丢模型"([issue #1](https://github.com/Mingbird/Mingbird-agent/issues/1))
- 旧行为:Ollama 还没启动时先打开鸣鸟,鸣鸟拉起的 `ollama serve` 只继承环境变量——而 Ollama 官方 GUI 设置的自定义模型目录存在 `%LOCALAPPDATA%\Ollama\db.sqlite` 里、并不写环境变量,于是这个实例退回默认目录,模型列表看起来空了(模型文件本身无恙)。新行为:鸣鸟启动 serve 前会读取该设置(经临时副本读这个常驻库,任何读取失败都静默跳过)并以 `OLLAMA_MODELS` 传给拉起的进程;优先级为 环境变量/配置层显式设置 > Ollama GUI 设置,没设自定义目录的用户行为不变。感谢 @LeftOwlRight 一份四要素俱全的问题报告。

### 🎨 界面:回答正文加大两号
- 此前回答正文与"思考"块只差一档字号加灰字,长回答扫读时不易分辨。回答正文从 10pt 提到 12pt,思考块维持 9pt 灰斜体(点击仍可折叠/展开),正文作为主内容的层级一眼可辨;用户气泡、工具行、代码块字号不变。

482 项测试全绿(472 + 10 项新增:伪造/损坏/缺失设置库的读取回退、环境变量与配置层的优先级接线)。

### 📦 构建说明
Windows 两包从 v1.9.2 tag 源码构建,并在冻结产物上实测:依赖自检全 OK、`--run-py` 通道实跑通过、GUI 启动存活、stt 双模型仅 int8、17 个技能文件在位;Linux/macOS 三包由 CI 构建并含冒烟步骤;五个资产的 SHA-256 已与本地构建逐字节核对一致。从 v1.8.x/v1.9.x 升级直接覆盖安装。完整变更见 [CHANGELOG_zh.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG_zh.md)。

## 🇬🇧 English

### 🔧 Fix: custom model directory no longer "loses" models ([issue #1](https://github.com/Mingbird/Mingbird-agent/issues/1))
- Old behavior: start Mingbird before Ollama, and the `ollama serve` it spawned inherited only the environment — but the custom model directory set in Ollama's GUI lives in `%LOCALAPPDATA%\Ollama\db.sqlite`, not in any env var, so that instance fell back to the default directory and the model list looked empty (the model files themselves were untouched). New behavior: before starting serve, Mingbird reads that setting (via a temp copy of the live DB; any read failure is silently skipped) and passes it as `OLLAMA_MODELS` to the spawned process. Precedence: explicit env/config > Ollama GUI setting; users without a custom directory see no change. Credit to @LeftOwlRight for a model bug report.

### 🎨 UI: answer text two sizes bigger
- The answer body and the thinking block previously differed by one font step and color, which was hard to scan in long replies. Answer text now renders at 12 pt (was 10) while the thinking block stays 9 pt gray italic (still click-to-collapse); user bubbles, tool lines and code blocks keep their sizes.

482 tests green (472 + 10 new: fabricated/corrupt/missing settings-DB fallbacks, env-var and config-layer precedence wiring).

### 📦 Build note
The two Windows packages were built from the v1.9.2 tag source and verified on the frozen binary: dependency selftest OK, the `--run-py` path exercised for real, GUI launch stays alive, both stt models int8-only, all 17 skill files present. The Linux/macOS packages are built by CI with a smoke step. All five asset SHA-256 digests were verified byte-for-byte against the local builds. Upgrading from v1.8.x/v1.9.x is a plain overwrite install. Full changelog in [CHANGELOG.md](https://github.com/Mingbird/Mingbird-agent/blob/main/CHANGELOG.md).

---

**Install / 安装**
- Windows: download `Mingbird-v1.9.2-CN-Setup.exe` (中文界面) or `Mingbird-v1.9.2-EN-Setup.exe` (English UI).
- Linux/macOS: experimental tarballs (`mingbird-v1.9.2-linux-x64.tar.gz` / `-macos-arm64.tar.gz` / `-macos-x64.tar.gz`), see `install-unix.sh` inside.
