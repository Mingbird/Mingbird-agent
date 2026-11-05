# Harness comparison — analysis and table verification

Scripts behind the five-harness comparison (0.75B to 4.7B, plus a 35.5B anchor).
They do not run any model. They read a tree of finished cells and produce, or
check, every number in that study.

## What you need

A results tree with one directory per cell, each holding a `score.json`:

```
<root>/experiments/results/b_matrix/<agent>_<model>_<task>/score.json
<root>/experiments/results/b_gradient/<...>/score.json
<root>/experiments/results/b_quant/<...>/score.json
<root>/experiments/results/b_35b_hlh03/<...>/score.json
```

The per-cell archive is large (transcripts and working directories, not just
scores) and is supplied by the authors on request; the study's data availability
statement has the details. Point `COMPARISON_ROOT` at whichever directory you
unpack it into:

```
set COMPARISON_ROOT=comparison-data
python analyze_comparison.py
python verify_tables.py
```

The task suite, the scorer and the runners are in this repository
(`bench/lrab/tasks_heldout`, `bench/lrab/scoring`), so a cell can also be
regenerated from scratch rather than unpacked.

## Files

| file | what it does |
|---|---|
| `analyze_comparison.py` | reads every cell, applies the exclusion rule, and writes the tidy per-cell CSV plus the summary the study's means, spans, gaps and tests are taken from |
| `verify_tables.py` | recomputes each printed table from the cells and fails if a value differs; eleven checks, one per table or per reported sub-result |
| `comparison_filters.py` | the single implementation of "this cell died because the server was unreachable", imported by both so the two cannot drift apart |

`verify_tables.py` exits non-zero on any mismatch and prints the value
it computed beside the value the table carries. Its last check reads a live
Ollama endpoint (`127.0.0.1:11437`) to confirm the served model digests; if
nothing is listening it reports that check as skipped rather than passing it.

## One difference from the scripts that produced the reported numbers

`ROOT` used to be hard-wired to the layout the study ran in, two directories
above the script. Both entry points now honour `COMPARISON_ROOT` and fall back to
the old behaviour when it is unset. That is the only edit; the estimators, the
exclusion rule and the checks are byte-for-byte what produced the reported
numbers.
