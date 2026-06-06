# upgrade-intake

A small, **queue-only** tool that turns public feedback into an append-only
local file of upgrade requests. Humans review and decide later. The repo
itself is never mutated by this tool beyond appending to the queue file.

Feedback arrives through exactly **three channels**:

1. **Telegram** — bot polling (`getUpdates`).
2. **Email** — IMAP polling of a mailbox/folder.
3. **WhatsApp** — consumes JSONL exported by a linked-device bridge.

All three normalise into the **same** append-only queue schema
(`schema.json`).

## Why queue-only

Anything that automatically turns external messages into PRs, commits, or
branches makes the repo an open attack surface. This tool deliberately does
the boring, safe thing: it writes one line to a file. Triage is a separate,
human step.

## Safety model

- **Polling / file consumption, not webhooks.** No public ingress; nothing to
  expose. There is no HTTP endpoint that accepts public input.
- **Allowlist per channel.** Messages are only accepted from configured chat
  IDs / names / usernames (Telegram), senders / recipients (Email), or chat /
  sender JIDs (WhatsApp). An **empty allowlist drops everything** — that is
  the safe default.
- **No execution.** Message text is data only. It is never `exec`'d, `eval`'d,
  shell'd, or passed to a template engine.
- **Append-only.** The tool only ever appends lines to
  `queue/upgrade-queue.jsonl`. It never edits, deletes, commits, pushes, or
  opens PRs.
- **Fail closed.** If a *selected* channel's config is missing or a
  placeholder, intake exits non-zero and writes nothing.
- **Dedupe.** Records are hashed on `(channel_name, contributor, summary)` so
  reposts don't bloat the queue. Per-channel cursors avoid re-fetching.
- **Junk preserved, not deleted.** Likely junk is written with
  `status: "junk"` and a `junk_reason`; the raw text is kept for audit.
- **Audit trail.** The verbatim message body is preserved in `raw_message`,
  separate from the derived `summary` and the `contributor` name.

## Files

| Path | Purpose |
|---|---|
| `core.py` | Shared schema assembly, classification, junk detection, stable IDs, queue IO, latest-per-id resolution. |
| `adapters/telegram.py` | Telegram `getUpdates` polling + allowlist + `.last_update_id`. |
| `adapters/email_imap.py` | IMAP polling (stdlib) + allowlist + `.last_email_uid`. Plain-text only. |
| `adapters/whatsapp_jsonl.py` | Consumes bridge JSONL + allowlist + `.last_whatsapp_message_id`. |
| `intake.py` | Multi-channel CLI. Polls/consumes, normalises, appends to queue. |
| `inspect_queue.py` | Read-only CLI: stats / list / show (latest status per id). |
| `triage_queue.py` | Append-only decision CLI (accept/reject/defer/junk/implemented/reviewed). |
| `schema.json` | JSON Schema for one queue record. |
| `config.example.json` | Template config. Copy to `config.json` and edit. |
| `queue/upgrade-queue.jsonl` | The append-only queue. |
| `queue/README.md` | Rules for the queue file. |

`config.json` and the cursor files (`.last_update_id`, `.last_email_uid`,
`.last_whatsapp_message_id`) are runtime state — they are gitignored. Do
**not** commit them.

## Setup

Copy the template, then fill in only the channel(s) you intend to run:

```
cp tools/upgrade-intake/config.example.json tools/upgrade-intake/config.json
```

### Telegram

1. Create a bot with [@BotFather](https://t.me/BotFather); get the token.
2. Add the bot to the chat/channel you want to read from. For groups, disable
   group privacy in BotFather so the bot can see messages.
3. Fill in `telegram.telegram_bot_token` and at least one of
   `allowed_chat_ids` / `allowed_chat_names` / `allowed_usernames`.

### Email (IMAP)

1. Use a dedicated feedback mailbox.
2. Generate an **app password / app-specific token** for IMAP. Never use your
   main account password, and never commit it. Read-only access is enough.
3. Fill in `email.imap_host`, `imap_port` (default 993), `username`,
   `password`, optional `folder` (default `INBOX`), and at least one of
   `allowed_senders` / `allowed_recipients`.

The adapter extracts `text/plain` only. It never decodes or renders HTML and
never opens attachments.

### WhatsApp (linked-device bridge JSONL)

> **Caveat:** WhatsApp has no official inbound API for this. The linked-device
> bridge that produces the JSONL is a **non-official protocol** and may break
> at any time. This adapter does not talk to WhatsApp itself — it only reads
> the JSONL the bridge writes.

1. Run your linked-device bridge separately; point it at a JSONL file
   (e.g. `incoming-pdfs/messages.jsonl`). Expected per-line fields:
   `messageId`, `chatJid`, `senderJid`, `senderName`, `timestamp`, `kind`,
   `text`, `fileName`, `mimeType`, `fromMe`.
2. Fill in `whatsapp.jsonl_path` (or pass `--whatsapp-jsonl <path>`) and at
   least one of `allowed_chat_jids` / `allowed_sender_jids`.

Outgoing (`fromMe: true`) messages are skipped.

## Running intake

```
# one-off across all three channels
python tools/upgrade-intake/intake.py --once --channels telegram,email,whatsapp

# poll forever (Ctrl+C to stop)
python tools/upgrade-intake/intake.py --poll --channels telegram,email

# one-off WhatsApp ingest from a specific JSONL (runs whatsapp only)
python tools/upgrade-intake/intake.py --once --whatsapp-jsonl incoming-pdfs/messages.jsonl
```

If you omit `--channels`, intake defaults to `telegram` (or to `whatsapp`
alone when `--whatsapp-jsonl` is given). A selected channel without valid
config makes intake exit non-zero without writing anything.

## Inspecting the queue

```
python tools/upgrade-intake/inspect_queue.py stats
python tools/upgrade-intake/inspect_queue.py list --status queued
python tools/upgrade-intake/inspect_queue.py list --source email --priority high
python tools/upgrade-intake/inspect_queue.py show <id-prefix>
```

The inspector collapses the append-only log to the **latest record per id**,
so a triaged item shows its current status, not its original one.

## Triaging (append-only decisions)

A human decides; the decision is recorded by appending a new line with the
same `id`:

```
python tools/upgrade-intake/triage_queue.py accept      <id-prefix> --reason "valid bug, will fix"
python tools/upgrade-intake/triage_queue.py reject      <id-prefix> --reason "out of scope"
python tools/upgrade-intake/triage_queue.py defer       <id-prefix> --reason "after launch"
python tools/upgrade-intake/triage_queue.py junk        <id-prefix> --reason "spam the filter missed"
python tools/upgrade-intake/triage_queue.py implemented <id-prefix> --reason "shipped in PR #123"
python tools/upgrade-intake/triage_queue.py reviewed    <id-prefix> --reason "noted, no action"
```

Each decision copies the latest record's fields forward (so the line stays
schema-complete) and overrides `status`, `decision_reason`, `decided_at`, and
`decided_by`. Existing lines are never edited — the audit trail is preserved.
Use `--by NAME` to attribute the decision; it defaults to the OS user.

## What this tool does NOT do

- Does not open pull requests, commit, or create branches.
- Does not run any code from message bodies.
- Does not expose any HTTP endpoint or web form.
- Does not write outside `tools/upgrade-intake/queue/`.
- Does not store secrets in the queue or in git.

If you want any of those behaviours, build them as a separate, explicit,
human-triggered tool that reads from this queue.
