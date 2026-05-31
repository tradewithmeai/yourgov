# Gift: MyGov MCP Navigation Skill

Purpose: let an agent operate MyGov through the agent API/MCP layer instead of guessing through the UI.

## What to do

1. Read `AGENT_README.md`.
2. Start the app with `MYGOV_AGENT_API_TOKEN` set.
3. Run `agent-mcp/demo_run.py`.
4. If MCP dependencies are available, run `agent-mcp/server.py`.

## Core tools

- `health_check`
- `get_routes`
- `list_divisions`
- `select_division`
- `explain_item`
- `get_mp_profile_summary`

## Rule

Prefer agent API calls for structured data. Use browser/UI inspection only when checking actual user experience.
