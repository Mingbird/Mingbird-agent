# Mingbird v1.6.0 — Release Notes · 发布说明

EN
--
Theme of this release line: small models occasionally act on destructive
impulses (impulsive uninstalls, blanket deletes, overwriting finished
deliverables with half drafts). v1.6.0 wraps them in a five-ring safety net.

v1.5.0 — harness robustness:
- read_file crawl guard v2, byte-budget based: budget = clamp(2x file size,
  64KB, 512KB). Never refuses — after the budget is spent it still returns
  the first 2000 characters of the requested range, so progress never stalls.
- Per-call output cap 2048 -> 8192. Truncation now triggers targeted
  "write the skeleton, then append" chunked feedback instead of an
  empty-turn spiral.
- Empty-turn ladder fix: unclosed <think> debris counts as an empty turn;
  nudge (x3) -> hard reset (x6) -> graceful exit is fully reachable.

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

Benchmarks: on the external tau2-bench, with the same local 4B model,
Mingbird tops all three domains — retail 0.789, airline 0.740,
telecom 1.000 (saturated: tied with the τ² native agent at full marks).

中文
--
本版本线主题：小模型偶发破坏性冲动（冲动卸载、全量删除、用半截稿覆盖
交付物）。v1.6.0 以五环安全垫兜住。

v1.5.0——harness 健壮性：
- read_file 爬行守卫 v2（字节预算制）：预算 = clamp(2×文件大小, 64KB,
  512KB)，永不拒绝——预算耗尽后仍返回所求区间前 2000 字符，进度不断。
- 单次调用输出上限 2048→8192；截断改给"骨架+追加"分块反馈，不再空轮螺旋。
- 空轮梯队修复：未闭合 <think> 残骸计为空轮；纠正×3→硬复位×6→优雅退出
  全程可达。

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

基准：外部 τ²-bench 三域，同一颗本地 4B，鸣鸟三域全部第一——retail 0.789、
airline 0.740、telecom 1.000（饱和域：与 τ² 原生 agent 并列满分）。
