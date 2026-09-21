# tokens_probe — transcript 中是否存在 token 计数

取证日期:2026-09-21(纯读,零新实验)
范围:主矩阵 288 格 transcript + 消融四臂 72 格 transcript + score.json 抽样 40 份 + matrix 运行日志抽样。

## 结论一句话

**鸣鸟系 transcript(Mingbird 主臂 72 格 + 消融四臂 72 格)自带真实的 prompt 侧 token 计数**,以 `[ctx: N/32768 = P%]` 行的形式逐轮打印,N 直接取自 Ollama 响应的 `prompt_eval_count`(代码证据:`mingbird-v150/ollama_agent.py` L2789-2792:`pt = r.get("prompt_eval_count") or (r.get("usage") or {}).get("prompt_tokens", 0)` 后打印)。**eval_count(生成侧)在任何 transcript 中均无出现**(见下),生成侧 token 确实需从 Ollama 响应侧另采。

## 各臂覆盖率(全量扫描,非抽样)

| 臂 | 文件数 | 含 `[ctx:` 行 | 含字面 eval_count / eval=N | 含 "token" 字样 |
|---|---|---|---|---|
| Mingbird(主臂) | 72 | **72(100%)** | 0 | 6(见下,非计数) |
| ablation 四臂 | 72 | **72(100%)** | 0 | 3(非计数) |
| agent-mini | 72 | 0 | 0 | 1(模型散文里的 "tokenized") |
| goose | 72 | 0 | 0 | 28(见下,均无数值) |
| opencode | 72 | 0 | 0 | 9(PowerShell `tokens=`、错误信息) |

score.json:40/40 抽样键集固定为 `task_id/domain/milestone_score/final_score/milestone_details/final_details/total/agent/model/wall_seconds/exit_code/run_id/failure_mode`,无任何 token 字段。matrix 运行日志(rr_think0/logs、ablation/*/logs 抽样)同样 0 命中。

## 提取样例

鸣鸟 `mingbird_LH01_gemma4_12b_m0_0914_014928/transcript.txt`(41 轮,41 行 ctx):

```
[ctx: 1811/32768 = 5%]     ← 首轮 prompt tokens
...
[ctx: 14564/32768 = 44%]   ← 本格峰值(prompt_eval_count)
```

主臂 72 格统计(已写入 `turns_resource.csv` 的 `ctx_lines`/`ctx_peak_tokens` 列):
- ctx 行数中位 ≈ tool_calls(逐轮打印,含无工具调用的轮);
- **ctx_peak(prompt 峰值 tokens)中位 14,624,最大 32,767**——有一格顶到 32,768 预算天花板,即发生过上下文压缩临界;
- 所有格 ctx 预算均为 32,768(`AGENT_CTX` 环境变量设定;代码默认 131,072)。

另有一类**估算值**(非 Ollama 真值):`[N] 事前估算 24879 token 超限,已压缩(L2)` ——来自本地启发式 `_estimate_messages_tokens`(ollama_agent.py L1577/L1590),主臂 4 个文件共 5 次压缩事件,可作"压缩事件计数"使用,不可当 token 真值。

## "token" 字样的定性(排除项)

- goose 28 个命中:PowerShell 批处理 `for /f "tokens=*"`,解析器错误 `Unexpected token`,以及 goose CLI 自身的无数值警告 `Warning: Response reached the model's output-token limit and may be incomplete.`(该警告本身是"输出被 token 上限截断"的事件信号,但无数字);
- Mingbird/agent-mini 命中:模型产出散文中的 "hash/tokenize"、todo 文案 "tokenized";
- opencode 命中:命令输出回显。均非 token 计数。

## 生成侧(eval_count)结论

代码中唯一的 eval_count 打印出口是空响应取证插桩:`[{i}] ⚠️ done_reason=length 且无正文无调用(eval={r.get('eval_count')})`(L2809)。本轮 360 份 transcript 中该行 0 次触发,因此**不存在任何生成侧 token 数据**。若要四臂可比的 token 资源表,需在 runner 层捕获 `/api/chat` 响应的 `prompt_eval_count`/`eval_count`(属新实验,不在本次取证范围);当前存量数据里,只有鸣鸟系(主臂+消融)的 prompt 侧可复原。
