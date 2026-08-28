# Analysis Plan: Ti-6Al-4V Aging Dataset

## Step 1: Read CSV and compute descriptive statistics for UTS and elongation (count, mean, min, max) → descriptive_stats.md

## Step 2: Identify peak UTS condition (550C/4h = 1105 MPa). Check monotonicity of UTS vs temperature at 4h. Flag anomaly: 620C/4h has UTS=1063 MPa, which is higher than 600C/4h (1040 MPa) but lower than 580C/4h (1088 MPa). This breaks the expected monotonic decrease → anomalies.md

## Step 3: Write analysis.py to load CSV, plot UTS vs temperature and elongation vs temperature with labeled axes, units, and title. Save fig_strength.png and fig_elongation.png. Print peak/valley conditions.

## Step 4: Run analysis.py and verify both PNG files exist and are >20KB.

## Step 5: Write analysis.md (300-500 words) describing trends, strength-ductility trade-off, 620C anomaly discussion, and actionable recommendation. Include at least 3 concrete numbers from data.

## Step 6: Verify all artifacts exist with proper sizes.
