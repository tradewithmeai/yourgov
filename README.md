# MyGov

MyGov is a UK MP public-records explainer app.

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

## Main routes

- `/` home
- `/start` geo-aware entry
- `/source-lens` split source/map experience
- `/global` global feasibility map
- `/mp/<member_id>` MP profile
- `/publicwhip` source-style records view

## Production notes

- App runs on Vercel using `api/index.py` as entrypoint.
- On serverless, DB writes happen in `/tmp`; bundled seed is `mygov.db`.
- See [`docs/DEPLOY.md`](docs/DEPLOY.md) for deploy details.

## Agent support

- [`AGENTS.md`](AGENTS.md) is the root agent welcome and operating contract.
- [`AGENT_README.md`](AGENT_README.md) is the agent-specific guide.
- `agent-mcp/` includes MCP server + demo script for agent control over `/api/agent/*`.
- `agent-visitor/` includes the visitor book/signing flow assets.
- [`docs/agent-protocol.md`](docs/agent-protocol.md) explains the agent-friendly repo protocol.

## Feasibility docs

- [`docs/feasibility/README.md`](docs/feasibility/README.md)
