# Deploy

YourGov runs in production as a Flask app on **Krystal** (cPanel + Passenger) at
`yourgov.solvx.uk`. See [`KRYSTAL_DEPLOY.md`](KRYSTAL_DEPLOY.md) for the full setup.

## How a change reaches production

1. Work on a branch and merge tested, approved changes into `main`.
2. The live deploy is owned by the separate `tradewithmeai/solvx-website` repo: its
   workflow checks out this repo, builds a runtime bundle, and uploads it by FTPS to
   the cPanel Python app directory, then writes `tmp/restart.txt` so Passenger
   reloads.
3. The daily `YourGov Data Refresh` workflow (`.github/workflows/update-data.yml`)
   refreshes `mygov.db`, validates it, commits it, and dispatches the solvx-website
   deploy so the fresh data goes live. See the data-refresh section of
   [`KRYSTAL_DEPLOY.md`](KRYSTAL_DEPLOY.md).

## Runtime behaviour

- `mygov.db` is bundled as seed data.
- On the server, writable DB state is copied to `/tmp/mygov.db`.

## Environment variables (cPanel)

- `MYGOV_AGENT_API_TOKEN` — set to enable the agent API.
- `OPENAI_API_KEY` — optional; leave unset for the deterministic explainer fallback.
- `ASSET_VERSION` — optional cache-busting override.

## Local verification before deploy

```powershell
py -3.12 -m pytest -q
py -3.12 scripts\validate_production_ready.py
```

Then manually confirm:

- `/source-lens` loads and shows the YourGov journey copy.
- `/global` and `/mp/206` load.
- Selecting an MP renders the voting record; clicking a division recolours the map.
- Each of the four map modes (vote / party / gender / rebel split) recolours the map.
