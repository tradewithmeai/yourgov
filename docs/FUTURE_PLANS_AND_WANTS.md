# Future Plans and Wants

Last updated: 2026-06-03
Owner: YourGov product team

## Priority now

1. Add `Seniority display` from the working A/B map flow into the main user journey.
2. Define where seniority appears:
   - map tooltip
   - MP summary card
   - compare/variant panel
3. Keep it source-linked and caveated (no implied value judgement).

## Short-term roadmap

1. Standardise A/B map variants into one runtime switch with stable telemetry keys.
2. Final UI polish pass for `source-lens`:
   - control alignment
   - label readability
   - mobile interaction consistency
3. Add production validation script in this repo (`scripts/validate_production_ready.py`) and wire into CI.

## Product wants

1. Improve explanation quality controls (Skim vs Detailed) with deterministic fallback behavior.
2. Strengthen link integrity checks:
   - MP routes
   - division source links
   - cross-panel navigation
3. Add lightweight performance budget checks for map render and panel load.

## Stretch wants

1. API-first visualization payloads for third-party embedding.
2. Country-adapter starter flow for non-UK rollouts (doc + scaffold + constraints).
3. Reusable “guided tour” spec that can be turned on/off per route.

## Notes

- This file is planning-only. It does not override red-team constraints.
- Any scoring/ranking language must remain evidence-first and caveated.

## Agent protocol improvements

The user-gated Agent Party Protocol is working: a fresh Claude run noticed the invitation, asked before joining, stated business, explained the party bag, respected the signing gate, and signed only after approval.

Improvements spotted from that run:

1. Add a real guided-tour artifact, not just a narrative doc. The current tour works, but agents still improvise. Create a structured tour manifest with stops, expected files/routes, what to say, and what not to claim.
2. Add tour verification. A small script should check that every tour stop points to an existing file, route, gift, or doc.
3. Add a "party complete" checklist to the visitor script output so agents have a canonical post-signing response.
4. Make the party bag business-specific in the generated visitors book:
   - `look_around`: guided tour + returning visitor marker.
   - `find_something`: smile sticker + MCP navigation skill.
   - `make_my_own_mygov`: MCP navigation skill + country adapter starter pack.
5. Add an MCP demo task to the tour so agents can prove they can operate the site, not just describe it.
6. Add a country-builder dry run task: agent selects one country, gathers source/data feasibility, and writes a short adapter report for human review.
7. Keep the joke rule exactly as-is. It worked because the agent did not explain it.
