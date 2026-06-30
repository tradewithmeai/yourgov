# YourGov — Architecture

A map of the moving parts, written for two readers: a coding agent that needs to
find the right file fast, and an inquisitive newcomer who wants to understand how
the whole thing fits together before changing anything.

YourGov shows people **what the UK public record actually says** about their MP —
how they voted, what they asked, and what a vote does and does *not* prove. It is
built [in public and by the public](CONTRIBUTING.md); this document is part of
keeping it understandable enough that anyone can pick it up.

> New here? Read this top-to-bottom once, then let your agent take the
> [guided tour](docs/agent-guided-tour.md) for the hands-on version.

---

## The one-paragraph version

Parliament's open APIs are pulled into a **SQLite snapshot** (`yourgov.db`). A
**Flask app** (`app.py`) serves that data three ways: as **HTML pages** people
read, as a **JSON data API** the interactive map calls, and as a **token-gated
agent control API** (`/api/agent/*`) for programmatic use. An **LLM explainer**
turns a raw division into plain English, grounded by `explainer_context.py` so it
explains rather than spins. The site is **stateless per request** — there are no
user accounts and no per-user tracking; the only writable state is the seed DB
(refreshed by a scheduled job) and rolling, anonymous metrics counters.

```
Parliament APIs ──▶ parliament_client.py ──▶ db.py ──▶ yourgov.db (SQLite snapshot)
                                                            │
                                                            ▼
                                                         app.py ──┬──▶ HTML pages (Jinja templates/)
                                                            │      ├──▶ /api/lens/*  data API ──▶ static/panel_test.js (the map)
                                                            │      ├──▶ /api/agent/* control API (token-gated)
                                                            │      └──▶ /api/explain-* ──▶ explainer_context.py ──▶ LLM
```

---

## The subsystems

### 1. Ingest — `parliament_client.py`
Best-effort HTTP client for the public Parliament APIs (members, votes,
divisions, written questions). Network calls are wrapped so a flaky upstream
degrades gracefully rather than crashing a page. This is the *only* code that
talks to Parliament directly.

### 2. Storage — `db.py` + `yourgov.db`
A read-mostly **SQLite snapshot**, not a live database. It ships **gzipped**
(`yourgov.db.gz`, ~31 MB; the raw file is ~280 MB and over GitHub's limit) and is
decompressed on first use to a writable path — `/tmp` on the read-only live host
(see `_ensure_seed_db` in `app.py`). `db.py` owns the schema, the migrations
(run once per process), and the `upsert_*` flattening from API JSON into rows.

Two connection helpers, both with always-closing context managers in `app.py`:
- `db_conn()` → read-write working DB (members, votes, questions; runs migrations).
- `pw_conn()` → the read-only PublicWhip-family seed used by `/publicwhip/*`.

The snapshot is rebuilt by a **scheduled data-refresh job**, not on the request
path — so a page load never waits on Parliament.

### 3. Web app — `app.py`
The hub (~3,500 lines). Major route groups:

| Group | Examples | What it serves |
|---|---|---|
| **Pages** | `/`, `/start`, `/mp/<id>`, `/source-lens`, `/accessibility` | Jinja-rendered HTML people read |
| **Search / lookup** | `/api/mps/search`, `/api/postcode`, `/api/postcode/autocomplete` | postcode → constituency → MP |
| **Map data API** | `/api/lens/map/party`, `/api/lens/map/gender`, `/api/lens/map/rebel-rate`, `/api/lens/division/<id>/map` | JSON the map JS colours constituencies from |
| **PublicWhip** | `/publicwhip`, `/publicwhip/division/<id>`, `/publicwhip/mp/<id>` | division-level vote browsing |
| **Explainer** | `/api/explain-vote`, `/api/explain-selection` | plain-English vote explanations (see §5) |
| **Agent control API** | `/api/agent/*` | token-gated programmatic surface (see §6) |
| **Metrics** | `/api/telemetry`, `/admin/metrics` | first-party privacy-first counters (see §7) |

Templates are in `templates/` (Jinja autoescaping on — user/data values are
escaped by default). Front-end JS/CSS is vanilla, in `static/`.

### 4. The map — `static/panel_test.js` + `templates/map_relay.html` + `static/promap/`
The constituency map is a **prebuilt React bundle** (`static/promap/`, minified;
its source lives in a separate promap project) hosted inside a **sandboxed
iframe** (`templates/map_relay.html`). The parent page and the iframe talk over a
small `postMessage` protocol (`yourgov:map:setMode` / `ping` / `ready` /
`applied`); the bundle dispatches a `CustomEvent("mygov:constituency:selected")`
that the relay still listens for — that `mygov:` event name is part of the
prebuilt bundle's contract and **must not be renamed** without rebuilding the
bundle. `panel_test.js` documents the full protocol at the top.

### 5. The explainer — `explainer_context.py`
Assembles a **grounded** prompt for the LLM "Explain" feature: it translates the
division title via a glossary, gives real context (structured division summaries,
party majorities, glossary terms), and constrains the model to *meaning /
does-not-prove / follow-ups* rather than restating the tally. This file is the
**single source of truth** for the party-majority / "who rebelled" logic
(`party_majorities()`, `is_whipped_party()`, `PARTY_MAJORITY_THRESHOLD`); both the
map and the explainer call it so they can never disagree. Falls back to a safe
non-LLM summary when no model key is configured.

### 6. Agent control API — `/api/agent/*`
A read-oriented, **token-gated** surface for operating YourGov programmatically
(health, routes, divisions, MP lookup, search, map payload, deeplinks, explain).
Designed so an agent never has to scrape the HTML. An **MCP server**
(`agent-mcp/server.py`) wraps it; the navigation skill in `agent-visitor/gifts/`
teaches an agent to drive it.

### 7. Metrics — `/api/telemetry` + `/admin/metrics`
First-party, **privacy-first**: a tiny beacon increments anonymous funnel
counters (pageview → search → mp_view → contact_click). No cookies, no per-user
identifiers. The `/admin/metrics` view is gated by `MYGOV_METRICS_TOKEN`
(constant-time check, fails closed to a 404 when unset).

### 8. Agent-friendliness — `AGENTS.md`, `docs/`, `agent-visitor/`, `agent-mcp/`
The repo explains itself: the [guided tour](docs/agent-guided-tour.md) (verifiable
via `scripts/verify_agent_tour.py`), the [agent protocol](docs/agent-protocol.md),
the [ethics guardrails](docs/ETHICS_GUARDRAILS.md), and the visitor "party"
(`AGENTS.md`). This is deliberate: the easier the repo is for an agent to
understand, the easier it is for a member of the public *using* an agent to
contribute. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Request lifecycle (an MP profile)

1. Visitor hits `/mp/<member_id>`.
2. `mp_profile` opens one `db_conn()` and reads the member row.
3. If the MP isn't in the snapshot yet, `_auto_ingest()` pulls them from
   Parliament (its own write connection), then the profile re-reads.
4. Votes, questions and counts are read on the same connection; it closes once.
5. Coverage + issue spotlight are computed in Python and the page is rendered.

No request mutates shared state beyond the (idempotent) auto-ingest and the
anonymous metrics counter.

---

## Deployment (the short version)

`main` is **live**. A plain code push does **not** auto-deploy — shipping happens
via the data-refresh dispatch or a solvx-website deploy run, which bundles a
**hand-maintained file list** (not the whole repo) and FTPS-uploads it to Krystal
(cPanel / LiteSpeed-Passenger). So: any new top-level module `app.py` imports must
be added to that deploy bundle, or the next deploy crashes live. Full detail in
[`docs/KRYSTAL_DEPLOY.md`](docs/KRYSTAL_DEPLOY.md) and [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Conventions worth knowing before you change anything

- **Source-led only.** Show what the record says; never infer intent or character
  from a vote, and never weaken the *shows / supports / does-not-prove* distinction.
- **Accessibility is native.** Keyboard-operable, labelled, legible — never an
  overlay/"accessibility widget". See the `/accessibility` page and the a11y notes.
- **Privacy by default.** No accounts, no per-user tracking, no analytics cookies.
- **Branch off `main`, read the diff, run `python -m pytest -q`.** `main` is the
  live site. The contributor finish line is a scoped PR, not a deploy.
- **One source of truth.** Shared logic (e.g. party majorities) lives in one
  helper that every caller uses — don't re-implement it inline.

## Where to look first

| You want to… | Start here |
|---|---|
| Understand the project end-to-end | this file, then [the guided tour](docs/agent-guided-tour.md) |
| Find a route or behaviour | the route table in §3, then `app.py` |
| Operate the site programmatically | [`AGENTS.md`](AGENTS.md) → `/api/agent/*` → `agent-mcp/` |
| Make your first change | [`CONTRIBUTING.md`](CONTRIBUTING.md) + [`docs/AGENT_TODO.md`](docs/AGENT_TODO.md) (`good-first`) |
| Understand the data | [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md), [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) |
| Deploy / release | [`docs/KRYSTAL_DEPLOY.md`](docs/KRYSTAL_DEPLOY.md), [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md) |
