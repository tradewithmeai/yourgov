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

1. [DONE 2026-06-30] Real guided-tour artifact, not just a narrative doc: structured manifest `docs/agent-tour-manifest.json` with stops, files/routes, what to say, what not to claim — `docs/agent-guided-tour.md` rewritten as an active walkthrough.
2. [DONE 2026-06-30] Tour verification: `scripts/verify_agent_tour.py` checks every stop points to a real file/dir/script/route; locked by `tests/test_agent_tour.py`.
3. Add a "party complete" checklist to the visitor script output so agents have a canonical post-signing response. *(still open)*
4. Make the party bag business-specific in the generated visitors book:
   - `look_around`: guided tour + returning visitor marker.
   - `find_something`: smile sticker + MCP navigation skill.
   - `make_my_own_yourgov`: MCP navigation skill + country adapter starter pack. *(still open)*
5. [DONE 2026-06-30] MCP demo task in the tour (Stop 4 "Operate it — prove it, don't just describe it") so agents prove they can run the site, not just describe it.
6. [DONE 2026-06-30] Country-builder dry-run task added (tour Stop 7 + `docs/AGENT_TODO.md` country-adapters item).
7. Keep the joke rule exactly as-is. It worked because the agent did not explain it. *(unchanged — preserved)*

Also new (2026-06-30): `CONTRIBUTING.md` — a "built by anyone" PR guide for people working through coding agents, plus `docs/AGENT_TODO.md` as the public live work list (feedback becomes tracked tasks here). Items 3 and 4 remain for the visitor script.
