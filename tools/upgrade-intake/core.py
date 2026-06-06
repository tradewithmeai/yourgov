"""
Shared core for the upgrade-intake tool.

This module holds everything that is NOT channel-specific:

- record schema assembly
- summary derivation
- category / kind / priority classification
- deterministic junk detection
- stable content-hash IDs
- append-only queue writes
- "latest record per id" resolution (used by the inspector and triage)

Safety model (read before changing):

- Message text is data only. It is never exec'd, eval'd, shell'd, or passed
  to a template engine.
- We only ever APPEND to the queue file. We never edit, delete, rewrite, or
  git anything.
- Likely junk is preserved (status="junk" + junk_reason), never deleted.

Every path is injectable: pass `queue_file=` to the read/write helpers so
tests can use a temp file and never touch the real queue.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
QUEUE_DIR = HERE / "queue"
QUEUE_FILE = QUEUE_DIR / "upgrade-queue.jsonl"

# --- enums kept in one place so adapters/tests agree -----------------------

SOURCES = ("telegram", "whatsapp", "email")
KINDS = (
    "complaint",
    "suggestion",
    "bug",
    "feature",
    "data_issue",
    "ux_issue",
    "praise",
    "needs_review",
)
CATEGORIES = ("bug", "ux", "feature", "data", "needs_review")
PRIORITIES = ("low", "medium", "high", "unknown")
STATUSES = (
    "queued",
    "needs_review",
    "junk",
    "reviewed",
    "accepted",
    "rejected",
    "deferred",
    "implemented",
)
DECISION_STATUSES = ("accepted", "rejected", "deferred", "junk", "implemented", "reviewed")

URL_RE = re.compile(r"https?://\S+")

CATEGORY_HINTS = {
    "bug": ("bug", "broken", "error", "crash", "regression", "doesn't work", "does not work", "fails", "exception", "traceback"),
    "ux": ("ux", "ui", "design", "label", "spacing", "alignment", "colour", "color", "confusing", "cluttered", "hard to read"),
    "feature": ("feature", "would be nice", "could you add", "request", "wish", "please add", "support for"),
    "data": ("data", "stats", "missing record", "wrong number", "count", "vote total", "incorrect"),
}

# Order matters: more specific signals first. The complaint/suggestion split
# is the important one, so it is handled explicitly.
KIND_HINTS = (
    ("bug", ("bug", "broken", "crash", "error", "exception", "traceback", "500 error", "doesn't work", "does not work", "stopped working")),
    ("data_issue", ("wrong number", "wrong count", "wrong total", "incorrect data", "missing record", "wrong vote", "data is wrong", "stats are wrong", "wrong figure")),
    ("ux_issue", ("confusing", "hard to find", "hard to read", "cluttered", "layout", "too small", "overlapping", "bad design")),
    ("praise", ("thank you", "thanks", "great work", "love this", "well done", "brilliant", "awesome", "really helpful", "this is great")),
    ("feature", ("please add", "could you add", "would be nice", "feature request", "it would help if", "add support", "wish you")),
    ("suggestion", ("suggest", "suggestion", "you should", "you could", "consider", "maybe", "why not", "it would be better", "i recommend", "i'd recommend")),
    ("complaint", ("complaint", "complain", "terrible", "awful", "useless", "rubbish", "angry", "disappointed", "unacceptable", "frustrat", "not happy", "hate")),
)

PRIORITY_HINTS = {
    "high": ("urgent", "critical", "blocker", "production down", "asap", "can't use", "completely broken"),
    "medium": ("important", "soon", "should fix", "annoying"),
    "low": ("nit", "small", "minor", "nice to have", "someday", "cosmetic"),
}

# Deterministic spam phrases. Kept lowercase; matched case-insensitively.
SPAM_PHRASES = (
    "crypto giveaway",
    "free bitcoin",
    "free btc",
    "double your",
    "investment opportunity",
    "betting tips",
    "sure bet",
    "casino bonus",
    "adult content",
    "xxx",
    "loan offer",
    "guaranteed loan",
    "make money fast",
    "earn $",
    "work from home and earn",
    "telegram.me/joinchat",
    "click here to win",
    "you have won",
)

# Phrases that rescue an otherwise-too-short message from the junk filter.
BUG_COMPLAINT_PHRASES = (
    "bug",
    "broken",
    "crash",
    "error",
    "wrong",
    "fail",
    "doesn't",
    "does not",
    "can't",
    "cannot",
    "missing",
    "404",
    "500",
)

MIN_MEANINGFUL_CHARS = 12


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def derive_summary(text: str, limit: int = 140) -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    cleaned = re.sub(r"\s+", " ", first_line).strip()
    if not cleaned:
        return "(no summary)"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def classify_category(text: str) -> str:
    lower = text.lower()
    for cat, hints in CATEGORY_HINTS.items():
        if any(h in lower for h in hints):
            return cat
    return "needs_review"


def classify_kind(text: str) -> str:
    lower = text.lower()
    for kind, hints in KIND_HINTS:
        if any(h in lower for h in hints):
            return kind
    return "needs_review"


def classify_priority(text: str) -> str:
    lower = text.lower()
    for level, hints in PRIORITY_HINTS.items():
        if any(h in lower for h in hints):
            return level
    return "unknown"


def extract_evidence(text: str) -> list[str]:
    return URL_RE.findall(text)


def stable_id(channel_name: str, contributor: str, summary: str) -> str:
    seed = f"{channel_name.strip().lower()}|{contributor.strip().lower()}|{summary.strip().lower()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def detect_junk(text: str, attachment_only: bool = False) -> tuple[bool, str | None]:
    """Deterministic, rule-based junk detection. No LLM.

    Returns (is_junk, reason). Junk is preserved, not deleted; the reason is
    stored so a human can audit why it was filtered.
    """
    stripped = (text or "").strip()
    if not stripped:
        if attachment_only:
            return True, "attachment_only_no_text"
        return True, "empty_after_strip"

    lower = stripped.lower()
    urls = URL_RE.findall(stripped)
    without_urls = URL_RE.sub("", stripped).strip()

    if urls and not without_urls:
        return True, "link_only"
    if len(urls) > 3:
        return True, "too_many_urls"

    for phrase in SPAM_PHRASES:
        if phrase in lower:
            return True, f"spam_phrase:{phrase}"

    # Repeated-character spam, e.g. "aaaaaaaaaaa" or "!!!!!!!!!!".
    if re.search(r"(.)\1{9,}", stripped):
        return True, "repeated_chars"

    # Very short text, unless it clearly names a bug/complaint.
    if len(without_urls) < MIN_MEANINGFUL_CHARS and not any(b in lower for b in BUG_COMPLAINT_PHRASES):
        return True, "too_short"

    return False, None


def make_record(
    *,
    source: str,
    channel_name: str,
    contributor: str,
    source_message_id: str,
    text: str,
    extra_evidence: list[str] | None = None,
    thread_ref: str | None = None,
    contact_ref: str | None = None,
    attachment_only: bool = False,
    max_chars: int = 4000,
) -> dict[str, Any]:
    """Assemble one normalised queue record from already-extracted fields.

    This is pure: no IO, no network. Adapters extract channel-specific fields
    then hand them here so every source produces the identical schema.
    """
    if source not in SOURCES:
        raise ValueError(f"unknown source: {source!r}")

    raw = text or ""
    if len(raw) > max_chars:
        raw = raw[:max_chars]

    summary = derive_summary(raw)
    category = classify_category(raw)
    kind = classify_kind(raw)
    priority = classify_priority(raw)

    evidence = extract_evidence(raw)
    if extra_evidence:
        for item in extra_evidence:
            if item and item not in evidence:
                evidence.append(item)

    is_junk, junk_reason = detect_junk(raw, attachment_only=attachment_only)

    contributor = (contributor or "").strip() or "anonymous"
    channel_name = channel_name or "unknown"

    if is_junk:
        status = "junk"
    elif category == "needs_review":
        status = "needs_review"
    else:
        status = "queued"

    rec: dict[str, Any] = {
        "id": stable_id(channel_name, contributor, summary),
        "timestamp": now_iso(),
        "contributor": contributor,
        "source": source,
        "channel_name": channel_name,
        "source_message_id": str(source_message_id or ""),
        "summary": summary,
        "kind": kind,
        "category": category,
        "priority": priority,
        "evidence": evidence,
        "raw_message": raw,
        "status": status,
    }
    if is_junk and junk_reason:
        rec["junk_reason"] = junk_reason
    if thread_ref:
        rec["thread_ref"] = thread_ref
    if contact_ref:
        rec["contact_ref"] = contact_ref
    return rec


# --- queue IO --------------------------------------------------------------


def load_records(queue_file: Path | None = None) -> list[dict[str, Any]]:
    # Resolve the module global at call time so tests can monkeypatch
    # core.QUEUE_FILE and have every default-path caller follow suit.
    queue_file = Path(QUEUE_FILE if queue_file is None else queue_file)
    if not queue_file.exists():
        return []
    out: list[dict[str, Any]] = []
    with queue_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def latest_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse an append-only log to the latest record per id.

    Later lines override earlier ones (that is how triage decisions take
    effect). Order follows first appearance, which is stable for humans.
    """
    latest: dict[str, dict[str, Any]] = {}
    for rec in records:
        rid = rec.get("id")
        if not isinstance(rid, str):
            continue
        latest[rid] = rec
    return list(latest.values())


def find_by_prefix(records: Iterable[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """Latest records whose id starts with `prefix`. Used by triage/show."""
    return [r for r in latest_records(records) if r.get("id", "").startswith(prefix)]


def load_seen_ids(queue_file: Path | None = None) -> set[str]:
    seen: set[str] = set()
    for rec in load_records(queue_file):
        rid = rec.get("id")
        if isinstance(rid, str):
            seen.add(rid)
    return seen


def append_records(records: Iterable[dict[str, Any]], queue_file: Path | None = None) -> int:
    queue_file = Path(QUEUE_FILE if queue_file is None else queue_file)
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with queue_file.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return written
