# Contributing / 贡献指南

Issues are welcome — bug reports with a transcript, benchmark questions,
feature ideas. / 欢迎 issue：带转录的 bug 报告、基准问题、功能想法。

For larger changes, please open an issue first so we can talk about the
design before you write code. Mingbird's core constraint is the **prefill
zero-growth rule** (the factory prefill is 797 tokens and CI fails any change
that grows it by a single byte) — anything that adds static text to the
model's context needs to pay for itself elsewhere. / 大改动请先开 issue 讨论
设计。鸣鸟的核心约束是 **prefill 零增长规则**（出厂 prefill 797 token，任何净增
一个字节都会让 CI 挂掉）——任何给模型上下文加静态文本的改动必须在别处把成本省回来。

- Run the tests before submitting: `python -m pytest tests/ -q`
  (451 tests, includes the prefill byte-level assertion). /
  提交前请跑测试：`python -m pytest tests/ -q`（451 项，含 prefill 逐字节断言）。
- Benchmark-related changes should keep the published protocol intact
  (temperature 0, thinking off). / 基准相关改动请保持已发布协议不变（0 温、关思考）。
- Apache-2.0. / 许可证 Apache-2.0。
