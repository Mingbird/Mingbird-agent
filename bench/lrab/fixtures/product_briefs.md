# Competitive Brief: Three Lab-Information Management Products (wf11 fixture)

## Product A — LabVault
- Positioning: enterprise LIMS (lab information management system)
- Pricing: $45/user/month, annual contract only
- Strengths: audit trail, 21 CFR Part 11 compliance, SSO
- Weaknesses: no offline mode; 6-week onboarding; vendor lock-in for data export
- Platform: web only (Chrome/Firefox), no desktop app
- Integration: REST API (documented), no MCP

## Product B — SampleTracker Pro
- Positioning: lightweight sample tracking for academic labs
- Pricing: free for academic use, $12/user/month commercial
- Strengths: 10-minute setup, QR-code sample labels, offline-first (local SQLite)
- Weaknesses: no compliance features, single-user only, no API
- Platform: Windows/Mac desktop
- Integration: CSV import/export only

## Product C — OpenLabChain
- Positioning: open-source, self-hosted collaboration platform
- Pricing: free (AGPL), paid hosting from $99/month
- Strengths: extensible plugin system, MCP tool support, active community (4.2k stars)
- Weaknesses: requires Docker administration, documentation gaps, mobile UI rough
- Platform: self-hosted web + desktop client
- Integration: REST + MCP + webhooks

## Market context
Mid-size materials research group (8-15 researchers) evaluating options for
sample tracking + experiment documentation + tool integration. Group has mixed
Windows/Linux desktops, intermittent network in lab areas, and one member with
compliance requirements (funded pilot plant).
