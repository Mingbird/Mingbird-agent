# 竞品调研:本地 LLM 轻型 agent(2026-08-19)

> 目标:别人能做到的我们做得更好更快;别人做不到的我们想办法做到。
> 来源:网络调研(轻量框架 + 桌面应用 + 小模型优化技术)。

## 一、竞品格局

### 轻量框架
| 框架 | 语言 | 特点 | 缺陷 |
|---|---|---|---|
| SmoLAgents (HF) | Python ~3K行 | 工具为中心,代码型 agent | **无持久记忆** |
| GenericAgent | Python ~3K行 | 技能结晶(技能树,复用不烧token) | 单维护、文档薄、无沙箱 |
| Micro-Agent | Python <3K行 | ReAct+RAG+MCP+多LLM配置 | 垂域窄 |
| Nanobot | Python ~4K行 | OpenClaw核心,MCP为中心 | 无容器隔离 |
| FastClaw | Go 单文件 | 零依赖,内置渠道+看板,并发工具 | 默认安全宽松 |
| ZeroClaw | Rust 单文件 | 20+ provider,30+ 渠道 | 生态薄 |
| NullClaw | Zig | 678KB,~1MB 内存 | 文档少 |
| IronClaw | — | WASM 沙箱,密钥/PII 泄漏检测 | WASM 生态未熟 |
| OpenClaw | Python | 最流行但**臃肿/烧token/无沙箱危险** | 前置上万 token |

### 桌面应用
| 应用 | 亮点 | 可借鉴 |
|---|---|---|
| Hermes Desktop (Nous) | 语音模式、**自然语言定时**、Computer Use、MCP 网关、桌面/CLI/TUI 共享配置 | NL 调度、跨界面共享 |
| Mint | SQLite 本地记忆、`/memory` 命令、**本地目录索引(知识库)** | 本地 RAG |
| VoiceAgent | **拆分模型架构**(路由 7B + 代码 7B + 摘要 8B)、**确定性管线(弃 ReAct)**、`_repair_json` 正则修复 | 路由+修复 |
| AI_Linux_Assistant | 13 个类型化工具、门控 shell、无 sudo | 安全门控 |
| A.I.V.A | int8 STT + 7B 意图、**Raw-Reasoning 正则提取**、单例驻留 | 结构输出 |

## 二、小模型优化关键技术(我们没全用上的)
1. **拆分模型路由**:一个 1-7B 轻量模型做意图/路由(JSON 稳定),专业任务交给更大模型。我们已有多模型,可加"路由层"。
2. **确定性管线 vs ReAct**:<10B 模型 ReAct 循环不稳(幻觉参数/死循环)。我们用工具调用+harness 检测已缓解;可进一步"结构化输出加固"。
3. **JSON 修复**:`_repair_json()` 正则回退抢救畸形输出。我们有 `try_parse_tool_calls` 抢救,可加正则修复。
4. **结构输出提示工程**:显式"只输出 JSON"、few-shot、pydantic schema。我们的 SYSTEM 已引导,可加。
5. **线性 VRAM 管线**:STT 先跑→释放→再加载 LLM。我们语音独立(CPU sherpa),天然线性。
6. **本地知识库/RAG**:Mint 索引目录可搜索。我们只有 memory.json,没有文件级 RAG。**最大缺口之一**。
7. **自然语言定时**:Hermes 用 NL 创建 cron。我们靠 MyAgents 外部任务,可加 NL→Task。
8. **技能结晶**:GenericAgent 把成功任务序列化成技能复用。我们 skills 是静态的,可加"学到的技能"。

## 三、我们的优势(别人未必有)
- **极简前置 737 tokens**(OpenClaw 9405,我们 1/13)
- **harness 健壮性全家桶**:文件自愈、工具调用抢救、四级循环检测、禁用机制、假完成守护、上下文自动压缩修复
- **Windows 桌面 GUI + 聊天气泡 + 会话历史全文搜索**
- **三模型实测迭代流程**(每轮自动发现并修 bug)
- **中文语音**(sherpa-onnx 14M,离线,快于实时 20×)

## 四、差距清单(我们要补的)
| 优先级 | 功能 | 参照 | 现状 |
|---|---|---|---|
| P0 | **本地知识库/RAG**(索引目录→检索) | Mint | 无 |
| P0 | **结构输出加固**(正则 JSON 修复) | VoiceAgent | 部分(有 salvage) |
| P1 | **模型路由**(轻量路由+专业模型) | VoiceAgent/Micro-Agent | 无(单模型) |
| P1 | **自然语言定时任务**(NL→schedule) | Hermes | 外部 MyAgents 可桥接 |
| P2 | 技能结晶(成功任务→新技能) | GenericAgent | 无 |
| P2 | 语音增强(持续聆听/唤醒词) | Chronos | 按钮式已有 |
| P2 | Computer Use / 系统控制 | Hermes | 仅 run_bash |

## 五、下一批 3 个版本设计方向(阶段三)
基于差距,设计 3 个版本让三模型迭代实现:
- **V21(0.6.1) 结构输出加固**:给 agent 加 `_repair_json` 正则修复 + 更严格的结构输出提示;用乱码 JSON 输入实测修复率。
- **V22(0.6.2) 本地知识库**:给 agent 加文件索引/检索工具(search 增强),实现 Mint 式本地 RAG,实测检索准确率。
- **V23(0.6.3) 模型路由层**:给 agent 加"路由"能力(简单任务用轻模型、复杂用重模型),三模型配合,实测任务分流正确率。

---
*下一轮调研将验证这些方向并找新差距。*
