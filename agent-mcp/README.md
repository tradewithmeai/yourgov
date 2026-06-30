# YourGov Agent MCP Server

Agent control surface for YourGov. External agents (Claude, Codex, any MCP client) can navigate core flows and fetch structured data via `/api/agent/*`.

## Quick start

1. Set env vars:

```bash
export MYGOV_AGENT_API_TOKEN=dev-token-123
export MYGOV_APP_URL=http://127.0.0.1:5050
```

2. Start app:

```bash
cd ..
MYGOV_AGENT_API_TOKEN=dev-token-123 python app.py
```

3. Run demo:

```bash
cd agent-mcp
pip install httpx
MYGOV_AGENT_API_TOKEN=dev-token-123 python demo_run.py
```

4. Run MCP server:

```bash
pip install mcp httpx
MYGOV_AGENT_API_TOKEN=dev-token-123 python server.py
```

## Tools

| Tool | Description |
|------|-------------|
| `health_check()` | Verify app reachability, DB access, auth |
| `get_routes()` | List canonical app and agent API routes |
| `list_divisions(limit)` | Recent parliamentary divisions |
| `select_division(division_id)` | Division metadata and sample voter breakdown |
| `explain_item(division_id, member_id, level, context)` | Plain-English vote explanation |
| `get_mp_profile_summary(member_id)` | MP profile summary |
| `search_mps(query, limit)` | Search MPs by name, party, constituency |
| `get_map_payload(mode, division_id)` | Map-ready payload for `vote-split`, `party-split`, `gender-split`, `rebel-rate` |
| `list_global_countries(status, limit)` | Global feasibility country list |
| `get_global_country(iso2)` | One country feasibility record |
| `get_deeplink(target, ...)` | Canonical in-app deep link generation |

## Deep link targets

- `source-lens` (optional: `cc`, `lang`, `source`)
- `global` (optional: `cc`, `lang`)
- `mp` (required: `member_id`)
- `ab-map` (optional: `variant` = `a` or `b`)
- `publicwhip-division` (required: `division_id`)

## Agent API contract

All `/api/agent/*` responses:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "ts": "2026-05-31T10:00:00+00:00"
}
```

- Auth: `Authorization: Bearer <token>`
- Missing/wrong token: `401`
- Token not configured on server: `503`
- Rate limit: `429` (60 req/min, in-memory)

## Known limits

- Explanation endpoint uses OpenAI when configured; otherwise deterministic fallback text.
- `sample_voters` is capped.
- Rate limiter is process-local and resets on restart.
