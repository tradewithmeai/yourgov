# YourGov — Known Limitations

_Updated: 2026-06-16 (Vercel retired; live host is Krystal / yourgov.solvx.uk)_

Honest list of things that are imperfect on the live deploy. Listed in
descending severity so a presenter can decide what to demo around. Each
entry has a **workaround** so the demo path still lands.

---

## 1. ~~Wedge map-mode repaint silent on live build~~ (RESOLVED on Krystal)

**Resolved.** This was a build-environment-specific regression on the old
Vercel deploy: the map iframe never visually repainted on wedge changes
because the `mygov:map:ready` postMessage raced the parent's listener
attachment. On the live Krystal deploy the relay handles all `*-split`
modes through the bundle's 'votes' channel behind an `applied` gate, and
division clicks / wedge changes paint the map correctly — verified live
(two division clicks → two full repaints of 650 constituencies). See
`templates/map_relay.html` and `tests/test_map_relay_contract.py`.

---

## 2. ~~Web Analytics 404 in console~~ (RESOLVED — Vercel retired)

**Resolved.** The old Vercel Web Analytics snippet (which produced a
`GET /_vercel/insights/script.js 404` on every page load) was injected by
an `app.py` `after_request` hook. With Vercel retired in favour of Krystal,
that hook and its snippet have been removed from `app.py` entirely, so the
404 no longer occurs.

---

## 3. Onboarding tour can intercept the first click in a session

**Symptom**: first visit lands on the tour overlay. Tab/Esc dismisses,
but the tour also fires the "demonstrate the suggestion" auto-action
on each step — so during the 3 steps the map mode and source iframe
both move under the user's feet.

**Workaround**: let the tour run (it's ~10s end-to-end), or click Skip.
The "Replay tour" item in the theme picker re-runs it on demand.

---

## 4. Rebel-rate map mode looks visually uniform

**Symptom**: clicking the Rebel wedge paints every constituency the
same dark-slate `#334155`.

**Cause**: the seed `mygov.db` shipped with the production repo only
has aggregated vote counts, not rebellion data — every MP comes back at
0% rebellion against party majority. The colouring rule is "low rebel
= darker slate" so 100% of constituencies fall into the same bucket.

**Workaround**: don't dwell on Rebel mode during the demo. Mention it
as the fourth dimension YourGov can surface and move on to the Vote /
Party / Gender modes that have visible variance.

**Fix path**: re-ingest with the rebellion-detection script from the
hackathon repo's `ingest.py` (~10 min) and ship a new `mygov.db`.

---

## 5. Globe initial view is not auto-centred on user's geo

**Symptom**: `/global` always loads with the same default rotation /
zoom. The user's IP-derived country preselect *card* updates (text
panel on the right of the globe), but the 3D globe itself doesn't
rotate to centre on their country.

**Cause**: a previous task asked for IP-based globe-view auto-rotation
but the implementation didn't land before the deploy lock-in.

**Workaround**: drag the globe with the mouse to rotate; type the
country name into the search box on the globe panel to focus.

**Fix path**: in `static/global_globe.js`, in `start()`, call
`focusCountryOnGlobe(initial)` (already implemented — already called)
plus a slightly less aggressive zoom-out so the whole disc is visible
at first paint.

---

## 6. Production repo has no `tests/` directory

**Symptom**: `pytest` in `D:\Documents\11Projects\mygov` finds nothing.

**Cause**: the production repo is a trimmed package — tests, the
`validation/` framework, and the agent-logs scaffolding live in the
hackathon repo. Production deployment validation goes through the
top-of-file smoke script in `RELEASE_CHECKLIST.md` instead.

**Workaround**: copy `tests/` from `D:\Documents\11Projects\mygov-hackathon`
if you want to run the full pytest suite (62 tests, ~10s) against the
production app.

---

## 7. `/api/explain-selection` requires `OPENAI_API_KEY` for live AI

**Symptom**: clicking explainable elements with Explain Mode on opens
the drawer but renders a fallback explanation if `OPENAI_API_KEY` is
not set in the live environment.

**Behaviour**: the fallback envelope is **safe by design** — it
returns valid JSON with all 5 required keys (`clicked`, `meaning`,
`source_support`, `does_not_prove`, `followups`) so the drawer never
shows an error state to the user. Just less informative copy.

**Workaround for demo**: set `OPENAI_API_KEY` in the Krystal environment
(cPanel env vars or `passenger_wsgi.py`), then restart the app. The fallback
otherwise reads as "AI explainer unavailable, here are the supporting
records".

---

## 8. Iframe sandbox warnings in console

**Symptom**:
`An iframe which has both allow-scripts and allow-same-origin for its
sandbox attribute can escape its sandboxing.`

**Cause**: by design — the source pane (`/publicwhip`) and map iframe
(`/map/relay`) both need `allow-scripts allow-same-origin` so the
parent can `postMessage` to them AND read their DOM for explain-mode
target injection. They're same-origin so the warning is moot for our
threat model.

**Workaround**: ignore.

---

## Acceptance contract

| Area | Live status | Demo blocker? |
|---|---|---|
| Routes (200/30x) | 32/32 pass | No |
| API contract | 7/7 pass | No |
| Explain fallback safety | Pass | No |
| Forbidden /global wording | 3/3 absent | No |
| Map wedge **visual** repaint | Resolved on Krystal (#1) | No |
| Map wedge payload contract | 4/4 pass | No |
| Rebel-rate visual variance | Uniform | Cosmetic |
| Globe auto-centre on IP | Not implemented | Cosmetic |
| Web analytics script | Removed with Vercel (#2) | No |

**Net**: the former P0 (item 1) is resolved on Krystal; remaining items
are cosmetic.
