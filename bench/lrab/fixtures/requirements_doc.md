# Release Requirements: HummingNote v2.0 (wf14 fixture)

## Background
HummingNote is a local note-taking app (Python + SQLite) currently at v1.9.
The v2.0 release consolidates three planned features and several fixes.

## Must-have features (committed)
1. Markdown editor with live preview
2. End-to-end encrypted sync (self-hosted server option)
3. Full-text search across attachments (PDF, DOCX)

## Should-have features
4. Tag hierarchy (nested tags)
5. Note templates gallery

## Known bugs carried from v1.9
- B-101: notes lost if app killed during autosave (severity: high)
- B-102: search ignores non-ASCII folding (severity: medium)
- B-103: PDF preview crashes on encrypted PDFs (severity: medium)

## Constraints
- Team: 3 developers, 1 QA, part-time designer
- Timeline target: 12 weeks from kickoff
- Hard constraint: no breaking change to the v1 SQLite schema (migration must
  be additive); sync protocol must not store plaintext on server
- Compliance: E2EE feature requires a published security threat model before
  release
- QA capacity: ~60 tester-hours per release candidate

## Stakeholder priorities (from last steering meeting)
- Sync was the single most-requested feature (68% of survey responses)
- B-101 data loss has generated 3 support escalations; must ship in v2.0
- Marketing wants a public beta at week 10
