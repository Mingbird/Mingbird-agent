# GAIA-L1 外部锚

GAIA validation L1(53 题)作为 LRAB 之外的外部锚基准。L2/L3 含图片/音频附件,
对四家文本模型结构性 0 分,不纳入。

## 组成

- `validation/` — HF `gaia-benchmark/GAIA` validation 集(gated;下载需 HF token
  通过 license 审批 + 代理)。本地已落 `validation/`,任务渲染在 `tasks/`。
- `gaia_scorer.py` — 官方 scorer 移植(规则判分,与 MUT 同源,确定性)。
- `run_gaia.py` — 单格 runner:prepare workdir(附件复制+question.txt)→
  复用 `run_bench.py` 四家 adapter → 判分 → score.json(含 failure_mode:
  completed / no_answer)。
- `run_gaia_matrix.py` — 424 格两端驱动:4 agent × 2 模型(gemma4:e2b 与
  ornith-1.5:35b 两端锚定,完整 4 模型梯度见 LRAB 288)× 53 题,30min 统一
  预算,model-outer 切片(边界重启 ollama + 35b 加载守卫),DONE.json 断点续跑,
  latest-attempt-wins;`wait_for_search()` 点火门 + 每 10 格 live 复探搜索,
  降级即暂停(2026-09-05 搜索标记事故后的连续守护)。
- `ddg_search_mcp.py` — 本地 stdio MCP 搜索封装(Bing HTML 优先 + DDG html
  回退,urllib 原生认代理 env;`setmkt=en-US`/`kl=us-en` 固定英区;磁盘缓存
  按 egress 模式打标 + 跨进程 4s 节流)。三家(hummingbird / goose / opencode)
  挂此 MCP,agent-mini 用内置 web_search(DDG 端点,当前出口 IP 被 anomaly
  标记,实际无搜索)——不对称在 METHODS 披露。

## 公平协议

与 LRAB 同规范(见 `bench/lrab/METHODS.md`):统一预算、timeout 计 0、
latest-attempt-wins、工具名中立、确定性判分、同一搜索上游。运行需
`GAIA_PROXY=http://127.0.0.1:7897`(或等效代理)且全程在线。

## 已知缺口(基线如实保留,不修)

- 蜂鸟 `read_file` 不解析 xlsx(GAIA 考二进制附件,LRAB 未考过)。
- argless 裸 `finish` 无纠正反馈(占位符形态已由 b929e7c 覆盖)。
