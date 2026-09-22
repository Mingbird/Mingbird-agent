# Judge rubric — HWF-04 (characterization-first variant)

The spec_pytest gate enforces: test_inventory.py byte-identical to the seed and 6/6 green. Grade the rest 0-10:

1. Root causes (0-4): overwrite-instead-of-raise on duplicate SKU; ghost zero-quantity entries and negative stock; total_value ignoring qty; case-sensitive search.
2. Characterization (0-3): repro_tests.py really reproduces each symptom and was demonstrably written before the fix (captured failing output counts).
3. Notes (0-2): regression_notes.md ties each change to its bug.
4. Hygiene (0-1): signatures unchanged, no test edits.

Deduction (up to -2): 'fixes' that special-case the exact test inputs.
