# Contributing / 贡献指南

Issues are welcome — bug reports with a transcript, benchmark questions,
feature ideas. / 欢迎 issue：带转录的 bug 报告、基准问题、功能想法。

For larger changes, please open an issue first so we can talk about the
design before you write code. Mingbird's core constraint is the **prefill
zero-growth rule** (the factory prefill estimates at 1250 tokens under the
v2.1.4 CJK-accurate estimator, and CI fails on any change
to it — growth or shrinkage) — anything that adds static text to the
model's context needs to pay for itself elsewhere. / 大改动请先开 issue 讨论
设计。鸣鸟的核心约束是 **prefill 零增长规则**（出厂 prefill 按 v2.1.4 的中文精确
估算器计量为 1250 token，任何改动——无论增减——都会让 CI 挂掉）——任何给模型上下文
加静态文本的改动必须在别处把成本省回来。

- Run the tests before submitting: `python -m pytest tests/ -q`
  (717 tests — 435 unit + 26 integration + 256 added since v1.9.1 across issue fixes (#1/#4/#6), multi-engine
  backends, workspace & session systems, the installer skills-path cases, the v3.0.0 platform-aware
  suite, the v3.1.1 audit fixes (parallel config passthrough,
  unattended global deny, crawl-guard byte accounting), the v3.1.3
  compaction-runner fix, the v3.1.4 conversation-hygiene suite
  (transcript cursor, gate exemptions, self-check original text), the v3.1.6
  ecosystem batch (compaction window guard, MCP resident broker,
  tool-argument normalization, AGENTS.md/SKILL.md compat), the v3.1.7
  tool-availability suite (per-turn offered-view gate, offline egress guards at
  the tool bodies incl. remote MCP), the v3.1.8 artifact-quality suite
  (disabled-compute-tool wording fork, unattended denial alternatives, finish
  content gate, task-following deliverable language), and the v3.1.9 robustness suites (anti-loop escape: refusal without
  unlock advice, real unlock revival with a 2-per-task cap, unattended
  write-route hint, scripted end-to-end replay; read-loop guard:
  signature-window bans that keep new ranges readable, crawl-guard hard
  stop, past-the-end signals; todo state hardening: shape normalization,
  harness-state write block, escape routes ordered inside the 120-char
  truncation window);
  includes the prefill
  no-change assertion; the benchmark runners under `bench/` and `benchmarks/` are
  separate programs and are not collected by pytest). /
  提交前请跑测试：`python -m pytest tests/ -q`（717 项——435 项单测 + 26 项集成 + v1.9.1 起新增 256 项，
  覆盖 issue 修复（#1/#4/#6）、多引擎后端、工作区与会话系统、安装版技能路径、v3.0.0 平台感知套件、
  v3.1.1 审计修复（并行配置直通、无人值守全局拒、爬行守卫字节口径）、v3.1.3 压缩 runner 修复、
  v3.1.4 会话卫生套件（转录游标/门禁豁免/自查原文）、v3.1.6 生态兼容批
  （压缩窗口护栏/MCP 常驻 broker/工具参数归一化/AGENTS.md·SKILL.md 兼容）、
  v3.1.7 工具可得性套件（本轮下发视图校验/联网工具本体断网闸/远程 MCP 断网禁探）、
  v3.1.8 产物质量套件（计算型禁用话术分叉/无人值守拒绝给替代做法/finish 内容门禁/交付物语言跟任务）、
  v3.1.9 加固套件（反循环出路=拒绝话术去解锁推荐/解锁真恢复并封顶 2 次/无人值守写方向提示/stub 整链回放；读循环守卫=签名窗封禁且新区间放行/限速梯子到硬拦/越界明确信号；todo 状态加固=形状归一化+harness 状态文件写保护/出路落在 120 字符截断窗内）等，
  含 prefill 不变式断言；`bench/` 与 `benchmarks/` 下的基准运行器是独立程序，
  不归 pytest 收集）。
- Benchmark-related changes should keep the published protocol intact
  (temperature 0, thinking off). / 基准相关改动请保持已发布协议不变（0 温、关思考）。
- Apache-2.0. / 许可证 Apache-2.0。
