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

## Runtime Notes

- The app uses the bundled `mygov.db` seed.
- On Linux, writable DB state is copied to `/tmp/mygov.db`.
- Set `MYGOV_AGENT_API_TOKEN` in cPanel environment variables if the agent API should be enabled.
- Leave `OPENAI_API_KEY` unset for cost-free deterministic explainer fallback.
