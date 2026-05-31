# MyGov Agent MCP Server

An agent control surface for MyGov. Lets an external AI agent (Claude, Codex, or any MCP client) navigate MyGov and perform core user flows programmatically.

## What this proves

> "MyGov is not just a website — it exposes a safe, authenticated agent control surface."

## Quick start

### 1. Set environment variables

```bash
# Required — shared secret between the MCP server and the Flask app
export MYGOV_AGENT_API_TOKEN=dev-token-123

# Optional — defaults to http://127.0.0.1:5050
export MYGOV_APP_URL=http://127.0.0.1:5050
```

### 2. Start the MyGov app

```bash
cd ..
MYGOV_AGENT_API_TOKEN=dev-token-123 python app.py
```

### 3. Run the demo (no MCP required)

```bash
cd agent-mcp
pip install httpx
MYGOV_AGENT_API_TOKEN=dev-token-123 python demo_run.py
```

### 4. Run the MCP server (optional — requires `mcp` package)

```bash
pip install mcp httpx
MYGOV_AGENT_API_TOKEN=dev-token-123 python server.py
```

If `mcp` install fails, the demo and API still work — MCP is the wrapper, not the core.

---

## Tools

| Tool | Description |
|------|-------------|
| `health_check()` | Verify app reachability, DB access, and auth |
| `get_routes()` | List canonical routes in the MyGov app |
| `list_divisions(limit)` | Recent parliamentary divisions from the database |
| `select_division(division_id)` | Full division metadata and sample voter breakdown |
| `explain_item(division_id, member_id, level, context)` | Plain-English explanation of an MP's vote |
| `get_mp_profile_summary(member_id)` | MP profile — votes, questions, recent activity |

### Explain levels

| Level | Name | Length |
|-------|------|--------|
| `"skim"` / `0` | SKIM | 1 sentence |
| `"practical"` / `1` | PRACTICAL | 2–3 sentences |
| `"detailed"` / `2` | DETAILED | 4–6 sentences |
| `"full"` / `3` | FULL | Structured 4-section response |

---

## Agent API contract

All `/api/agent/*` responses:

```json
{
  "ok": true,
  "data": { ... },
  "error": null,
  "ts": "2026-05-30T10:00:00+00:00"
}
```

- Auth: `Authorization: Bearer <token>` header required on every request.
- No token → `401`.
- Wrong token → `401`.
- Missing `MYGOV_AGENT_API_TOKEN` on the server → `503`.
- Rate limit (60 req/min) → `429`.

---

## Demo flow

`demo_run.py` performs this sequence and prints a structured JSON summary:

1. `health_check` — confirm app alive
2. `list_divisions(limit=5)` — see recent votes
3. `select_division(id)` — inspect first result
4. `explain_item(division_id, member_id, level="practical")` — get plain-English summary

---

## Known limits

- Explanation endpoint calls OpenAI (gpt-4o-mini by default). Falls back to a plain-text summary if `OPENAI_API_KEY` is not set — the API still returns 200.
- `sample_voters` in `select_division` is capped at 20. Full map data is available via `/api/lens/division/<id>`.
- Rate limit is in-memory; resets on server restart.
- MCP package (`pip install mcp`) requires Python 3.10+. If unavailable, `mygov_client.py` and `demo_run.py` work standalone.
