# Judge rubric — HWF-03 (day-report feature variant)

Deterministic checks cover design/test docs and the wired command. Grade 0-10:

1. Implementation (0-4): cmd_day filters entries by calendar day, excludes the running timer, honours --project, prints a correct grand total.
2. Tests (0-3): >=4 meaningful pytest cases that would fail on a wrong implementation, all green.
3. Docs (0-2): usage_day.md shows a genuinely captured session.
4. Integration (0-1): argparse registration matches the existing style; no regression in start/stop/report.

Deduction (up to -2): tests that assert nothing (tautologies).
