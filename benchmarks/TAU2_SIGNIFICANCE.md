# tau2-bench paired significance (exact McNemar primary)

Per-task outcomes are pass/fail (reward 0/1). McNemar exact on
discordant pairs is the primary test; Wilcoxon (normal approx,
zeros dropped) reduces to the sign test on binary pairs and is
shown for continuity with the paper's earlier wording. Holm k=2
across the two comparisons.

## Mingbird vs native LLM agent
- pooled (278 tasks): 40W / 216T / 22L
  McNemar exact p = 0.03002 | Wilcoxon p = 0.02225
- discriminating subset retail+airline (164 tasks): 32W / 110T / 22L, McNemar p = 0.2203
- per-domain: retail 26/72/16, airline 6/38/6, telecom 8/106/0

## Mingbird vs opencode
- pooled (278 tasks): 47W / 217T / 14L
  McNemar exact p = 2.719e-05 | Wilcoxon p = 2.387e-05
- discriminating subset retail+airline (164 tasks): 46W / 104T / 14L, McNemar p = 4.224e-05
- per-domain: retail 31/72/11, airline 15/32/3, telecom 1/113/0

Holm-adjusted (k=2) McNemar p, vs native LLM agent: 0.03002  <- significant at 0.05
Holm-adjusted (k=2) McNemar p, vs opencode: 5.438e-05  <- significant at 0.05

Effect-size retention (common opponent opencode): paired margin
+0.407 on LRAB-288 vs +0.119 here (29% retained); the native arm
does not appear in the LRAB matrix.

