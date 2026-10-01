# Mingbird v1.9.1 — Release Notes · 发布说明

EN
--
Theme of this release: out-of-the-box for everyday computer work, not just
coding. The app now bundles bilingual voice input, six universal skills
(files / web research / document digest / Word / Excel / images), and a
built-in Python runtime the agent can call — while the installer actually
got ~9 MB smaller.

v1.9.1 — universal skills & bilingual voice:
- New `run_python` tool: executes Python on the interpreter bundled inside
  the app. No Python, no Office install needed on the user machine.
  pandas / numpy / PIL ship with it. Same safety gates as run_bash
  (danger patterns blocked, destructive ops classified, workspace sandbox,
  300 s tree-kill timeout). Behind enable_tools in the code category, so
  the factory prefill is byte-identical (797-token budget test unchanged).
- Six universal built-in skills (joining the 11 coding ones):
  file_organizer, web_research, doc_digest, office_word, office_excel,
  image_batch. Progressive loading: only names + one-line descriptions
  are visible until a skill is actually loaded.
- Voice input is bilingual out of the box: a second bundled streaming
  Zipformer (English, en-20M int8) beside the Chinese one; a 中/EN toggle
  by the mic, persisted per user. Audio never leaves the machine.
- Installer is ~9 MB SMALLER: bundled STT models now ship int8-only (the
  float32 weights nobody loaded are gone) even after adding the English
  model.
- Skill & MCP visibility: the GUI Skills window lists skill directories,
  how to install your own skills, and configured MCP servers.
  skills/README.md documents the format and lookup order.
- Tests: 472 green (461 + 11 new). Upgrading from v1.8.x is drop-in.

ZH
--
这一版的主题:日常电脑活也开箱即用,不止写代码。内置中英双语语音输入、
六个通用技能(文件/联网调研/长文速读/Word/Excel/图片),以及一个 agent
可以直接调用的内置 Python 运行时;安装包反而小了约 9 MB。

v1.9.1——通用技能与双语语音:
- 新工具 `run_python`:用程序内置的解释器跑 Python,用户机器无需装
  Python 或 Office;pandas/numpy/PIL 随包可用。安全门与 run_bash 同款
  (危险模式硬拦、破坏性操作分级、工作目录沙箱、300 秒超时进程树杀)。
  归在"代码"类别经 enable_tools 装配,出厂 prefill 一字不变
  (797 token 预算测试不变且全绿)。
- 六个通用内置技能(加入原 11 个编码技能):file_organizer、
  web_research、doc_digest、office_word、office_excel、image_batch。
  渐进式加载:平时只暴露名字与一行描述,用到才载全文。
- 语音输入中英双语开箱即用:在中文模型旁内置英文流式 Zipformer
  (en-20M,int8);麦克风旁 中/EN 按钮切换,选择持久化。录音不出机器。
- 安装包反而小约 9 MB:内置 STT 只带 int8 权重(没人加载的 float32
  已删),即便多塞了一个英文模型。
- 技能与 MCP 可见性:GUI 技能窗口列出技能目录、自装技能方法、已配置
  的 MCP 服务器;skills/README.md 写明格式与查找顺序。
- 测试:472 全绿(461 + 11 新增)。从 v1.8.x 升级直接覆盖安装即可。
