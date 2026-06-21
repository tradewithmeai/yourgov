"""Email adapter (IMAP polling).

Uses only the Python standard library (`imaplib`, `email`). It polls a
configured mailbox/folder, reads messages with a UID greater than the last
seen UID, allowlists senders and/or accepted recipient aliases, extracts the
plain-text body safely, and NEVER renders HTML or opens attachments.

- `fetch_messages(...)` does the IMAP IO.
- `normalize_email(msg, cfg)` is pure: an `email.message.Message` -> record
  (or None if not allowlisted / no usable text).
"""

from __future__ import annotations

import email
import imaplib
import sys
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr
from pathlib import Path
from typing import Any

import core

CURSOR_FILE = core.HERE / ".last_email_uid"


def required_config_ok(cfg: dict[str, Any]) -> tuple[bool, str]:
    em = cfg.get("email") or {}
    for key in ("imap_host", "username", "password"):
        if not em.get(key):
            return False, f"email.{key} missing"
    # Reject the shipped placeholder so a copied-but-unfilled config fails
    # closed (exit non-zero, write nothing) instead of silently no-op'ing.
    if "PUT-APP-PASSWORD-HERE" in str(em.get("password")):
        return False, "email.password is the example placeholder"
    if not (em.get("allowed_senders") or em.get("allowed_recipients")):
        return False, "email allowlist empty (allowed_senders/allowed_recipients)"
    return True, ""


def read_cursor() -> int:
    if CURSOR_FILE.exists():
        try:
            return int(CURSOR_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            return 0
    return 0


def write_cursor(value: int) -> None:
    CURSOR_FILE.write_text(str(value), encoding="utf-8")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _plain_text_body(msg: Message, max_chars: int = 4000) -> str:
    """Extract text/plain only. HTML and attachments are ignored entirely."""
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disposition.lower():
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    parts.append(payload.decode(charset, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    parts.append(payload.decode("utf-8", errors="replace"))
    else:
        if msg.get_content_type() == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload is not None:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    parts.append(payload.decode(charset, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    parts.append(payload.decode("utf-8", errors="replace"))
    text = "\n".join(p for p in parts if p).strip()
    return text[:max_chars]


def _allowed(from_addr: str, to_addrs: list[str], cfg: dict[str, Any]) -> bool:
    em = cfg.get("email") or {}
    allowed_senders = {a.lower() for a in (em.get("allowed_senders") or [])}
    allowed_recipients = {a.lower() for a in (em.get("allowed_recipients") or [])}
    if not (allowed_senders or allowed_recipients):
        return False
    if allowed_senders and from_addr.lower() in allowed_senders:
        return True
    if allowed_recipients and any(r.lower() in allowed_recipients for r in to_addrs):
        return True
    return False


def normalize_email(msg: Message, cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Pure: an email.message.Message -> queue record, or None to skip."""
    em = cfg.get("email") or {}
    from_name, from_addr = parseaddr(_decode(msg.get("From")))
    to_field = _decode(msg.get("To")) or ""
    cc_field = _decode(msg.get("Cc")) or ""
    # getaddresses parses RFC 5322 address lists correctly, including commas
    # inside quoted display names (a naive split(",") would drop the address).
    to_addrs = [addr for _name, addr in getaddresses([to_field, cc_field]) if addr]

    if not _allowed(from_addr, to_addrs, cfg):
        return None

    max_chars = int(em.get("max_message_chars") or 4000)
    subject = _decode(msg.get("Subject"))
    body = _plain_text_body(msg, max_chars=max_chars)

    # Subject leads the body so the summary is meaningful even for short mails.
    combined = (f"{subject}\n\n{body}" if subject else body).strip()
    has_attachment = any(
        "attachment" in str(p.get("Content-Disposition") or "").lower()
        for p in (msg.walk() if msg.is_multipart() else [msg])
    )

    if not combined and not has_attachment:
        return None  # genuinely empty, no attachment — skip as a non-message

    contributor = from_name.strip() or from_addr or "anonymous"
    channel_name = em.get("channel_name") or "email"

    return core.make_record(
        source="email",
        channel_name=channel_name,
        contributor=contributor,
        source_message_id=_decode(msg.get("Message-ID")) or "",
        text=combined,
        thread_ref=_decode(msg.get("References")) or _decode(msg.get("In-Reply-To")) or None,
        contact_ref=from_addr or None,
        attachment_only=bool(has_attachment and not combined),
        max_chars=max_chars,
    )


def fetch_messages(cfg: dict[str, Any]) -> tuple[list[Message], int | None]:
    """IMAP IO: connect, select folder, fetch messages with UID > cursor.

    Returns (messages, new_cursor). new_cursor is the UID to persist, or None
    if nothing advanced. The cursor is clamped below the first UID that failed
    to fetch so a transient mid-batch failure is retried next poll rather than
    silently skipped. The caller persists the cursor only after a durable
    append (see write_cursor / poll's commit).
    """
    em = cfg.get("email") or {}
    host = em["imap_host"]
    port = int(em.get("imap_port") or 993)
    folder = em.get("folder") or "INBOX"
    last_uid = read_cursor()

    messages: list[Message] = []
    highest = last_uid
    min_failed: int | None = None
    timeout = int(em.get("imap_timeout_seconds") or 30)
    try:
        conn = imaplib.IMAP4_SSL(host, port, timeout=timeout)
    except OSError as exc:
        print(f"[email] connect failed: {exc}", file=sys.stderr)
        return [], None
    try:
        conn.login(em["username"], em["password"])
        conn.select(folder, readonly=True)
        # First run (no cursor): fast-forward to the newest UID and ingest
        # NOTHING. This mailbox is a real, busy inbox (the alias just routes into
        # it), so an "ALL" backfill would try to download the entire history and
        # hang. We only want feedback that arrives AFTER setup; to deliberately
        # backfill, seed .last_email_uid manually.
        if last_uid <= 0:
            typ, data = conn.uid("search", None, "ALL")
            if typ != "OK":
                return [], None
            uids = data[0].split() if data and data[0] else []
            newest = max((int(u) for u in uids), default=0)
            return [], (newest or None)
        # UID search for anything newer than the cursor.
        criterion = f"UID {last_uid + 1}:*"
        typ, data = conn.uid("search", None, criterion)
        if typ != "OK":
            return [], None
        uids = [u for u in (data[0].split() if data and data[0] else [])]
        for raw_uid in uids:
            uid = int(raw_uid)
            if uid <= last_uid:
                continue  # IMAP "UID n:*" can return the boundary message
            typ, fetched = conn.uid("fetch", raw_uid, "(RFC822)")
            if typ != "OK" or not fetched or not fetched[0]:
                min_failed = uid if min_failed is None else min(min_failed, uid)
                print(f"[email] fetch failed for UID {uid}; will retry next poll", file=sys.stderr)
                continue
            msg = email.message_from_bytes(fetched[0][1])
            messages.append(msg)
            highest = max(highest, uid)
    except imaplib.IMAP4.error as exc:
        print(f"[email] IMAP error: {exc}", file=sys.stderr)
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    # Never advance the cursor past a UID we failed to fetch (order-independent).
    if min_failed is not None:
        highest = min(highest, min_failed - 1)
    new_cursor = highest if highest > last_uid else None
    return messages, new_cursor


def poll(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
    """Returns (records, commit). commit() persists the cursor; the caller
    invokes it only after a durable append so a failed append never skips
    un-written messages."""
    messages, new_cursor = fetch_messages(cfg)
    records: list[dict[str, Any]] = []
    for msg in messages:
        rec = normalize_email(msg, cfg)
        if rec is not None:
            records.append(rec)

    def commit() -> None:
        if new_cursor is not None:
            write_cursor(new_cursor)

    return records, commit
