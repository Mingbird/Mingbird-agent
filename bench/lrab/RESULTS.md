# LRAB 矩阵结果（论文数据源）

> 数据日期: 2026-08-28。所有 run 在 `~/dev/hummingbird/eval_results/`，MANIFEST 在 `bench/lrab/MANIFEST.json`。
> 公平性协议: DuckDuckGo 搜索同源，temp=0（goose 无温度旋钮按默认）。
> **num_ctx 披露（自省 P0-1 修正）**: 蜂鸟=32768（AGENT_CTX），opencode=32768（config 钉死），agent-mini=32768（provider patch）。
> goose 无 ctx 配置项，走 ollama 默认（预计 4K）——唯一 ctx 差异源，单独披露。
> **注意**: 第一批 8 格用了旧任务提示（含 todo() 工具名），opencode-e2b 因此得假 0 分；
> 已修提示 + 修 opencode `--format json` 吞 prompt bug，opencode-e2b 重跑为 0.429。

## 本轮矩阵（2026-08-28）

### WF-06（统计分析与可视化）— 第一批 4×2 + 蜂鸟 4 模型

| Agent | ornith 35b | gemma4 12b | qwen3.5 4b | e2b | 降级幅度 |
|---|---|---|---|---|---|
| hummingbird | 1.0 | 0.857 | 1.0 | 0.714 | 0.286 |
| opencode | 1.0 | — | — | 0.429* | 0.571 |
| agent-mini | 1.0 | — | — | 0.857 | 0.143 |
| goose | 1.0 | — | — | 0.714 | 0.286 |

\* opencode-e2b 用修复后 adapter 重跑（提示中立 + 去 --format json）。

### 关键结论（论文叙事）

1. **蜂鸟 harness 让 4B 模型达到 35B 水平**（4b=1.0 == 35b）——扁平 prefill + 类别路由兜底强。
2. **降级平缓度**（35B→e2b）: agent-mini 0.143 < 蜂鸟 0.286 = goose 0.286 < opencode 0.571。
3. **e2b 上蜂鸟 0.714 且 136s** < opencode 0.429 且 272s（更快且更高分）。

## 下一步

- [ ] 竞品补齐 12b/4b 梯度（进行中）
- [ ] 扩展到多任务（WF-01..15 抽样）
- [ ] 全矩阵 4×4×15 = 60 格
- [ ] GAIA-L1（等 HF license）
