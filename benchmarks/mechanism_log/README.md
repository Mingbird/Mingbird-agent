# P1 取证输出(纯读,零新实验)

生成:2026-09-21。脚本:`extract_p1.py`(同目录,可复现;`--sample` 为 3+1 目录小样本自检模式)。
数据源(只读):`mingbird-v16/benchmarks/lrab_scores.csv`(288 格)、`<HB>/eval_results/`(Mingbird、agent-mini 臂)、`mingbird-v150/eval_results/rr_think0/`(goose、opencode 统一协议臂)、`mingbird-v150/eval_results/ablation/{finish_gate,verify_feedback,anti_loop,flat_prefill}/`(消融四臂,每臂 18 格、仅 gemma4_e2b)。
**未触碰**:`ablation/baseline_samebatch`、`ablation/finish_gate_text_only`(另一进程在跑)。未修改任何源文件,未 commit。编码:全部 utf-8(无 BOM)。

## 交付物与行数

| 文件 | 行数(含表头) | 说明 |
|---|---|---|
| `mechanism_activation.csv` | 3024+1 | 144 格(鸣鸟 72 + 消融 4×18)× 21 类 marker,含 0 触发行(0 也是发现) |
| `mechanism_activation_summary.csv` | 168+1 | arm×model×marker 总触发数(8 个 arm-model 组合 × 21) |
| `turns_resource.csv` | 288+1 | 主矩阵全部 288 格;附 attempt_dir/method/note/ctx_lines/ctx_peak_tokens 辅助列 |
| `turns_resource_summary.csv` | 4+1 | 每臂 tool_calls 均值/中位/min/max |
| `tokens_probe.md` | — | token 计数调查(见该文件) |
| `tokens_probe_data.json` | — | probe 原始统计与 quirk 清单 |

## 关键汇总数字

### 机制触发(鸣鸟主臂 72 格,marker 家族合计)

| family | 总触发 | 主要构成 |
|---|---|---|
| finish_gate | **155** | 交付自查:回注任务原文 65、计划未同步 43、产物核对 23、计划核对 11、测试未通过 13、拒绝假 finish **0** |
| plan_nudge | 99 | 计划停滞提醒 |
| anti_loop | 95 | 重复调用拦截 63、检测到重复输出 13、强制收尾(防死循环) 6、禁用工具硬复位 10、连续空轮硬复位 3 |
| edit_guard | 9 | 霰弹枪编辑提示 |
| format_rescue | 4 | 抢救到文本工具调用 1、别名映射 3 |
| budget_nudge | 0 | 预算提示(90min 预算内未触发) |

消融臂(各 18 格,gemma4_e2b;finish_gate 家族合计):finish_gate 臂 32、verify_feedback 臂 55、anti_loop 臂 56、flat_prefill 臂 69。**finish_gate 臂中 测试未通过/产物核对/计划核对/拒绝假finish 四项精确归零**(消融生效);残留的计划未同步 15 与交付自查 17 属代码设计,见"数据坑 #6"。

### tool_calls(288 格,每臂 72 格)

| 臂 | 均值 | 中位 | min–max | 计数口径 |
|---|---|---|---|---|
| Mingbird | **46.6** | 33.5 | 15–200 | `[\d\|+\d+s] ⚙` 行 |
| goose | 28.6 | 15.0 | 0–242 | `▸` 工具行(含 50 次 `[subagent:N]` 派发行) |
| opencode | 23.0 | 5.0 | 0–230 | ANSI 剥离后 `$ 命令` 行 + `→ 动作` 行 |
| agent-mini | 11.5 | 7.0 | 1–41 | `⚡ 工具` 行 |

注意:四臂 transcript 格式不同,口径是"各臂自己的工具行为行",跨臂只宜比量级;goose/opencode 的长尾(max 242/230 vs 中位 15/5)来自个别失控格。鸣鸟的 ⚙ 行含 todo/finish 等内置工具。

### token(详见 tokens_probe.md)

鸣鸟系 144/144 格 transcript 含 `[ctx: N/32768 = P%]` 行,N 为 Ollama 真值 `prompt_eval_count`;主臂 ctx_peak 中位 14,624、最大 32,767(顶到预算)。eval_count(生成侧)全量 0 覆盖。

## marker 定义(21 类)

文案双重确认:transcript 实际词汇表(全量经验扫描)+ `mingbird-v150/ollama_agent.py` 打印语句行号。前 6 类为任务指定;anti_loop/format_rescue 系按任务要求从代码 grep 确认的打印文案;plan_nudge/edit_guard/budget_nudge 为经验扫描中实际出现、值得留痕的补充机制(家族列已区分,不需要可过滤)。

| marker | 中文文案(计数子串) | family | 代码行 |
|---|---|---|---|
| fake_finish_reject | 拒绝假 finish | finish_gate | L2917 |
| tests_failed_reject | 测试未通过 | finish_gate | L2950 |
| artifact_missing_reject | 产物核对:summary 声称但缺失 | finish_gate | L2965 |
| plan_missing_reject | 计划核对:计划点名但缺失 | finish_gate | L2981 |
| plan_unsynced_reject | 计划未同步 | finish_gate | L3001 |
| selfcheck_reinject | 交付自查:回注任务原文 | finish_gate | L3023 |
| dup_call_intercept | 重复调用拦截 | anti_loop | L2874 |
| disabled_tool_hard_reset | 被禁用后仍被调用 | anti_loop | L2861 |
| empty_turns_hard_reset | 连续空轮× | anti_loop | L3201 |
| empty_graceful_exit | 个空轮且 3 次复位无效 | anti_loop | L3205 |
| repeat_output_detected | 检测到重复输出 | anti_loop | L3222 |
| qa_guard_intercept | 问答守护:拦截 | anti_loop | L2887 |
| force_finish_loop_guard | 本轮已足够,强制结束 | anti_loop | L2672 |
| break_500_loop_inject | 500 错误,已注入继续提示 | anti_loop | L2778 |
| len_trunc_signature | done_reason=length 且无正文无调用 | anti_loop | L2809 |
| salvage_text_toolcall | 抢救到文本工具调用 | format_rescue | L2816 |
| alias_mapping | 别名映射: | format_rescue | L2842 |
| repair_conversation | 修复对话结构 | format_rescue | L2723 |
| plan_stall_nudge | 计划停滞提醒 | plan_nudge | L3169 |
| shotgun_edit_warn | 霰弹枪编辑提示 | edit_guard | L3145 |
| budget_nudge_inject | 预算提示已注入 | budget_nudge | L3154 |

零触发的 marker(全 144 格):empty_graceful_exit、qa_guard_intercept、break_500_loop_inject、len_trunc_signature、repair_conversation、budget_nudge_inject,以及主臂的 fake_finish_reject(消融 verify_feedback/flat_prefill 臂各 2 次)。

## 数据坑(10 条)

1. **CSV 的 rr 臂目录名是逻辑名**:goose/opencode 行的 `latest_attempt_dir` 形如 `rr_think0_WF01`(不含 harness/model),实际目录在 `rr_think0/<harness>_<task>_<model>_<m0|m1>_<MMDD_HHMMSS>`。本表按 (harness,task,model) 映射,取时间戳最新。
2. **goose WF08 qwen3.5_4b 有 4 个尝试目录**(m0×2、m1×2;EXCLUSIONS.md:m0 两次 90min 超时、m1 两次被外部击杀,用户裁定记 0 分)。最新目录 m1_0918_181950 无 transcript,回退选 m0_0918_164743,其 transcript 为 0 字节 → tool_calls=0 已在 note 注明,该格资源数据不可用。
3. **<HB>/eval_results 有 73 个 `mingbird_*` 目录,CSV 只引用 72**:`mingbird_WF09_qwen3.5_4b_m0_0913_181117` 未被引用(旧尝试),未计入任何表。同理该目录下还有大量 agentmini 旧尝试,均以 CSV 引用为准。
4. **消融臂目录前缀是 `<legacy_prefix>_*` 而非 `mingbird_*`**,且仅 gemma4_e2b 一个模型;解析时勿按前缀区分臂。
5. 「拒绝假 finish」主臂 72 格 0 触发:机制存在(代码 L2917)但从未开火——本身是有效发现,勿当作解析失败。
6. **消融臂的机制残留是代码设计,不是数据错误**:finish_gate 消融(`_FG_OFF`)只关 假finish(L2915)/测试门(L2932)/产物核对(L2961)/计划核对(L2977)四道门;计划未同步门(L2997)只受 `finish_gate_text_only` 控制,交付自查(L3017)无开关(每任务至多回注一次,`finish_reread_used` 单次闸,故各臂稳定 14-17 次/18 格)。anti_loop 消融只关 8 连击强禁用(L3088),重复调用拦截/重复输出检测照常工作。verify_feedback 消融只把 pytest 反馈降级为通用文案(L2943),测试门本身照常触发。
7. **主臂跑批(0913-0914)的代码与当前 v150 ollama_agent.py 可能存在版本差**:marker 文案以 transcript 实际词汇表为准(全部命中),但行号引用对应 v150 现行文件。
8. **opencode transcript 混有 ANSI 转义码与 stdout 回显**,工具行为需 ANSI 剥离后按 `$ 命令` + `→ 动作` 双口径计;个别格(如 opencode LH01 gemma4_12b)transcript 仅 12 行、模型直接放弃,低计数是真实行为。
9. score.json 无 token 字段;matrix 日志无 token 字段(见 tokens_probe.md)。
10. agent-mini transcript 的 `⚡` 是工具行前缀(与鸣鸟的格式拯救 `⚡` 无关);机制 marker 统计只覆盖鸣鸟臂与消融臂,不受影响。
