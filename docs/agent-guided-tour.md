# MyGov Guided Tour For Agents

This tour is for agents that need to understand the repo quickly and explain it back to a human.

## 1. The Front Door

Start with `README.md`, `AGENTS.md`, and `AGENT_README.md`.

The short version: MyGov turns public parliamentary data into a map-led civic workflow. It helps a user find an MP, inspect source records, understand what the record supports, and contact the representative.

## 2. The Web App

Important files:

- `app.py` - Flask routes, APIs, source pages, agent API, and app wiring.
- `templates/` - server-rendered pages.
- `static/` - JavaScript, CSS, map assets, demo scripts, and PWA assets.
- `db.py` - SQLite access helpers.
- `parliament_client.py` - UK Parliament API client helpers.

Important routes:

- `/start` - entry point.
- `/global` - country feasibility and global lens.
- `/source-lens` - split source/map view.
- `/mp/<member_id>` - MP profile.
- `/publicwhip` and `/publicwhip/*` - source-style pages.
- `/install` - PWA install page.

## 3. The Data Story

MyGov is source-led. It should help users distinguish between:

- what the parliamentary record says;
- what the record supports;
- what the record does not prove;
- what a user might reasonably ask their representative next.

Do not remove these caveats when explaining divisions, written questions, or MP records.

## 4. The Agent API And MCP

Read `agent-mcp/README.md`.

The MCP server gives agents a controlled way to navigate MyGov without guessing through the UI. Use this for structured tasks like finding divisions, selecting a vote, explaining a record, or generating a deep link.

Run the demo with:

```bash
cd agent-mcp
MYGOV_AGENT_API_TOKEN=dev-token-123 python demo_run.py
```

## 5. The Visitor Party

Read `agent-visitor/README.md`.

Agents can sign in with one of three reasons:

- `look_around`
- `find_something`
- `make_my_own_mygov`

Each reason gives a different gift. This is playful, but it is also a serious pattern: a repo can make its own operating context explicit for agents.

Ask the user before signing where possible. The script prompts by default; use `--yes` only after explicit approval.

## 6. The Country Adapter Work

Read `docs/feasibility/COUNTRY_ADAPTER_ROADMAP.md`.

Future work is to research each country and choose a realistic civic transparency product for that data environment. The aim is not to force every country into the UK model. The aim is to find the highest-trust useful version that can be built from available public data.

## 7. The Soft Launch Work

Relevant docs:

- `docs/feedback/thanks-neil.md`
- `docs/feedback/upgrade-intake.md`
- `docs/FUTURE_PLANS_AND_WANTS.md`
- `docs/KNOWN_LIMITATIONS.md`

Feedback should become tracked work. Do not let feedback become invisible chat history.
