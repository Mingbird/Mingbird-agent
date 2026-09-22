# Judge rubric — HWF-08 (query-half variant)

Grade 0-10:
1. Spec fidelity (0-3): pagination limit/offset, sensor/from/to filters, hourly min/max/avg semantics exactly as the requirements state them.
2. OpenAPI quality (0-3): 3.1 syntax that validates, complete parameter and schema definitions, Problem schema present.
3. Mock correctness (0-2): seeded store demonstrably returns correct pages and aggregates.
4. Demo (0-2): captured pairs including the rejection path.

Deduction (up to -2): aggregation that averages averages, or pagination that repeats rows.
