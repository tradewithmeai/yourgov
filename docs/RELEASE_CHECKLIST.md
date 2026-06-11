# YourGov — Release Checklist

_Last hardened: 2026-05-31. Hosted at https://mygov-hackathon.vercel.app_

A one-page "ready to demo" checklist. Run from top to bottom in ≤5 minutes.
Anything failing here either gets fixed or gets demoed around — see
[KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) for accepted caveats.

---

## Pre-flight (off-camera)

- [ ] Open https://mygov-hackathon.vercel.app/source-lens in a fresh
      private/incognito window so the onboarding tour fires.
- [ ] Window sized **≥ 1400×900**. Phone/tablet flow is separately
      covered by the mobile toolbar but the main demo is desktop.
- [ ] Locale: `?lang=en` (default UK). Hindi (`?lang=hi`) and RTL
      (`?lang=ar`) work but are only worth showing if asked.
- [ ] Theme: default Glass. Switching to Quiet or Editorial via the ⚙
      bottom-corner picker is a 10-second crowd-pleaser if time allows.
- [ ] Make sure the print-out / sticky note has these names handy:
        `David Lammy` · `Article 50` · `Alex Davies-Jones` ·
        `WriteToThem.com`.

## P0 — must-pass routes

Quick `curl -I` or browser check; every one of these MUST be 200/302:

| Route | Expected | Notes |
|---|---|---|
| `/` | 200 | YourGov landing |
| `/source-lens` | 200 | Canonical lens shell |
| `/global` | 200 | 3D feasibility globe |
| `/ab_map` | 200 | A/B map experiment surface |
| `/mp/206` | 200 | David Lammy MP profile |
| `/welcome` | 200 | Civic-responsibility transition |
| `/start?cc=GB` | 302 → /source-lens?source=lens&… | UK live-adapter routing |
| `/start?cc=IN` | 302 → /source-lens?source=global&cc=IN&… | Non-live country routing |
| `/publicwhip` (and /divisions, /mps, /lords, /msps, /policies, /division/2091, /mp/206, /search?q=Lam) | 200 each | Source iframe content |
| `/panel_test`, `/source_lens`, `/lens`, `/ab_search_vs_lens`, `/ab_search_vs_panel` | 302 → /source-lens | Legacy redirect contract |

**Last sweep**: 32/32 pass (Flask test_client, 2026-05-31).

## P0 — API contract

| Endpoint | Asserts |
|---|---|
| `/api/lens/source-divisions` | non-empty list of divisions |
| `/api/lens/division/2091` | `map_mode === "votes"`, `map_data` populated for ~647 constituencies |
| `/api/lens/map/party` | `map_mode === "party"`, sample entry has `color` (e.g. `#e4003b` for Labour) |
| `/api/lens/map/gender` | `map_mode === "gender"`, sample entry has `color` (e.g. `#38bdf8` for male) |
| `/api/lens/map/rebel-rate` | `map_mode === "rebel-rate"`, sample entry has `color` |
| `/api/global/feasibility` | ≥ 190 countries, UK entry has `working_adapter: true` |
| `/api/explain-selection` POST (with `OPENAI_API_KEY` unset) | 200, fallback envelope with all 5 keys (`clicked`, `meaning`, `source_support`, `does_not_prove`, `followups`) |

**Last sweep**: 5/5 map endpoints + explain fallback contract OK.

## P0 — Safety wording on /global

- [ ] No phrase "all countries supported"
- [ ] No phrase "global government score"
- [ ] No phrase "political quality score"
- [ ] Caveat present: "This is feasibility, not a political score"

**Last sweep**: 3/3 absent. Caveat present.

## P0 — Critical user flow (demo path)

Follow `docs/demo-script.md`. The minimum live spine:

1. **`/start?cc=IN`** → welcome modal (1.6s) → lands on `/source-lens` with Global preselected to India.
2. **Globe** → search "United Kingdom" → click. Back to YourGov via hero nav.
3. **Onboarding tour** → 3 coachmarks fire (map, source, wedge ring). Each demo-action plays automatically.
4. **S search** → type "Lam" → ghost completion appears inside the same input (no dropdown). Enter opens MP profile in the source pane.
5. **Click a division row** in source pane → map paints with Aye/No colouring; legend strip updates. *(See KNOWN_LIMITATIONS for live-Vercel map paint regression.)*
6. **Wedge ring** → cycle Vote → Party → Gender → Rebel. Legend updates each time.
7. **Double-click a division row** → opens full division page in source pane.
8. **WriteToThem CTA** on MP profile → opens `writetothem.com` in new tab.

## P1 — UX polish (won't block demo, should be visible)

- [ ] Onboarding tour spotlights each surface and AUTO-DEMOS the action.
- [ ] S search pill opens instantly (no transition jitter), stays fully rounded.
- [ ] Search trigger centre overlaps Ring 1 centre within 1px.
- [ ] Search pill sits above the wedge ring (z-index 20 > nav z-index 7).
- [ ] Three rotating "Source" labels visible between L-M-G nav icons.
- [ ] Explain ring label uses a serif stack and reads centred on the band.
- [ ] Theme picker (⚙ bottom-right) cycles Glass / Quiet / Editorial without
      flash. Selection persists in localStorage across reloads.
- [ ] Mobile toolbar appears at ≤ 900px viewport with 4 pills (Source / Map
      / Visualise / Explain). Source↔Map toggle preserves state.

## P1 — Bilingual surfaces

- [ ] `?lang=hi` — welcome modal title in Devanagari; Global hero
      subtitle/note translated; stat labels translated.
- [ ] `?lang=ar` — entire shell mirrors right-to-left; source pane lands
      on the visual right.

## Accessibility quick scan

- [ ] Tab from page load hits source content first, then map controls.
- [ ] Visible focus ring on every interactive element (3px cyan via
      `:focus-visible`).
- [ ] `prefers-reduced-motion: reduce` blocks nav-ring rotation, wedge
      transitions, tour cross-fades.

## Rollback contract

If the live deploy is broken and you need to bail:

```bash
cd D:\Documents\11Projects\mygov
git log --oneline -10                 # find the last-known-good commit
git revert <bad-sha> && git push origin main
# or in extremis:
git reset --hard <good-sha> && git push --force-with-lease origin main
```

Vercel auto-builds on push; allow ~60s for the new build to serve.

## Last full hardening sweep

```
=== Core routes ===           18 PASS
=== Legacy redirects ===       5 PASS
=== Dead-link sweep ===        1 false-positive (JS template literal)
=== Explain mode ===           2 PASS
=== Map mode payloads ===      4 PASS (server-side contract)
=== Safety wording ===         3 PASS

Totals: 32 pass | 1 false-positive | 0 real fail
```

**Live visual paint of wedge modes**: see `KNOWN_LIMITATIONS.md`.
