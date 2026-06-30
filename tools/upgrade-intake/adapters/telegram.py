"""Telegram adapter.

Preserves the original behaviour: polling `getUpdates` (no webhook), an
allowlist on (chat_id, chat_name, username), and a `.last_update_id` cursor.

- `fetch_updates(...)` does the network IO.
- `normalize_update(update, cfg)` is pure: a Telegram update dict -> record
  (or None if it is not an allowlisted, text-bearing message).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse, request

import core

CURSOR_FILE = core.HERE / ".last_update_id"


def required_config_ok(cfg: dict[str, Any]) -> tuple[bool, str]:
    tg = cfg.get("telegram") or cfg
    token = tg.get("telegram_bot_token") or tg.get("bot_token")
    if not token or "PUT-YOUR-BOT-TOKEN" in str(token):
        return False, "telegram_bot_token missing or placeholder"
    if not (tg.get("allowed_chat_ids") or tg.get("allowed_chat_names") or tg.get("allowed_usernames")):
        return False, "telegram allowlist empty (allowed_chat_ids/names/usernames)"
    return True, ""


def _tg(cfg: dict[str, Any]) -> dict[str, Any]:
    return cfg.get("telegram") or cfg


def read_cursor() -> int:
    if CURSOR_FILE.exists():
        try:
            return int(CURSOR_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            return 0
    return 0


def write_cursor(value: int) -> None:
    CURSOR_FILE.write_text(str(value), encoding="utf-8")


def fetch_updates(token: str, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
    params = parse.urlencode(
        {
            "timeout": timeout,
            "offset": offset,
            "allowed_updates": json.dumps(["message", "channel_post"]),
        }
    )
    url = f"https://api.telegram.org/bot{token}/getUpdates?{params}"
    req = request.Request(url, headers={"User-Agent": "yourgov-upgrade-intake/1.0"})
    try:
        with request.urlopen(req, timeout=timeout + 5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError) as exc:
        print(f"[telegram] network error: {exc}", file=sys.stderr)
        return []
    except json.JSONDecodeError as exc:
        print(f"[telegram] returned non-JSON: {exc}", file=sys.stderr)
        return []
    if not payload.get("ok"):
        print(f"[telegram] returned not-ok: {payload}", file=sys.stderr)
        return []
    return payload.get("result", []) or []


def is_allowed(message: dict[str, Any], cfg: dict[str, Any]) -> bool:
    tg = _tg(cfg)
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    chat_id = chat.get("id")
    chat_title = chat.get("title") or chat.get("username") or ""
    username = user.get("username") or ""

    allowed_ids = set(tg.get("allowed_chat_ids") or [])
    allowed_names = {n.lower() for n in (tg.get("allowed_chat_names") or [])}
    allowed_users = {u.lower() for u in (tg.get("allowed_usernames") or [])}

    if not (allowed_ids or allowed_names or allowed_users):
        return False
    if allowed_ids and chat_id in allowed_ids:
        return True
    if allowed_names and chat_title.lower() in allowed_names:
        return True
    if allowed_users and username.lower() in allowed_users:
        return True
    return False


def normalize_update(update: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Pure: Telegram update -> queue record, or None to skip."""
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return None
    if not is_allowed(msg, cfg):
        return None

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text:
        return None  # non-text message (sticker, etc.) — skip, not junk

    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    channel_name = chat.get("title") or chat.get("username") or str(chat.get("id") or "unknown")
    contributor = " ".join(
        p for p in (user.get("first_name") or "", user.get("last_name") or "") if p
    ).strip() or (user.get("username") or "anonymous")

    max_chars = int(_tg(cfg).get("max_message_chars") or 4000)
    return core.make_record(
        source="telegram",
        channel_name=channel_name,
        contributor=contributor,
        source_message_id=str(msg.get("message_id") or ""),
        text=text,
        thread_ref=str(chat.get("id")) if chat.get("id") is not None else None,
        contact_ref=("@" + user["username"]) if user.get("username") else None,
        max_chars=max_chars,
    )


def poll(cfg: dict[str, Any], timeout: int = 2) -> tuple[list[dict[str, Any]], Any]:
    """Fetch + normalise one batch.

    Returns (records, commit). The cursor is NOT advanced here — the caller
    invokes commit() only after the records are durably appended, so a failed
    append never strands acknowledged updates. (Telegram drops acked updates
    once the offset moves, so committing early would lose them permanently.)
    """
    token = _tg(cfg).get("telegram_bot_token") or _tg(cfg).get("bot_token")
    offset = read_cursor()
    updates = fetch_updates(token, offset, timeout=timeout)
    records: list[dict[str, Any]] = []
    last_update_id = offset - 1 if offset else 0
    for upd in updates:
        upd_id = int(upd.get("update_id") or 0)
        if upd_id > last_update_id:
            last_update_id = upd_id
        rec = normalize_update(upd, cfg)
        if rec is not None:
            records.append(rec)

    new_cursor = (last_update_id + 1) if updates else None

    def commit() -> None:
        if new_cursor is not None:
            write_cursor(new_cursor)

    return records, commit
