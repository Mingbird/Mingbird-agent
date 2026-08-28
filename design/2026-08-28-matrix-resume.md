# 正式矩阵重启恢复清单（2026-08-28 22:15 电脑休眠后）

> 用途：休眠/重启后恢复 LRAB 正式矩阵的现场。所有代码已提交 git + 同步远程，
> 数据在 eval_results/（本地，不入 git）。重启后按本清单续跑。

## 一、已完成（休眠前落盘）

| run | 结果 | 说明 |
|---|---|---|
| hummingbird 35b | **1.0** (1437s) | 正式矩阵唯一完整格，run-id `hummingbird_WF06_ornith1.5_35b_m0_0828_184926` |
| hummingbird 12b 第1次 | **timeout** (1500s) | 产物几乎齐全(analysis.py+2图+anomalies.md)，只差 analysis.md 收尾，25min 不够 |
| hummingbird 12b 第2次 | **timeout** (1500s) | 只有 todo.json，从头没推进（休眠时 ollama 状态可能坏了） |

**关键发现（更正）**：12b 在 32K 下**工作正常**（analysis.py 可编译、图正常产出），
不是 32K 压垮它。m0 的 25 分钟超时是因为**时间预算不够**（19:33 还在产图，只差 analysis.md
收尾）；m1 只写 todo.json 没推进更像**休眠后 ollama 状态坏**。需要重测验证。

## 二、休眠中断的矩阵进度

正式矩阵（WF-06 × 4agent × 4model = 16 格）只跑完 1 格（蜂鸟 35b），
第 2 格（蜂鸟 12b）超时 2 次后进入第 3 格（蜂鸟 4b，20:03 启动）时休眠中断。
**剩余 15 格未跑**。

## 三、重启后恢复步骤

1. **确认 ollama 正常**（休眠可能让 ollama 状态损坏）：
   ```bash
   curl http://127.0.0.1:11434/api/tags
   ```
   若异常，重启 ollama 服务（OLLAMA_VULKAN=1 + OLLAMA_IGPU_ENABLE=1）。

2. **清理残留进程**（休眠可能留下僵尸 python/goose/node）：
   ```bash
   tasklist | grep -iE "python|goose|node"
   ```

3. **重启正式矩阵**（续跑，run_matrix.py 已支持 --start 跳过已完成格）：
   ```bash
   cd ~/dev/hummingbird/bench/lrab
   python runners/run_matrix.py --agents hummingbird,opencode,agent-mini,goose \
     --models ornith-1.5:35b,gemma4:12b,qwen3.5:4b,gemma4:e2b \
     --tasks WF-06 --timeout-min 25 --results ~/dev/hummingbird/eval_results
   ```
   ⚠️ run_matrix 会重新跑全部 16 格（含已完成的 35b）。若要跳过已完成格，
   把 35b 那个结果保留，或改 tasks 子集。

4. **12b 重测验证**（优先）：
   - a) 单独重跑 12b 格（重启后环境干净），timeout 提到 35-40 分钟：
     `python runners/run_bench.py --agent hummingbird --task tasks/tier2_synthesis/WF-06.json --model gemma4:12b --timeout-min 40 --results ~/dev/hummingbird/eval_results --run-id hb_12b_verify`
   - b) 若正常完成（预期，m0 已证明 12b 在 32K 能干活）→ 确认 32K 没问题，之前是休眠干扰+预算不够

## 四、数据与代码位置

- **代码**：`~/dev/hummingbird/bench/lrab/`（已 git 提交 + 远程同步）
- **矩阵数据**：`~/dev/hummingbird/eval_results/`（MATRIX_MANIFEST.json 每格记录）
- **归档规范**：`bench/lrab/MANIFEST.json`（canonical/pre-fix 分类）
- **结果文档**：`bench/lrab/RESULTS.md`（论文数据源）
- **图表**：`eval_results/degradation_*.png`

## 五、记住的教训（重启后自省会复核）

1. 12b 在 32K 下超时 → 需验证 32K 对小模型的实际代价
2. 休眠中断矩阵 → 长时任务跑前确认电源/休眠设置
3. 正式矩阵没跑完，论文数据仍缺（只有蜂鸟 35b 一格是干净的）
