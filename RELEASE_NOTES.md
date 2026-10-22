## 🇨🇳 中文

# 鸣鸟 v3.1.3

压缩 runner 修复版。桌面 UI 不变。**631 项测试全绿**（628 + 3 新增）。

- **L2/L3 压缩不再另起第二份模型实例**：摘要调用此前钉死 `num_ctx=8000`，而主循环跑在会话档位上——ollama 按（模型， options）起 runner，ctx 不同等于同一个模型再载一份，每次压缩都多一次全量加载，紧显存机器上还会驱逐乒乓（日志特征：`predicted_num_ctx=8000` 与主档位交替加载）。摘要现在骑主上下文的常驻 runner，超长摘要输入也不再被 8K 窗口静默左截断。
- **压缩失败不再无声**：失败时打印层级与原因——此前静默跳过但压缩阶梯已消耗，正是"超上下文但压缩永不触发"的失败形态。

---

## 🇬🇧 English

# Mingbird v3.1.3

Compaction-runner fix. Desktop UI unchanged. **631 tests green** (628 + 3 new).

- **L2/L3 compaction no longer spawns a second model instance**: the summary call pinned `num_ctx=8000` while the main loop runs at the conversation's tier — Ollama keeps one runner per (model, options), so every compaction reloaded the same model at a different context (eviction ping-pong on memory-tight setups; log signature: `predicted_num_ctx=8000` alternating with the main budget). The summary now rides the resident runner at the main context, and long summary inputs are no longer silently left-truncated at 8K.
- **Compaction failures are no longer silent**: the layer and reason are printed — previously the failure was swallowed while the compaction ladder was already consumed, the exact "context over budget but compaction never fires" shape.
