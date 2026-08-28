# Experiment Description (wf15 fixture): Isothermal Aging Kinetics of Ti-6Al-4V

## Claimed procedure (as written in the paper under audit)

Specimens of Ti-6Al-4V (dimensions 10 x 10 x 5 mm) were isothermally aged in a
salt bath at 500C. Electrical resistivity was measured in situ using a
four-point probe with a DC current of 10 A. The onset time of alpha
precipitation t0 was determined by the tangent-intersection method on the
resistivity-time curve. Arrhenius analysis of 1/t0 versus 1/T across five
temperatures yielded an activation energy of 152 kJ/mol.

## Raw resistivity data (provided as raw_measurements.csv)

Columns: t_min (time), R_uOhm_cm (resistivity) for each of the five nominal
temperatures (500, 520, 540, 560, 580C), one series per column pair.

## Provided auxiliary data (from established literature, for verification)

- Matrix resistivity at 500C (solution treated, before precipitation):
  172.0 uOhm*cm
- Saturation resistivity change (fully aged): +6.5 uOhm*cm
- Expected tangent-intersection behavior: resistivity first decreases slightly
  (matrix relaxation), then rises as alpha precipitation depletes solute.

## Audit questions (the paper's numbers must be recomputed from raw data)

1. Does the raw data actually show the described two-stage behavior?
2. What onset times t0 does the tangent-intersection method give per series?
3. Does an Arrhenius fit of ln(1/t0) vs 1/T reproduce the claimed 152 kJ/mol?
4. Is the claimed five-temperature scope consistent with the provided raw data?
