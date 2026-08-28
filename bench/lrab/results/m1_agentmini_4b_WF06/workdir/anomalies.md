# Anomaly Detection in Ti-6Al-4V Aging Data

## Peak UTS Condition Analysis

The peak UTS (Ultimate Tensile Strength) of 1105 MPa occurs at **550°C for 4 hours** (row H550A).

## Temperature vs UTS Monotonicity Check

Examining the UTS values across temperatures at fixed aging time (4h):
- 480°C: 1012 MPa
- 500°C: 1045 MPa
- 520°C: 1080 MPa
- **550°C: 1105 MPa (peak)**
- 580°C: 1088 MPa ← ANOMALY
- 600°C: 1040 MPa
- 620°C: 1063 MPa ← ANOMALY

## Flagged Anomalies

**Anomaly 1: Non-monotonic behavior at 580°C**
The UTS drops from 1105 MPa (550°C) to 1088 MPa (580°C), then rises again to 1063 MPa (620°C). This violates the expected monotonic decrease after peak.

**Anomaly 2: The 620°C/4h row (H620A)**
At 620°C with only 4 hours aging, UTS is 1063 MPa — higher than at 600°C (1040 MPa) despite the higher temperature. This suggests either:
- Measurement error or data inconsistency
- A real physical effect where prolonged exposure near peak temperature allows partial recovery

The expected trend after peak should be monotonic decrease, but we observe an increase from 600°C to 620°C.
