# Changelog

## v1.8.2 (2026-09-21)

### 🔒 Conversation isolation (hardening after a real incident)
- "Clear chat" only wiped the display while the next message silently continued the previous session's full history. Removed; replaced by a prominent **＋ New Chat** button that resets session, context, working directory (back to the default) and the todo panel — a new conversation can no longer inherit an old one's context or folders.
- The first message of a new conversation force-clears stale `.agent_state.json`/`todo.json` in the working directory; follow-ups honor the "resume" checkbox (previously the checkbox was ignored).
- Offline-mode visibility: asking for web search while offline now produces an explicit transcript note at task start, instead of the model silently scavenging local files.

### 🖱️ UI fixes
- Streaming rewrite: thinking/answer tokens are buffered and rendered in 150 ms batches. Thinking-heavy replies no longer freeze the UI (each token previously triggered a state toggle + forced reflow; thousands of thinking tokens saturated the Tk event loop).
- The transcript is now mouse-selectable and copyable (Ctrl+C); read-only is enforced by blocking edit keys instead of disabling the widget.

### ☁️ Cloud model picker
- A cloud-model box next to the 🔒 toggle: selectable only when online **and** configured; mutually exclusive with the local-model box (picking one clears the other — one model per conversation). Offline disables the box; the cloud path stays architecturally dead (`cloud_provider()` returns `{}`). A `?` button shows setup guidance; configuration is a `cloud` section in `config.json` (example in README).
- Tests: routing tests are now isolated from the host's real offline-mode config (459 green).
- Correction (added later, v1.8.2 entry kept as written): the suite currently collects **461** cases (`python -m pytest tests/ --collect-only -q` at the time of writing) — 435 unit + 26 integration. It contains no live-Ollama end-to-end test, and the benchmark runners under `bench/` and `benchmarks/` are separate programs, not part of the pytest suite. The 459 recorded above is the figure as of this release and is left unchanged as history.


## v1.8.1 (2026-09-21)

### 🚑 Hotfix: GUI failed to launch in v1.8.0
- The v1.8.0 offline-toggle edit accidentally inserted the new `_toggle_offline` method **inside** `_build_chat_page`, so the chat page's input box / transcript / directory bar were never constructed — the desktop GUI crashed immediately on launch (`AttributeError: no attribute 'input'`). All v1.8.0 packages (Windows installers and the Linux/macOS tarballs) were built from the affected source and can crash at GUI startup — upgrade to v1.8.1.
- Fix: the method now sits after `_build_chat_page` completes. Verified by actually launching the packaged executable (10 s alive, zero exceptions in the global error log) and by the full suite: 459 tests green.
- Process fix recorded: a release now requires launching the frozen build before upload — unit tests do not cover GUI construction order.


## v1.8.0 (2026-09)

### 🔒 One-click offline/online (offline mode) — privacy as an architectural commitment
- **One-click toolbar toggle** (🌐 online / 🔒 offline): offline = local Ollama models only; built-in web tools (web_search / web_fetch / web_search_multi / batch_tools) are **not assembled into the prefill** (the model cannot call what it cannot see; static prefill shrinks accordingly); URL-based (HTTP) MCP servers are skipped entirely (local stdio processes kept); the cloud provider is force-disabled. The claim is verifiable with `netstat -ano | findstr <pid>`: zero outbound connections for the whole duration of a task in offline mode.
- CLI / environment: `AGENT_OFFLINE=1` overrides; `offline_mode` persisted in config.json.
- Tests: tests/test_offline_mode.py (8 cases — assembly filtering / cloud disable / message mapping; zero network requests).

### ☁️ Cloud provider (OpenAI-compatible endpoint, optional)
- config.json `cloud` section (`base_url` / `api_key` / `model` / `enabled`): when enabled and not offline, inference goes through the OpenAI-compatible `/chat/completions` (local-first unchanged; one-click fallback to offline). The api_key is stored only in the local config. Tool calls are mapped bidirectionally ollama↔OpenAI (tool_call_id paired in FIFO order — the same logic as measured on all four harnesses).

## v1.7.0 (2026-09)

### 🎛️ Three-state sampling: hidden defaults removed, back to ollama defaults
- **Temperature: three states** — not set by the user → the /api/chat options carry no temperature field at all (the model manifest's baked-in value / the ollama default decides); explicitly set (including 0) → sent as set. The old default of 0 (inherited from the v1.5 benchmark protocol's `AGENT_TEMP` default) was a hidden particularity in a released product; removed.
- **Thinking: three states** — not set → no think field is sent (ollama factory default: models with thinking capability think by default and return a separate thinking field); explicit on/off → top-level think field (placed inside options it would be silently dropped by ollama). The old default suppression of "think:false for every capable model" is removed; the 400 retry-without-the-param fallback is kept for non-thinking models that reject the think field.
- **Empty-thinking turns handled properly**: when thinking is non-empty but content is empty (thinking burned through the generation budget), the thinking excerpt is still reported/logged as-is (the streaming thinking UI shows it as usual), and the empty content enters the empty-turn protection ladder as a normal empty response (3 nudges / 6 hard reset / graceful exit when the budget is spent) — no infinite loop, no crash.
- **Settings wired end to end** (desktop GUI + WebUI → gui_prefs.json → agent runtime → payload): empty temperature = not set; thinking becomes a "default / on / off" three-state selector. Fixed two defects in the old "thinking off" checkbox: the wiring was inverted (checking it actually sent AGENT_THINK=1) and it never persisted; the WebUI toolbar thinking quick-toggle previously had no event binding at all (pure decoration) and is now wired to the three states.
- **Shared-preferences migration**: gui_prefs.json gains a prefver marker; the old hidden defaults (temperature 0, thinking on) are migrated once to "not set", so an explicit 0 / off set by the user is no longer wiped as a default.
- Environment-variable behavior: `AGENT_TEMP` / `AGENT_THINK` unset = the payload carries no corresponding field. Tests: new tests/test_sampling_three_state.py (12 payload-construction assertions, no network requests).

## v1.6.0 (2026-09)

### 🛡️ General safety cushion: protection against small-model destructive behavior (four layers)
- **Overwrite self-destruction guard**: create_file is refused when it would overwrite an existing large file with much shorter content; an explicit replace=true is required. Use append_file to add content and edit_file for local edits. (Observed in practice: e2b once overwrote a complete delivery manual with a half draft in 91 seconds.)
- **Rollback-able deletion**: delete_file no longer erases outright; files are moved into .mingbird_trash/ in the working directory and are recoverable.
- **Tiered command protection**: package uninstalls / environment mutation (setx, scheduled tasks, service deletion) are denied by default in unattended mode and queried when attended; recursive deletes are allowed only inside the working directory; system-level destructive commands (format/diskpart/vssadmin etc.) are refused unconditionally.
- **~ path guidance**: file tools refuse paths starting with ~ and steer toward relative paths inside the working directory.
- Escape hatches: AGENT_UNSAFE=1 turns all of it off; AGENT_ALLOW_ENV_MUTATION=1 allows unattended environment mutation.

### 🧭 Other
- Benchmark ablation framework: mechanism-level ablations (baseline + finish_gate/anti_loop/flat_prefill/verify_feedback) get independent result directories; resumed runs no longer contaminate each other.

## v1.5.0 (2026-09)

### 🛡️ harness robustness, three fixes (driven by evidence from a 72-cell rerun)
- **read_file crawl guard v2 (byte-budget based)**: budget = clamp(2× file size, 64KB, 512KB), never refuses — after the budget is spent, each read still returns the first 2000 characters of the requested range, so progress never breaks; the 4th/10th read adds a one-line policy hint. v1's hard refusal by call count pushed small models into wall-banging loops in real batches (redesigned after the evidence).
- **Output cap 2048 → 8192** (a cap, not a target): a single tool call can now carry a complete medium-sized code file; the old 2048 cut large-file emissions in half and spiraled into empty turns. The truncation death signature (done_reason=length with no body text and no calls) now gets targeted chunked feedback: "create_file the skeleton + append_file the rest".
- **Empty-turn ladder fix**: truncation debris from an unclosed <think> is correctly counted as an empty turn; the consecutive-empty-turn ladder — nudge (×3) → hard reset (×6) → graceful exit — is now fully reachable in practice.

### 🧭 Other
- run_matrix cell-level checkpoint resume: cells already scored are skipped automatically; restarts waste nothing.
- Rich release documentation committed (bilingual README + benchmark evidence pack in benchmarks/).
- Full changes in git log; benchmark-number basis: LRAB-288 final (see benchmarks/ for details).

## v1.4.0 (2026-09)

### 🎀 Brand naming: Mingbird
- The English name, GUI title, installer and facade docs all ship under the Mingbird brand. The new name has zero conflicts across the four registries GitHub/npm/PyPI/crates, and the Chinese name has zero usage by existing software.
- Zero user-data migration: config directories `~/.ollama_agent` and `%LOCALAPPDATA%\LocalAgent` unchanged; new environment variables `MINGBIRD_HOME` / `MINGBIRD_DEPTH`.
- The Inno install directory is `{localappdata}\Mingbird`.

### Delivery self-check gate (finish re-read)
- When a task's finish fires, the original task text is dynamically re-injected once and the model must re-check format / units / named sub-items against the assignment before calling finish again (guards against semantic drift at the tail of long tasks). Fires only after all existence gates pass; once per task; Q&A and sub-agents exempt; static prefill net growth 0.

## v1.3.0 (2026-09-01)

### todolist planning pipeline (key fix)
- **Fix: short follow-up instructions mid-task could be misread as chit-chat**, unloading the planning (todo) tools and intercepting file writes / commands — as long as the session already holds real work, short follow-ups are now always treated as task continuation; explicit greetings are unaffected.
- **Planning lifecycle backstop**: a dynamic reminder when several real work steps pass without a plan update (at most 2 per task); a finish with an out-of-sync plan is intercepted with an executable catch-up call (`todo(update, all=true)`); after context compaction the current plan text is re-injected automatically, so the progress coordinate is never lost.
- **GUI plan panel**: a new task clears the previous task's stale plan; the title shows completion progress live (n/m); scrollable and auto-positioned on the first unfinished item.

### Task time limit (new, off by default)
- New "task time limit" input in the GUI directory bar: empty by default = no limit; accepts forms such as `40` / `1.5h` / `90m` / `half an hour`.
- The limit can also be written in natural language (Chinese or English) directly in the task description (e.g. "timebox 40 minutes"); it is auto-detected and back-fills the input box; on conflict, **the prompt takes highest priority**.
- Crossing 50% / 75% / 90% each produces one wind-down nudge; after a checkpoint resume the clock continues without repeat nagging. CLI equivalent: `--time-budget <minutes>`.
- For slow local models and time-sensitive users: keeps the run from burning all its time on a single dead point.

### Edit convergence guard
- When several consecutive successful edits to the same file still do not converge (tests still fail after the changes), a strategy hint is injected: read the full error and locate the root cause first, verify the hypothesis before acting; at most 2 reminders per file, and no tool is disabled.

### Long-output slimming for small models
- For ≤4B models, very long command output keeps only a tail summary (test results and errors live at the end) plus an escape hatch — full output written to disk, then read back in chunks — noticeably lowering context pressure and reducing compaction; output for ≥12B models is byte-for-byte unchanged.

### Parallel sub-agent dispatch (new, off by default)
- Detects spare hardware capacity automatically (budgeted on physical RAM, fitting iGPU shared-memory machines); when the plan contains many mechanical small tasks that are simple and hard to get wrong, sandboxed sub-agents are dispatched in parallel, integrated after a six-step deterministic acceptance pass, with automatic fallback to serial execution on the main model on failure.
- **Security model: sub-agents hold strictly fewer permissions than the main agent** — any path outside the work partition is deny-by-default for writes (no configuration can undo it); sensitive directories (credentials / VM disks / system areas) are double-listed; a dangerous-command blacklist (including quoted / escaped / chained variants); full audit logging; immediate circuit-breaker fallback on severe violations; the confirmation-dialog channel is short-circuited for sub-agents as a whole (default-deny).

### Other
- The factory prefill (system prompt + tool definitions injected before the first token) stays byte-for-byte identical to v1.2.0 — all new features are injected dynamically at runtime, adding no resident tokens and slowing nothing before the first response.

## v1.2.0 (2026-08-31)

### harness reliability (iterated on the LRAB benchmark's long-horizon layer)
- **Anti-loop fix**: the hard rule "same tool called repeatedly → disable" now requires "repeated with identical arguments" to count as a death loop — legitimate batch work with varying arguments (a script per slice, a read per file) is no longer wrongly disarmed; `enable_tools` with nothing new to enable now replies explicitly "already enabled, call directly"; disable messages now give a concrete next action instead of pushing small models into detours and deadlocks.
- **Finish gate**: task completion uniformly goes through an explicit finish call, reducing early_finish walkaways.
- **Tool downgrade for small models**: small-context models shrink their tool surface automatically, lowering the mis-call rate.

## v1.1.0 (2026-08-26)
- **Working-directory boundary guard system**: out-of-bounds file operations raise a GUI confirmation dialog; sensitive paths (.ssh/.env etc.) protected; dangerous-command interception expanded; verify-before-retry.
- **Tool layering + flat category routing**: tools/MCP tagged by category and loaded on demand; prefill down another 50%+.
- **Context engineering**: universal disk cache; full spill-to-disk + summaries + on-demand close reading; tiered compaction; parallel retrieval.
- **MCP connection pool** (cures intermittent 500s); context pre-estimation; batch orchestration; remote MCP (search) integrated.

## v1.0.0 (2026-08-21) — first stable release

### 🎉 Milestone: first stable release of the local small-model agent Mingbird
- **Positioning**: a local AI agent specialized for 0.5-9B small models / integrated graphics / 16 GB laptops.
- **Core capabilities** (validated by the V1-V38d benchmarks + 10 rounds of research iteration):
  - flat prefill: tools load by category on demand — prefill down 50%+, faster
  - Q&A/task layering: chit-chat answers directly (chat prompt + read-only tools), tasks execute with the full toolset
  - streaming output + collapsible thinking display
  - tool safety gate (rm -rf / system-path interception)
  - harness backstop trio: .bak backup rollback / precise failure injection / syntax-error recovery hints
  - strict repeated-tool-call interception + death-loop detection
  - model auto-detection + context gradient (16K-256K) + voice input (sherpa-onnx)
- **Three-model profile** (measured): qwen3.5:2b (most stable on long context / well-specified tasks), gemma4:e2b (fastest at 40 t/s / web research), Mellum2 (strong on rules / code, short sessions only).
- Installers: `Mingbird-v1.0.0-EN-Setup.exe` / `鸣鸟-v1.0.0-中文安装包.exe` (247 MB each, bundling the offline voice STT model, ready on install), with full documentation (AGENTS.md).

### 🔧 Pre-release closing fixes (2026-08-21 afternoon)
- **Bilingual purity**: full i18n — previously only the main toolbar had been translated, and 198 visible Chinese strings (model names / sidebar / buttons / dialogs / status bar / thinking fold / voice feedback) still displayed Chinese in the English build. The English build is now all English, the Chinese build all Chinese.
- **Voice input no longer ends by itself after a few seconds**: fixed a stale-timer bug (manual stop-recording did not `after_cancel` the pending callback, so the next recording was cut short by the previous 20 s timer). Added energy VAD — about 1.2 s of silence after speech stops transcription automatically (no manual stop needed), with a 60 s safety cap; also fixed `_voice_worker` touching Tk variables from its thread.
- **Window maximized by default**: double-click opens an adaptive large window (previously a small window showed only the top-left corner).
- **Installer robustness**: the installer now terminates a running LocalAgent.exe before installing, avoiding file locks that abort the copy and leave a broken install (missing base_library.zip → fatal `encodings` error at startup).
- **UI polish**: empty-state welcome copy; ℹ about dialog (version / docs / install directory); Ollama online status light (click to auto-start); ttkbootstrap 2.0 theme (removes legacy deprecation warnings).

## v0.12.0 (2026-08-21)

### agent reliability hardening

(Driven by the internal V1-V38d development benchmarks; key finding: weak self-debugging is a common small-model shortfall, and harness backstops — backups + precise failure feedback — relieve it markedly: repair tasks went from stuck at 42+ turns to done in 16-24 turns.)
- **`.bak` file backup**: automatic backup before edit_file, so the model can roll back when it wrecks a file (measured on three models: repair tasks from stuck at 42+ turns to done in 16-24 turns).
- **Syntax-error recovery hint**: when a pytest failure contains a SyntaxError, the model is told to restore from .bak or rebuild the file.
- **Precise failure injection `_pytest_hint`**: on test failure, the failing test / file / line / assertion is injected for the model, helping it localize the defect.
- **Tool safety gate**: intercepts rm -rf / format / writes and deletes to system paths.
**Model routing module**: recommends a model automatically by task type; usable as the GUI's auto-selection reference.

## v0.11.0 (2026-08-20)

### Product
- **Brand named Mingbird** (formerly LocalAgent): GUI title, installer and docs updated across the chain.

### Architecture (root-cause level)
- **Q&A/task layered prefill**: root cause confirmed — the small-model "Q&A death loop" comes from [task-style system prompt + full tools + Continue injection], not a model defect. Q&A → chat prompt + read-only tools; answer once and stop.
- **Tagged flat prefill**: tools tagged by category (files / code / web / memory / MCP), tasks routed automatically to the relevant categories, **exposing only the relevant tools** (measured: search → 8 tools, coding → 12, instead of all 17) → prefill down 50%+, faster.
- **Repeated-output death-loop detection**: text similarity ≥ 0.75 repeated ≥ 2 times → forced wind-down (guards both Q&A and tasks).
- **Voice fix**: numpy switched from the MKL build to the OpenBLAS build (MKL DLL removal had broken voice).

### Verification
- flat prefill verified on real hardware across the three models: qwen2b ✅23 / e2b ⚠️16 (stddev formula; model capability) / Mellum2 ✅11.

## v0.10.0 (2026-08-20)

### Added
- **Streaming output (the core speedup)**: conversation replies render token by token in real time — no more staring at a blank panel waiting for the whole block. The first token appears within 1 second.
- **Streaming thinking + auto-fold**: the thinking stream renders in gray and folds automatically into "🤔 Thinking (N chars) — click to expand/collapse"; clicking toggles.
- **New top-three models**: qwen3.5:2b (256K long context) / gemma4:e2b (128K, 40 t/s) / Mellum2 (code). The model list is updated, replacing the old e4b/lfm.
- **Context gradient extended**: five tiers — 16K / 32K / 64K / 128K / 256K (256K reserved).
- Measured: small models can safely take large contexts (qwen2b 256K, e2b 128K, Mellum2 64K) — a step change from the old e4b's 32K deadlocks.

### v0.10.0 fixes (2026-08-20, round two)
- **Mojibake fix**: agent subprocess stdout forced to UTF-8 (PyInstaller's default GBK → garbled Chinese text).
- **Thinking fold rewritten**: tag-region tracking; folding touches only the thinking region, never the body; clicking expands/collapses normally (no more duplicated copies).
- **Voice fix**: packaging adds `--collect-all numpy` (numpy previously failed importing from the source directory).
- **Default model fixed**: e4b → automatically take the first entry of the model list.
- **Model auto-detection**: the model list is read dynamically from ollama `/api/tags` (adapting to each user/machine); known models get friendly names, unknown ones show the raw tag.
- **Agent-run fix**: the packaged exe runs in agent CLI mode (no longer pops a new window on message).

## v0.9.0 (2026-08-20)

### Added
- **On-demand ollama (not resident)**: no more auto-start at boot. Opening the agent (GUI or CLI) triggers `ensure_ollama()`, which detects and starts ollama serve (with iGPU environment variables, ready in ≤25 s). Zero boot cost; loaded only when used.

## v0.8.0 (2026-08-20)

### Added
- **Context deadlock fix (critical)**: CTX_BUDGET default 32768 → **16384**. Previously a 3.3 GB model + 32K KV cache filled 13.7 GB of RAM and deadlocked the ollama service (even the smallest requests timed out); at 16K it runs stably.
- **Checkpoint-restore hardening `sanitize_ckpt()`**: if a crash lands on "assistant with tool_calls but no tool results", recovery cleans dangling calls / empty content / `response:unknown{...}` junk, preventing the model from emitting corrupted content.
- **Actionable missing-argument errors `_REQ_ARGS`**: when a tool such as edit_file lacks a parameter, the error clearly lists the required and the received arguments (the old `[tool error: 'path']` was unreadable to the model, which retried in place).
- **Second batch of internal benchmark iterations V24-V26 designed**: V24 skill crystallization / V25 natural-language scheduling / V26 compound voice commands.

## v0.7.0 (2026-08-19)

### Added
- **First batch of internal benchmark iterations (V21-V23) completed**: structured-output hardening (repair_json) / local knowledge base (RAG) / model routing layer
- The test-verification guard stayed effective across V18-V23 (blocked a large number of "finish without verifying")
- **Key finding**: qwen3.5:4b passed all three versions of this batch (e4b degrades over long sessions and V22 was not implemented; lfm stayed weak on complex tasks)
- LocalAgent_setup.exe installer completed and verified end to end (onefile, 137 MB)

## v0.6.0 (2026-08-19)

### Added
- **UI modernization round one (modern minimal)**: rebuilt following the UI design skill — warm off-white background + charcoal text + a single green accent, flat buttons, no emoji, editorial typography; the window title shows the real version dynamically (fixed the hardcoded "v4")
- **Packaging**: LocalAgent.exe builds (PyInstaller, slimmed 710 MB → 77 MB); installer LocalAgent_setup.exe (onefile, app bundled)
- **Competitor research**: first round completed, written to research/2026-08-19-competitor-analysis.md (SmoLAgents/Hermes/VoiceAgent etc.)
- **Test-verification guard**: when the model calls finish and the directory holds test_*.py, the harness runs pytest itself and refuses finish on failure (cures "done without verifying")

## v0.5.0 (2026-08-19)

### Added
- **Chinese voice input**: sherpa-onnx 14M model (20× faster than real time), available to every model, two-stage recording (start/stop)
- **MCP integration**: 3 servers (official filesystem/memory + in-house utils for time/math/hash), lenient parameter-name aliases
- **20-version iteration benchmark**: V1-V17 completed (see bench/results.md), validating capability across the e4b/qwen/lfm trio

### Core agent improvements (18 items)
- Fixed the ollama 0.32 usage-field bug (automatic context compaction actually took effect for the first time)
- Fake-finish guard (finishing without doing real work is refused)
- File self-healing (escaping at any depth), run_bash command normalization, Linux path-hallucination hints
- Tool-call rescue; four-level detection of repeated failure / success / research / todo loops; disable mechanism
- Prefill tokens trimmed to 737 (1/13 of MyAgents)

(The mechanisms in this section were driven by the internal V1-V17 development benchmarks — 18 harness defects exposed by cross-testing the three models, fixed one by one; the process notes are not published with the product changelog.)
