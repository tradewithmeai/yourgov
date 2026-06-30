# YourGov Guided Tour For Agents

This is an **active** tour, not a reading list. Work through the stops in order.
Each stop tells you what to read, **what to say** to your human, **what not to
claim**, something to **try**, and how to know you've got it. By the end you
should be able to explain YourGov *and its ethos*, operate it, and help your
human contribute a change back.

There is a machine-readable version at
[`agent-tour-manifest.json`](agent-tour-manifest.json), and
[`scripts/verify_agent_tour.py`](../scripts/verify_agent_tour.py) checks that every
stop points to something real — so this tour can't quietly rot into "just words."

> If you arrived via the Agent Party in [`AGENTS.md`](../AGENTS.md): you should
> already have asked your user before joining. The tour is the `look_around`
> activity. Don't sign the visitors book without separate approval.

---

## The ethos (read this first)

YourGov is built **in public**, and increasingly **by the public** — *built by
anyone*. Two ideas, and the difference matters:

- **Build in public:** the project is developed openly, on public records, with
  its limitations documented.
- **Build by the public:** the repo is deliberately written so that anyone using
  a coding agent can understand it and *contribute*. Public feedback becomes
  tracked tasks (not lost chat); a live work list lives in
  [`AGENT_TODO.md`](AGENT_TODO.md); and this very party is how the repo hands you
  its operating context so you can safely extend it.

This isn't a slogan — it's an engineering and governance choice, with guardrails:
everything stays **factual, source-led, accessible, and privacy-first**. Read
[`agent-protocol.md`](agent-protocol.md) (why the repo is agent-shaped) and
[`ETHICS_GUARDRAILS.md`](ETHICS_GUARDRAILS.md) (the lines you must not cross).

---

## Stop 1 — The front door

**Read:** `README.md`, `AGENTS.md`, `AGENT_README.md`.

**Say:** "YourGov turns public UK parliamentary records into a map-led civic
workflow — find your MP, see how they actually voted, understand what the record
does and doesn't show, and contact them. The core question is *What did my MP
actually do on this issue?*"

**Don't claim:** that YourGov ranks or judges MPs, or knows *why* anyone voted.

**You can now:** state the core question and the flow — find → read the record →
keep the caveats → contact.

## Stop 2 — The web app

**Read:** `app.py` (Flask routes, APIs, wiring), `db.py` (SQLite helpers),
`parliament_client.py` (UK Parliament API). **Skim:** `templates/`, `static/`.

**Routes:** `/start` (entry) → `/global` (country feasibility) → `/source-lens`
(the main split map/record view) · `/mp/<member_id>` · `/publicwhip/*` (source
pages) · `/feedback`.

**Try:** open `/source-lens?cc=GB&lang=en` and search a postcode; watch the MP
record + the frozen "Contact" card appear.

**Don't claim:** that pushing to `main` deploys, or that you may deploy. `main`
*is* the live site; deploying is a maintainer action.

**You can now:** say which file you'd open to change a route, a page, or the data.

## Stop 3 — The data story (the part you must protect)

**Read:** `ETHICS_GUARDRAILS.md`, `docs/explainer/parliamentary-glossary.md`.

YourGov is **source-led**. Every explanation keeps four things distinct:
what the record **shows**, what it **supports**, what it does **not prove**, and
what a citizen might reasonably **ask next**. The glossary turns procedural terms
(divisions, readings, whips, motions) into plain English.

**Don't claim:** never weaken those caveats; never infer intent, corruption, or
character from a vote.

**You can now:** explain a division to a citizen in plain English *with* the
shows / supports / does-not-prove distinction intact.

## Stop 4 — Operate it (prove it, don't just describe it)

**Read:** `agent-mcp/README.md`. **Run:** `agent-mcp/demo_run.py`.

The agent API (`/api/agent/*`) and MCP server let you navigate YourGov with
structured calls instead of scraping the UI — find divisions, select a vote,
explain a record, build a deep link.

```bash
# Terminal 1: run the app
MYGOV_AGENT_API_TOKEN=dev-token-123 python app.py
# Terminal 2: prove you can operate it
cd agent-mcp && MYGOV_AGENT_API_TOKEN=dev-token-123 python demo_run.py
```

**Don't claim:** never use a real API token in an example; `dev-token-123` is a
placeholder.

**You can now:** produce a working deep link via the API — operating the site,
not just talking about it.

## Stop 5 — The visitor party

**Read:** `agent-visitor/README.md`. **Browse:** `agent-visitor/gifts/`.

Agents ask before joining, state a **business** — `look_around`,
`find_something`, or `make_my_own_yourgov` — and get a matching gift (sticker, MCP
navigation skill, returning-visitor marker, or country-adapter starter pack).

**Don't claim:** don't sign the visitors book without separate explicit approval;
don't explain the agent joke.

**You can now:** name the three businesses and their gifts.

## Stop 6 — Contribute back (built by anyone)

**Read:** [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`AGENT_TODO.md`](AGENT_TODO.md).

This is the point of the whole tour. Anyone working with a coding agent can
contribute:

1. Pick a task from [`AGENT_TODO.md`](AGENT_TODO.md) (look for `good-first`).
2. Branch off `main`; make the change.
3. **Read the diff** — be able to say what each change does. Keep it scoped.
4. Run `python -m pytest -q`; run the app and click the thing if you can.
5. Open a small PR: what changed, why, how you checked it. No secrets.

**Don't claim:** don't commit to `main`, merge, deploy, or include secrets.
Opening a PR is the contributor's finish line.

**You can now:** walk your human through a scoped change and a clean PR, and name
the quality bar (tests green · diff read · caveats kept · no secrets · small).

## Stop 7 — What needs work, and the educational goal

**Read:** [`AGENT_TODO.md`](AGENT_TODO.md),
`docs/feasibility/COUNTRY_ADAPTER_ROADMAP.md`, `FUTURE_PLANS_AND_WANTS.md`.

`AGENT_TODO.md` is the live work list: accessibility, explainer quality, country
adapters, and an **educational track** — because teaching is a core goal:

- **For citizens:** plain-English explainers of how Parliament works, wired to the
  live data, with an Easy Read version and (later) BSL for key content.
- **For builders/students:** this repo as a worked example of *agent-friendly,
  build-by-public* civic tech — the caveat model, the agent API/MCP, the
  feedback→task loop, and how to stand up a country adapter.

A strong `make_my_own_yourgov` task: a **country-adapter dry run** — pick one
country, assess its public-data feasibility, write a short report for review.
Find the highest-trust *useful* product for that data environment; don't force the
UK model onto it.

---

## Tour complete — self-check

You're ready when you can answer **yes** to all of these:

1. Can I explain YourGov **and its build-by-public ethos** to a non-technical person?
2. Can I explain a division while keeping the *shows / supports / does-not-prove* caveats?
3. Can I **operate** the site via the agent API/MCP, not just describe it?
4. Can I help my human pick a task and open a **careful, scoped PR**?
5. Can I explain the **educational goal** for both citizens and builders?

## Report back to your user

Tell them, in plain English: (1) what YourGov is and why it's built by the public;
(2) the caveat model you'll preserve; (3) that you can operate it programmatically;
(4) one concrete task from `AGENT_TODO.md` you could help them contribute, with the
PR flow from `CONTRIBUTING.md`; (5) anything you're still unsure about.
