## 🇨🇳 中文

# 鸣鸟 v3.1.4

会话卫生版——源自一次真实 6 分钟会话的事后解剖，全部按"类"修不按"例"修。桌面 UI 不变。**642 项测试全绿**（631 + 11 新增）。

- **追问消息不再从转录消失**：续跑游标此前取 len(messages)，每次 --append 的新用户消息被静默吞掉（事故会话上下文 33 条 vs 转录 30 条）。游标现在数转录文件实际行数；压缩后续跑的完整历史也被保住。
- **交付自查对照正确的题面**：回注"本次交付所响应的指令"（最近一条真实用户输入），不再把会话第一句当题面；⏱/提示等全部注入消息补进前缀表，不会被误当原文。
- **假完成门两则豁免**：问答会话豁免；实质性 summary 算交付（讲解型 finish 不再被逼去建文件）。基准注记：主臂数据在旧门禁语义下产生。
- **拒绝不再携带成功语义**：六道 finish 门拒绝时一律回填中性结果（旧版回填含 [TASK_COMPLETE] 的结果，给模型矛盾信号、中途标 done）。
- **测试门豁免问答**：工作目录恰好有 test_*.py 时，聊天收尾不再先跑测试套件。
- **工具话术如实**：不在装配列表的工具（幻觉名/未装配）得到"不可用"话术，不再误标"连续重复调用保护"。
- **MAX ITERATIONS 只在真耗尽时打印**。

---

## 🇬🇧 English

# Mingbird v3.1.4

Conversation-hygiene release from a real 6-minute session post-mortem; every fix is class-level, not scenario-level. Desktop UI unchanged. **642 tests green** (631 + 11 new).

- **Follow-up messages no longer vanish from the transcript**: the resume cursor now counts the transcript file's actual lines instead of len(messages), which silently swallowed every --append user message (incident: 33 context vs 30 transcript). Full history survives compacted resumes.
- **Delivery self-check reads the right instruction**: the last real user input is re-injected — not the conversation's first line; budget nudges and teaching notes joined the harness-prefix list so they can never pose as the original task.
- **Fake-finish gate exemptions**: QA sessions are exempt, and a substantive summary counts as delivery (explanatory finishes are no longer pushed into creating files). Benchmark note: main arms ran under the old gate semantics.
- **Rejections carry no success semantics**: all six finish gates append neutral results instead of the [TASK_COMPLETE]-bearing one (which fed the model contradictory signals and marked the meta done mid-run).
- **Test-run gate exempts QA**: a chat ending in a workdir that happens to contain test_*.py no longer runs the suite first.
- **Truthful tool wording**: a tool outside the loaded list (hallucinated, or real but unloaded) reads "unavailable", not "disabled by repeat-call protection".
- **MAX ITERATIONS only prints on true exhaustion.**
