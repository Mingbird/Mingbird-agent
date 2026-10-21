## 🇨🇳 中文

# 鸣鸟 v3.1.1

平台感知 + 桌面 UI 重设计。**625 项测试全绿**（576 + 49 新增）。

### 🎨 桌面界面重设计
- **会话侧边栏**：历史会话常驻左侧，按今天/昨天/更早分组，支持即时搜索；点击即切换。旧版导航轨与独立历史页移除。
- **计划抽屉**：右侧默认收起，只留完成角标；展开后显示进度条与当前项，不再长期占用主窗口宽度（长清单仍可滚动）。
- **统一输入区**：附件、语音、语言、工作目录、任务时限、续跑收进底部输入卡；模型/思考/联网收进顶部胶囊，旧版两条工具栏移除。
- **视觉与主题**：一套令牌覆盖深浅色（含侧边栏、软色、边框、状态色），消息右对齐、思考/工具行紧凑化，Windows 11 标题栏随主题切换；欢迎页四条建议可点击填入输入框。
- **Web UI 同步重设计**：浏览器端换成同一套令牌与布局——会话侧边栏、顶部胶囊、圆角输入卡、计划抽屉、设置/审批弹窗；流式输出改为按帧重绘。
- **云端 API 进设置**：设置 → 推理引擎新增「云端 API」协议（端点 / API Key / 模型名，任意 OpenAI 兼容服务）；云端与本地互斥，云端生效时断网开关置灰，状态栏显示「联网 · 云端模型」。
- **跨平台**：字体族按平台解析（Windows / macOS / Linux），Linux 语言探测，POSIX 进程组终止。
- **状态修复**：运行中禁止切换会话（含搜索窗入口）、队列旧任务残留不再污染新任务、计划面板按会话隔离、停止/关窗保存使用启动时的工作目录与会话、附件名同秒不再互相覆盖。
- **会话管理**：侧栏会话右键即可归档（移出列表、文件保留在 `sessions/_archived` 可找回）或删除（确认后彻底移除）；运行中的当前会话禁止操作。
- **输入快捷键**：Enter 发送、Shift+Enter 换行（Ctrl+Enter 仍为发送）；Web 端带输入法组合保护。

### ✨ 平台感知
- **平台信息块**：每个任务告知模型真实的平台、shell 与命令对照（Windows：cmd.exe / `dir` / `findstr`；POSIX：`ls` / `grep`），静态出厂提示零改动。
- **工具参数类型校正**：字符串数字/布尔按 schema 校正；解析失败返回结构化错误；空串可选参数按未提供处理。
- **命令输出精简三态**：自动（上下文档位 ≤32K）/ 强制开 / 强制关；`AGENT_SLIM_OUTPUT=1|0` 可覆盖，基准脚本默认置 0 以复现旧数据。
- **注册表写入纳入确认门**：`reg add/delete/import` 与 `setx`/`schtasks` 同门；无人值守下默认拒绝。
- **Web UI**：SSE 事件改为单调 id，超过 600 条不再永久静默；越界确认需要匹配当前待答请求，预置 `allow` 无效。

### 📦 构建说明
本版本当前为源码基线，尚未打包。从干净提交构建 Windows 两包，并在冻结产物上跑依赖自检 / `--run-py` / GUI 启动冒烟；Linux/macOS 由 CI 构建。安装包与 Release 资产在正式发版时附上。

---

## 🇬🇧 English

# Mingbird v3.1.1

Platform-aware harness + a redesigned desktop UI. **625 tests green** (576 + 49 new).

### 🎨 Desktop UI redesign
- **Conversation sidebar**: history lives in a persistent left rail grouped by today/yesterday/earlier with instant search; click to switch. The old nav rail and separate history page are gone.
- **Plan drawer**: collapsed by default with a progress badge; expands to show the progress bar and current item without occupying a permanent column (long lists still scroll).
- **Unified composer**: attachments, voice, language, workdir, time limit and resume live in the bottom card; model/thinking/online move into header pills. The two old toolbars are gone.
- **Visual system**: one token set covers light/dark (sidebar, soft surfaces, borders, status colours); right-aligned user messages, tighter thinking/tool rows, Windows 11 caption colour follows the theme, and the welcome suggestions fill the composer on click.
- **Web UI redesign**: the browser frontend now shares the same tokens and layout — conversation sidebar, header pills, rounded composer, plan drawer, and themed settings/approval dialogs; streaming repaints once per frame.
- **Cloud API in Settings**: Inference engine → Cloud API (endpoint / API key / model for any OpenAI-compatible service). Cloud and local models are mutually exclusive; while cloud is active the offline toggle is disabled and the status bar reads "Online · cloud model".
- **Cross-platform**: font families resolve per OS (Windows / macOS / Linux), Linux locale detection, and POSIX process-group termination.
- **State fixes**: session switching is blocked mid-run (including the search dialog), stale queue output cannot leak into a new run, the plan panel is per-session, stop/close saves use the launch-time workdir/session, and same-second pasted screenshots no longer overwrite each other.
- **Conversation management**: right-click any sidebar conversation to archive (hidden from list and search, files kept under `sessions/_archived`, move back to restore) or delete (confirm dialog, full sidecar set removed); blocked for the current conversation while a task runs.
- **Input shortcuts**: Enter sends, Shift+Enter for a newline (Ctrl+Enter still sends); the web composer guards IME composition.

### ✨ Platform awareness
- **Platform block**: every task states the real platform, shell and command mapping (Windows: cmd.exe / `dir` / `findstr`; POSIX: `ls` / `grep`) with the static factory prompt untouched.
- **Tool-argument type repair**: numeric/boolean strings are coerced per schema; unparseable values get structured errors; empty optional values are treated as omitted.
- **Compact command output (three states)**: auto (context tier ≤32K) / force on / force off; `AGENT_SLIM_OUTPUT=1|0` overrides, and benchmark runners default it off to reproduce older data.
- **Registry writes join the confirm gate**: `reg add/delete/import` now follows the same ring as `setx`/`schtasks`, and is denied under unattended runs.
- **Web UI**: SSE events now carry monotonic ids, so the stream no longer goes permanently silent after 600 events; an out-of-workspace approval must match the current pending request, so pre-seeded `allow` replies are rejected.

### 📦 Build note
This version is currently a source baseline and has not been packaged. Build both Windows installers from a clean commit and run dependency selftest / `--run-py` / GUI launch smoke on the frozen artifacts; Linux/macOS builds come from CI. Installers and release assets will be attached when the release is cut.
