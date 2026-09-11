# 🐦 鸣鸟 Mingbird

**让你笔记本上的本地小模型真的把活干完——而不只是聊天。**

鸣鸟是一个本地优先的 agent harness，面向 Windows + Ollama（Linux 实验版），为大多数人真正跑得动的模型设计：**2–9B 参数，核显 + 16–32 GB 内存即可**。无云依赖、无账号、无遥测（除你显式配置的 Ollama/搜索端点外无任何外联）；核显或入门级独立显卡即可。

[English](README.md) · Apache-2.0 · Windows 10/11 · Linux & macOS（实验版） · 离线优先

![鸣鸟截图](docs/assets/screenshot-app.png)

## 我们要解决的问题

主流 agent 框架是为云上大模型设计的。喂给它一个 2B 本地模型，演示视频里的一切都会崩掉：全量工具 prefill 撑爆上下文、模型无法自我纠错、陷入工具调用死循环，或者半途悄无声息地放弃。

**我们的立场：这些是 harness 的缺陷，不是模型的缺陷。** 小模型经常"知道该做什么"，只是不能稳定地"发射并执行"。鸣鸟就是补上这一段的 harness——同一个模型，在别处只会聊天，在这里开始干活。

## 它能做什么

- **真实任务**：写代码并跑测试、整理文件、联网调研、分析数据、调用 MCP 工具。
- **流式输出 + 思考过程可见**——看着它推理，然后思考折叠、答案流出。
- **拖入/粘贴即附件**——文件直接拖进聊天框，或 Ctrl+V 粘贴：剪贴板里的文件、截图瞬间成为附件，随指令一起发送。- **语音输入开箱即用**——安装包内置本地 STT 小模型（纯 CPU，~20× 实时转写），说完自动停。
- **任务时限系统（基线默认关）**——输入框填 `40` / `1.5h` / `半小时`，或直接在任务描述里写"限时 40 分钟"（自动识别、优先级最高）；临近时限自动收尾提醒。本地模型用户对墙钟时间敏感，时限是一等公民配置。
- **会话记忆**——历史会话持久保存，可搜索、可回放。
- **模型自动识别**——Ollama 里拉什么就用什么，最高 256K 上下文。
- **技能 & MCP**——markdown 技能按需装载；MCP 服务器纯 JSON 配置。
- **中英双语**界面。
- **Web UI（实验版）**——同一个 agent 跑进浏览器：源码运行 `python webui/server.py`，打开它打印的本机地址（仅绑定 127.0.0.1，数据不出机）。
- **一键安装包**，也可源码运行。

## 有什么不同

每个机制都源于"小模型做不到 X，所以 harness 替它做"：

| 小模型做不到… | 鸣鸟替它做 |
|---|---|
| …自我调试 | harness 亲自跑测试，回喂精确失败（`file:line` + 报错原文） |
| …无风险地改代码 | 每次改动自动备份（`.bak`），一条命令回滚 |
| …跳出工具演示循环 | 问答/任务分层——聊天答完即停，任务才解锁全部工具 |
| …把工具塞进上下文 | 扁平 prefill 按类别装载：出厂 prefill 稳定在 ~774–851 token，任何净增一个字节的改动都会让 CI 挂掉 |
| …长任务不跑偏 | 交付自查门禁：宣称完成前回读任务原文核对 |

零硬编码：Ollama 地址、可执行文件、GPU 环境变量、模型别名——全部运行时识别或在 `~/.ollama_agent/config.json` 配置（见 [AGENTS.md](AGENTS.md)）。

## 实测：同一个模型，不同的 harness

我们自建了 **LRAB** 基准：**4 个 harness（鸣鸟/goose/agent-mini/opencode，均为原装）× 4 个开源模型（gemma4:e2b 2B、qwen3.5:4b 4B、gemma4:12b 12B、ornith-1.5:35b 35B MoE）× 18 个真实任务 = 288 格**，同机、同预算（工作流 90 分钟 / 长视野 180 分钟）、确定性判分、超时计 0。

![按模型规模](docs/assets/lrab_by_model.png)

![总分](docs/assets/lrab_overall.png)

| Harness | gemma4:e2b (2B) | qwen3.5:4b (4B) | gemma4:12b (12B) | ornith-1.5:35b (35B MoE) | **总分** |
|---|---|---|---|---|---|
| **鸣鸟** | **0.80** | **0.92** | **0.92** | **0.94** | **0.895** |
| goose | 0.27 | 0.64 | 0.62 | 0.82 | 0.586 |
| agent-mini | 0.25 | 0.71 | 0.58 | 0.09 | 0.405 |
| opencode | 0.02 | 0.40 | 0.14 | 0.78 | 0.334 |

真正重要的是这个模式：**模型越小，其他 harness 崩得越狠**——而那正是人们笔记本上真正跑得动的模型。本对比中鸣鸟是唯一在 2B 上保持可用的 harness。同样的模型、同样的任务，只换了 harness。

在**外部基准**（τ²-bench retail，官方 115 题套件、本环境 114 题双侧同题计分，pass^1）上，同一个本地 4B 模型：鸣鸟 **0.746 vs 原生 agent 0.430——光换 harness，端到端完成率 +73%**：

![tau2](docs/assets/tau2_headline.png)

\* 图中 gpt-4o 0.604 仅为尺度参照（官方设定用 gpt-4o 作 user simulator），不可直接对比；本次实测双侧使用同一 user simulator。方法、任务清单、判分代码与逐格数据：[benchmarks/](benchmarks/README.md)。同模型的 CLI harness 对比（goose / opencode 经 MCP 接入）**正在运行**，跑完即更新同文件中的表格。

## 硬件

真实机器实测，不是估算：

| 档位 | 硬件 | 模型范围 | 体验 |
|---|---|---|---|
| 入门 | AMD 680M 核显 · 16 GB 内存 | 2–4B | 流式近实时 |
| 基准 | Intel Arc B390 核显 · 32 GB 内存 | 2–35B（MoE） | 35B 长任务端到端可跑 |

核显或入门级独显即可，更高端的独显自然不在话下。鸣鸟不包装、不代理模型——自身静态 prefill 稳定在 ~850 token 以内。

## 快速开始

鸣鸟有**四种运行方式**——引擎相同，按需选择：

| 你想要 | 方式 |
|---|---|
| Windows 桌面客户端 | [Releases](../../releases) 里的 `Mingbird-v1.4.0-EN/CN-Setup.exe` |
| Linux / macOS 桌面客户端（实验） | Releases 里的 CI 构建 tar.gz → `sh install-unix.sh` |
| 源码运行（桌面 GUI） | `pip install -r requirements.txt` → `python agent_gui.py` |
| **浏览器里的 Web UI**（实验） | `pip install -r requirements.txt` → `python webui/server.py` → 打开 http://127.0.0.1:8765 —— [指南](docs/webui_zh.md) |

四种方式共享会话、技能、MCP 与设置。

1. 安装 [Ollama](https://ollama.com) 并拉一个模型：
   ```
   ollama pull gemma4:e2b      # 小而快
   ollama pull qwen3.5:4b      # 4B，基准主力
   ```
2. 从 [Releases](../../releases) 下载 `Mingbird-v1.4.0-EN-Setup.exe`（或 `-CN` 中文版）并安装 → 桌面快捷方式。
3. 启动，选模型，直接派活。

Linux & macOS（实验性，CI 构建）：从 Releases 下载 `mingbird-v1.4.0-linux-x64.tar.gz` 或 `mingbird-v1.4.0-macos-*.tar.gz`，解压后 `sh install-unix.sh`，启动 `~/.local/share/Mingbird/LocalAgent`。macOS 需在该机上安装 Ollama。

源码运行：`python agent_gui.py`（图形界面）或 `python ollama_agent.py --help`（命令行）。建议 Python 3.12。

## 安全

> [!WARNING]
> 鸣鸟会读写你磁盘上的文件、执行命令。请谨慎指定工作目录。

机制而非口号：工作目录边界守护（规范化路径判定）、敏感路径读写门（`.ssh`、`.env`、凭据）、越界操作 GUI 人工确认、并行子代理默认拒绝。

## 诚实的局限

2B 模型不会一次性重写你的整个代码库——但它能可靠完成日常 agent 工作的大头，做不到时会大声失败（而不是悄悄做错）。核显跑 35B 可用但不快。LRAB 是我们自建的基准——这正是我们把任务、判分、转录全部公开的原因：欢迎复跑，不用信我们。

## 许可

Apache-2.0 —— 自由使用、修改、分发。
