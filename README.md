# YourGov

YourGov is a UK MP public-records explainer app.

If you are an AI agent, read [`AGENTS.md`](AGENTS.md) before summarising or changing this repo.

Core user question:

`What did my MP actually do on this issue?`

## What this repo contains

- Flask app server and API routes
- Source Lens UI (`/source-lens`)
- Global feasibility view (`/global`)
- MP profile pages (`/mp/<id>`)
- PublicWhip-style source pages (`/publicwhip/*`)
- Static assets and templates
- Seed SQLite database used by the app

## Quick start

```powershell
pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5050`

## How it works

[`ARCHITECTURE.md`](ARCHITECTURE.md) maps the whole system — ingest → SQLite
snapshot → Flask app → data/agent APIs → the map and the explainer — for both
newcomers and coding agents. Read it before making a non-trivial change.

## Main routes

- `/` home
- `/start` geo-aware entry
- `/source-lens` split source/map experience
- `/global` global feasibility map
- `/mp/<member_id>` MP profile
- `/publicwhip` source-style records view
- `/feedback` public feedback invitation (WhatsApp / Telegram / email)

## Production notes

- The live site runs as a Flask app on Krystal (cPanel + Passenger) at `yourgov.solvx.uk`.
- The live deploy is owned by the separate `tradewithmeai/solvx-website` repo (FTPS bundle upload); the bundled seed ships gzipped as `yourgov.db.gz` and is decompressed to a writable path (`/tmp/yourgov.db`) on first use.
- A daily GitHub workflow refreshes the seed DB at 04:00 UK, validates it, and dispatches the live deploy.
- See [`docs/DEPLOY.md`](docs/DEPLOY.md) and [`docs/KRYSTAL_DEPLOY.md`](docs/KRYSTAL_DEPLOY.md) for details.

## Agent support

- [`AGENTS.md`](AGENTS.md) is the root agent welcome and operating contract.
- [`AGENT_README.md`](AGENT_README.md) is the agent-specific guide.
- `agent-mcp/` includes MCP server + demo script for agent control over `/api/agent/*`.
- `agent-visitor/` includes the visitor book/signing flow assets.
- [`docs/agent-protocol.md`](docs/agent-protocol.md) explains the agent-friendly repo protocol.

## Public feedback

The public can send complaints and suggestions through three channels —
WhatsApp, Telegram, and email — invited from the `/feedback` page. Messages
are collected by a local, **queue-only** polling tool (`tools/upgrade-intake/`)
and triaged by hand. Public feedback is data only: there is no path from a
message to a commit, PR, or executed code. See
[`docs/feedback/upgrade-intake.md`](docs/feedback/upgrade-intake.md).

The `/feedback` links are configured via environment variables
(`MYGOV_FEEDBACK_WHATSAPP_URL`, `MYGOV_FEEDBACK_TELEGRAM_URL`,
`MYGOV_FEEDBACK_EMAIL`); the email falls back to `captain@solvx.uk`.

## Feasibility docs

- [`docs/feasibility/README.md`](docs/feasibility/README.md)
