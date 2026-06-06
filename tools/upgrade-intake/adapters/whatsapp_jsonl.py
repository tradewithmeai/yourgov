"""WhatsApp adapter (JSONL consumer).

MVP: consumes a JSONL file produced by the existing linked-device WhatsApp
bridge (e.g. `incoming-pdfs/messages.jsonl`). It does NOT talk to WhatsApp
itself. The bridge connects as a linked device, which is a non-official
protocol and may break — that is a documented caveat, not something this
tool can control.

Expected bridge fields per line:
  messageId, chatJid, senderJid, senderName, timestamp, kind, text,
  fileName, mimeType, fromMe

- `iter_records(path)` reads the JSONL file (IO).
- `normalize_record(obj, cfg)` is pure: one bridge dict -> queue record (or
  None to skip).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import core

CURSOR_FILE = core.HERE / ".last_whatsapp_message_id"

TEXT_KINDS = {"text", "caption", "document", "image", "video"}

# Cap the persisted seen-id file so a long-lived bridge log can't grow it
# without bound. The most-recent ids are kept; any older id that falls out is
# still protected from re-queueing by the queue-level stable_id dedupe.
SEEN_CAP = 10000


def required_config_ok(cfg: dict[str, Any], jsonl_path: str | None = None) -> tuple[bool, str]:
    wa = cfg.get("whatsapp") or {}
    path = jsonl_path or wa.get("jsonl_path")
    if not path:
        return False, "whatsapp jsonl path missing (--whatsapp-jsonl or whatsapp.jsonl_path)"
    if not (wa.get("allowed_chat_jids") or wa.get("allowed_sender_jids")):
        return False, "whatsapp allowlist empty (allowed_chat_jids/allowed_sender_jids)"
    return True, ""


def read_seen() -> set[str]:
    if not CURSOR_FILE.exists():
        return set()
    return {
        line.strip()
        for line in CURSOR_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def write_seen(ordered_ids: list[str]) -> None:
    """Persist the most-recent message ids (in file order), capped at SEEN_CAP."""
    capped = ordered_ids[-SEEN_CAP:] if len(ordered_ids) > SEEN_CAP else ordered_ids
    CURSOR_FILE.write_text("\n".join(capped), encoding="utf-8")


def is_allowed(obj: dict[str, Any], cfg: dict[str, Any]) -> bool:
    wa = cfg.get("whatsapp") or {}
    allowed_chats = {c.lower() for c in (wa.get("allowed_chat_jids") or [])}
    allowed_senders = {s.lower() for s in (wa.get("allowed_sender_jids") or [])}
    if not (allowed_chats or allowed_senders):
        return False
    chat = str(obj.get("chatJid") or "").lower()
    sender = str(obj.get("senderJid") or "").lower()
    if allowed_chats and chat in allowed_chats:
        return True
    if allowed_senders and sender in allowed_senders:
        return True
    return False


def normalize_record(obj: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Pure: one bridge JSONL dict -> queue record, or None to skip."""
    if obj.get("fromMe"):
        return None  # never ingest our own outgoing messages
    if not is_allowed(obj, cfg):
        return None

    kind = str(obj.get("kind") or "").lower()
    if kind and kind not in TEXT_KINDS:
        return None  # e.g. audio/sticker with no useful text

    text = (obj.get("text") or "").strip()
    file_name = obj.get("fileName") or ""
    has_attachment = bool(file_name or obj.get("mimeType"))

    if not text and not has_attachment:
        return None  # nothing usable — skip as a non-message

    contributor = (obj.get("senderName") or obj.get("senderJid") or "anonymous").strip()
    channel_name = (cfg.get("whatsapp") or {}).get("channel_name") or str(obj.get("chatJid") or "whatsapp")
    extra_evidence = [file_name] if file_name else None

    max_chars = int((cfg.get("whatsapp") or {}).get("max_message_chars") or 4000)
    return core.make_record(
        source="whatsapp",
        channel_name=channel_name,
        contributor=contributor,
        source_message_id=str(obj.get("messageId") or ""),
        text=text,
        extra_evidence=extra_evidence,
        thread_ref=str(obj.get("chatJid")) if obj.get("chatJid") else None,
        contact_ref=str(obj.get("senderJid")) if obj.get("senderJid") else None,
        attachment_only=bool(has_attachment and not text),
        max_chars=max_chars,
    )


def iter_records(path: str | Path) -> Iterator[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return
    # utf-8-sig drops a leading BOM if the exporter wrote one.
    with path.open("r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def poll(cfg: dict[str, Any], jsonl_path: str | None = None) -> tuple[list[dict[str, Any]], Any]:
    """Returns (records, commit). commit() persists the seen-id set; the caller
    invokes it only after a durable append so a failed append never marks
    un-written messages as seen."""
    wa = cfg.get("whatsapp") or {}
    path = jsonl_path or wa.get("jsonl_path")
    if not path:
        return [], (lambda: None)
    seen = read_seen()
    records: list[dict[str, Any]] = []
    ordered_ids: list[str] = []  # all ids in file order, for a recency-capped commit
    for obj in iter_records(path):
        mid = str(obj.get("messageId") or "")
        if mid:
            ordered_ids.append(mid)
        if mid and mid in seen:
            continue
        rec = normalize_record(obj, cfg)
        if rec is not None:
            records.append(rec)
        if mid:
            seen.add(mid)

    def commit() -> None:
        write_seen(ordered_ids)

    return records, commit
