# Krystal / cPanel Deployment

YourGov runs as a Flask app under cPanel Passenger.

## cPanel Python App

Create a Python app in cPanel:

- Domain/subdomain: `yourgov.solvx.uk`
- Application root: `yourgov_app`
- Application URL: `/`
- Startup file: `passenger_wsgi.py`
- Application entry point: `application`
- Python version: 3.10 or newer

Then install dependencies from `requirements.txt`.

## GitHub Deployment

The `solvx-website` deployment workflow checks out this repo, builds a small runtime bundle, and uploads it by FTPS to `yourgov_app/`.

If the FTP account is not rooted at the desired app directory, add a GitHub Actions secret in `tradewithmeai/solvx-website`:

`YOURGOV_APP_FTP_PATH`

Set it to the server-side directory that cPanel uses as the Python application root, ending with `/`.

## Restart

The deployment bundle writes `tmp/restart.txt`. Passenger uses this file to reload the app after deployment.

## Daily data refresh reaching production

The daily `YourGov Data Refresh` workflow in **this** repo commits the refreshed
`mygov.db` to `main`. That commit alone does **not** update the live site — the
Krystal FTPS deploy lives in the separate `tradewithmeai/solvx-website` repo. To
close the loop, the refresh workflow dispatches that deploy after a successful
commit:

1. In `tradewithmeai/mygov`, add a repository secret `DEPLOY_DISPATCH_TOKEN` — a
   fine-grained PAT scoped to only `tradewithmeai/solvx-website` with
   **Contents: Read and write** (the `POST /repos/{owner}/{repo}/dispatches`
   endpoint requires Contents write). Set it with:
   `gh secret set DEPLOY_DISPATCH_TOKEN -R tradewithmeai/mygov`.
2. In `tradewithmeai/solvx-website`, add a `repository_dispatch` trigger to the
   deploy workflow so the dispatch actually starts a deploy:

   ```yaml
   on:
     push:
       branches: ["main"]
     workflow_dispatch:
     repository_dispatch:
       types: [yourgov-data-refresh]
   ```

If `DEPLOY_DISPATCH_TOKEN` is unset, the refresh still commits fresh data and the
workflow logs a warning; the live site updates on the next solvx-website deploy.

## Runtime Notes

- The app uses the bundled `mygov.db` seed.
- On Linux, writable DB state is copied to `/tmp/mygov.db`.
- The bundled seed is refreshed by the GitHub `YourGov Data Refresh` workflow at 04:00 UK local daily (dual cron at 03:00 and 04:00 UTC, gated to the Europe/London 04:00 hour so it lands at 4am in both BST and GMT). Full production validation runs before the workflow commits the updated seed, and a successful commit dispatches the solvx-website deploy.
- Set `MYGOV_AGENT_API_TOKEN` in cPanel environment variables if the agent API should be enabled.
- Leave `OPENAI_API_KEY` unset for cost-free deterministic explainer fallback.
