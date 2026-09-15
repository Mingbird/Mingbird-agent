# 🐦 鸣鸟 Mingbird

**让你笔记本上的本地小模型真的把活干完——而不只是聊天。**

鸣鸟是一个本地优先的 agent harness，面向 Windows + Ollama（Linux/macOS 实验包），为大多数人真正跑得动的模型设计：**2–9B 参数，核显 + 16–32 GB 内存即可**（实测上限 35B MoE）。无云依赖、无账号、无遥测（除你显式配置的 Ollama/搜索端点外无任何外联）；核显或入门级独显即可。

[English](README.md) · Apache-2.0 · Windows 10/11 · Linux & macOS（实验版） · 离线优先

![鸣鸟截图](docs/assets/screenshot-app.png)

## 我们要解决的问题

主流 agent 框架是为云上大模型设计的。喂给它一个 2B 本地模型，演示视频里的一切都会崩掉：全量工具 prefill 撑爆上下文、模型无法自我纠错、陷入工具调用死循环，或者半途悄无声息地放弃。

**我们的立场：这些是 harness 的缺陷，不是模型的缺陷。** 小模型经常"知道该做什么"，只是不能稳定地"发射并执行"。鸣鸟就是补上这一段的 harness——同一个模型，在别处只会聊天，在这里开始干活。

## 它能做什么

- **真实任务**：写代码并跑测试、整理文件、联网调研、分析数据、调用 MCP 工具。
- **流式输出 + 思考过程可见**——看着它推理，然后思考折叠、答案流出。
- **拖入/粘贴即附件**——文件直接拖进聊天框，或 Ctrl+V 粘贴：剪贴板里的文件、截图瞬间成为附件，随指令一起发送。
- **语音输入开箱即用**——安装包内置本地 STT 小模型（纯 CPU，~20× 实时转写），说完自动停。
- **任务时限系统（基线默认关）**——输入框填 `40` / `1.5h` / `半小时`，或直接在任务描述里写"限时 40 分钟"（自动识别、优先级最高）；临近时限自动收尾提醒。本地模型用户对墙钟时间敏感，时限是一等公民配置。
- **会话记忆**——历史会话持久保存，可搜索、可回放。
- **模型自动识别**——Ollama 里拉什么就用什么，最高 256K 上下文。
- **技能 & MCP**——markdown 技能按需装载；MCP 服务器纯 JSON 配置。
- **中英双语**界面。
- **Web UI（实验版）**——同一个 agent 跑进浏览器：源码运行 `python webui/server.py`，打开 http://127.0.0.1:8765（仅绑定 127.0.0.1，数据不出机）——[指南](docs/webui_zh.md)。
- **一键安装包**，也可源码运行。

## 有什么不同

每个机制都源于"小模型做不到 X，所以 harness 替它做"：

| 小模型做不到… | 鸣鸟替它做 |
|---|---|
| …自我调试 | harness 亲自跑测试，回喂精确失败（`file:line` + 报错原文） |
| …无风险地改代码 | 每次改动自动备份（`.bak`），一条命令回滚 |
| …跳出工具演示循环 | 问答/任务分层（聊天答完即停）+ 签名级反循环梯队：纠正 → 硬复位 → 优雅退出 |
| …把工具塞进上下文 | 扁平 prefill 按类别装载：出厂 prefill 恰为 797 token，任何净增一个字节的改动都会让 CI 挂掉 |
| …一次发射整个大文件 | 单次调用输出上限 8192（原 2048）；仍被截断时改给"先写骨架、再追加"的分块反馈，不再空轮螺旋 |
| …停止爬行巨大文件 | 爬行守卫 v2 字节预算制（2× 文件大小，64KB–512KB 夹取）——永不拒绝，进度不断 |
| …长任务不跑偏 | 交付自查门禁：宣称完成前回读任务原文核对 |
| …抵住破坏性冲动 | 五环安全垫兜住（见[安全](#安全)） |

零硬编码：Ollama 地址、可执行文件、GPU 环境变量、模型别名——全部运行时识别或在 `~/.ollama_agent/config.json` 配置（见 [AGENTS.md](AGENTS.md)）。质量底线：v1.6.0 共 441 个测试，prefill 零增长断言在内。

## 实测：同一个模型，不同的 harness

### LRAB-288（自建基准，原始数据全公开）

4 个 harness（鸣鸟/goose/agent-mini/opencode，均为原装）× 4 个开源模型（gemma4:e2b 2B · qwen3.5:4b 4B · gemma4:12b 12B · ornith-1.5:35b 35B MoE）× 18 个真实任务 = 288 格。同机、同预算（工作流 90 分钟 / 长视野 180 分钟）、确定性判分、超时计 0。

![按模型规模](docs/assets/lrab_by_model.png)

| Harness | 2B | 4B | 12B | 35B MoE | **总分** |
|---|---|---|---|---|---|
| **鸣鸟** | **0.799** | **0.921** | **0.920** | **0.939** | **0.895** |
| goose | 0.266 | 0.636 | 0.620 | 0.822 | 0.586 |
| agent-mini | 0.246 | 0.706 | 0.576 | 0.092 | 0.405 |
| opencode | 0.017 | 0.404 | 0.140 | 0.776 | 0.334 |

- **2B 列就是故事**：0.799 vs 0.017–0.266——唯一没有小模型断崖的 harness，而那正是笔记本跑得动的尺寸。3 个长视野任务上鸣鸟同样第一（0.808）。
- **显著性**（Holm 校正 Wilcoxon，按任务配对）：2B/4B/12B 上的优势显著；35B 段各家靠拢——鸣鸟 vs goose p=0.085，不显著，如实写明。
- **消融**（v1.5.0 代码、同代码 baseline 0.821、18 任务 × 4 变体）：去 finish_gate → 0.723（−0.098，单项最大）· 去 verify_feedback → 0.772（−0.049）· 去 anti_loop → 0.805（−0.016）· 去 flat_prefill → 0.818（−0.003，2B 上中性）。四个机制均非负贡献。（与上面的 0.895 分属两批，不可比。）

### τ²-bench 三域四家（外部基准，已收官）

Sierra Research 的 [τ²-bench](https://github.com/sierra-research/tau2-bench)，三个域全部跑完。四家口径完全一致：agent 侧都是同一颗本地 `qwen3.5:4b`（Ollama），user simulator 都是云端 `qwen3.8-flash`，pass^1、error 计 0、判分校验数据库终态——假装调用工具过不了 DB 重放。

![tau2](docs/assets/tau2_headline.png)

| Harness | retail（114 题） | airline（50 题） | telecom（114 题） |
|---|---|---|---|
| **鸣鸟** | **0.789** | **0.740** | **1.000** |
| τ² 原生 agent | 0.640 | 0.520 | 1.000 |
| goose | 0.588 | 0.460 | 0.377 |
| opencode | 0.246 | 0.460 | 0.298 |

telecom 是饱和域——两强都拿满分，没有区分度；如实呈现，不挑更好看的切法。

### 我们不喜欢的数字

BFCL v3 multi_turn（800 题、同一颗 4B、官方 evaluator）：**鸣鸟 36.25% vs 模型原生 function calling 通道 46.50%**。在 4B 上，专用 FC 通道强于通用 agent 循环——这是通用性换准确率的代价，如实披露。

全部原始数据公开：[`benchmarks/lrab_scores.csv`](benchmarks/lrab_scores.csv)（288 格全量）、τ² 三域 manifest、BFCL 双臂判分明细——见 [benchmarks/](benchmarks/README.md)。

## 硬件

真实机器实测，不是估算：

| 档位 | 硬件 | 模型范围 | 体验 |
|---|---|---|---|
| 入门 | AMD 680M 核显 · 16 GB 内存 | 2–4B | 流式近实时 |
| 基准 | Intel Arc B390 核显 · 32 GB 内存 | 2–35B（MoE） | 35B 长任务端到端可跑 |

核显或入门级独显即可，更高端的独显自然不在话下。鸣鸟不包装、不代理模型——自身静态 prefill 为 797 token。

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
   ollama pull qwen3.5:4b      # 4B，基准主力
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

v1.6.0 起内置五环安全垫——小模型冲动卸载、全量删除是实测到的事故模式，不是假设：

| 环 | 做什么 |
|---|---|
| 环0 · 子代理沙箱 | 并行子代理 default-deny，权限永远严格小于主代理 |
| 环1 · 不可逆操作直接拒绝 | `format`、`diskpart`、`vssadmin delete shadows`、`dd` 裸设备、`wsl --unregister`、`dism`、驱动卸载、`userdel`——无条件拒绝 |
| 环2 · 行为分级 | 卸载软件/系统环境变更：有人值守逐条确认，无人值守默认拒绝（`AGENT_ALLOW_ENV_MUTATION=1` 放行） |
| 环3 · 边界确认 | 递归删除限工作目录内；越界拒绝并给逐文件出路 |
| 环4 · 可回滚 | 写前 `.bak`；`delete_file` 落 `.mingbird_trash/`；短内容覆盖既有大文件需显式 `replace=true` |

逃生口：`AGENT_UNSAFE=1` 全关——风险自担。

## 诚实的局限

- 2B 模型不会一次性重写你的整个代码库——但日常 agent 工作的大头它能可靠完成，做不到时会大声失败（而不是悄悄做错）。
- BFCL multi_turn 上，通用循环低于模型原生 FC 通道（36.25% vs 46.50%）。
- 核显跑 35B 端到端可用但不快（128K 上下文 ~26 tok/s）。
- Linux/macOS 包是 CI 实验构建，Windows 是主平台。
- LRAB 是我们自建的基准——这正是我们把任务、判分代码、逐格原始数据全部公开的原因：欢迎复跑，不用信我们。

## 许可

Apache-2.0 —— 自由使用、修改、分发。
