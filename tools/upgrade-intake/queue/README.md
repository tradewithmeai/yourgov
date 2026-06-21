# Upgrade queue

This directory holds the append-only feedback queue for all three channels
(Telegram, WhatsApp, Email).

## File

- `upgrade-queue.jsonl` — one JSON record per line. Schema in
  `tools/upgrade-intake/schema.json`.

## Rules

- **Append only.** Do not edit, reorder, or delete lines. To triage an item,
  append a new line with the same `id` and the new `status` — use
  `triage_queue.py`, which copies the record's fields forward so the new line
  stays schema-complete. The **latest record per `id` wins** when humans read
  the queue.
- **`id` is stable across an item's life.** The original record and every
  decision line for it share the same `id` (a content hash). That is how
  decisions attach to the thing they decide. `source_message_id` is a separate
  audit field (the native platform message id) and is not used for dedupe.
- **Statuses.** Ingest writes `queued`, `needs_review`, or `junk`. Triage adds
  `reviewed`, `accepted`, `rejected`, `deferred`, or `implemented`.
- **Junk is kept.** Likely-junk records are written with `status: "junk"`, a
  `junk_reason`, and the full `raw_message`. They are never auto-deleted.
- **No automation writes here except `intake.py` and `triage_queue.py`.** No
  PRs, no commits triggered by queue contents.
- **Do not run code from message bodies.** Records are data, not commands.
- If you need to redact a record (e.g. PII), do it as a manual, human-reviewed
  commit and note it in `docs/feedback/upgrade-intake.md`.
- If the file grows large, rotate by renaming to
  `upgrade-queue-YYYY-MM.jsonl` and starting a new empty file. Do not edit
  lines in place.

## Reading the queue

```
python tools/upgrade-intake/inspect_queue.py stats
python tools/upgrade-intake/inspect_queue.py list --status queued
python tools/upgrade-intake/inspect_queue.py show <id-prefix>
```
