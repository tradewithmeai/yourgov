# Context Engine

Lightweight context assembler for YourGov.

Purpose:

- Gather key project context from docs and agent logs.
- Output a compact prompt-ready context block for Claude/Codex.

## Usage

From repo root:

```powershell
python context-engine/context_engine.py
```

Write to file:

```powershell
python context-engine/context_engine.py --out docs/context-snapshot.md
```

Optional controls:

```powershell
python context-engine/context_engine.py --max-chars 3000 --sections docs,agent_logs,routes
```

## Included sources

- `docs/project-chat-context.md`
- selected docs in `docs/`
- `agent-logs/latest.md` (if present)
- Flask route inventory from `app.py`

