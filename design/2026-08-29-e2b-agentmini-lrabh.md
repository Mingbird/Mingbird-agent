# e2b 落后 agent-mini 根因分析 + LRAB 长视野盲区 + 改进方案

> 2026-08-29。触发:WF-06 正式矩阵中蜂鸟 e2b(0.43) < agent-mini e2b(0.64),
> 且用户指出 agent-mini 实际毫无长任务能力(无 todolist),当前基准没测出来。
> 证据:WF-06 两次 e2b 运行 transcript + 蜂鸟源码。64 格批次跑完后实施本方案。

## 一、e2b 为什么输:轨迹解剖(WF-06)

### 蜂鸟 e2b(0.429, 364s, 19 回合)

| 回合 | 事件 | 性质 |
|---|---|---|
| 0 | todo create | 协议开销 |
| 2,3 | 把 Python 代码直接塞给 run_bash → `'import' is not recognized` ×2 | **浪费**(解释器混淆) |
| 5 | `python analysis.py` exit 1 | 修复成本 |
| 7,9 | 重写 analysis.py ×2(第 2 次冗余) | 浪费 |
| 11,16,17 | 重复调用拦截 list_dir ×3 | 浪费(拦截生效但已烧回合) |
| 13 | edit_file old_text 找不到 | 失败 |
| 18 | **finish 谎报**:"descriptive_stats.md 已写入、anomalies.md 已加、图已生成"——实际全都没创建 | **致命** |
| 结果 | analysis.py ✓ + analysis.md ✓;anomalies.md/两图/descriptive_stats.md 缺 | 0.429 |

### agent-mini e2b(0.643, 124s, 10 回合)

5 write + 2 read + 2 shell + 1 list,全线性无浪费,只漏了 anomalies.md 一个文件。

### 根因(按权重排序)

1. **协议过载压垮 2B 模型**:蜂鸟暴露 todo/run_bash/edit_file/重复拦截等丰富协议,
   2B 模型在"哪个工具、什么参数格式"上反复跌倒(19 回合浪费 8 个=42%);
   agent-mini 只有 list/read/write/shell 四件套,无脑线性刚好适配 2B。
2. **finish 是裸门禁**:模型谎报产物,harness 直接收货结束(`ollama_agent.py:1102`
   只回显 summary)。模型自己"以为"做完了——没人核对。
3. agent-mini 的循环"模型停止调工具就退出",没有 finish 汇报环节,反而无从谎起。

## 二、用户判断验证:LRAB 当前测不出长任务能力

**结论:成立。** 证据链:

1. agent-mini e2b **124 秒、10 次工具调用**就拿 0.643——这不是长任务,是长一点的脚本活。
2. agent-mini **没有 todo/持久化机制照样高分**→ 说明任务不 REQUIRE 这些机制。
3. 蜂鸟的长任务机械(checkpoint `.agent_state.json`/resume/上下文压缩/verify-before-retry)
   在 WF-06 全程没被触发(32K 上下文只用到 27%,无中断,无恢复)。
4. 全部 15 域任务都是"单次坐下 5-30 分钟"规模,steps 8-12 步,产物 5-7 个,
   依赖深度 ≤2——测的是"多步执行",不是"长视野"。

**架构差异(蜂鸟的真正卖点)目前完全不可见**:checkpoint 恢复、长会话上下文管理、
数百回合后的稳定性——这些恰是用户实测 agent-mini 崩掉的场景。

## 三、改进方案

### A. 蜂鸟 harness(预计 e2b 0.43→0.7+,对大模型无害)

1. **Finish 产物核对门禁**(P0):finish 时解析 summary 声称的产物,逐一对照 workdir;
   缺失则拒绝 finish 并注入一轮:"claimed artifacts missing: [...], continue"。
   谎报是本次 0 分的直接原因,这一条收益最大。~30 行,加在 `ollama_agent.py` finish 分支。
2. **小模型协议自动降级**(P1):model 参数量 ≤4B 时——
   - edit_file 移出工具列表(只用 create_file 重写,消灭 old_text 匹配失败);
   - run_bash 报错信息教学化:检测到 `'import' is not recognized` 时附加
     "run_bash 执行 shell 命令。运行 Python 用: python script.py";
   - todo 保留(成本 1 回合,价值在长任务)。
3. **重复调用拦截前置**(P2):拦截发生时立即在下一轮提示"上次调用被判定重复,
   换方法或继续下一步",减少连烧 3 回合。

### B. LRAB-H:真正测长视野的 tier4(测出 agent-mini 的真实短板)

三个新任务(tasks/tier4_longhorizon/,fixture 由脚本确定性生成,ground truth 内嵌判分):

| 任务 | 长视野压力 | 测什么 |
|---|---|---|
| LH-01 数据切片依赖链 | 30+ 步:8 切片统计→交叉验证→两轮修订报告,后步吃前步产物 | 深依赖链的规划与执行 |
| LH-02 上下文压力流式 | fixture ~400KB 文本(超任何上下文),必须写脚本处理而非通读 | 分治/流式策略,禁止 read-all |
| LH-03 十模块修复流水线 | 10 模块×(诊断→修→跑→日志)≈40 回合,`resume_test: true` | **中断恢复**:runner 在 50% 预算 SIGKILL 后重启续跑,终态+恢复效率计分 |

**LH-03 是蜂鸟与 agent-mini 的照妖镜**:蜂鸟有 checkpoint 会自动续;
agent-mini 重启即失忆(用户实测:完全没长任务能力),预计断崖。
这是论文"Harness, not model size, determines long-horizon capability"的核心实验。

**Runner 支持规格**(批次跑完后实现,勿在批次中改 runner):
`run_bench.py --kill-at-pct 50`:到达 50% 预算 kill 进程树 → 记录现场快照 →
原 workdir 重启(蜂鸟自然 resume;竞品同样拿到"continue"提示)→ score.json 记
`resumed: true, pre_kill_artifacts: N`。判分 = 终态产物分(权重不变),另记恢复成本。

### C. 论文叙事修正

当前 80 格数据降级为"short-horizon 多步执行对比"(蜂鸟 0.79 第一);
LRAB-H 作为第二实验:"long-horizon 对比"——预期叙事:短任务大家都能干,
长任务只有带持久化机械的 harness 活下来。两章合起来才是完整主张。

## 四、实施顺序(64 格批次完成后)

1. 蜂鸟 finish 门禁 + 小模型降级(先改,直接提分)
2. LH fixture 生成器 + 3 任务 JSON(可先行,CPU 工作)
3. run_bench kill-resume 支持 + LH-03 冒烟
4. LH 16 格矩阵 → 与 short-horizon 数据分开呈现
