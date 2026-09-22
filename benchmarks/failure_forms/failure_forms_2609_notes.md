# M10 编码表配套说明（判据、独立性核验、已知边界）

生成物：`failure_forms_2609.csv`（288 行逐格）、`failure_forms_summary_2609.csv`、`failure_forms_2609.md`（表）
生成脚本：`code_failure_forms.py`（只读既有产物，可复跑；288 格全部解析成功，唯一缺件为 goose/WF08/qwen3.5:4b 的 0 字节 transcript）

## 1 判据来源分层（决定可信度等级）

| 等级 | 形态 | 判据 |
|---|---|---|
| A 记录字段 | platform_exit / budget_exhausted / 交付不完整 | `score.json` 的 `failure_mode` / `exit_code` / 产物检查明细，零判读 |
| B 文档化标记 | spin（空转拦截）/ format_breakdown / context_pressure / false_finish | transcript 里 harness 自己打印的固定文案（与 `mechanism_log/extract_p1.py` 同一套已验证标记） |
| C 近似口径 | provider_error | transcript 含 `Provider error` / `Error communicating with LLM` 等字样（由盲编码者独立发现后加入） |
| D 判断口径 | early_stop | 非崩溃/超时且发布分 < 0.5（阈值型定义，见 §3 分歧） |

## 2 独立性核验（inter-coder agreement）

第二位编码者（独立 LLM，盲于第一位的输出）对**分层抽样 24 格**（4 臂 × 低/中/高各 2 格，种子 2609）独立判读；样品清单 `sample_cells_2609.csv`，盲编结果 `sample_codes_2609_blind.csv`。

| 形态 | 一致 | 双方都判 | 分歧明细 |
|---|---|---|---|
| platform_exit | 24/24 | 24 | — |
| budget_exhausted | 24/24 | 24 | — |
| never_engaged | 24/24 | 24 | — |
| spin | 6/6 | 6（仅鸣鸟有判据） | — |
| format_breakdown | 6/6 | 6（仅鸣鸟有判据） | — |
| early_stop | 21/24 | 24 | 3 格，全部落在定义边界：2 格（opencode WF08/WF09，发布分 0.571）盲编按"产物未写完即停"判是、脚本按"分 < 0.5"判否；1 格（鸣鸟 LH02）盲编用 `score.json` 的 `final_score`(0.607) 而脚本用发布口径 `total`(0.403) |

结论：**机械判据（A/B/C 级）在样品上 100% 一致；唯一分歧来自 D 级阈值定义**，已在正文把 early_stop 标注为"判断型"并给出定义。

## 3 已知边界与陷阱（勿误读）

1. **`spin` / `format_breakdown` / `context_pressure` / `false_finish` 只对鸣鸟臂可编码**：其余三臂没有对应计数器，且它们 transcript 里的 "error/✗" 字样会把 PowerShell 报错回显、生成侧截断等异构事件一起算进来（曾试算得 goose 69/72 的假阳性），因此汇总表对这些臂一律记 `n/a`，原始计数只留在逐格 CSV 备查。
2. **轻度拦截也计为"是"**：`spin` 是"标记出现"而非"因果致败"。样品里 3 格（鸣鸟 WF10/WF14 满分、goose WF10 0.786）被拦截后自行恢复或已交付。正文必须写成"发生率"而非"致败率"。
3. **`provider_error` 是基础设施层失败**：agent-mini 8/72，`failure_mode` 仍记 `completed`、`exit_code` 0 —— 只看记录字段会漏掉它。这解释了 agent-mini 部分零分格与 harness 机制无关。
4. **`early_stop` 与 `incomplete_delivery` 不应混用**：前者是"分低且非崩溃/超时"，后者是"至少一条产物检查未过"（机械）。两列的臂间排序一致方向（鸣鸟最少），但数值不可互相替代。
5. **goose/WF08/qwen3.5:4b 一格**：0 字节 transcript（两次合法超时 + 一次外部击杀，2026-09-18 用户裁定记零分，见 `rr_think0/EXCLUSIONS.md`），其工具调用计数记 unknown 而非 0，避免造出假"零工具接触"。
6. **opencode 的"零工具接触"21/72** 是真实形态：该臂在 2B 档（18 格）几乎全程未发出工具调用，另有 3 格散落别处；这与 `turns_resource_summary.csv` 里 opencode 2B 工具调用均值为 0 相互印证。
