# Public feedback intake (three channels → local queue)

This is the human-facing guide for the `tools/upgrade-intake/` system.

## What it is

YourGov invites the public to help improve the service by sending complaints and
suggestions through **three channels**:

1. **WhatsApp**
2. **Telegram**
3. **Email**

A polling tool on a trusted machine normalises each message into a structured
record and appends it to `tools/upgrade-intake/queue/upgrade-queue.jsonl`.
Humans triage the queue later. The repo is **not** modified beyond that one
append-only file.

The public-facing invitation lives at the `/feedback` route on the live site.
That page only *links out* to the three channels — it has no form and accepts
no input server-side.

## Why it is deliberately queue-only

This system is intentionally queue-only to avoid turning the repo into an open
attack surface. There is **no path** from a public message to a commit, a
branch, a PR, an executed shell command, or any executed code. Public feedback
is **data only**. Every change to the codebase still goes through a
human-authored PR.

## Configuring each channel

Copy `tools/upgrade-intake/config.example.json` to `config.json` (gitignored)
and fill in only the channel(s) you run. Full setup steps are in
`tools/upgrade-intake/README.md`. Summary:

- **Telegram** — a BotFather bot token + an allowlist of chat IDs / names /
  usernames.
- **Email** — IMAP host/user + an **app password / app-specific token** (never
  the main password, never committed) + an allowlist of senders and/or
  recipient aliases. Only `text/plain` is read; HTML and attachments are never
  decoded or executed.
- **WhatsApp** — a path to JSONL written by a linked-device bridge + an
  allowlist of chat / sender JIDs. The linked-device protocol is **not
  official and may break**; this tool only reads the bridge's JSONL output, it
  does not connect to WhatsApp.

## Running intake

On a trusted machine (your laptop, a small VM you own). Do **not** expose any
port — this is polling/file consumption only.

```
# one-off across all channels
python tools/upgrade-intake/intake.py --once --channels telegram,email,whatsapp

# poll forever
python tools/upgrade-intake/intake.py --poll --channels telegram,email

# one-off WhatsApp ingest from a JSONL export
python tools/upgrade-intake/intake.py --once --whatsapp-jsonl incoming-pdfs/messages.jsonl
```

If a selected channel is missing required config, intake exits non-zero and
writes nothing (fail closed). An empty allowlist drops every message.

## Inspecting the queue

```
python tools/upgrade-intake/inspect_queue.py stats
python tools/upgrade-intake/inspect_queue.py list --status queued
python tools/upgrade-intake/inspect_queue.py list --source whatsapp --priority high
python tools/upgrade-intake/inspect_queue.py show <id-prefix>
```

The inspector shows the **latest** status per item, so a triaged record
reflects its current decision.

## Deciding: accept / reject / defer / junk / implemented

Triage is append-only — a decision adds a new line with the same `id`:

```
python tools/upgrade-intake/triage_queue.py accept      <id-prefix> --reason "..."
python tools/upgrade-intake/triage_queue.py reject      <id-prefix> --reason "..."
python tools/upgrade-intake/triage_queue.py defer       <id-prefix> --reason "..."
python tools/upgrade-intake/triage_queue.py junk        <id-prefix> --reason "..."
python tools/upgrade-intake/triage_queue.py implemented <id-prefix> --reason "..."
python tools/upgrade-intake/triage_queue.py reviewed    <id-prefix> --reason "..."
```

Typical flow:

- **Accept** → write the fix yourself and open a PR (if attribution is in
  order, use the existing `thanks-<contributor>:` convention, see
  `docs/feedback/thanks-neil.md`), then run `triage_queue.py accept` so the
  queue records the decision. After the PR merges, run
  `triage_queue.py implemented`.
- **Reject** → record `reject` with a reason.
- **Defer** → record `defer`.
- **Reviewed, no action** → record `reviewed`.
- **Junk the filter missed** → record `junk`.
- **Needs more info** → leave as `needs_review`; ask the contributor.

The queue is append-only, so the audit trail of who said what, and who decided
what, when, is preserved.

## Junk filtering

Junk detection is **deterministic and rule-based** (no LLM in this pass). A
record is marked `status: "junk"` with a `junk_reason` when it is empty,
link-only, has more than three URLs, is repeated-character spam, matches a
known spam phrase (crypto/betting/adult/loan, etc.), is an attachment with no
useful text, or is too short without a clear bug/complaint phrase. Junk is
**preserved**, never deleted, so a human can audit why it was filtered.

## Contributor tagging

If a queue item lines up with an existing contributor convention (e.g. the
`thanks-neil:` PR prefix), use that convention when you open the PR. The queue
stores `contributor` separately from the message body, so you don't have to
grep raw text to attribute work. Keep stored personal data to the minimum
needed for attribution and follow-up.

## Operational notes

- `config.json` holds tokens/passwords. Keep it out of git (it is gitignored).
- Cursor files (`.last_update_id`, `.last_email_uid`,
  `.last_whatsapp_message_id`) are runtime state and gitignored.
- If the queue file grows large, rotate it (rename to
  `upgrade-queue-YYYY-MM.jsonl`, start a new empty file). Do not edit lines in
  place.

## What this never does

- No automatic PRs, commits, or branches.
- No execution of contributor text.
- No public HTTP endpoint or web form.
- No secrets stored in the queue or in git.
