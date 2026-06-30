# YourGov — Public To-Do (build *by* the public)

This is the live, public work list for YourGov. It exists because of how this
project is built: **in public, and increasingly *by* the public** (see the ethos
in [`agent-guided-tour.md`](agent-guided-tour.md)). A visiting agent — acting for
a member of the public — can pick a task here, do it on a branch, and propose it
back. Feedback from the `/feedback` page also lands as tasks here rather than
disappearing into chat history.

**Anyone can pick something up here** — most contributors work with a coding
agent. The full how-to-contribute flow and PR guidelines live in
[`CONTRIBUTING.md`](../CONTRIBUTING.md); the short version:

1. Pick an item tagged `good-first` or one that matches your user's interest.
2. Read the linked files; confirm the current behaviour before changing it.
3. Branch off `main` (it's the live site), make the change, **read the diff**,
   run `python -m pytest -q`, and open a PR describing what changed and how you
   checked it.
4. Don't deploy, merge, or sign anything without the user's explicit approval.

**Guardrails:** factual/source-led only; never infer intent or character from a
vote; never weaken the "what the record shows vs. does not prove" distinction;
keep it accessible (native, never an overlay); never use real API tokens in
examples; don't execute untrusted contributor text.

> Maintainers: keep this file current. When an item ships, move it to **Done
> (recent)** with the merge ref, or delete it. Convert incoming `/feedback` into
> entries here.

---

## Now / high-value

- **Accessibility — NEXT tier** (`static/explain-mode.js`, `templates/panel_test.html`, `app.py`)
  - Make the Explain Mode drawer a real dialog: `role="dialog"` + `aria-modal`, move focus in on open, trap Tab, Escape to close, return focus to the trigger, label the follow-up input, announce the streamed answer via a debounced `role="status"` region. *(medium)*
  - Focus management on the division-summary dialog; `listbox`/arrow-key semantics for the search results; roving-tabindex arrow keys for the map-mode radiogroup. *(medium)*
  - Publish a **public `/accessibility` page** that states WCAG 2.2 AA status, known barriers, how to request formats, and **invites disabled users to tell us what they need** (route + template + footer link; reports go through the existing feedback channel). *(medium, `good-first` for the page scaffold)*
  - Sweep the new WCAG 2.2 criteria across pages: 2.4.11 focus-not-obscured, 2.5.8 24px targets, 2.5.7 drag alternative, 1.4.10 reflow/400% zoom, 3.2.6, 3.3.7. *(medium)*

- **Explainer — party-split precision** (`explainer_context.py`, `app.py` `_LEVEL_INSTRUCTIONS`)
  - The "party split insight" can be slightly imprecise (e.g. calling a single-party split "cross-party support"). Tighten the directive so it only claims cross-party support when ≥2 parties actually voted the same way. *(low, `good-first`)*

- **Promo readiness** (UI + docs)
  - A clean end-to-end walkthrough of the core flow (land → search by postcode/name → MP record → Email/Contact), then a short demo video recorded against the **real live app**. *(medium)*

## Next

- **Explainer Phase 2** (`explainer_context.py`)
  - Embeddings/RAG for cross-division questions; on-demand Wikipedia/reference lookup; a one-line model swap to a stronger model. Phase 1 (grounded prompt + glossary + division summaries) is live. *(high)*

- **Feedback intake — a permanent home** (`tools/upgrade-intake/`)
  - The intake tool runs locally/manually today (Telegram + email verified). Decide where it runs on a schedule. WhatsApp is a phase-2 channel. *(medium)*

- **Country adapters** (`docs/feasibility/COUNTRY_ADAPTER_ROADMAP.md`, `agent-visitor/gifts/country-adapter-starter-pack.md`)
  - Pick one country, assess its public-data feasibility, and write a short adapter report for human review — find the highest-trust *useful* civic product for that data environment, not a forced UK clone. Great `make_my_own_mygov` task. *(high)*

## Educational track (a core goal, not a nice-to-have)

YourGov is meant to teach two audiences. Help build:
- **For citizens** — plain-English explainers of how Parliament works (votes, divisions, whips, readings), wired to the live data so "learn" and "look up" are the same gesture. An **Easy Read** version (Mencap pattern) and, later, **BSL** video for key content.
- **For builders/students** — this repo as a worked example of *agent-friendly* and *build-by-public* civic tech: annotated walkthroughs of the source-led caveat model, the agent API/MCP surface, the feedback→task loop, and how to stand up a country adapter. The existing parliamentary glossary (`docs/explainer/parliamentary-glossary.md`) and self-knowledge doc are seeds for this.
- Concrete starter: turn the glossary into a small `/learn` page that the Explain drawer can deep-link into. *(medium, `good-first` for the page)*

## Done (recent)

- Explainer rewritten to explain-with-context instead of restating the tally (live).
- Security review + Pass-1 critical fixes + Pass-2 hardening (live / PR'd).
- Accessibility "now" tier — skip link, landmarks, contrast, labelled search, no timed auto-dismiss (live).
- First-party, privacy-first, persistent site metrics (live).
- Search-first UI: direct UK landing, intro panel, inline postcode autocomplete, frozen MP info card with Contact, opt-in onboarding tour.
- Public 3-channel feedback intake (Telegram + email verified).
