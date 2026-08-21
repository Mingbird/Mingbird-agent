# AGENTS.md — 蜂鸟 · 本地 AI 助手:给 AI 阅读的安装与使用手册

> 本文档面向「在安装了本软件的电脑上运行的 AI agent」。目标是让任何 agent 读完后都能:
> 1) 理解这个软件是什么、能做什么;2) 正确启动/配置;3) 帮助人类用户完成本地大模型任务。

---

## 1. 软件是什么

这是一个 **面向本地小模型的自主 agent 桌面应用**(Windows)。核心特点:

- **极简前置 token**:系统提示 + 9 个核心工具 schema 共约 **737 tokens**,本地小模型也能直接工作(对比主流 agent 上万 token 的前置)。
- **渐进式披露**:高级工具(网页/记忆/MCP/搜索等 8 个)默认不加载,模型需要时用 `enable_tools` 按需启用;技能只列名字+一句话,用到才加载全文。
- **自主执行**:模型通过工具调用真正读写文件、运行命令、迭代测试,而非只给建议。
- **GUI 交互**:聊天式界面,支持任务/对话、附件上传、会话历史搜索、实时计划面板、中文语音输入、主题切换。

## 2. 前置条件(目标电脑必须满足)

- Windows 10/11
- **Ollama 已安装并运行**(默认 http://127.0.0.1:11434),且已拉取本地模型
- Python 3.10+(若源码运行;安装版 exe 不需要)

### 按硬件选模型(重要 — 不同机器差异很大)
软件会自动识别 ollama 里已装的模型(GUI 模型下拉动态列出)。按机器算力选合适的模型:

| 机器档次 | 参考硬件 | 推荐模型 | 说明 |
|---|---|---|---|
| **入门(1B 级)** | 核显笔记本 / 8GB 内存 | `qwen3:0.6b` / `gemma3:1b` / `llama3.2:1b` | 只能跑 1-3B;上下文建议 8-16K,速度优先 |
| **主流(4B 级)** | 核显 / 16GB 内存 | `gemma4:e2b`(5.1B,快) / `qwen3.5:2b`(256K 上下文) | 最均衡,日常主力 |
| **高性能(35B 级)** | 独立显卡 / 32GB+ 内存 | `qwen3.5:35b-a3b`(MoE 只激活 3B) / `qwen3:32b` | 复杂推理/长代码,上下文可上 128K |

要点:
- **MoE 模型**(如 `qwen3.5:35b-a3b`,总 35B 但每 token 只激活 ~3B)是"弱硬件跑大模型"的王道——推理快、质量高。
- 模型越大,上下文别开太大(内存墙);模型越小,越要靠**长上下文**补工作记忆(如 qwen2b 开 128K/256K)。
- 软件内置模型路由参考(bench/v37):网络调研类→偏 e2b,规则/安全类→偏 Mellum2,明确代码类→偏 qwen2b。

## 3. 安装方式

### 方式 A:安装版(exe/setup.exe,推荐)
1. 运行 `setup.exe`,按向导安装(默认装到 `C:\Program Files\LocalAgent`)。
2. 安装程序会自动放置:`LocalAgent.exe`(主程序)、`skills/`(技能库)、`AGENTS.md`(本文档)、`README.md`(人类文档)、`mcp.json`(MCP 配置模板)。
3. 双击桌面「蜂鸟」图标启动。

### 方式 B:源码运行(开发)
```bash
# 依赖(Windows):
pip install ttkbootstrap sounddevice sherpa-onnx soundfile numpy requests beautifulsoup4 mcp==1.9.0 pyinstaller
# 启动 GUI:
python agent_gui.py
# 或命令行 agent:
python ollama_agent.py <model> <taskfile> <workdir>
```

## 4. 首次配置

1. 确认 Ollama 在运行:`curl http://127.0.0.1:11434/api/version` 返回版本号。
2. 拉取模型(如需):`ollama pull gemma4:e2b`(或其他,按上表硬件选型)。
3. 打开 GUI,顶部模型下拉框会**自动列出 ollama 里所有已装模型**(自动识别)。
4. 设置工作目录(默认 `~/agent_tasks`),点「打开」可查看。

### 4.1 机器配置(config.json)— 让软件适配你的机器,而非写死

软件**不硬编码任何个人/机器信息**。所有本机相关的配置都放在
`~/.ollama_agent/config.json`(没有则用默认值,首次可复制仓库里的 `config.json.example`)。

```json
{
  "ollama_host": "http://127.0.0.1:11434",
  "ollama_exe": "",
  "ollama_env": {},
  "models": {}
}
```

| 字段 | 说明 |
|---|---|
| `ollama_host` | Ollama API 地址。改了端口/换了远程机器,改这里即可。 |
| `ollama_exe` | `ollama.exe` 完整路径。留空 `""` = 自动检测(PATH 或常见安装目录)。 |
| `ollama_env` | 启动 Ollama 时的**额外环境变量**(按你机器配置,如 AMD 核显加速 `{"OLLAMA_IGPU_ENABLE": "1"}`)。 |
| `models` | 模型**显示名→tag** 映射,给模型起友好名(可选)。未配置的模型在下拉框显示原始 tag。 |

环境变量可覆盖:`OLLAMA_HOST`(API 地址)、`OLLAMA_BIN`(ollama.exe 路径)。

> 模型不预置:下拉框自动读取你本机 ollama 里实际安装的模型,你不需要在代码里配置模型。

## 5. 全部功能速览

### GUI 界面
| 区域 | 功能 |
|---|---|
| 顶部工具栏 | 模型选择、关闭思考开关、⚙设置、🌓主题 |
| 目录行 | 工作目录选择/浏览/打开 |
| 左侧栏 | 附件列表、会话列表、实时计划(todo) |
| 💬 对话页 | 聊天气泡视图;底部输入框 + ▶运行任务 / ➤发送消息 / 🎤语音 |
| 🖥 日志页 | 流式执行日志 + 清空输出 |
| 状态栏 | 上下文占用进度条(≥90% 自动压缩) |

### 快捷键
- `Ctrl+N` 新对话 · `Ctrl+Enter` 发送 · `Ctrl+F` 历史搜索 · `Ctrl+L` 清日志 · `F5` 运行

### 语音输入
- 按钮「🎤 语音」→ 点击开始录音(按钮变「■ 停止录音」)→ 再点结束,自动转写填入输入框(20 秒超时自动停)。
- 使用本地 sherpa-onnx 14M 中文模型(纯 CPU,快于实时 20×),无需联网。

### MCP 接口
- 配置文件:`~/.ollama_agent/mcp.json`(或程序目录 `mcp.json`)。
- 默认 server:
  - `utils`:current_time / calculate / sha256(自建,参数名宽容)
  - `filesystem`:官方文件系统工具
  - `memory`:官方知识图谱记忆
- agent 通过 `enable_tools(["mcp_call"])` 后可用 `mcp_call(server, tool, args)` 调用。

### 核心工具(9 个,默认可用)
`create_file` `read_file` `edit_file` `list_dir` `run_bash` `todo` `skills` `enable_tools` `finish`

### 高级工具(8 个,按需 enable)
`append_file` `delete_file` `search_files` `web_search` `web_fetch` `memory_store` `memory_recall` `mcp_call`

### 技能库(11 个)
`test_driven` `bug_fix` `markdown_report` `git_workflow` `security_review` `refactor` `performance` `architecture` `documentation` `code_review` `python_best_practices`
- 位置:`<程序目录>/skills/` 或 `~/.ollama_agent/skills/`
- agent 用 `skills(action=load, name=...)` 加载,用 `skills(action=list)` 列出。

## 6. 环境变量(可覆盖默认)

| 变量 | 默认 | 说明 |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API 地址(替代 config.json 的 ollama_host) |
| `OLLAMA_BIN` | 自动检测 | ollama.exe 路径(替代 config.json 的 ollama_exe) |
| `AGENT_CTX` | 32768 | 上下文窗口 |
| `AGENT_TEMP` | 0 | 温度 |
| `AGENT_NUMPREDICT` | 2048 | 输出上限 |
| `AGENT_THINK` | 0 | 1=开启思考模型 thinking |
| `AGENT_SYSTEM_FILE` | - | 自定义系统提示文件路径 |

## 7. 命令行 agent 用法

```bash
python ollama_agent.py <model> <taskfile> <workdir> [--session NAME] [--new] [--append]
python ollama_agent.py <model> --chat <workdir>   # 交互式
```
- `--append`:对话延续(新消息追加进历史)
- 崩溃后重跑同命令(不加 `--new`)可从检查点续跑

## 8. 给 agent 的协作建议

- 本软件是**自主 agent**:给它任务时它会自己规划、执行、验证。你(agent)的职责是帮人类用户把需求转成清晰的任务描述、启动 GUI 或 CLI、解释结果。
- 遇到「假完成」(模型声称完成但没验证):检查产物是否真实存在、测试是否通过。
- 长任务上下文 90% 时自动压缩;崩溃可续跑。
- 详细协作细则见 **第 12 节**(.bak 回滚/精确失败/拦截换策略/模型选型)。

## 9. 版本与更新

- 版本号在 `VERSION` 文件,变更记录在 `CHANGELOG.md`。
- 作息制度:每天 9:00-12:00、14:00-18:00 软件不开发(休息);休息前 10 分钟自动上线已完成功能。

---

*本文档由 AGENTS.md 维护。任何 agent 读完都应能独立完成安装、配置与使用。*

## 10. 安装技能(Skills)—— 让 agent 学会新能力

技能是**纯 Markdown 指令文件**,放在 `skills/` 目录(安装版在 `LocalAgent\skills\`,源码版在 `agent_test\skills\`)。agent 启动时会渐进式披露:只列技能名+一句话描述,**用到才加载全文**——所以技能可以很多,但前置 token 不会膨胀。

### 技能文件格式(必须带 frontmatter)
```markdown
---
name: 技能英文名(小写,如 code_review)
description: 一句话说明这个技能干什么(≤30 字,agent 靠它判断何时用)
---
# 技能正文(给 agent 的完整操作指引)
1. 步骤...
2. 要点...
- 该技能的规则/最佳实践/输出要求
```

### 安装步骤(给 agent 看)
1. 写一个带 frontmatter 的 `.md` 文件(参考 `skills/architecture.md` 的格式)。
2. 放到 `skills/` 目录:`cp my_skill.md skills/my_skill.md`。
3. 立即生效(每次会话启动时扫描)。可在 GUI 的技能列表里看到,或调用 `skills` 工具 list 验证。

### 规范
- **name 用小写英文 + 下划线**,description 一句话说清"何时用"。
- 正文聚焦**该技能的操作流程**,不要放与技能无关的内容。
- 一个技能一个文件;不要把所有技能塞进一个文件(会破坏渐进式披露)。

## 11. 安装 MCP 服务器 —— 接入外部工具

MCP(Model Context Protocol)让 agent 调用外部程序的能力(文件系统、数据库、浏览器、自定义工具)。

### 配置格式(`~/.ollama_agent/mcp.json`)
```json
{
  "server名": {
    "command": "可执行命令(在 PATH 里)",
    "args": ["参数1", "参数2"]
  },
  "my_server": {
    "command": "python",
    "args": ["C:/path/to/my_mcp_server.py"]
  }
}
```

### 安装步骤(给 agent 看)
1. 确认目标电脑有所需运行时(node/npx/python 等,按 MCP server 要求)。
2. 把 server 程序放到本机,在 `mcp.json` 里加一个条目(command + args)。
3. 重启软件。agent 需要时调用 `enable_tools(["mcp_call"])`,然后用 `mcp_call(server="my_server", tool="工具名", args={...})` 调用。

### 内置示例 server(见 `~/.ollama_agent/mcp.json` 或 `mcp/` 目录)
- `filesystem`:文件系统读写(需 mcp-server-filesystem,npm 安装)
- `memory`:持久记忆(需 mcp-server-memory)
- `utils`:纯 Python 工具(时间/计算/哈希,`mcp_utils_server.py`,无需额外依赖)

> 注意:node 类 MCP server 需要目标电脑装 Node.js;纯 Python 的 `utils` server 开箱即用。

## 12. 给 agent 的协作建议(重要)
- 遇到"模型反复修不好"的情况,**先检查是否有 `.bak` 备份可回滚**(edit_file 自动生成),或让模型 `read_file` 看真实内容再改,不要重复同一命令。
- 测试失败时,harness 会注入精确失败信息(文件/行/断言),**先读那段代码**再改,不要盲目重跑。
- 工具被拦截(安全门/重复调用/问答守护)时,**读拦截消息并换策略**,不要原样重试。
- 模型选型参考 `bench/v37` 的路由逻辑:网络调研→e2b,规则/安全→Mellum2,明确代码→qwen2b。
