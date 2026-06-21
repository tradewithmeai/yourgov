"""Grounding and context assembly for the YourGov explainer.

The explainer is grounded in three layers, in priority order:
  1. The CLICK — what the citizen clicked is first-class context. It dominates
     the opening turns and then decays into background as the chat broadens.
  2. The DIVISION SUMMARY — when a division is in context we inject a structured,
     DB-derived summary (precise lookup by id, not retrieval).
  3. The GROUNDING DOCS — YourGov self-knowledge + a parliamentary glossary,
     injected directly (the corpus is small, so no RAG is needed in phase 1).

Cross-division semantic retrieval (embeddings/RAG) and live Wikipedia fetch are
deliberately deferred to phase 2; this module keeps everything deterministic.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

# Bump to invalidate every cached opening-turn explanation at once (e.g. after a
# prompt or grounding change).
SELECTION_CACHE_VERSION = "sel-v1"

# A party is treated as having a whip position on a division only when at least
# this fraction of its voting members went the same way; members who went the
# other way are flagged as voting against the party majority (rebels).
PARTY_MAJORITY_THRESHOLD = 0.60

# The click stays the dominant focus for this many turns, then decays to a
# one-line background reference so the explainer can follow a broadening chat.
CLICK_FOCUS_TURNS = 3

# Keep prompt size bounded even though the docs are small.
_MAX_DOC_CHARS = 14000

_DOC_FILES = (
    "docs/explainer/yourgov-self-knowledge.md",
    "docs/explainer/parliamentary-glossary.md",
)

_GROUNDING_CACHE: dict | None = None


def load_grounding_docs(root: str | os.PathLike | None = None) -> str:
    """Return the concatenated grounding docs, cached after first read.

    Missing docs degrade gracefully to an empty string so the explainer still
    works (just less grounded) if a doc has not been written yet.
    """
    global _GROUNDING_CACHE
    base = Path(root) if root is not None else Path(__file__).resolve().parent
    key = str(base)
    if _GROUNDING_CACHE is not None and _GROUNDING_CACHE.get("key") == key:
        return _GROUNDING_CACHE["text"]

    parts: list[str] = []
    for rel in _DOC_FILES:
        path = base / rel
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(text[:_MAX_DOC_CHARS])
    text = "\n\n---\n\n".join(parts)
    _GROUNDING_CACHE = {"key": key, "text": text}
    return text


def clear_grounding_cache() -> None:
    """Drop the cached docs (used by tests that write temp docs)."""
    global _GROUNDING_CACHE
    _GROUNDING_CACHE = None


def _outcome(aye: int, no: int) -> str:
    if aye > no:
        return "passed"
    if no > aye:
        return "rejected"
    return "tied"


def build_division_summary(conn, division_id: int) -> dict | None:
    """Build a structured, explainer-ready summary of one division from the DB.

    Uses a precise lookup by division id (no retrieval) and returns None when the
    division is not present locally. Computes the headline result, per-party
    split, and the members who voted against their party's clear majority.
    """
    meta = conn.execute(
        """
        SELECT title, division_date, aye_count, no_count
        FROM votes WHERE division_id = ? LIMIT 1
        """,
        (division_id,),
    ).fetchone()
    if not meta:
        return None

    rows = conn.execute(
        """
        SELECT v.member_id AS member_id, v.voted_aye AS voted_aye,
               m.name AS name, m.party AS party
        FROM votes v LEFT JOIN members m ON m.member_id = v.member_id
        WHERE v.division_id = ?
        """,
        (division_id,),
    ).fetchall()

    aye_count = int(meta["aye_count"] or 0)
    no_count = int(meta["no_count"] or 0)

    # Per-party split + majority position.
    party_counts: dict[str, dict[int, int]] = {}
    for r in rows:
        party = (r["party"] or "").strip()
        v = r["voted_aye"]
        if not party or v not in (0, 1):
            continue
        c = party_counts.setdefault(party, {0: 0, 1: 0})
        c[v] += 1

    party_majorities: dict[str, int] = {}
    party_breakdown: list[dict] = []
    for party, c in party_counts.items():
        total = c[0] + c[1]
        if total <= 0:
            continue
        if c[1] / total >= PARTY_MAJORITY_THRESHOLD:
            party_majorities[party] = 1
        elif c[0] / total >= PARTY_MAJORITY_THRESHOLD:
            party_majorities[party] = 0
        party_breakdown.append({"party": party, "aye": c[1], "no": c[0]})
    party_breakdown.sort(key=lambda p: (p["aye"] + p["no"]), reverse=True)

    # Members who voted against their party's clear majority position.
    rebels: list[dict] = []
    for r in rows:
        party = (r["party"] or "").strip()
        v = r["voted_aye"]
        if party in party_majorities and v in (0, 1) and v != party_majorities[party]:
            rebels.append({
                "name": r["name"] or "Unknown member",
                "party": party,
                "voted": "Aye" if v == 1 else "No",
            })
    rebels.sort(key=lambda x: x["party"])

    return {
        "division_id": division_id,
        "title": meta["title"] or "Untitled division",
        "date": (meta["division_date"] or "")[:10],
        "aye_count": aye_count,
        "no_count": no_count,
        "outcome": _outcome(aye_count, no_count),
        "total_recorded": aye_count + no_count,
        "party_breakdown": party_breakdown,
        "rebel_count": len(rebels),
        "notable_rebels": rebels[:8],
    }


def render_division_summary(summary: dict, compact: bool = False) -> str:
    """Render a division summary as compact text for prompt injection."""
    if not summary:
        return ""
    head = (
        f'Division {summary["division_id"]} — "{summary["title"]}" '
        f'({summary["date"]}). Result: {summary["outcome"].upper()} '
        f'(Ayes {summary["aye_count"]}, Noes {summary["no_count"]}).'
    )
    if compact:
        return head

    lines = [head]
    if summary["party_breakdown"]:
        parts = ", ".join(
            f'{p["party"]} {p["aye"]}-{p["no"]}'
            for p in summary["party_breakdown"][:8]
        )
        lines.append(f"Party split (Aye-No): {parts}.")
    if summary["rebel_count"]:
        rebels = "; ".join(
            f'{r["name"]} ({r["party"]}, voted {r["voted"]})'
            for r in summary["notable_rebels"]
        )
        more = "" if summary["rebel_count"] <= len(summary["notable_rebels"]) else \
            f' and {summary["rebel_count"] - len(summary["notable_rebels"])} more'
        lines.append(f"Voted against their party majority: {rebels}{more}.")
    else:
        lines.append("No members voted against a clear party majority on this division.")
    return "\n".join(lines)


SAFETY_RULES = (
    "STRICT RULES (never break):\n"
    "- Factual only. Never infer intent, motivation, guilt, corruption, hypocrisy, or character.\n"
    "- Never treat absence of a vote or record as evidence of wrongdoing or disinterest.\n"
    "- Distinguish clearly between what the public record SHOWS and what it does NOT prove.\n"
    '- Use language like "the public record shows" or "according to the division record".\n'
    "- No best/worst-MP ranking, no political recommendations, no \"broke a promise\" claims "
    "without source-linked pledge evidence.\n"
    "- Records can be incomplete or lag current events; a recorded vote shows what happened, not why."
)


def assemble_system_prompt(
    level_name: str,
    level_instruction: str,
    grounding: str,
    division_summary_text: str,
    click_context: str,
    turn_index: int,
) -> str:
    """Assemble the system prompt with click-focus decay.

    turn_index is the number of prior user turns: 0 is the opening click. For the
    first CLICK_FOCUS_TURNS turns the clicked element + full division summary lead;
    afterwards the click decays to a one-line background reference and the
    grounding + conversation lead, so a broadened question can still be answered.
    """
    decayed = turn_index >= CLICK_FOCUS_TURNS

    sections = [
        "You are a neutral parliamentary explainer for a UK civic accountability app (YourGov).",
        f"Explanation depth: {level_name}\n{level_instruction}",
        SAFETY_RULES,
    ]

    if not decayed:
        if click_context:
            sections.append(f"CURRENT FOCUS — the citizen clicked:\n{click_context}")
        if division_summary_text:
            sections.append(f"DIVISION IN CONTEXT (use this as primary evidence):\n{division_summary_text}")
    else:
        if click_context:
            sections.append(
                "This conversation began from the citizen clicking: "
                f"{click_context}\nThe discussion has broadened — answer the latest "
                "question directly using the conversation and the reference material "
                "below, while staying factual and within the rules."
            )
        if division_summary_text:
            sections.append(f"Originating division (background): {division_summary_text}")

    if grounding:
        sections.append(
            "REFERENCE MATERIAL (YourGov self-knowledge + parliamentary glossary — "
            "use to ground definitions and app facts; cite naturally, do not quote verbatim):\n"
            + grounding
        )

    sections.append(
        "Respond with a JSON object with exactly these keys: clicked, meaning, "
        "source_support, does_not_prove, followups. 'meaning' carries your main "
        "answer (obeying the depth instruction). 'followups' is an array of 2-3 "
        "plain-English follow-up questions the citizen might ask next."
    )
    return "\n\n".join(sections)


def is_cacheable_turn(followup_question: str, history) -> bool:
    """An opening turn (a fresh click, no follow-up and no prior conversation) is
    deterministic for the same inputs, so it is safe to cache. Follow-ups depend
    on the conversation and are never cached."""
    if (followup_question or "").strip():
        return False
    return not history


def selection_cache_key(parts) -> str:
    """Stable cache key from a list of string parts. The caller chooses the parts:
    for a division click, key on (level, division id, vote fingerprint, element
    type) so every user clicking that division shares one cached answer AND an
    attacker cannot force endless cache misses by mutating free-text fields; for a
    non-division click the click text is included. The division fingerprint means a
    corrected division naturally invalidates its cached explanation."""
    raw = "|".join([SELECTION_CACHE_VERSION] + [str(p) for p in parts])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_EXPLAIN_TYPE_MAP = {
    "division": "division",
    "division-row": "division",
    "vote": "vote",
    "mp": "mp",
}


def normalise_explain_type(raw) -> str:
    """Collapse the client-supplied explain_type to a small fixed set so it is safe
    to include in the cache key — an attacker can produce at most these few values,
    bounding cache-miss inflation, while genuine element types (division row vs a
    specific MP vote) still get distinct cached answers."""
    key = raw.strip().lower() if isinstance(raw, str) else ""
    return _EXPLAIN_TYPE_MAP.get(key, "other")


def sliding_window_allow(store: dict, key: str, now: float, window: float, max_hits: int) -> bool:
    """Record a hit for `key` and return whether it is within `max_hits` over the
    trailing `window` seconds. Mutates `store` (a dict of key -> [timestamps]).
    Pure and testable; the same primitive serves the per-minute and per-day caps.
    """
    hits = [t for t in store.get(key, []) if now - t < window]
    if len(hits) >= max_hits:
        store[key] = hits
        return False
    hits.append(now)
    store[key] = hits
    return True


def normalise_history(messages, limit: int = 8) -> list[dict]:
    """Sanitise a client-supplied chat history into [{role, content}] pairs.

    Keeps only user/assistant roles with non-empty string content, trims to the
    most recent `limit` messages, and bounds each message length — which also caps
    how large a hostile client can make the prompt (and so the per-call cost).
    """
    out: list[dict] = []
    if not isinstance(messages, list):
        return out
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        out.append({"role": role, "content": content[:1200]})
    return out[-limit:]
