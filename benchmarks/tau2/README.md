# τ²-bench per-trial data (unified protocol: temperature 0, thinking off)

One manifest per domain, keyed by task id. Each row records, per harness:
`status`, `reward`, and `wall` (seconds).

Arms: `mingbird`, `llm_agent` (the benchmark's native agent), `opencode`.
goose is **deferred** on this benchmark — under the same protocol it needs
40–113 min per task (~4.85M input tokens per task, nested sub-agent loops),
so it is not part of this data release.

Batch composition (all cells temperature 0 with thinking off, verified
end-to-end at the transport layer):

- **retail**: unified re-run batch (all three arms).
- **airline, telecom** (`llm_agent`, `opencode`): unified re-run batch.
- **airline, telecom** (`mingbird`): the earlier verified no-thinking batch
  for those domains — its protocol already matched (thinking off at the
  request level), so those cells were carried over unchanged.

Domain means recomputable from these files:

| Harness | retail (114) | airline (50) | telecom (114) |
|---|---|---|---|
| Mingbird | 0.763 | 0.740 | 1.000 |
| llm_agent | 0.675 | 0.740 | 0.930 |
| opencode | 0.588 | 0.500 | 0.991 |

The thinking-on sensitivity data (the superseded legacy batch, four arms)
is archived under [`tau2_thinking_on/`](tau2_thinking_on/); it is retained
for the thinking-configuration analysis only and is **not** the current
protocol's numbers.
