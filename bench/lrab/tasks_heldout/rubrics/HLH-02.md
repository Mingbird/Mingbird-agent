# Judge rubric — HLH-02 (long-word index variant)

Deterministic checks verify the index content. Ground truth: top-8 words of length>=6 = stress 3726, fraction 3609, structure 3609, energy 3594, temperature 3588, process 3569, boundary 3530, sample 3517; lines containing 'energy' = 2714; raw lines = 6005, distinct = 6000 (so 5 exact duplicates). Per-topic counts are 600 or 601. Grade the rest 0-10:

1. Index correctness (0-4): all 8 words AND counts exact.
2. Energy analysis (0-2): count correct and compared to the even-share baseline (1/20 of the vocabulary) with the right conclusion.
3. Script-based evidence (0-2): streaming implementation; no whole-file read into chat context.
4. Distinct report (0-2): duplicate count 5 with a concrete example.

Deduction (up to -2): prose contradicting wordlen_index.json.
