# Contributing / 贡献指南

Issues are welcome — bug reports with a transcript, benchmark questions,
feature ideas. / 欢迎 issue：带转录的 bug 报告、基准问题、功能想法。

For larger changes, please open an issue first so we can talk about the
design before you write code. Mingbird's core constraint is the **prefill
zero-growth rule** (the factory prefill estimates at 1250 tokens under the
v2.1.4 CJK-accurate estimator, and CI fails any change
that grows it by a single byte) — anything that adds static text to the
model's context needs to pay for itself elsewhere. / 大改动请先开 issue 讨论
设计。鸣鸟的核心约束是 **prefill 零增长规则**（出厂 prefill 按 v2.1.4 的中文精确
估算器计量为 1250 token，任何净增一个字节都会让 CI 挂掉）——任何给模型上下文
加静态文本的改动必须在别处把成本省回来。

- Run the tests before submitting: `python -m pytest tests/ -q`
  (600 tests — 435 unit + 26 integration + 139 added since v1.9.1 across issue fixes (#1/#4/#6), multi-engine
  backends, workspace & session systems, the installer skills-path cases, and the v3.0.0 platform-aware
  suite; includes the prefill byte-level
  assertion; the benchmark runners under `bench/` and `benchmarks/` are
  separate programs and are not collected by pytest). /
  提交前请跑测试：`python -m pytest tests/ -q`（600 项——435 项单测 + 26 项集成 + v1.9.1 起新增 139 项，
  覆盖 issue 修复（#1/#4/#6）、多引擎后端、工作区与会话系统、安装版技能路径、v3.0.0 平台感知套件等，
  含 prefill 逐字节断言；`bench/` 与 `benchmarks/` 下的基准运行器是独立程序，
  不归 pytest 收集）。
- Benchmark-related changes should keep the published protocol intact
  (temperature 0, thinking off). / 基准相关改动请保持已发布协议不变（0 温、关思考）。
- Apache-2.0. / 许可证 Apache-2.0。
