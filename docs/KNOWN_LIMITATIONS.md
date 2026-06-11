# YourGov — Known Limitations

_Updated: 2026-05-31_

Honest list of things that are imperfect on the live deploy. Listed in
descending severity so a presenter can decide what to demo around. Each
entry has a **workaround** so the demo path still lands.

---

## 1. Wedge map-mode repaint silent on live Vercel build (P0 for demo)

**Symptom**: clicking the Vote / Party / Gender / Rebel wedges on
https://mygov-hackathon.vercel.app/source-lens updates the active wedge,
updates the bottom legend strip, fires the correct
`/api/lens/map/{party|gender|rebel-rate}` fetch, AND calls
`mapFrame.contentWindow.postMessage({type:'mygov:map:setMode', mode, data})`
— but the **map iframe never visually repaints**. Sampling SVG `<path>`
fills inside the iframe shows the bundle stuck in its idle "demo score"
state (top fills: `#ff4fd8`, `#ad7fe4`, `#01def8` — these are the
React-bundle demo overlay, not party/vote/gender colours).

**Confirmed working locally** at `127.0.0.1:5050` with the same code:
4 distinct fingerprints across 4 wedges; tens of Labour-red /
Conservative-blue paths after a Party click.

**Likely cause**: the iframe's `mygov:map:ready` postMessage races the
parent's `addEventListener('message', ...)` attachment. On Vercel's
cold-start CDN the iframe responds before the parent listener is
mounted, `mapReady` stays `false`, and the parent's `sendMapColours`
queues the payload to a pending var that's only flushed on a `:ready`
message that never arrives. Manual call into
`iframe.contentWindow.mygovConstituencyMap.setConstituencyColours(...)`
also had 0 effect on live — suggesting the iframe surface on the
Vercel build is a different React mode entirely (the promap bundle has
a Three.js globe path + a Leaflet path; the Vercel build may be
running the globe path while local serves Leaflet).

**Workaround for demo**:
- Click a **division row in the source pane** (left), then click a
  wedge. The first-click visualise path paints the map; subsequent
  wedge clicks re-skin it.
- If even that fails, **switch theme** and back — re-mounting can
  re-resolve the iframe wiring.
- Worst case, talk through what each wedge would show; the legend
  strip changes correctly and tells the right story.

**Fix path** (post-submission): bind the parent's message listener
**before** the iframe `src` is set, and have the parent fire its own
"are you ready?" probe message every 250ms until the iframe responds.

---

## 2. Vercel Web Analytics 404 in console (cosmetic)

**Symptom**: every page load shows
`GET /_vercel/insights/script.js 404`
in the browser console.

**Cause**: my `app.py` injects the Vercel Analytics snippet on every
HTML response when `VERCEL=1` is present in env. The snippet expects
the Analytics edge handler, which is only mounted after Analytics is
enabled in the Vercel dashboard. It's currently off.

**Workaround**: ignore — the 404 doesn't affect any user-facing
behaviour. To silence it, either enable Web Analytics in Vercel
Settings or set `ANALYTICS_DISABLED=1` in the project env vars.

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
not set in the Vercel project env.

**Behaviour**: the fallback envelope is **safe by design** — it
returns valid JSON with all 5 required keys (`clicked`, `meaning`,
`source_support`, `does_not_prove`, `followups`) so the drawer never
shows an error state to the user. Just less informative copy.

**Workaround for demo**: add `OPENAI_API_KEY` in Vercel
Settings → Environment Variables → Production, then redeploy. The fallback
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
| Map wedge **visual** repaint on Vercel | **Broken (#1)** | **Yes — work around per #1** |
| Map wedge payload contract | 4/4 pass | No |
| Rebel-rate visual variance | Uniform | Cosmetic |
| Globe auto-centre on IP | Not implemented | Cosmetic |
| Vercel analytics script | 404 console noise | Cosmetic |

**Net**: 1 P0 demo-flow blocker (item 1), 4 cosmetic items. Demo path
still lands if presenters click a source row before each wedge demo.
