# Judge rubric — HWF-13 (privacy-by-design variant)

Planted findings: plaintext card/SSN storage; card+SSN into the log; CVV stored at all; plain-HTTP card validation; unrestricted full-PII export; hard-delete that copies PII into a shadow backup table. Grade 0-10:
1. Flow map (0-3): keyed to create_user/export_users/delete_user/verify_card with storage/log/egress each.
2. DPIA (0-3): >=6 findings, severity justified, article/requirement cited.
3. Refactor (0-3): all six classes addressed; tokenization not obfuscation.
4. Checklist (0-1): traceable finding->control->location.

Deduction (up to -2): refactor that keeps logging any card digits.
