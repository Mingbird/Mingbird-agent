# LRAB 矩阵结果（论文数据源）

> **正式数据集**: 2026-08-28/29 夜间矩阵，WF-06 × 4 agent × 4 model = 16 格全部完成，
> 归档于 `~/dev/hummingbird/eval_results/`（16/16 canonical），MANIFEST 在 `bench/lrab/MANIFEST.json`。
> 此前的旧配置批次（旧提示词 + 25min 预算 + num_ctx 不一致）已整体归档至
> `bench/lrab/results/prematrix_archive_20260828/`，只作开发验证，不入论文。

## 公平性协议（本数据集实测口径）

| 维度 | 设定 |
|---|---|
| 模型 | 同一 ollama 实例，同 tag：ornith-1.5:35b / gemma4:12b / qwen3.5:4b / gemma4:e2b |
| num_ctx | 蜂鸟=32768（AGENT_CTX）、opencode=32768（config 钉死）、agent-mini=32768（provider patch）；goose 无 ctx 旋钮走 ollama 默认（唯一差异源，单独披露） |
| 温度 | 全部 temp=0（goose 无温度旋钮按默认，披露） |
| 搜索 | DuckDuckGo 同源（蜂鸟/opencode/goose 走 MCP，agent-mini 内置 web_search 直连 DDG html/lite 端点——暴露形式不同、来源相同，披露） |
| 任务提示 | 工具名中立（"todo tool if available, otherwise plan.md"），四家逐字相同 |
| 时间预算 | **统一 40 min/cell**（旧批 25 min 会截断健康 12b 运行，见下方"预算教训"） |
| 判分 | 纯确定性（8 种 check + image_valid PNG 校验），无 LLM judge，跨格可复现 |
| 隔离 | opencode XDG 空目录屏蔽全局 7 学术 MCP；agent-mini 备份/还原真机配置；goose --path 钉工作目录 |

## 正式矩阵：WF-06（统计分析与可视化，tier2）

| Agent | ornith 35b | gemma4 12b | qwen3.5 4b | gemma4 e2b | 均值 |
|---|---|---|---|---|---|
| **hummingbird** | **1.00** (383s) | **1.00** (1013s) | **0.71** (479s) | 0.43 (364s) | **0.79** |
| goose | 1.00 (503s) | 1.00 (1812s) | 0.57 (1067s) | 0.29 (290s) | 0.71 |
| agent-mini | 0.00† (53s) | 1.00 (276s) | 0.57 (102s) | **0.64** (124s) | 0.55 |
| opencode | 1.00 (728s) | 0.00 (322s) | 0.00 (1040s) | 0.00 (100s) | 0.25 |

全部 16 格 completed，**零超时/零崩溃**（40 min 预算下）。
† agent-mini-35b: 模型写完 plan.md 后输出纯文本"下一步计划"（无工具调用），
harness 视其为最终回答退出（failure_mode=early_finish）——真实行为数据。

### 关键结论（论文叙事）

1. **蜂鸟均值第一（0.79）**，且是唯一 35b 与 12b 双满分的 agent；12b 满分耗时
   1013s，比 goose 同满分 1812s 快 44%。
2. **优雅降级曲线最平缓**（35b→e2b 保留率 43%）vs goose 29% vs opencode 断崖
   （1.0→0→0→0）。蜂鸟在中档模型段（12b/4b）全部领先。
3. **e2b 段蜂鸟第二**（agent-mini 0.64 > 蜂鸟 0.43）：agent-mini 轻量 harness 在
   2B 级模型上反而占优——如实报告；蜂鸟优势集中在 ≥4B 区间。
4. **opencode 的 0 分是真实能力失败**，非环境故障：12b/e2b 读任务后无产物
   （no_artifacts），4b 干满 17 min 但无视 exact-filename 要求、产物全部改名
   （completed 但 0 分）。35b→小模型的指令遵循崩塌是 LRAB 要量化的核心现象。
5. **蜂鸟 4b（0.71）> 竞品 4b（0.57）**，验证"扁平 prefill + 类别路由"对中档
   模型的兜底作用。

### 预算教训（方法学披露）

旧批 25 min 预算产生过 5 个 timeout"失败"；40 min 预算下同样的格全部正常完成
（goose-12b 旧批超时×2，本批 1812s 满分；蜂鸟-12b 干净环境 712s 0.929 / 矩阵内
1013s 满分）。**小模型超时≠能力不足，先排除预算与环境污染再定结论。**
2026-08-28 晚的 2h 系统休眠曾毁掉一批运行——run_matrix 现内建 keep-awake
（SetThreadExecutionState，进程级，不改系统设置），长矩阵不再依赖外部进程存活。

### 单任务快照的方差警告

WF-06 单任务格间存在真实方差（蜂鸟-12b 两次运行 0.929/1.0；opencode-4b 历史
1.0 → 本批 0.0）。单任务矩阵是快照，不能当稳定均值引用；论文结论以
4agent×4model×15task=240 格全集（当前 16 格）或多样本子集为准。

## 下一步

- [ ] 扩展到多任务（WF-01..15 抽样 ≥5 域）
- [ ] 全矩阵 4×4×15 = 60 格（Task #63）
- [ ] GAIA-L1（等 HF license + 网络，Task #62）
