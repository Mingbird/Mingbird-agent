# Judge rubric — HLH-01 (mean-aggregation variant)

Deterministic checks verify each batch_profile file contains its batch's true mean UTS and that means_check.json carries all eight. Ground truth (1 dp): B01=1057.7, B02=1047.2, B03=1039.9, B04=999.7, B05=1045.2, B06=988.4, B07=1052.3, B08=1072.8.

Mean ranking: B08 > B01 > B07 > B02 > B05 > B03 > B04 > B06. Widest spread: B08 at 436.0 MPa; narrowest: B06. Grade the rest 0-10:

1. Ranking correctness (0-4): exact mean order; the B02/B05 near-tie (1047.2 vs 1045.2) separates real computation from guessing.
2. Spread analysis (0-2): widest batch named with value and a plausible process reading of high spread.
3. Mean-vs-peak insight (0-2): notes where the mean ranking disagrees with a peak-based ranking and why that matters for specification limits.
4. next_steps substance (0-2): concrete corrections/confirmations per file.

Deduction (up to -2): means in the JSON inconsistent with the profile files.
