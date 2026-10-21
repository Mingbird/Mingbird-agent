## 🇨🇳 中文

# 鸣鸟 v3.1.2

v3.1.1 源码审计修复版。**628 项测试全绿**（625 + 3 新增）。

- **并行派发死路径修复**：`config.json` 手写的 `parallel` 段此前被配置层静默丢弃——`load_config()` 只拷贝默认表已有的键，而默认表没有这个键，环境变量也没有通道能打开 `enabled`，整条链路从未打开过。现在默认表携带该键，并有全链路回归测试钉住。
- **无人值守 = 全局拒绝**：`AGENT_UNATTENDED=1` 下所有人类确认通道（含流式 `@@ASK@@` 弹窗分支）一律立即拒绝，不再为一个不存在的人类挂 120 秒等待。
- **爬行守卫字节口径**：预算按字节（2× 文件大小）、消耗此前按字符累计——中文文件实际拿到约 3 倍额度；现在两侧统一为 UTF-8 字节。
- **文档措辞如实化**：prefill 钉子是"1250 估算 token（中文校准估算器）不变式"——任何改动、无论增减都会挂 CI；旧"797 token / 单字节"表述已过期，全部改齐。

桌面 UI 与 v3.1.1 相同，无界面变化。

---

## 🇬🇧 English

# Mingbird v3.1.2

Audit-fix release from a source review of v3.1.1. **628 tests green** (625 + 3 new).

- **Parallel dispatch dead path fixed**: a hand-written `parallel` section in `config.json` was silently dropped — `load_config()` only copies keys the defaults table knows, the key was missing there, and no environment variable could flip `enabled`. The defaults table now carries the key, pinned by a full-pipeline regression test.
- **Unattended = global deny**: with `AGENT_UNATTENDED=1`, every human-confirmation channel (including the streaming `@@ASK@@` pop-up branch) denies immediately instead of waiting 120 s for a human that was promised absent.
- **Crawl guard byte accounting**: the budget is byte-based (2× file size) while consumption counted characters — CJK files got roughly 3× the intended quota. Both sides now count UTF-8 bytes.
- **Docs made honest**: the prefill pin is an estimated-token equality (1250 under the CJK-calibrated estimator) that fails on any change, growth or shrinkage; the stale "797 tokens / single byte" phrasing is gone everywhere.

The desktop UI is unchanged from v3.1.1.
