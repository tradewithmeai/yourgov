# Feedback intake — go-live checklist

What it takes to turn the three feedback channels from "built and tested" into
"actually collecting messages on the live site". Nothing here is required to
*deploy* the code safely — the `/feedback` page works without it (links fall
back to "coming soon" / `captain@solvx.uk`). This is the operator's setup.

There are **two independent halves**:

- **A. Frontend** — make `/feedback` show real links. Lives in the deployed
  app; needs three environment variables on the live host.
- **B. Backend intake** — actually collect and triage messages. Runs on a
  trusted machine you own (your laptop / a small VM). It is **not** deployed
  and never exposed to the internet.

Current status: code for all three channels is unit-tested and the queue /
triage / `/feedback` paths are verified; WhatsApp has had a live end-to-end
run with a sample bridge file. **No live credentials are configured for any
channel** — that is this checklist.

---

## A. Frontend: make `/feedback` show real links

The route reads three environment variables (see `app.py`, `feedback()`):

| Variable | Controls | If unset |
|---|---|---|
| `MYGOV_FEEDBACK_WHATSAPP_URL` | WhatsApp link (e.g. `https://wa.me/4477…`) | "WhatsApp channel coming soon" |
| `MYGOV_FEEDBACK_TELEGRAM_URL` | Telegram link (e.g. `https://t.me/your_bot`) | "Telegram channel coming soon" |
| `MYGOV_FEEDBACK_EMAIL` | Contact email shown + `mailto:` | falls back to `captain@solvx.uk` |

These values are **public** (a wa.me link, a t.me handle, a public address) —
they are not secrets, so it is fine to commit them if you choose.

The live site is **https://yourgov.solvx.uk**, hosted on **Krystal
(cPanel / LiteSpeed Passenger)**, entrypoint `passenger_wsgi.py`. Set the
variables one of two ways:

1. **cPanel → Setup Python App → Environment variables** (recommended; no code
   change, no redeploy of code, just restart the app). Add the three vars
   there and restart.
2. **In `passenger_wsgi.py`**, following the existing repo precedent
   (`os.environ.setdefault("ANALYTICS_DISABLED", "1")`):
   ```python
   os.environ.setdefault("MYGOV_FEEDBACK_WHATSAPP_URL", "https://wa.me/4477…")
   os.environ.setdefault("MYGOV_FEEDBACK_TELEGRAM_URL", "https://t.me/your_bot")
   os.environ.setdefault("MYGOV_FEEDBACK_EMAIL", "feedback@yourdomain")
   ```
   This commits the (public) URLs to `main` and deploys with the next commit.

After setting, load `https://yourgov.solvx.uk/feedback` and confirm the
WhatsApp/Telegram links render (not "coming soon").

---

## B. Backend intake: collect + triage messages

Runs on a trusted machine. **Do not expose a port** — intake is polling /
file-consumption only, never a webhook.

### B0. One-time

```
cp tools/upgrade-intake/config.example.json tools/upgrade-intake/config.json
```

`config.json` is gitignored (secrets). Fill in only the channel(s) you run.
A selected channel with missing/placeholder config makes intake **exit
non-zero and write nothing** (fail closed), so a half-filled config can't
silently no-op.

### B1. Telegram

Config block `telegram` in `config.json`:

| Key | Required? | Notes |
|---|---|---|
| `telegram_bot_token` | yes | From [@BotFather](https://t.me/BotFather). Must not be the `PUT-YOUR-BOT-TOKEN…` placeholder. |
| `allowed_chat_ids` / `allowed_chat_names` / `allowed_usernames` | **at least one non-empty** | Allowlist. Empty ⇒ every message dropped. |
| `max_message_chars` | no | Defaults to 4000. |

Setup: create the bot, add it to the feedback chat, and for groups disable
group privacy in BotFather so it can read messages. Then:

```
python tools/upgrade-intake/intake.py --once --channels telegram
```

### B2. Email (IMAP)

Config block `email`:

| Key | Required? | Notes |
|---|---|---|
| `imap_host` | yes | e.g. `imap.gmail.com`, your provider's IMAP host. |
| `imap_port` | no | Defaults to 993 (IMAPS). |
| `username` | yes | The mailbox login. |
| `password` | yes | **App password / app-specific token**, never your main password. Must not be the `PUT-APP-PASSWORD-HERE` placeholder. |
| `folder` | no | Defaults to `INBOX`. |
| `channel_name` | no | Label stored on records. |
| `allowed_senders` / `allowed_recipients` | **at least one non-empty** | Allowlist by sender address and/or the alias it was sent to. |

Only `text/plain` is read; HTML and attachments are never decoded or executed.

```
python tools/upgrade-intake/intake.py --once --channels email
```

### B3. WhatsApp (linked-device bridge JSONL)

> The bridge connects as a WhatsApp linked device — a **non-official protocol
> that may break at any time**. This adapter does not talk to WhatsApp; it only
> reads the JSONL the bridge writes.

Config block `whatsapp`:

| Key | Required? | Notes |
|---|---|---|
| `jsonl_path` | yes (or pass `--whatsapp-jsonl`) | Path to the bridge's JSONL, e.g. `incoming-pdfs/messages.jsonl`. |
| `channel_name` | no | Label stored on records. |
| `allowed_chat_jids` / `allowed_sender_jids` | **at least one non-empty** | Allowlist by chat / sender JID. |
| `max_message_chars` | no | Defaults to 4000. |

Run the bridge separately, then:

```
python tools/upgrade-intake/intake.py --once --whatsapp-jsonl incoming-pdfs/messages.jsonl
```

(Outgoing `fromMe` messages are skipped.)

### B4. Run continuously

```
python tools/upgrade-intake/intake.py --poll --channels telegram,email,whatsapp
```

Polls every `poll_interval_seconds` (default 60). Ctrl+C to stop. A transient
error in one cycle is logged and retried; cursors only advance after a durable
write, so messages aren't lost on failure.

### B5. Inspect + triage

```
python tools/upgrade-intake/inspect_queue.py stats
python tools/upgrade-intake/inspect_queue.py list --status queued
python tools/upgrade-intake/inspect_queue.py show <id-prefix>

python tools/upgrade-intake/triage_queue.py accept      <id-prefix> --reason "…"
python tools/upgrade-intake/triage_queue.py reject      <id-prefix> --reason "…"
python tools/upgrade-intake/triage_queue.py defer       <id-prefix> --reason "…"
python tools/upgrade-intake/triage_queue.py junk        <id-prefix> --reason "…"
python tools/upgrade-intake/triage_queue.py implemented <id-prefix> --reason "…"
python tools/upgrade-intake/triage_queue.py reviewed    <id-prefix> --reason "…"
```

The queue is append-only; the inspector shows the latest status per item.

---

## Pre-deploy verification (already done on this branch)

- `python -m pytest tests/test_upgrade_intake.py` (or `python -m unittest
  tests.test_upgrade_intake`) — 45 tests, all passing.
- App boots; `/feedback`, `/`, `/source-lens`, `/global`, `/publicwhip`,
  `/start` all return 200; `POST /feedback` returns 405.

## Deploy

`main` is the live branch and auto-deploys on commit. When the feature is
approved:

```
git checkout main && git merge feedback-intake && git push
```

Setting the frontend env vars (section A) can happen before or after the
merge; the page degrades gracefully until they're set.
