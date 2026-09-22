# per-arm 资源计量表 — LRAB-288(2026-09-21 取证,零新实验)

生成脚本:`diagnosis/p1_forensics/resource_table_2609.py`(同目录,`python resource_table_2609.py` 可复跑);逐格数据:`resource_table_2609.csv`(288 行)。

数据源(只读):`<EVAL_ROOT>/mingbird-v16/benchmarks/lrab_scores.csv`(288 格 = 4 臂 × 4 模型 × 18 任务)、`<EVAL_ROOT>/<HB>/eval_results/<attempt_dir>/`(Mingbird、agent-mini 臂)、`<EVAL_ROOT>/mingbird-v150/eval_results/rr_think0/<attempt_dir>/`(goose、opencode 臂)。未修改任何源文件。

## 0 口径(先读这一节再看数字)

| 项 | 口径 |
|---|---|
| tool_calls | 各臂自己的工具行为行(正则见脚本头 [1]):Mingbird `[N\|+Xs] ⚙`、agent-mini `⚡ <tool>`、goose `▸ <tool>`、opencode(ANSI 剥离后)`$ 命令` + `→ 动作`。四臂打印格式不同,**跨臂只宜比量级**。 |
| turns | 仅 Mingbird 有真值 = 逐轮 `[ctx: N/32768 = P%]` 行数(每轮一行,含无工具调用的轮)。agent-mini / goose / opencode 无任何逐轮计数器 → `n/a (not recorded)`,不估算。 |
| prompt_tokens_peak | 仅 Mingbird 有真值 = 该格 `[ctx: N/…]` 的最大 N;N 取自 Ollama 响应的 `prompt_eval_count`(打印侧 `mingbird-v150/ollama_agent.py` L2789-2792)。其余三臂 → `n/a (not recorded)`。 |
| 生成侧 token(eval_count) | **全 360 份 transcript 中 0 出现**(唯一打印出口 L2809 本轮 0 触发) → 全表 `n/a (not recorded)`,不估算。 |
| timeout | T1 `score.json.failure_mode == "timeout"`,或 T2 `wall_seconds >= 预算`(WF/tier1-3 = 5400s=90min,LH/tier4 = 10800s=180min;预算由 run_matrix.py `--timeout-min`/`--timeout-min-lh` 下发,本批日志明示 "WF budget=90min, LH budget=180min")。timeout 列写 `yes:<命中判据>` / `no`。 |
| wall_seconds | 直接取 `lrab_scores.csv`;goose/WF08/qwen3.5_4b 一格在源 CSV 缺失 → 保留 `n/a`,不补数。 |
| 未采用的粗口径 | "transcript 里出现 timeout 字样即算超时" 会假阳性:Mingbird 的 `[已超时:300 秒上限]` 是**单条命令** 300s 上限(4 格)、goose 的 output-token limit 警告是**生成侧截断**(17 格)、goose/WF07+WF10 qwen 的 106/216 次 `timeout` 全来自 PowerShell 报错回显。 |

## 1 per-arm 汇总(每臂 72 格 = 4 模型 × 18 任务)

| arm | cells | wall mean (s) | wall median (s) | tool_calls mean | tool_calls median | turns mean | prompt 峰值 median | timeout 格数 |
|---|---|---|---|---|---|---|---|---|
| Mingbird | 72 | 585.5 (n=72) | 440.5 | 46.6 (n=72) | 33.5 | 46.2 | 14624 | 0 |
| agent-mini | 72 | 233.5 (n=72) | 116.4 | 11.5 (n=72) | 7 | n/a (not recorded) | n/a (not recorded) | 0 |
| goose | 72 | 866.4 (n=71) | 692.4 | 28.6 (n=72) | 15 | n/a (not recorded) | n/a (not recorded) | 1 |
| opencode | 72 | 633.4 (n=72) | 450.1 | 23.0 (n=72) | 5 | n/a (not recorded) | n/a (not recorded) | 0 |

注:wall 的统计基数 = 有 wall 值的格;goose 少 1 格(WF08/qwen3.5_4b,源 CSV 缺失)。
turns / prompt 峰值只有 Mingbird 有值,故其余三臂该两列为 `n/a`。

## 2 per-tier 断面(2B/4B/12B/35B × 各臂;每格 18 cells)

| tier | arm | cells | wall mean (s) | wall median (s) | tool_calls mean | tool_calls median | turns mean | prompt 峰值 median | timeout 格数 |
|---|---|---|---|---|---|---|---|---|---|
| 2B | Mingbird | 18 | 384.1 (n=18) | 135.8 | 32.9 | 33 | 36.8 | 8938 | 0 |
| 2B | agent-mini | 18 | 68.2 (n=18) | 63.3 | 4.8 | 5 | n/a (not recorded) | n/a (not recorded) | 0 |
| 2B | goose | 18 | 69.7 (n=18) | 62.5 | 7.7 | 5.5 | n/a (not recorded) | n/a (not recorded) | 0 |
| 2B | opencode | 18 | 38.7 (n=18) | 40 | 0 | 0 | n/a (not recorded) | n/a (not recorded) | 0 |
| **2B 合计** | 全臂 | 72 | 140.2 (n=72) | 57.9 | 11.4 | 5 | 36.8 | 8938 | 0 |
| 4B | Mingbird | 18 | 848.7 (n=18) | 640.6 | 73.4 | 58.5 | 74.1 | 19162 | 0 |
| 4B | agent-mini | 18 | 209.2 (n=18) | 199.2 | 22.9 | 18.5 | n/a (not recorded) | n/a (not recorded) | 0 |
| 4B | goose | 18 | 1037.8 (n=17) | 1121.5 | 58.2 | 32 | n/a (not recorded) | n/a (not recorded) | 1 |
| 4B | opencode | 18 | 1023.7 (n=18) | 1003.4 | 70.9 | 42 | n/a (not recorded) | n/a (not recorded) | 0 |
| **4B 合计** | 全臂 | 72 | 776.2 (n=71) | 629.8 | 56.4 | 37 | 74.1 | 19162 | 1 |
| 12B | Mingbird | 18 | 594.4 (n=18) | 443.1 | 29.9 | 22.5 | 31 | 9277 | 0 |
| 12B | agent-mini | 18 | 606.7 (n=18) | 544.9 | 13.1 | 8.5 | n/a (not recorded) | n/a (not recorded) | 0 |
| 12B | goose | 18 | 1443.8 (n=18) | 788.9 | 14.4 | 12 | n/a (not recorded) | n/a (not recorded) | 0 |
| 12B | opencode | 18 | 967.7 (n=18) | 521.5 | 8.9 | 2 | n/a (not recorded) | n/a (not recorded) | 0 |
| **12B 合计** | 全臂 | 72 | 903.1 (n=72) | 569.3 | 16.6 | 11.5 | 31 | 9277 | 0 |
| 35B | Mingbird | 18 | 514.8 (n=18) | 437.8 | 50.2 | 41 | 42.9 | 20112 | 0 |
| 35B | agent-mini | 18 | 50.0 (n=18) | 26.9 | 5.1 | 4 | n/a (not recorded) | n/a (not recorded) | 0 |
| 35B | goose | 18 | 923.7 (n=18) | 890.5 | 34 | 27.5 | n/a (not recorded) | n/a (not recorded) | 0 |
| 35B | opencode | 18 | 503.2 (n=18) | 491.7 | 12.3 | 10.5 | n/a (not recorded) | n/a (not recorded) | 0 |
| **35B 合计** | 全臂 | 72 | 497.9 (n=72) | 409.3 | 25.4 | 17.5 | 42.9 | 20112 | 0 |

## 3 字段可得性清单(不可得 = 不估算)

| 字段 | Mingbird | agent-mini | goose | opencode | 说明 |
|---|---|---|---|---|---|
| wall_seconds | ✓ 72 | ✓ 72 | ✓ 71 + 1 n/a | ✓ 72 | goose WF08/qwen3.5_4b 源 CSV 缺失 |
| tool_calls | ✓ 72 | ✓ 72 | ✓ 72(1 格 0,因 0 字节 transcript) | ✓ 72 | 各臂口径不同 |
| turns | ✓ 72 | n/a (not recorded) | n/a (not recorded) | n/a (not recorded) | 只有鸣鸟逐轮打印 ctx 行 |
| prompt tokens(峰值/逐轮) | ✓ 72 | n/a (not recorded) | n/a (not recorded) | n/a (not recorded) | 三臂未采 prompt_eval_count |
| 生成侧 token(eval_count) | n/a (not recorded) | n/a (not recorded) | n/a (not recorded) | n/a (not recorded) | 任何 transcript 中 0 出现 |
| 逐格 exit_code / failure_mode | ✓ | ✓ | ✓ | ✓ | 来自各格 `score.json`(见第 5 节) |

要让四臂 token 可比,需在 runner 层捕获 `/api/chat` 的 `prompt_eval_count`/`eval_count`(属新实验,不在本次取证范围)。

## 4 与 `mechanism_log/turns_resource_summary.csv` 的交叉校验

**逐格对照**(比 summary 更强:`turns_resource.csv` 288 格 × {tool_calls, attempt_dir} ∪ 鸣鸟 72 格 × {turns, prompt 峰值} = 720 项):**不一致 0 项**。

**逐臂汇总对照**(cells / tool_calls mean·median / min / max):**共 20 项,不一致 0 项**。

| arm | 字段 | 本表 | turns_resource_summary.csv | 一致 |
|---|---|---|---|---|
| Mingbird | cells | 72 | 72 | ✓ |
| Mingbird | tool_calls_mean | 46.6 | 46.6 | ✓ |
| Mingbird | tool_calls_median | 33.5 | 33.5 | ✓ |
| Mingbird | min | 15 | 15 | ✓ |
| Mingbird | max | 200 | 200 | ✓ |
| agent-mini | cells | 72 | 72 | ✓ |
| agent-mini | tool_calls_mean | 11.5 | 11.5 | ✓ |
| agent-mini | tool_calls_median | 7.0 | 7.0 | ✓ |
| agent-mini | min | 1 | 1 | ✓ |
| agent-mini | max | 41 | 41 | ✓ |
| goose | cells | 72 | 72 | ✓ |
| goose | tool_calls_mean | 28.6 | 28.6 | ✓ |
| goose | tool_calls_median | 15.0 | 15.0 | ✓ |
| goose | min | 0 | 0 | ✓ |
| goose | max | 242 | 242 | ✓ |
| opencode | cells | 72 | 72 | ✓ |
| opencode | tool_calls_mean | 23.0 | 23.0 | ✓ |
| opencode | tool_calls_median | 5.0 | 5.0 | ✓ |
| opencode | min | 0 | 0 | ✓ |
| opencode | max | 230 | 230 | ✓ |

## 5 资源相关诊断(非 timeout 但有预算压力)

**5.1 failure_mode 分布(各格实际解析到的 attempt 的 score.json)**

| arm | completed | early_finish | error | timeout |
|---|---|---|---|---|
| Mingbird | 71 | 0 | 1 | 0 |
| agent-mini | 70 | 2 | 0 | 0 |
| goose | 71 | 0 | 0 | 1 |
| opencode | 69 | 0 | 3 | 0 |

**5.2 历史 attempt 曾超时的格(含被重试覆盖、发布行非超时的情形)**

| arm | task | model | attempts | 超时 attempts | 超时 attempt 目录 | 该 attempt wall (s) | 发布行是否 timeout |
|---|---|---|---|---|---|---|---|
| Mingbird | WF09 | qwen3.5_4b | 2 | 1 | mingbird_WF09_qwen3.5_4b_m0_0913_181117 | 5400.7 | no(重试后被覆盖) |
| goose | WF08 | qwen3.5_4b | 4 | 2 | goose_WF08_qwen3.5_4b_m0_0918_141216, goose_WF08_qwen3.5_4b_m0_0918_164743 | 5520.3, 5520.5 | yes |

**5.3 生成侧截断信号(goose CLI)** — `reached the model's output-token limit`:17 格

| task | model | 次数 |
|---|---|---|
| WF03 | qwen3.5_4b | 1 |
| WF05 | qwen3.5_4b | 1 |
| WF06 | qwen3.5_4b | 1 |
| WF07 | qwen3.5_4b | 1 |
| WF10 | qwen3.5_4b | 1 |
| WF13 | qwen3.5_4b | 1 |
| WF15 | qwen3.5_4b | 1 |
| LH01 | qwen3.5_4b | 1 |
| LH02 | qwen3.5_4b | 1 |
| LH03 | qwen3.5_4b | 1 |
| WF03 | gemma4_12b | 2 |
| WF04 | gemma4_12b | 1 |
| WF09 | gemma4_12b | 1 |
| WF15 | gemma4_12b | 1 |
| WF05 | ornith1.5_35b | 1 |
| WF09 | ornith1.5_35b | 1 |
| LH03 | ornith1.5_35b | 1 |

**5.4 鸣鸟上下文预算事件(两类,勿混为一谈)**

- A 类 = 事前估算超限后压缩 `超限,已压缩(L…`:**4 格 / 5 次**。触发文案里的 token 数是本地启发式`_estimate_messages_tokens` 的**估算值**,不是 Ollama 真值,只能当事件计数用。
- B 类 = 旧工具输出截断 `[上下文压缩 L1: 截断旧工具输出]`:**24 格 / 24 次**(不涉及 token 计数,纯上下文策略事件)。

口径提示:以上只统计 288 个发布格所解析到的 attempt(与 `turns_resource.csv` 同口径)。若把 `<HB>/eval_results/` 下全部历史 attempt 目录(含被重试覆盖者)都算,A 类 4 个目录、B 类 25 个目录(多出的目录是未进入发布矩阵的旧 attempt,勿与发布口径混用)。

| task | model | A 类:压缩(L1/L2/L3) | B 类:L1 旧工具输出截断 |
|---|---|---|---|
| LH03 | gemma4_12b | 0 | 1 |
| LH01 | gemma4_e2b | 0 | 1 |
| LH03 | gemma4_e2b | 0 | 1 |
| WF03 | gemma4_e2b | 1 | 1 |
| WF08 | gemma4_e2b | 0 | 1 |
| WF09 | gemma4_e2b | 1 | 0 |
| WF15 | gemma4_e2b | 2 | 0 |
| LH01 | ornith1.5_35b | 0 | 1 |
| LH03 | ornith1.5_35b | 0 | 1 |
| WF01 | ornith1.5_35b | 0 | 1 |
| WF03 | ornith1.5_35b | 0 | 1 |
| WF05 | ornith1.5_35b | 0 | 1 |
| WF07 | ornith1.5_35b | 1 | 1 |
| WF09 | ornith1.5_35b | 0 | 1 |
| WF12 | ornith1.5_35b | 0 | 1 |
| WF13 | ornith1.5_35b | 0 | 1 |
| WF15 | ornith1.5_35b | 0 | 1 |
| LH01 | qwen3.5_4b | 0 | 1 |
| LH03 | qwen3.5_4b | 0 | 1 |
| WF03 | qwen3.5_4b | 0 | 1 |
| WF05 | qwen3.5_4b | 0 | 1 |
| WF07 | qwen3.5_4b | 0 | 1 |
| WF08 | qwen3.5_4b | 0 | 1 |
| WF11 | qwen3.5_4b | 0 | 1 |
| WF14 | qwen3.5_4b | 0 | 1 |
| WF15 | qwen3.5_4b | 0 | 1 |

**5.5 鸣鸟 prompt 峰值触及 ctx 预算(32768 天花板)** — 1 格

| task | model | prompt 峰值 | 预算 |
|---|---|---|---|
| WF09 | gemma4_e2b | 32767 | 32768 |

## 6 数据坑(复跑时勿踩)

1. goose/opencode 行的 `latest_attempt_dir` 是逻辑名 `rr_think0_<task>`,不是目录名;须按 (harness,task,model) 在 `rr_think0/` 反查实际目录,取时间戳最新且**含 transcript.txt** 者。
2. goose/WF08/qwen3.5_4b 有 4 个 attempt 目录(m0×2 均 90min 超时;m1×2 被外部击杀、无 transcript 无 score.json)→ 解析回退到 m0_0918_164743(0 字节 transcript,tool_calls=0);发布行 wall 为空,本表保留 `n/a`。
3. Mingbird/WF09/qwen3.5_4b 发布行是 failure_mode=error 的重试 attempt(1043.7s);同格更早 attempt(5400.7s)是 90min 超时(见 5.2)。
4. `score.json` 与 matrix 运行日志均无 token 字段(见 mechanism_log/tokens_probe.md)。
5. 鸣鸟的 ctx 行数在 71/72 格等于最大轮号+1;唯一例外 WF09/qwen3.5_4b 是掉线格(退化轮无模型响应,不打印 ctx 行)。

### 解析告警(自动生成)

- CTX/TURN-INDEX GAP Mingbird/qwen3.5_4b/WF09: ctx_lines=95 max_turn=102 (退化轮无模型响应)
- AMBIGUOUS goose/qwen3.5_4b/WF08: 4 dirs -> chose goose_WF08_qwen3.5_4b_m0_0918_164743
