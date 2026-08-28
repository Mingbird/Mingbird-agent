# Hummingbird Publication & Launch Roadmap (HN → JOSS)

> 设计日期: 2026-08-28
> 目标: ①无懈可击的 HN 发布 ②同行评议开源软件期刊(JOSS)发表
> 基于五轮系统调研: 竞品(agent-mini/goose/opencode)、JOSS 审稿标准、agent benchmark 现状、HN 发布要素

---

## 1. 调研发现汇总 (Research Findings)

### 1.1 竞品对比 (同一赛道: local-first agent)

| 维度 | **Hummingbird (我们)** | **agent-mini** | **goose (Block)** | **opencode (SST)** |
|---|---|---|---|---|
| 语言/规模 | Python, ~3K 行(引擎) | Python, ~3K 行 | Rust, 大型 workspace | TypeScript (Bun 编译) |
| 界面 | **GUI(tkbootstrap) + CLI + 语音** | 纯 CLI (+Telegram) | CLI + Electron 桌面 + REST/ACP | TUI/CLI + 桌面 |
| 定位 | 本地小模型科研工作流 agent | 极简本地 ReAct agent | 通用开发者 agent 框架 | 开发者编码 agent |
| 小模型特化 | 扁平 prefill(类别路由,851tok)、问答/任务分层、渐进披露 | tier 分级提示、上下文剪枝、工具修复、循环检测 | 无(面向强模型) | budgeted catalog、CodeMode |
| 文档处理 | **内置 create/read docx/pdf、语音输入、学术技能 22 个** | 无 | 无 | 无 |
| 安全 | **守护系统(边界+敏感路径+GUI 确认+危险命令)** | sandboxLevel 配置 | 权限系统+环境变量保护 | 沙箱+审批 |
| 评测 | 五轮非正式对决(待系统化) | **已有 task-eval harness** | 无公开 | 无公开 |
| 生态 | MCP 7 服务器+远程 HTTP | 插件(py 文件) | MCP 70+ 扩展 | 插件+MCP |

**定位结论**: "minimal local agent"赛道已经很卷(agent-mini/mini-swe-agent/miniagent 等 dozens),但**"面向科研工作流 + 文档产出 + 端到端打包(语音/GUI/守护)"是空白**。JOSS 视角的 build-vs-contribute 论证: 现有框架均不提供"开箱即用的学术文献工作流"(检索→审稿→返修→引用),也均不面向"UMA 核显 + 32GB 内存"的极端资源约束做 harness 级优化。

### 1.2 JOSS 硬门槛 (关键时间约束)

| 门槛 | 现状 | 差距/行动 |
|---|---|---|
| **公开开发史 ≥6 个月**(自动检查 commit 分布) | ❌ repo 2026-08-21 公开(7 天) | **最早投稿 2027-02-21**;期间持续开发即可满足 |
| 明确 research application | ✓ 学术文献工作流场景 | 论文明确表述 |
| 测试套件 + CI | ⚠️ 少量手动测试 | **补 pytest 套件 + GitHub Actions** |
| 打包规范 | ⚠️ 无 pip 包 | PyPI 可安装(engine 包) |
| 文档/CHANGELOG/releases | ✓ 部分 | 补 CONTRIBUTING + 版本化 release |
| Research impact 证据 | ⚠️ 需积累 | 自己用它跑科研工作流 + preprint 引用 |
| 论文 750-1750 词, 六节固定结构 | - | Summary / Statement of need / State of the field / Software design / Research impact / **AI usage disclosure**(诚实披露 AI 辅助开发,JOSS 允许但必须披露+人工审核) |
| 收费 | JOSS 免费(OA); SoftwareX 收 $1560 | 选 JOSS |

### 1.3 Benchmark 选型 (调研结论)

| 基准 | 适合度 | 说明 |
|---|---|---|
| **GAIA L1 (53 题)** | ★★★ 主基准 | 权威、单答案可验证、规模适中;**已有先例**(atomic-agent vs Hermes 同一本地 35B 跑 L1,控制变量法+原始数据放 GitHub release);官方 scorer 有开源移植,判分公平。需 HF token+GAIA license。需联网(搜索类任务) |
| **自建 LRAB** (Local Research Agent Benchmark) | ★★★ 特色基准 | 英文、材料科研工作流垂直场景(检索→综合→审稿→引用),GAIA 不覆盖;10-15 任务,分级判分(产物存在性+内容判据+LLM judge) |
| SWE-bench / τ-bench / AgentBench | ✗ 不采用 | 测的是别的能力(代码修复/客服对话/广度);与"科研工作流 agent"不匹配——benchmark 必须匹配被测能力(2026-08 综述结论) |

### 1.4 HN 发布要素
- Show HN 格式: 标题 "Show HN: Hummingbird – a local-first AI agent for research workflows on small GPUs"
- 发布时机: 美东周二-周四早上;首条评论讲动机+架构+**诚实局限**(HN 最反感营销腔)
- 数据支撑: 带上 GAIA/LRAB 分数表(有数据的 Show HN 存活率和讨论质量远高于裸发布)
- 现有 hn-post.md 为 v1.0.0 版本,需按 v1.1.x + 评测数据重写

---

## 2. 蜂鸟 SWOT (发布/投稿视角)

**S**: 端到端打包(GUI+语音+学术技能+守护)唯一;harness 兜底哲学(500 自愈/结构修复/守护)有真实实证;851-token prefill + 按需分层有可量化优势;真实 UMA 核显场景稀缺
**W**: 单作者;无测试/CI;无学术评测;Python 性能一般;文档偏中文
**O**: local-first agent 是 2026 热点;材料×AI 交叉期刊蓝海;JOSS 6 个月窗口正好用于建设
**T**: agent-mini 同类快速迭代;GAIA 网络依赖(国内访问需代理);OEM 驱动不稳定(B390 已实证)

---

## 3. 基准测试设计 (Benchmarks — 英文原始内容)

### 3.1 Benchmark A: GAIA validation Level 1 (53 tasks)
- 数据: GAIA 2023 validation L1(HF, 需 license)
- 判分: 官方 scorer 逻辑移植(Python): 数字归一化 + 列表切分 + 标点不敏感匹配; 每任务 `FINAL ANSWER:` 提取
- 协议: 每任务独立临时 workdir、max 40 steps、15min 超时、temp=0(蜂鸟)/各家默认(记录在案)、顺序执行(单 GPU 排他)
- 报告: accuracy + avg steps + avg wall-time + token 成本; 原始轨迹全部发布到 GitHub release

### 3.2 Benchmark B: LRAB (Local Research Agent Benchmark) — 自建,英文
15 个材料科研工作流任务,3 级:
- **Tier 1 Retrieval (5)**: e.g. *"Find the 2023 Materials journal paper on Ti-6Al-4V aging at 500°C. Save title, authors, DOI to references.md."* 判分: 文件存在 + DOI 正则 + 关键字段 LLM judge
- **Tier 2 Synthesis (5)**: e.g. *"Given data_table.md (provided), write a 300-word analysis of aging temperature vs elongation with mechanistic reasoning. Cite [n] markers."* 判分: 结构完整性 + 引用一致性(脚本) + 质量评分(rubric LLM judge)
- **Tier 3 Workflow (5)**: e.g. *"Review draft.md as referee: produce review_round1.md with ≥4 numbered issues (location+problem+severity); then revise to final.md with change log."* 判分: 流程完成性 + 问题真实性(judge) + 修复对应率
- 全部任务带确定性前置检查(文件存在/格式)+ 二级 rubric judge(独立 judge 模型,不用被测模型)
- fixture 数据(论文/表格)随 repo 发布,任务可离线复现(检索类任务 mock 化可选)

### 3.3 实验矩阵 (模型梯度 = 核心论证)
```
软件: {Hummingbird, opencode, agent-mini, goose}
模型梯度: {ornith-1.5:35b, gemma4:12b, qwen3.5:4b, gemma4:e2b}
         (本地 Ollama; 35B→2B 四点梯度, 控制变量: 同模型同量化同 num_ctx=32K)
基准: {GAIA-L1, LRAB}
指标: task accuracy | avg tool calls | prompt tokens | completion tokens |
      wall time | crash/recovery count | failure-mode classification
组合: 4 软件 × 4 模型 × 2 基准 = 32 runs (LRAB 全矩阵; GAIA 小模型格允许 L1 前 20 题抽样)
```
- **核心图表: graceful degradation 曲线** — x=模型规模(35B→12B→4B→e2b), y=任务完成率。
  预期/主张: 蜂鸟曲线平缓(harness 兜底: 类别路由+问答分层+结构修复+防假完成),
  其他 agent 随模型变小断崖式下跌(tool-format-failure / loop / timeout)。
- **失败模式分类**(小模型格的"失败"是核心数据, 非缺失):
  {completed, partial, tool-format-failure, loop, fake-finish, timeout, crash}
- 公平性协议: 同一 Ollama 实例、同一模型 tag、同一硬件、各软件默认配置+记录在案(不完全可控变量须披露,参考 atomic-agent 的 caveats 写法)
- 附加测量: 每软件的 prefill token/轮次(验证蜂鸟"低 prefill"主张)、token/s 吞吐(同一后端下差异=harness 开销)
- 分层执行: LRAB(离线、稳定)跑全 32 格; GAIA L1 先跑 4 软件×35B/12B(16 格), 小模型格(4B/e2b)先抽样 20 题再决定是否全跑

---

## 4. 开发流程 (6 个月 JOSS 窗口里程碑)

### M0 (现在 → 2026-09-15): 评测基础设施
- [ ] `bench/` 目录: LRAB 任务集(英文, 15 tasks + fixtures + judge 脚本 + runner)
- [ ] GAIA L1 runner(HF 下载 + scorer 移植 + 各软件 adapter: 蜂鸟 CLI/opencode run/agent-mini/goose CLI)
- [ ] 指标采集: 各软件日志解析器(工具调用数/token/时间)→ 统一 results JSON
- [ ] 蜂鸟补 pytest 核心测试(safe_path/batch_tools/compact/routing) + GitHub Actions CI
- [ ] PyPI 可安装包(hummingbird-agent)

### M1 (2026-09): 数据收集 + HN 发布
- [ ] 跑满 16-run 矩阵(每 run 全轨迹存档)
- [ ] 结果表 + 图(accuracy/token cost/时间)
- [ ] **Show HN 发布**(数据在手后): 重写 hn-post.md(v1.1 卖点 + 评测表); checklist.md 执行
- [ ] 同步: Reddit r/LocalLLaMA、B站

### M2 (2026-10 → 11): arXiv preprint
- [ ] 技术报告(英文, 8-12 页): 动机(UMA 资源约束)→ 设计(prefill 预算/渐进披露/守护/自愈)→ 评测(GAIA+LRAB 矩阵)→ 失败模式分析(五轮对决的 500 根因/UMA 换页/harness 兜底实证)
- [ ] arXiv 挂 cs.MA/cs.AI; 引用格式确立(Research impact 证据#1)
- [ ] 用户自用案例: 用蜂鸟完成一次真实文献综述并记录(Research impact 证据#2)

### M3 (2027-02 →): JOSS 投稿
- [ ] paper.md(英文, ≤1750 词, 六节)
- [ ] 检查全部 JOSS 门槛: 6 个月历史✓ / 测试 CI✓ / PyPI✓ / 文档✓ / impact✓
- [ ] 公开 review 流程(1-2 月)

---

## 5. HN 发布稿结构 (v2, 英文)

- **标题**: `Show HN: Hummingbird – local-first AI agent for research workflows on an iGPU`
- **正文要点**(首评论): 动机(32GB UMA 笔记本,无独显,不想数据出机器)→ 核心设计(851-token prefill、类别路由、渐进披露、守护系统、500 自愈)→ **评测表**(GAIA L1 + LRAB × 4 agents × 2 models)→ 诚实局限(单作者、Windows 优先、35B 贴极限跑、偶发 500 自愈)→ GitHub 链接
- **数据表格**(发布稿内嵌): 同 layout 的对比表(设计见 §3.3)
- 避坑: 不用营销词、准备被问"为什么不 LangChain/为什么 Windows"、所有声称可复现(bench/ 全公开)

---

## 6. JOSS 论文结构 (英文六节, ≤1750 词)

1. **Summary**: 面向非专家: local AI agent that runs literature-review workflows entirely on a consumer laptop with an integrated GPU
2. **Statement of need**: researchers without discrete GPUs / privacy-constrained labs need offline agents; existing frameworks target strong cloud models and developer workflows
3. **State of the field**: 对比 goose/opencode/agent-mini 表格 + build-vs-contribute(无现成框架覆盖科研文档工作流 + 资源受限 harness 优化)
4. **Software design**: flat prefill & category routing / progressive disclosure / guard system / self-healing loop / eval harness;架构取舍说明
5. **Research impact statement**: arXiv preprint + 自用案例 + GAIA/LRAB 公开数据 + GitHub stars/issues
6. **AI usage disclosure**: 诚实披露 AI 辅助开发范围 + 人工审核与设计决策声明

---

## 7. 风险与诚实清单
- **单作者**: JOSS 明确接受 solo(要求更多开放信号),但要提前补 CONTRIBUTING/governance
- **AI 开发**: JOSS 允许+要求披露;核心设计决策(本路线图全部架构方向)由人确认
- **GAIA 网络依赖**: 国内网络需代理跑评测;记录网络环境于 caveats
- **OEM 驱动不稳定**: B390 驱动历史(B390 Vulkan bug)写入 limitations——这反而是"harness 自愈设计"的动机证据
- **评测可复现性**: 单 run、temp=0、软件默认参数不完全可控——按 atomic-agent 先例逐项披露
- **时间**: JOSS 最早 2027-02;HN 可提前(M1)不受限

---

## 8. 立即行动项 (本周)
1. LRAB 15 任务英文定稿(人工审核 AI 草案) → `bench/lrab/`
2. GAIA HF license 申请 + 数据下载 → `bench/gaia/`
3. 蜂鸟 pytest + CI 最小集
4. opencode/agent-mini/goose 三软件安装 + CLI adapter 验证(各跑 1 个 LRAB smoke task)
