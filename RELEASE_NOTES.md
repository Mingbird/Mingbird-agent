# Mingbird v1.7.0 — Release Notes · 发布说明

EN
--
Theme of this release line: remove the hidden sampling special-cases. A
released product should not ship opinionated defaults baked into the
harness. v1.7.0 returns temperature and thinking to ollama's own defaults
and makes the existing switches truly three-state.

v1.7.0 — sampling goes three-state (user choice / ollama default):
- Temperature: when unset, /api/chat requests carry NO temperature field —
  ollama uses the model manifest's baked-in value. When the user sets a
  value (including 0), it is sent explicitly. The old "default 0" is gone.
- Thinking: three-state. Unset = no think field (ollama factory default:
  thinking-capable models think by default); on = top-level think:true;
  off = top-level think:false. The old default think:false suppression for
  capable models is removed.
- think stays a top-level field (it is silently dropped inside options);
  models that reject the field still get the drop-and-retry fallback.
- Thinking non-empty but content empty (a thinking model burning its
  generation budget) is now reported verbatim — thinking excerpt logged,
  streamed thinking stays visible in the UI — and handled as a normal
  empty response by the existing empty-turn ladder. No crashes, no loops.
- Settings surfaces wired end to end (desktop GUI + WebUI): temperature
  box empty = unset; thinking is a default/on/off selector (the old
  "disable thinking" checkbox had inverted wiring and never persisted —
  both fixed). Shared gui_prefs.json migrates once: legacy hidden defaults
  (temp 0, think on) become "unset", marked by prefver so a deliberate 0
  survives restarts.

v1.6.0 — five-ring safety net:
- Ring 0: sub-agent sandbox — default-deny, strictly fewer permissions than
  the main agent.
- Ring 1: irreversible operations refused outright — format, diskpart,
  dd to raw devices, wsl --unregister, dism, driver uninstall, userdel.
- Ring 2: behavior tiering — software uninstalls / system environment
  changes confirm per action when attended, deny by default when unattended
  (AGENT_ALLOW_ENV_MUTATION=1 to opt in).
- Ring 3: boundary confirmation — recursive deletes confined to the working
  directory; out-of-bounds refusals come with a per-file way out.
- Ring 4: rollback everywhere — .bak before writes; delete_file lands in
  .mingbird_trash/; overwriting a large file with much shorter content
  needs an explicit replace=true.
- Escape hatches: AGENT_ALLOW_ENV_MUTATION=1 for unattended env changes;
  AGENT_UNSAFE=1 disables the whole net (at your own risk).

中文
--
本版本线主题：移除隐藏的采样特殊性。发布产品不应在 harness 里烤入带倾向的
默认值。v1.7.0 把温度与思考还给 ollama 默认，并让既有开关真正三态生效。

v1.7.0——采样三态（用户选择 / ollama 默认）：
- 温度：未设置时 /api/chat 请求完全不带 temperature 字段，由模型 manifest
  烤入值决定；用户设置后（含 0）按设置显式下发。旧"默认 0"移除。
- 思考：三态。未设置 = 不带 think 字段（ollama 出厂默认：具备 thinking
  能力的模型默认开思考）；开 = 顶层 think:true；关 = 顶层 think:false。
  旧版对能力模型一律 think:false 的默认抑制移除。
- think 保持顶层字段（放 options 会被 ollama 静默丢弃）；拒收该字段的
  模型仍走"去参重试"兜底。
- "思考非空、正文为空"（思考烧光生成预算）现在如实上报——思考摘录入日志、
  界面思考流照常可见——并按正常空响应进入既有空轮防护梯。不崩溃、不死循环。
- 设置面端到端贯通（桌面 GUI + WebUI）：温度留空 = 未设置；思考改为
  默认/开/关三态选择（旧"关闭思考"勾选框接线相反且从不持久化，一并修复）。
  共用的 gui_prefs.json 做一次性迁移：旧隐藏默认（温度 0、思考开）转为
  "未设置"，prefver 标记保证用户显式设置的 0 重启后仍在。

v1.6.0——五环安全垫：
- 环0 子代理沙箱：default-deny，权限严格小于主代理。
- 环1 不可逆操作直接拒绝：format / diskpart / dd 裸设备 /
  wsl --unregister / dism / 驱动卸载 / userdel。
- 环2 行为分级：卸载软件、系统环境变更——有人值守逐条确认，无人值守
  默认拒绝（AGENT_ALLOW_ENV_MUTATION=1 放行）。
- 环3 边界确认：递归删除限工作目录内，越界拒绝并给逐文件出路。
- 环4 可回滚：写前 .bak；delete_file 落 .mingbird_trash/；短内容覆盖
  大文件需显式 replace=true。
- 逃生口：AGENT_ALLOW_ENV_MUTATION=1 放行无人值守环境变更；
  AGENT_UNSAFE=1 全关（自担风险）。
