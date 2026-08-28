# Ti-6Al-4V Aging Dataset Analysis Plan

## Step 1: Read CSV and compute descriptive statistics for UTS and elongation (count, mean, min, max) → descriptive_stats.md

## Step 2: Identify peak UTS condition (550C/4h = 1105 MPa), note 620C/4h anomaly (UTS drops from 1105 to 1063 MPa despite higher temperature), flag monotonicity issue → anomalies.md

## Step 3: Write analysis.py that loads CSV, plots UTS vs temperature and elongation vs temperature with labeled axes, units, title; saves fig_strength.png and fig_elongation.png; prints peak/valley conditions to stdout

## Step 4: Run analysis.py and verify both PNG files exist and are non-trivial (>20KB)

## Step 5: Write analysis.md (300-500 words): trend description, strength-ductility trade-off, 620C anomaly discussion (measurement error vs real effect), actionable recommendation with at least 3 concrete numbers from data

## Step 6: Verify all artifacts (list files with sizes) and complete analysis
