# 🐦 鸣鸟 Mingbird

**本地优先的 agent harness：让核显上的 2–9B 小模型把活干完。**

鸣鸟面向 Windows + Ollama（Linux/macOS 实验包），为大多数人真正跑得动的模型设计：**2–9B 参数、核显、16–32 GB 内存**（实测上限 35B）。无云依赖、无账号、无遥测——除你显式配置的 Ollama/搜索端点外，无任何外联。

[English](README.md) · Apache-2.0 · Windows 10/11 · Linux & macOS（实验版） · 离线优先

![鸣鸟截图](docs/assets/screenshot-app.png)

## 我们要解决的问题

主流 agent 框架是为云上大模型设计的。喂给它一个 2B 本地模型，演示视频里的一切都会崩掉：全量工具 prefill 撑爆上下文、模型无法自我纠错、陷入工具调用死循环，或者半途悄无声息地放弃。

**我们的主张：这些是 harness 的缺陷，不是模型的缺陷。** 小模型经常知道该做什么，只是不能稳定地一步步做出来。鸣鸟就是补上这一段的 harness：同一个模型，在别处只会聊天，在这里交付产物。

## 它能做什么

- **真实任务**：写代码并跑测试、整理文件、联网调研、分析数据、调用 MCP 工具。
- **流式输出 + 思考过程可见**——交付内容流式输出，思考过程随后自动折叠、进入正式回答。
- **拖入/粘贴即附件**——文件直接拖进聊天框，或 Ctrl+V 粘贴：剪贴板里的文件、截图瞬间成为附件，随指令一起发送。
- **语音输入开箱即用**——安装包内置本地 STT 小模型（纯 CPU，~20× 实时转写），说完自动停。
- **任务时限（默认关）**——输入框填 `40` / `1.5h` / `半小时`，或直接在任务描述里写"限时 40 分钟"（自动识别、优先级最高）；临近时限自动收尾提醒。本地模型用户在意墙钟时间。
- **会话记忆**——历史会话持久保存，可搜索、可回放。
- **模型自动识别**——Ollama 里拉什么就用什么，最高 256K 上下文。
- **技能 & MCP**——markdown 技能按需装载；MCP 服务器纯 JSON 配置。
- **中英双语**界面。
- **Web UI（实验版）**——同一个 agent 跑进浏览器：源码运行 `python webui/server.py`，打开 http://127.0.0.1:8765（仅绑定 127.0.0.1，数据不出本机）——[指南](docs/webui_zh.md)。
- **一键安装包**，也可源码运行。

## 有什么不同

每个机制都源于"小模型做不到 X，所以 harness 替它做"：

| 小模型做不到… | 鸣鸟替它做 |
|---|---|
| …自我调试 | harness 亲自跑测试，回喂精确失败（`file:line` + 报错原文） |
| …无风险地改代码 | 每次改动自动备份（`.bak`），一条命令回滚 |
| …跳出工具演示循环 | 问答/任务分层（聊天答完即停）+ 签名级反循环梯队：纠正 → 硬复位 → 优雅退出 |
| …把工具塞进上下文 | 扁平 prefill 按类别装载：出厂 prefill 恰为 797 token，任何净增一个字节的改动都会让 CI 挂掉 |
| …一次输出整个大文件 | 单次调用输出上限 8192（原 2048）；仍被截断时改给"先写骨架、再追加"的分块反馈，不再陷入空转循环 |
| …停止爬行巨大文件 | 爬行守卫 v2 字节预算制（2× 文件大小，钳制在 64KB–512KB）——永不拒绝 |
| …长任务不跑偏 | 交付自查门禁：宣称完成前回读任务原文核对 |
| …抵住破坏性冲动 | 五环安全网兜住（见[安全](#安全)） |

没有任何东西是写死的：Ollama 地址、可执行文件、GPU 环境变量、模型别名，全部运行时识别或在 `~/.ollama_agent/config.json` 配置（见 [AGENTS.md](AGENTS.md)）。质量底线由 v1.6.0 的 441 个测试守住，prefill 零增长断言也在其中。

## 实测：同一个模型，不同的 harness

第 1 层四行看全貌；第 2 层逐个基准给出设计、表格与适用边界；第 3 层是原始数据。

**第 1 层——一眼看全：**

| 基准 | 出品方 | 一句话结果 |
|---|---|---|
| LRAB-288 | 我们（自建） | 总分 0.886 vs goose 0.631 / opencode 0.479 / agent-mini 0.405 |
| τ²-bench 三域 | Sierra Research（外部） | retail 0.763 / airline 0.740 / telecom 1.000——全第一；goose 统一协议补跑中 |
| 消融（v1.5.0 代码） | 我们 | 去掉 finish_gate 代价最大：−0.098 |

### LRAB-288（自建基准）

4 个 harness（鸣鸟/goose/agent-mini/opencode，均为原装）× 4 个开源模型（gemma4:e2b 2B · qwen3.5:4b 4B · gemma4:12b 12B · ornith-1.5:35b 35B）× 18 个真实任务 = 288 格。同机、同预算（工作流 90 分钟 / 长程任务 180 分钟）、确定性判分、超时计 0。

![按模型规模](docs/assets/lrab_by_model.png)

| Harness | 2B | 4B | 12B | 35B | **总分** |
|---|---|---|---|---|---|
| **鸣鸟** | **0.821** | **0.876** | **0.906** | **0.941** | **0.886** |
| goose | 0.271 | 0.801 | 0.772 | 0.679 | 0.631 |
| agent-mini | 0.246 | 0.706 | 0.576 | 0.092 | 0.405 |
| opencode | 0.017 | 0.465 | 0.539 | 0.896 | 0.479 |

- **2B 列就是故事**：0.821 vs 0.017–0.271——四家里唯一没有小模型断崖式下滑的，而 2B 正是核显笔记本从容跑得动的尺寸。
- **显著性**（Holm 校正 Wilcoxon，按任务配对）：对三家全显著的是 2B 与 12B；4B 上仅对 opencode 显著（goose 关思考后追到 0.801，p=0.33）；35B 上对 goose/agent-mini 显著、对 opencode（0.896）不显著。两个方向都如实写明。
- 3 个长程任务（LH-01…03，每题预算 180 分钟）上鸣鸟同样第一（0.827 vs 0.484 / 0.394 / 0.354）。

*四臂同一协议——0 温 + 关思考（传输层钉死）；goose/opencode 于 2026-09-18..20 重拍，二进制未动。自建基准，18 个任务——任务集、判分代码、逐格数据全部公开，请自行复跑。*

### τ²-bench 三域（外部基准）

Sierra Research 的 [τ²-bench](https://github.com/sierra-research/tau2-bench)，三个域，与 LRAB 同一套统一协议：0 温 + 关思考（传输层钉死、端到端验证）。agent 侧都是同一颗本地 `qwen3.5:4b`（Ollama），pass^1、error 计 0、判分校验数据库终态——假装调用工具过不了 DB 重放。

![tau2](docs/assets/tau2_headline.png)

| Harness | retail（114 题） | airline（50 题） | telecom（114 题） |
|---|---|---|---|
| **鸣鸟** | **0.763** | **0.740** | **1.000** |
| τ² 原生 agent | 0.675 | 0.740 | 0.930 |
| opencode | 0.588 | 0.500 | 0.991 |
| goose | 统一协议补跑中 | — | — |

已收官三臂全部零 error。思考开关对数字影响巨大（opencode 的 telecom 开思考 0.298、关思考 0.991）——这本身就是 harness 层效应。goose 臂正在按统一协议补收，到齐即更新。

*user simulator 是云端 `qwen3.8-flash`，各家完全一致——不是官方的 gpt-4o 设定，因此这批数字不与官方 τ² 排行榜比较。*

### 消融：哪个机制值得留（v1.5.0 代码）

18 个 LRAB 同题任务、`gemma4:e2b`，通过 `AGENT_ABLATION` 环境变量闸门每次关掉一个机制；baseline = 同代码全机制臂（0.821）。

| 变体 | total（18 任务） | Δ vs baseline |
|---|---|---|
| 全机制（baseline） | 0.821 | — |
| − finish_gate | 0.723 | **−0.098** |
| − verify_feedback | 0.772 | −0.048 |
| − anti_loop | 0.805 | −0.015 |
| − flat_prefill | 0.818 | −0.003 |

两个机制承担主要效应（finish_gate、验证反馈回路）；另外两个是廉价保险——反循环与扁平 prefill（后者在 2B 上中性）。

*每臂只有 18 格，只看方向。0.821 不是另一批对照：它就是上面 LRAB-288 表的 2B 列——同 18 格、同 v1.5.0 代码、同一批。*

**第 3 层——请自行验证。** 全部原始数据公开在 [benchmarks/](benchmarks/README.md)：

- [`benchmarks/lrab_scores.csv`](benchmarks/lrab_scores.csv)——288 格全量（harness、任务、模型、得分、墙钟）
- [`benchmarks/tau2/`](benchmarks/tau2)——τ² 三域逐题 manifest
- [`benchmarks/ablation/`](benchmarks/ablation)——消融逐格数据（5 臂 × 18 任务）

## 硬件

真实机器实测，不是估算：

| 档位 | 硬件 | 模型范围 | 体验 |
|---|---|---|---|
| 入门 | AMD 680M 核显 · 16 GB 内存 | 2–4B | 流式近实时 |
| 基准 | Intel Arc B390 核显 · 32 GB 内存 | 2–35B | 35B 长任务端到端可跑 |

核显或入门级独显即可，更高端的独显当然也能跑。鸣鸟对模型的全部静态附加只有 797 token。

## 快速开始

鸣鸟有**四种运行方式**——引擎相同，按需选择：

| 你想要 | 方式 |
|---|---|
| Windows 桌面客户端 | [Releases](https://github.com/Mingbird/Mingbird-agent/releases) 里的 `Mingbird-v1.6.0-EN-Setup.exe` / `-CN-Setup.exe` |
| Linux / macOS 桌面客户端（实验） | Releases 里的 CI 构建 tar.gz → `sh install-unix.sh` |
| 源码运行（桌面 GUI） | `pip install -r requirements.txt` → `python agent_gui.py` |
| **浏览器里的 Web UI**（实验） | `pip install -r requirements.txt` → `python webui/server.py` → 打开 http://127.0.0.1:8765 —— [指南](docs/webui_zh.md) |

四种方式共享会话、技能、MCP 与设置。

1. 安装 [Ollama](https://ollama.com) 并拉一个模型：
   ```bash
   ollama pull gemma4:e2b      # 小而快
   ollama pull qwen3.5:4b      # 4B，主力型号
   ```
2. 从 [Releases](https://github.com/Mingbird/Mingbird-agent/releases) 下载 `Mingbird-v1.6.0-EN-Setup.exe`（或 `-CN` 中文版）并安装 → 桌面快捷方式。
   Windows 可能对未签名安装包弹出 SmartScreen——点"更多信息"→"仍要运行"。
3. 启动，选模型，直接派活。

Linux & macOS（实验性，CI 构建）：从 [Releases](https://github.com/Mingbird/Mingbird-agent/releases) 下载 `mingbird-v1.6.0-linux-x64.tar.gz` 或 `mingbird-v1.6.0-macos-arm64.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。需在该机上安装 Ollama。

源码运行：`python agent_gui.py`（图形界面）或 `python ollama_agent.py --help`（命令行）。建议 Python 3.12。

## 隐私

无遥测、无账号，除你显式配置的 Ollama/搜索端点外无任何外联。会话与设置保存在 ~/.ollama_agent。

## 安全

> [!WARNING]
> 鸣鸟会读写你磁盘上的文件、执行命令。请谨慎指定工作目录。

v1.6.0 起内置五环安全网——小模型冲动卸载、全量删除是实测到的事故模式，不是假设：

| 环 | 做什么 |
|---|---|
| 环0 · 子代理沙箱 | 并行子代理 default-deny，权限永远严格小于主代理 |
| 环1 · 不可逆操作直接拒绝 | `format`、`diskpart`、`vssadmin delete shadows`、`dd` 裸设备、`wsl --unregister`、`dism`、驱动卸载、`userdel`——无条件拒绝 |
| 环2 · 行为分级 | 卸载软件/系统环境变更：有人值守逐条确认，无人值守默认拒绝（`AGENT_ALLOW_ENV_MUTATION=1` 放行） |
| 环3 · 边界确认 | 递归删除限工作目录内；越界拒绝并给逐文件出路 |
| 环4 · 可回滚 | 写前 `.bak`；`delete_file` 落 `.mingbird_trash/`；短内容覆盖既有大文件需显式 `replace=true` |

逃生口：`AGENT_UNSAFE=1` 全关——风险自担。

## 诚实的局限

- 2B 模型不会一次性重写你的整个代码库——但日常 agent 工作的大头它能可靠完成，做不到时会明确报错停下，而不是悄悄出错。
- 核显跑 35B 端到端可用但不快（128K 上下文 ~26 tok/s）。
- Linux/macOS 包是 CI 实验构建，Windows 是主平台。
- LRAB 是我们自建的基准——这正是我们把任务、判分代码、逐格原始数据全部公开的原因：欢迎复跑，不用信我们。

## 许可

Apache-2.0 —— 自由使用、修改、分发。
