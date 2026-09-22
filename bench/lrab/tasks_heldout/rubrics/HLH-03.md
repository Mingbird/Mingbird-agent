# Judge rubric — HLH-03 (reverse-order endurance variant)

The script_pass gate enforces the suite oracle '10 passed, 0 failed'. Ground truth bugs: m01 divisor len+1; m02 median not mean-of-middle-two; m03 population variance (needs n-1); m04 slope not least-squares; m05 trailing None; m06 smoothing steps back `factor` instead of 1; m07 multiply by max instead of divide; m08 integer division; m09 one-based index slip; m10 returns a slice, not the intercept. Grade the rest 0-10:

1. Baseline capture (0-2): baseline_failures.md quotes the initial run showing 10 failures before any fix.
2. Root-cause quality (0-4): >=8 diag logs state the actual cause with specifics.
3. Order discipline (0-2): evidence of m10 -> m01 progression (per-module re-runs, not one batch rewrite).
4. Final report (0-2): 'all tests' quotes the final suite output; 'regression' addresses cross-module breakage.

Deduction (up to -2): test_suite.py edited (the suite is the oracle).
