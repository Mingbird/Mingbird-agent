# Judge rubric — HWF-05 (quarantine variant)

Ground truth: 40 raw rows -> 35 clean, 5 rejected (sentinel 9999, -40.0, one missing humidity, one error row, one exact duplicate). Grade 0-10:

1. Ledger arithmetic (0-4): rows-in = sum of per-rule drops + rows-out, exactly.
2. Quarantine completeness (0-3): rejected.csv accounts for every dropped row with a correct reason; nothing vanishes silently.
3. Rollup (0-2): stats computed from the clean rows only, correctly rounded.
4. Re-scan (0-1): an actual second pass proving the tidy file is clean.

Deduction (up to -2): counts that cannot be reproduced from the fixture.
