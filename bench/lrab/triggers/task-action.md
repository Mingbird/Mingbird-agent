你被本探测器唤醒,说明 LRAB 64 格批次(WF-01/03/09/15 × 4 agent × 4 model,2026-08-29 起跑)出现了「完成」或「停滞/无产出」。请立即处理:

1. 先跑真实探针确认现状(不要用 fixture):
   `python C:\Users\99491\dev\hummingbird\bench\lrab\runners\batch_status.py`

2. **verdict=complete(批次完成)**:
   - 运行汇总器(自动处理 m0/m1 重跑归属,输出写 eval_results/BATCH64_SUMMARY.md):
     `python C:\Users\99491\dev\hummingbird\bench\lrab\analyze_batch64.py`
   - 用【批次完成】开头向用户报告:总表 + 蜂鸟 vs 三竞品的各模型均值 + 异常格一句话点评。
   - 报告后执行 `myagents task exit --reason "batch complete reported"` 结束本任务。

3. **verdict=stalled 或 idle(批次异常)**:
   - 用【批次告警】开头向用户报告:已完成格数、最后活动时间、newest_artifact 路径。
   - 读最新 run 目录的 `transcript.txt` 末尾约 50 行与 `score.json`(如有)定位原因(常见:B390+Vulkan 长推理崩溃、ollama 500 连发、驱动卡死)。
   - **绝对不要自行重启批次**(run_matrix 无断点续跑保证,重复启动=重复格污染数据)。重启决策留给主会话/用户。本任务保持运行继续监视。

4. 报告保持简短(结论先行,不超过 15 行);不要执行改进本身。

注意:蜂鸟块可能出现的 timeout 格是 run_matrix 自动重跑策略的一部分(四家 agent 同策略,公平);若某格 attempt 1 timeout 但已出现重跑目录,属正常,不算告警。
