# -*- coding: utf-8 -*-
import os
import gzip
import shutil
import sqlite3
import json
import re
import time
from difflib import SequenceMatcher
from copy import deepcopy
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
import httpx

import explainer_context as ec

app = Flask(__name__)
# Cache-busting for static assets so real users don't get stale JS/CSS after deploys.
app.config["ASSET_VERSION"] = os.environ.get("ASSET_VERSION") or str(int(time.time()))
# Bound request bodies so a hostile oversized payload can't be used to inflate the
# explainer's prompt (and cost) or exhaust memory. Generous for legit JSON bodies.
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_CONTENT_LENGTH", str(256 * 1024)))
_SEED_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mygov.db")
_SEED_GZ = _SEED_DB + ".gz"


def _ensure_seed_db():
    """The full-history seed DB ships gzipped (the raw file is ~280MB, over
    GitHub's 100MB limit and heavy for the FTPS deploy; gzipped it is ~31MB).
    Decompress mygov.db.gz -> mygov.db on first use. Prefer the raw file when it
    is present and at least as new as the archive (local dev / CI), so this is a
    no-op there. Falls back to /tmp if the app root is read-only."""
    global _SEED_DB
    raw, gz = _SEED_DB, _SEED_GZ
    raw_current = os.path.exists(raw) and (
        not os.path.exists(gz) or os.path.getmtime(raw) >= os.path.getmtime(gz)
    )
    if raw_current or not os.path.exists(gz):
        return
    # Prefer /tmp (the writable DB location) so we hold a single decompressed copy
    # rather than one at the app root plus the /tmp working copy; fall back to the
    # app root when there is no /tmp (local Windows dev).
    candidates = ["/tmp/mygov.db", raw] if os.path.exists("/tmp") else [raw]
    for target in candidates:
        try:
            if os.path.exists(target) and os.path.getmtime(target) >= os.path.getmtime(gz):
                _SEED_DB = target
                return
            with gzip.open(gz, "rb") as fsrc, open(target, "wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)
            _SEED_DB = target
            return
        except OSError:
            continue


_ensure_seed_db()
# The deployment root may be read-only; use /tmp for any writes when available.
_WRITABLE_DB = "/tmp/mygov.db" if os.path.exists("/tmp") else _SEED_DB
DB_PATH = _WRITABLE_DB


@app.context_processor
def _inject_asset_version():
    return {"asset_version": app.config.get("ASSET_VERSION", "")}


# A subtle, always-available "Feedback" link on every page. There is no shared
# base template (each page is standalone), so inject it once here rather than
# edit 24 templates (and miss future ones). It is a real <a> (keyboard-focusable,
# aria-labelled, visible focus ring), sits bottom-left clear of the map controls,
# and is unobtrusive until hovered/focused. Skips the feedback page itself, the
# embedded map iframe, and any non-HTML response.
_FEEDBACK_LINK_SNIPPET = (
    b'<a href="/feedback" id="global-feedback-link" '
    b'aria-label="Send feedback about YourGov" '
    b'style="position:fixed;left:12px;bottom:10px;z-index:9000;'
    b'font:600 12px/1 ui-sans-serif,system-ui,-apple-system,sans-serif;'
    b'letter-spacing:.02em;color:#cbd5e1;background:rgba(15,23,42,.72);'
    b'border:1px solid rgba(148,163,184,.32);border-radius:999px;'
    b'padding:6px 12px;text-decoration:none;opacity:.6;'
    b'backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);">Feedback</a>'
    b'<style>#global-feedback-link:hover,#global-feedback-link:focus-visible'
    b'{opacity:1;border-color:#22d3ee;color:#e6f6ff;outline:none;'
    b'box-shadow:0 0 0 2px rgba(34,211,238,.55)}'
    b'@media print{#global-feedback-link{display:none}}</style>'
)
_FEEDBACK_LINK_SKIP_PREFIXES = ("/feedback", "/map/relay", "/static", "/api")


@app.after_request
def _inject_feedback_link(response):
    try:
        path = request.path or ""
        if any(path == p or path.startswith(p + "/") or path == p
               for p in _FEEDBACK_LINK_SKIP_PREFIXES):
            return response
        if path.startswith("/feedback") or path.startswith("/map/relay"):
            return response
        ctype = response.headers.get("Content-Type", "")
        if "text/html" not in ctype or response.direct_passthrough:
            return response
        body = response.get_data()
        if b"</body>" not in body or b'id="global-feedback-link"' in body:
            return response
        response.set_data(body.replace(b"</body>", _FEEDBACK_LINK_SNIPPET + b"</body>", 1))
    except Exception:
        # A feedback link must never break a page render.
        return response
    return response


def _ensure_db():
    """Copy seed DB to /tmp; re-copy if the bundled seed is newer."""
    if DB_PATH == _SEED_DB:
        return
    import shutil
    if not os.path.exists(DB_PATH):
        shutil.copy2(_SEED_DB, DB_PATH)
        return
    if os.path.exists(_SEED_DB) and os.path.getmtime(_SEED_DB) > os.path.getmtime(DB_PATH):
        shutil.copy2(_SEED_DB, DB_PATH)

PARTY_COLOURS = {
    "Labour": "#e4003b",
    "Liberal Democrat": "#faa61a",
    "Conservative": "#0087dc",
    "Scottish National Party": "#fff95d",
    "Green Party": "#02a95b",
}

MODE_ALIASES = {
    "vote": "vote-split",
    "votes": "vote-split",
    "vote-split": "vote-split",
    "party": "party-split",
    "party-split": "party-split",
    "gender": "gender-split",
    "gender-split": "gender-split",
    "rebel": "rebel-split",
    "rebel-split": "rebel-split",
    "rebel-rate": "rebel-split",
}
DIVISION_MAP_MODES = {"vote-split", "party-split", "gender-split", "rebel-split"}
PARTY_MAJORITY_THRESHOLD = 0.60
VOTE_COLOURS = {
    "Aye": "#16a34a",
    "No": "#dc2626",
    "Absent/unknown": "#6b7280",
    "Vacant seat": "#111827",
}
GENDER_COLOURS = {
    "M": "#38bdf8",
    "F": "#f472b6",
    "Unknown": "#6b7280",
    "No current MP": "#111827",
}
REBEL_COLOURS = {
    "with_party_majority": "#16a34a",
    "against_party_majority": "#f59e0b",
    "no_clear_party_majority": "#64748b",
    "absent_or_unknown": "#6b7280",
    "independent_or_no_party_grouping": "#0ea5e9",
    "vacant_seat": "#111827",
}
# Party-split and gender-split are scoped to the SELECTED division: MPs who did not
# record an Aye/No on that division are shown as "Did not vote", so the colouring
# reflects who actually took part in this division rather than a constant national map.
DID_NOT_VOTE_KEY = "Did not vote"
DID_NOT_VOTE_COLOUR = "#6b7280"

MOCK_PLEDGES = [
    {"pledge": "Improve NHS waiting times in constituency", "status": "no_record", "label": "No public record found"},
    {"pledge": "Vote against cuts to public services", "status": "partial", "label": "Voted against 3 of 5 relevant divisions"},
    {"pledge": "Support local housing development", "status": "no_record", "label": "No questions tabled on this topic"},
]

ISSUE_TOPICS = {
    "NHS & Health": ["nhs", "health", "hospital", "social care", "mental health", "ambulance", "cancer"],
    "Housing": ["housing", "planning", "renters", "landlord", "leasehold", "affordable homes", "building safety"],
    "Climate & Energy": ["climate", "net zero", "renewable", "energy", "carbon", "environment", "green"],
    "Education": ["education", "school", "university", "tuition", "student", "ofsted", "teacher"],
    "Justice & Crime": ["crime", "policing", "courts", "tribunal", "victims", "justice", "prison", "sentencing"],
    "Defence & Security": ["defence", "military", "armed forces", "nato", "security"],
    "Immigration": ["immigration", "asylum", "refugee", "border", "migration", "visa"],
    "Employment & Pensions": ["employment", "workers", "wages", "pension", "trade union", "minimum wage"],
    "Devolution & Democracy": ["devolution", "northern ireland", "scotland", "wales", "local government", "representation of the people"],
}


EXPLAIN_PROMPT_VERSION = "v2"

_LEVEL_NAMES = {0: "SKIM", 1: "PRACTICAL", 2: "DETAILED", 3: "FULL"}
_LEVEL_TOKENS = {0: 40, 1: 120, 2: 200, 3: 320}
_LEVEL_INSTRUCTIONS = {
    0: (
        "Write ONE sentence only. Maximum 25 words. No jargon at all. "
        "Answer only: what was this vote basically about?"
    ),
    1: (
        "Write exactly 2–3 sentences. "
        "First sentence: what did voting Aye or No mean in practice for people in the UK? "
        "Second sentence: why should an ordinary voter care about this? "
        "No procedural or technical detail. Plain everyday English only."
    ),
    2: (
        "Write 4–6 sentences covering all of these: "
        "(1) what this division was about; "
        "(2) what the Aye and No outcomes each meant in practice; "
        "(3) broader context if clearly relevant to the title; "
        "(4) a caveat if the title is vague, technical, or procedural. "
        "Plain English. No bullet points."
    ),
    3: (
        "Write a structured explanation with exactly four labelled sections:\n"
        "**What this was:** One sentence on the subject of the division.\n"
        "**What Aye/No meant:** What each side voted for in practice.\n"
        "**Why it mattered:** The broader significance or practical implication.\n"
        "**Caveat:** What this record does not show or prove.\n"
        "Parliamentary terms are allowed but must be briefly explained inline. "
        "Maximum 220 words total."
    ),
}
_LEVEL_FALLBACKS = {
    0: "This was a recorded House of Commons vote.",
    1: (
        "This is a Parliamentary vote. The public record shows how this MP voted and the overall result. "
        "Check the Parliament source link for what it meant in practice."
    ),
    2: (
        "This is a recorded House of Commons division. The public record shows how this MP voted and the overall result. "
        "The division title indicates the subject matter, though the precise policy effect depends on the full legislative context."
    ),
    3: (
        "**What this was:** A recorded House of Commons division.\n"
        "**What Aye/No meant:** The public record shows the vote tally; the full legislative effect depends on the bill or motion.\n"
        "**Why it mattered:** Context depends on the subject — see the Parliament source link for details.\n"
        "**Caveat:** This record does not prove intent, motivation, or personal character."
    ),
}

_EXPLAIN_SYSTEM_PROMPT = """You are a neutral parliamentary explainer for a UK civic accountability app.
Explanation depth: {level_name}

{level_instructions}

STRICT RULES (all levels):
- Factual only. Never infer intent, motivation, morality, or character.
- Never suggest corruption, hypocrisy, or any judgment of the MP.
- Use language like "the public record shows" or "according to the division record".
- Do not add claims not supported by the division title and vote direction."""

# Used by Variant B auto-summaries — kept separate, do not remove
_EXPLAIN_BRIEF_PROMPT = """You are a plain-English explainer for a UK civic app. Given a Parliamentary division title and an MP's vote, write ONE sentence in plain English starting with "In practice," that tells a citizen what this vote meant for everyday life in the UK. Be direct and specific. Under 30 words. No jargon. Factual only — never infer intent or make judgements about the MP."""

_EXPLAIN_USER_TEMPLATE = "Division title: {title}\nMP voted: {vote_direction}\nWrite the explanation now."


def topic_to_slug(topic: str) -> str:
    return topic.lower().replace(" & ", "-").replace(" ", "-")


def slug_to_topic(slug: str) -> str | None:
    for t in ISSUE_TOPICS:
        if topic_to_slug(t) == slug:
            return t
    return None


def build_issue_spotlight(votes: list) -> list[dict]:
    results = []
    for topic, keywords in ISSUE_TOPICS.items():
        matched = []
        for v in votes:
            title_lower = (v["title"] or "").lower()
            if any(kw in title_lower for kw in keywords):
                matched.append(v)
        if matched:
            aye = sum(1 for v in matched if v["voted_aye"])
            no = len(matched) - aye
            results.append({
                "topic": topic,
                "total": len(matched),
                "aye": aye,
                "no": no,
                "recent": matched[:3],
            })
    return results


_migration_done = False


def get_conn():
    global _migration_done
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if not _migration_done:
        from db import _migrate_explanations, _migrate_activity_fetched, _migrate_pw_indexes
        _migrate_explanations(conn)
        _migrate_activity_fetched(conn)
        _migrate_pw_indexes(conn)
        _migration_done = True
    return conn


def get_publicwhip_conn():
    """Open the bundled seed DB read-only for PublicWhip-family routes."""
    try:
        conn = sqlite3.connect(f"file:{_SEED_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(_SEED_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _auto_ingest(member_id: int) -> bool:
    from parliament_client import get_member, get_votes, get_questions
    from db import init_db, upsert_member, upsert_votes, upsert_questions
    from datetime import datetime, timezone
    conn = get_conn()
    init_db(conn)
    member_data = get_member(member_id)
    if not member_data:
        conn.close()
        return False
    upsert_member(conn, member_id, member_data)
    upsert_votes(conn, member_id, get_votes(member_id))
    upsert_questions(conn, member_id, get_questions(member_id))
    conn.execute(
        "UPDATE members SET activity_fetched_at=? WHERE member_id=?",
        (datetime.now(timezone.utc).isoformat(), member_id),
    )
    conn.commit()
    conn.close()
    return True


def _compute_coverage(votes_count: int, questions_count: int, activity_fetched_at) -> dict:
    if votes_count >= 10:
        return {
            "status": "good",
            "label": "Good coverage",
            "message": None,
            "show_spotlight": True,
            "show_pledges": True,
        }
    elif votes_count > 0 or questions_count > 0:
        return {
            "status": "partial",
            "label": "Partial coverage",
            "message": (
                "Some records are loaded but this MP may have more activity on the public record. "
                "Data may be incomplete."
            ),
            "show_spotlight": True,
            "show_pledges": False,
        }
    elif activity_fetched_at:
        return {
            "status": "possible_api_mismatch",
            "label": "Records not available via API",
            "message": (
                "This app attempted to load records but the Parliament API returned none. "
                "This does not mean the MP has no activity. "
                "They may be newly elected, currently suspended, or their records may be "
                "available under a different member ID."
            ),
            "show_spotlight": False,
            "show_pledges": False,
        }
    else:
        return {
            "status": "not_loaded",
            "label": "Not loaded",
            "message": "Records for this MP have not been loaded yet.",
            "show_spotlight": False,
            "show_pledges": False,
        }


def _global_entry_url(include_start_modal: bool = False) -> str:
    cc = resolve_country_code(request)
    locale = resolve_locale(request)
    parts = []
    if include_start_modal:
        parts.append("from=start")
    parts.extend([f"cc={cc}", f"lang={locale}"])
    if _autopilot_requested(request):
        parts.append("autopilot=1")
    qs = "&".join(parts)
    return f"/global?{qs}"


def _render_search_home():
    query = request.args.get("q", "").strip()
    error = None
    search_results = []

    if query:
        postcode_match = _lookup_postcode_mp(query)
        if postcode_match and postcode_match.get("mp"):
            return redirect(url_for("mp_profile", member_id=postcode_match["mp"]["id"]))

        if query.isdigit():
            return redirect(url_for("mp_profile", member_id=int(query)))

        conn = get_conn()
        rows = conn.execute(
            """
            SELECT member_id, name, party, constituency
            FROM members
            WHERE constituency IS NOT NULL
            """
        ).fetchall()
        conn.close()

        ranked = _rank_member_rows(rows, query, limit=10)
        if len(ranked) == 1:
            return redirect(url_for("mp_profile", member_id=ranked[0]["member_id"]))
        elif ranked:
            search_results = ranked
        else:
            error = f'No MP found for "{query}". Try a full surname, constituency name, or postcode.'

    return render_template("index.html", error=error, query=query, search_results=search_results)


@app.route("/")
def index():
    if _autopilot_requested(request) or not request.args.get("q", "").strip():
        return redirect(_global_entry_url(), code=302)
    return _render_search_home()


@app.route("/home")
def home():
    return _render_search_home()


@app.route("/api/mps/search")
def mp_search_api():
    from parliament_client import search_members
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify(results=[])

    postcode_match = _lookup_postcode_mp(q)
    if postcode_match and postcode_match.get("mp"):
        mp = postcode_match["mp"]
        return jsonify(results=[{
            "id": mp.get("id"),
            "name": mp.get("name") or "",
            "party": mp.get("party") or "",
            "constituency": postcode_match.get("constituency") or "",
            "match_type": "postcode",
        }])

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT member_id, name, party, constituency
        FROM members
        WHERE constituency IS NOT NULL
        """
    ).fetchall()
    conn.close()

    ranked = _rank_member_rows(rows, q, limit=8)
    results = []
    seen_ids = set()
    for row in ranked:
        mid = row["member_id"]
        seen_ids.add(mid)
        results.append({
            "id": mid,
            "name": row["name"],
            "party": row["party"] or "",
            "constituency": row["constituency"] or "",
            "match_type": "text",
        })

    if len(results) < 8:
        api_hits = search_members(q)
        api_scored = []
        for m in api_hits:
            mid = m.get("id")
            if not mid or mid in seen_ids:
                continue
            name = m.get("nameDisplayAs", "")
            constituency = (m.get("latestHouseMembership") or {}).get("membershipFrom", "")
            score = max(_search_score(q, name), _search_score(q, constituency))
            if score <= 0:
                continue
            api_scored.append((score, (name or "").lower(), m, constituency))
        api_scored.sort(key=lambda item: (-item[0], item[1]))
        for _, _, m, constituency in api_scored:
            mid = m.get("id")
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            results.append({
                "id": mid,
                "name": m.get("nameDisplayAs", ""),
                "party": (m.get("latestParty") or {}).get("name", ""),
                "constituency": constituency,
                "match_type": "text",
            })
            if len(results) >= 8:
                break

    return jsonify(results=results)


@app.route("/api/postcode")
def postcode_lookup():
    pc = request.args.get("q", "").strip()
    if not pc:
        return jsonify(error="No postcode provided"), 400
    match = _lookup_postcode_mp(pc)
    if not match:
        return jsonify(error="Postcode not found"), 404
    return jsonify(constituency=match["constituency"], mp=match["mp"])


@app.route("/api/postcode/autocomplete")
def postcode_autocomplete():
    raw = request.args.get("q", "").strip().upper()
    query = re.sub(r"\s+", "", raw)
    if len(query) < 3:
        return jsonify(results=[])
    if not re.fullmatch(r"[A-Z0-9]+", query):
        return jsonify(results=[])
    try:
        r = httpx.get(
            f"https://api.postcodes.io/postcodes/{query}/autocomplete",
            timeout=4.0,
        )
        if r.status_code != 200:
            return jsonify(results=[])
        data = r.json() or {}
        results = data.get("result") or []
        # Keep shortlist small for a fast dropdown.
        return jsonify(results=results[:8])
    except Exception:
        return jsonify(results=[])


@app.route("/api/explain-vote")
def explain_vote():
    division_id = request.args.get("division_id", type=int)
    member_id   = request.args.get("member_id", type=int)
    if not division_id or not member_id:
        return jsonify({"error": "division_id and member_id required"}), 400

    level = request.args.get("level", type=int)
    style = request.args.get("style", "")
    if level is None:
        if style == "brief":
            level = 0
        elif style == "full":
            level = 2
        else:
            level = 1
    if level not in (0, 1, 2, 3):
        return jsonify({"error": "level must be 0, 1, 2, or 3"}), 400

    conn = get_conn()
    cached = conn.execute(
        "SELECT explanation FROM explanations WHERE division_id=? AND member_id=? AND level=? AND prompt_version=?",
        (division_id, member_id, level, EXPLAIN_PROMPT_VERSION),
    ).fetchone()
    if cached:
        conn.close()
        return jsonify({"explanation": cached["explanation"], "cached": True})

    conn.close()
    # RETIRED billable path. This endpoint previously made an UNAUTHENTICATED,
    # unthrottled OpenAI call on every cache miss — an unbounded-spend vector
    # (security review 2026-06). It is no longer used by the live product (the
    # current explainer is the grounded, cost-guarded /api/explain-selection),
    # so it no longer calls the model: it serves a cached explanation if one
    # exists (handled above) and otherwise the static fallback. Any remaining
    # caller (legacy A/B templates) degrades gracefully to that fallback.
    return jsonify({"explanation": _LEVEL_FALLBACKS[level], "cached": False, "fallback": True})


@app.route("/mp/<int:member_id>/issue/<slug>")
def issue_card(member_id: int, slug: str):
    topic = slug_to_topic(slug)
    if not topic:
        abort(404)
    conn = get_conn()
    member = conn.execute("SELECT * FROM members WHERE member_id=?", (member_id,)).fetchone()
    if not member:
        conn.close()
        abort(404)
    all_votes = conn.execute(
        "SELECT * FROM votes WHERE member_id=? ORDER BY division_date DESC",
        (member_id,),
    ).fetchall()
    conn.close()

    spotlight_all = build_issue_spotlight(all_votes)
    spotlight = next((s for s in spotlight_all if s["topic"] == topic), None)

    party_colour = PARTY_COLOURS.get(member["party"], "#555")
    live_url = request.host_url.rstrip("/")
    return render_template(
        "issue_card.html",
        member=member,
        topic=topic,
        slug=slug,
        spotlight=spotlight,
        party_colour=party_colour,
        live_url=live_url,
        variant="B",
    )


@app.route("/api/mp/<int:member_id>/coverage")
def mp_coverage_api(member_id):
    conn = get_conn()
    member = conn.execute("SELECT * FROM members WHERE member_id=?", (member_id,)).fetchone()
    if not member:
        conn.close()
        return jsonify({
            "member_id": member_id,
            "mp_name": None,
            "votes_loaded": 0,
            "questions_loaded": 0,
            "last_ingested": None,
            "coverage_status": "missing",
            "likely_issue": "Member not in database",
            "recommended_action": f"Visit /mp/{member_id} to trigger automatic ingest",
        }), 404

    votes_count = conn.execute("SELECT COUNT(*) FROM votes WHERE member_id=?", (member_id,)).fetchone()[0]
    q_count = conn.execute("SELECT COUNT(*) FROM questions WHERE member_id=?", (member_id,)).fetchone()[0]
    try:
        activity_fetched = member["activity_fetched_at"]
    except Exception:
        activity_fetched = None
    conn.close()

    cov = _compute_coverage(votes_count, q_count, activity_fetched)
    likely = {
        "good": None,
        "partial": "Ingest ran but returned limited results",
        "possible_api_mismatch": "Parliament API returned zero records — MP may be newly elected, suspended, or under a different ID",
        "not_loaded": "Ingest has never run for this member",
    }.get(cov["status"])
    action = {
        "good": "No action needed",
        "partial": "Re-run ingest or check Parliament API directly",
        "possible_api_mismatch": f"Verify member_id at members-api.parliament.uk/api/Members/{member_id}",
        "not_loaded": f"Visit /mp/{member_id} to trigger automatic ingest",
    }.get(cov["status"])

    return jsonify({
        "member_id": member_id,
        "mp_name": member["name"],
        "votes_loaded": votes_count,
        "questions_loaded": q_count,
        "last_ingested": activity_fetched,
        "coverage_status": cov["status"],
        "likely_issue": likely,
        "recommended_action": action,
    })


@app.route("/mp/<int:member_id>")
def mp_profile(member_id):
    conn = get_conn()
    member = conn.execute("SELECT * FROM members WHERE member_id = ?", (member_id,)).fetchone()
    conn.close()

    if not member:
        ok = _auto_ingest(member_id)
        if not ok:
            return render_template("index.html", error=f"MP not found (ID {member_id}).", query=""), 404
        conn = get_conn()
        member = conn.execute("SELECT * FROM members WHERE member_id = ?", (member_id,)).fetchone()
        conn.close()

    # Trigger activity ingest if it has never run for this member
    try:
        activity_fetched = member["activity_fetched_at"]
    except Exception:
        activity_fetched = None

    if not activity_fetched:
        _auto_ingest(member_id)
        conn = get_conn()
        member = conn.execute("SELECT * FROM members WHERE member_id = ?", (member_id,)).fetchone()
        conn.close()
        try:
            activity_fetched = member["activity_fetched_at"]
        except Exception:
            activity_fetched = None

    conn = get_conn()
    votes = conn.execute(
        "SELECT * FROM votes WHERE member_id = ? ORDER BY division_date DESC LIMIT 15",
        (member_id,),
    ).fetchall()
    all_votes = conn.execute(
        "SELECT * FROM votes WHERE member_id = ? ORDER BY division_date DESC",
        (member_id,),
    ).fetchall()
    questions = conn.execute(
        "SELECT * FROM questions WHERE member_id = ? ORDER BY date_tabled DESC LIMIT 10",
        (member_id,),
    ).fetchall()
    vote_count = conn.execute("SELECT COUNT(*) FROM votes WHERE member_id = ?", (member_id,)).fetchone()[0]
    q_count = conn.execute("SELECT COUNT(*) FROM questions WHERE member_id = ?", (member_id,)).fetchone()[0]
    aye_count = conn.execute("SELECT COUNT(*) FROM votes WHERE member_id = ? AND voted_aye = 1", (member_id,)).fetchone()[0]
    no_count = vote_count - aye_count
    conn.close()

    coverage = _compute_coverage(vote_count, q_count, activity_fetched)
    issue_spotlight = build_issue_spotlight(all_votes) if coverage["show_spotlight"] else []
    party_colour = PARTY_COLOURS.get(member["party"], "#555")

    variant = request.args.get("variant", "B").upper()
    if variant not in ("A", "B"):
        variant = "B"

    return render_template(
        "mp.html",
        member=member,
        votes=votes,
        questions=questions,
        vote_count=vote_count,
        q_count=q_count,
        aye_count=aye_count,
        no_count=no_count,
        party_colour=party_colour,
        pledges=MOCK_PLEDGES,
        issue_spotlight=issue_spotlight,
        coverage=coverage,
        topic_to_slug=topic_to_slug,
        variant=variant,
    )


def _division_id_from_metadata(metadata):
    """Find a division id in the click metadata: the clicked element's
    data-division-id takes priority, then the selected division in yourgov_state."""
    raw = metadata.get("division_id")
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    state = metadata.get("yourgov_state")
    if isinstance(state, dict):
        sd = state.get("selected_division")
        if isinstance(sd, dict) and sd.get("division_id"):
            try:
                return int(sd["division_id"])
            except (TypeError, ValueError):
                pass
    return None


def _division_summary_text_for(metadata):
    """Build the structured division-summary text if a division is in context."""
    return _division_context_for(metadata)[0]


def _division_context_for(metadata):
    """Return (summary_text, fingerprint) for the in-context division, or ("", "").
    The fingerprint (current aye-no) feeds the cache key so a corrected division
    invalidates its cached explanation instead of serving stale numbers."""
    division_id = _division_id_from_metadata(metadata)
    if not division_id:
        return "", ""
    conn = get_publicwhip_conn()
    try:
        summary = ec.build_division_summary(conn, division_id)
    finally:
        conn.close()
    if not summary:
        return "", ""
    fingerprint = f'{summary["aye_count"]}-{summary["no_count"]}'
    return ec.render_division_summary(summary), fingerprint


# ── Explainer cost guards ─────────────────────────────────────────────────
# /api/explain-selection is unauthenticated and calls OpenAI per request, so it
# is the one real cost risk. Three layers protect it, and EVERY one degrades to
# the safe non-LLM fallback envelope (never an error, never an unbounded bill):
#   1. cache        — identical opening-turn clicks are served from SQLite ($0).
#   2. per-IP rate  — sliding per-minute + per-day caps per client IP.
#   3. daily budget — a hard global ceiling on LLM calls per UTC day, persisted
#                     in SQLite so it survives worker respawns and is shared
#                     across Passenger workers. The backstop against abuse.
# All limits are env-tunable (restart to apply).
_EXPLAINER_IP_STORE: dict = {}
# Hard cap on distinct tracked IPs. X-Forwarded-For is spoofable, so a flood of
# fake IPs could otherwise grow this dict without bound (memory DoS). When the cap
# is hit we drop entries with no recent hits, then clear wholesale if still over —
# safe because the global daily budget, not this per-IP map, is the cost backstop.
_EXPLAINER_IP_STORE_CAP = int(os.environ.get("EXPLAINER_IP_STORE_CAP", "20000"))
_EXPLAINER_RATE_PER_MIN = int(os.environ.get("EXPLAINER_RATE_PER_MIN", "10"))
_EXPLAINER_RATE_PER_DAY = int(os.environ.get("EXPLAINER_RATE_PER_DAY", "100"))
_EXPLAINER_DAILY_BUDGET = int(os.environ.get("EXPLAINER_DAILY_BUDGET", "2000"))
_EXPLAINER_CACHE_TTL = int(os.environ.get("EXPLAINER_CACHE_TTL_SECONDS", str(7 * 86400)))
# Per-level output ceiling, sized for the JSON envelope (5 fields). Caps the cost
# of each LLM call so the daily budget translates to a tighter dollar ceiling;
# higher levels get more room so the JSON is never truncated into invalid output.
_SELECTION_MAX_TOKENS = {0: 160, 1: 260, 2: 400, 3: 600}


def _ensure_explainer_tables(conn):
    # CREATE ... IF NOT EXISTS is cheap and idempotent, so run it on every guard
    # connection rather than caching a process-global "ready" flag — a worker that
    # outlives a DB-file swap (e.g. a redeploy that re-seeds /tmp) then still has
    # the tables instead of silently failing every cache/budget query.
    conn.execute("PRAGMA busy_timeout=3000")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS selection_cache "
        "(key TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS explainer_budget "
        "(day TEXT PRIMARY KEY, count INTEGER NOT NULL)"
    )
    conn.commit()


def _prune_ip_store(now):
    """Bound the in-process IP rate map. Drop keys whose hits are all older than
    the day window; if still over the cap, clear it (the global budget still caps
    cost, so a rare rate-limit reset is acceptable)."""
    store = _EXPLAINER_IP_STORE
    if len(store) <= _EXPLAINER_IP_STORE_CAP:
        return
    for key in [k for k, ts in store.items() if not any(now - t < 86400.0 for t in ts)]:
        store.pop(key, None)
    if len(store) > _EXPLAINER_IP_STORE_CAP:
        store.clear()


def _client_ip():
    # Behind LiteSpeed/Passenger the real client is the first X-Forwarded-For hop.
    # Spoofable, which is exactly why the global daily budget (not per-IP) is the
    # real cost backstop.
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.remote_addr or "unknown")[:64]


def _explainer_day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _explainer_budget_reserve(conn, day, budget):
    """Atomically reserve one LLM call against the day's budget. Returns True if
    within budget (and increments the day's count), False if it is exhausted."""
    if budget <= 0:
        return False
    cur = conn.execute(
        "INSERT INTO explainer_budget(day, count) VALUES(?, 1) "
        "ON CONFLICT(day) DO UPDATE SET count = count + 1 WHERE count < ?",
        (day, budget),
    )
    conn.commit()
    return cur.rowcount > 0


def _explainer_cache_get(conn, key, ttl=_EXPLAINER_CACHE_TTL):
    row = conn.execute(
        "SELECT payload, created_at FROM selection_cache WHERE key=?", (key,)
    ).fetchone()
    if not row:
        return None
    if ttl > 0 and (time.time() - row["created_at"]) > ttl:
        return None
    try:
        return json.loads(row["payload"])
    except (ValueError, TypeError):
        return None


def _explainer_cache_put(conn, key, payload):
    conn.execute(
        "INSERT OR REPLACE INTO selection_cache(key, payload, created_at) VALUES(?,?,?)",
        (key, json.dumps(payload), time.time()),
    )
    conn.commit()


def _explainer_fallback(level, target_text, source_links, followup_q):
    """The safe, non-LLM envelope returned whenever the LLM path is skipped
    (no API key, rate-limited, or over the daily budget). Identical shape to a
    real answer so the drawer renders normally and no cost is incurred."""
    if followup_q:
        return {
            "clicked": followup_q[:120],
            "meaning": (
                "The AI explainer is unavailable right now, so a full answer "
                "cannot be generated. The underlying public record is still "
                "available via the source links."
            ),
            "source_support": f"See: {source_links[0] if source_links else 'the Parliament open API'}",
            "does_not_prove": (
                "A vote or activity record shows what happened in Parliament — not why."
            ),
            "followups": [],
        }
    fallback_source = source_links[0] if source_links else "the Parliament open API"
    return {
        "clicked": target_text[:120],
        "meaning": _LEVEL_FALLBACKS[level],
        "source_support": f"The public record is available at: {fallback_source}",
        "does_not_prove": (
            "This record does not prove intent, motivation, or personal character. "
            "A vote or activity record shows what happened in Parliament — not why."
        ),
        "followups": [
            "What does Aye or No mean in practice?",
            "Where can I verify this record directly?",
            "How are these records collected?",
        ],
    }


@app.route("/api/explain-selection", methods=["POST"])
def explain_selection():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = {}

    # Coerce every client-supplied field to a safe type. This endpoint is
    # unauthenticated, so a wrong-typed body (non-dict metadata, numeric
    # target_text, non-string source_links, etc.) must degrade gracefully, never
    # raise an unhandled 500.
    def _s(v):
        return v if isinstance(v, str) else ""

    target_text = _s(data.get("target_text")).strip()[:300]
    surrounding = _s(data.get("surrounding_text")).strip()[:400]
    src = data.get("source_links")
    source_links = [s for s in src if isinstance(s, str)][:5] if isinstance(src, list) else []
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    url = _s(data.get("url"))
    followup_q = _s(data.get("followup_question")).strip()
    prior_expl = _s(data.get("prior_explanation")).strip()
    level = data.get("level", 1)
    # `bool` is an `int` subclass, so reject it explicitly before the range check.
    if isinstance(level, bool) or not isinstance(level, int) or level not in (0, 1, 2, 3):
        level = 1

    if not target_text:
        return jsonify({"error": "target_text required"}), 400

    # Conversation history. Prefer an explicit messages array; fall back to the
    # legacy single prior_explanation so older clients still get continuity.
    history = ec.normalise_history(data.get("messages"))
    if not history and prior_expl:
        history = [{"role": "assistant", "content": prior_expl[:2000]}]
    turn_index = sum(1 for m in history if m["role"] == "user")

    # Grounding: small docs injected directly + the clicked division's structured
    # summary (precise DB lookup, not retrieval). The click leads early, then
    # decays to background after a few turns (see assemble_system_prompt).
    grounding = ec.load_grounding_docs()
    division_summary_text, division_fp = _division_context_for(metadata)
    division_id = _division_id_from_metadata(metadata)

    source_links_text = "\n".join(source_links[:5]) if source_links else "None provided"
    click_context = (
        f'"{target_text}"'
        + (f"\nSurrounding context: {surrounding}" if surrounding else "")
        + (f"\nSource links: {source_links_text}" if source_links else "")
        + (f"\nPage: {url}" if url else "")
    )

    system_prompt = ec.assemble_system_prompt(
        level_name=_LEVEL_NAMES[level],
        level_instruction=_LEVEL_INSTRUCTIONS[level],
        grounding=grounding,
        division_summary_text=division_summary_text,
        click_context=click_context,
        turn_index=turn_index,
    )

    # The current user turn: a follow-up question if supplied, otherwise the
    # opening request to explain what was clicked.
    if followup_q:
        current_user = followup_q
    else:
        current_user = f"Explain what I just clicked: {target_text}"

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return jsonify(_explainer_fallback(level, target_text, source_links, followup_q))

    # ── Cost guards (cache → per-IP rate → global daily budget) ───────────
    # Each layer that trips returns the same safe fallback envelope; only a real
    # cache miss that clears rate + budget reaches OpenAI. A single try/finally
    # spans the whole path so the guard connection is always closed, and any
    # error (guard DB or the OpenAI call itself) degrades to the fallback.
    cache_key = None
    if ec.is_cacheable_turn(followup_q, history):
        ntype = ec.normalise_explain_type(metadata.get("explain_type"))
        if division_id and division_fp:
            # Division clicks share one cached answer per (level, division, result,
            # element-type): every user clicking that division hits the cache and an
            # attacker cannot force misses by mutating the free-text fields.
            cache_parts = ["div", level, division_id, division_fp, ntype]
        else:
            cache_parts = ["txt", level, ntype, target_text, surrounding]
        cache_key = ec.selection_cache_key(cache_parts)

    guard_conn = None
    try:
        guard_conn = get_conn()
        _ensure_explainer_tables(guard_conn)

        if cache_key:
            cached = _explainer_cache_get(guard_conn, cache_key)
            if cached is not None:
                cached = dict(cached)
                cached["cached"] = True
                return jsonify(cached)

        # Per-IP sliding-window caps. Minute first so a blocked minute does not
        # also consume the day allowance.
        now = time.time()
        _prune_ip_store(now)
        ip = _client_ip()
        within_min = ec.sliding_window_allow(
            _EXPLAINER_IP_STORE, ip + ":m", now, 60.0, _EXPLAINER_RATE_PER_MIN
        )
        within_day = within_min and ec.sliding_window_allow(
            _EXPLAINER_IP_STORE, ip + ":d", now, 86400.0, _EXPLAINER_RATE_PER_DAY
        )
        if not (within_min and within_day):
            return jsonify(_explainer_fallback(level, target_text, source_links, followup_q))

        # Global daily budget — the hard backstop.
        if not _explainer_budget_reserve(guard_conn, _explainer_day(), _EXPLAINER_DAILY_BUDGET):
            return jsonify(_explainer_fallback(level, target_text, source_links, followup_q))

        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": current_user})
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            max_tokens=_SELECTION_MAX_TOKENS.get(level, 400),
            response_format={"type": "json_object"},
            messages=messages,
        )
        result = json.loads(resp.choices[0].message.content)
        # Ensure all required keys present
        for key in ("clicked", "meaning", "source_support", "does_not_prove", "followups"):
            if key not in result:
                result[key] = "" if key != "followups" else []
        if cache_key:
            try:
                _explainer_cache_put(guard_conn, cache_key, result)
            except Exception:
                pass
        return jsonify(result)
    except Exception:
        # Guard DB error or an OpenAI/parse failure — degrade to the safe envelope
        # (HTTP 200) so the drawer always renders, never a raw 500.
        return jsonify(_explainer_fallback(level, target_text, source_links, followup_q))
    finally:
        if guard_conn is not None:
            try:
                guard_conn.close()
            except Exception:
                pass


@app.route("/lens")
@app.route("/panel_test")
@app.route("/source_lens")
def legacy_redirect():
    return redirect("/source-lens", 302)


@app.route("/source-lens")
def source_lens():
    return render_template(
        "panel_test.html",
        asset_version=app.config["ASSET_VERSION"],
    )




def _load_global_feasibility():
    """Load the static global feasibility dataset used by /global."""
    data_path = os.path.join(app.root_path, "static", "data", "global_feasibility.json")
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Country + locale resolution (smart entry routing) ────────────
# Live set: countries where YourGov has a working data adapter today.
# Add new ISO2s here as adapters ship.
LIVE_COUNTRIES = {"GB"}


def _known_country_codes():
    """Return the set of valid ISO2 country codes from the feasibility dataset."""
    try:
        data = _load_global_feasibility()
        return {(c.get("iso2") or "").upper() for c in data.get("countries", []) if c.get("iso2")}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def is_live_country(cc: str) -> bool:
    return (cc or "").upper() in LIVE_COUNTRIES


def resolve_country_code(req) -> str:
    """Resolve the requesting user's ISO2 country code.

    Priority:
      1. ?cc= query param  (testing override / explicit selection)
      2. cf-ipcountry header  (Cloudflare geo if ever proxied)
      3. 'GB' default

    Result is validated against the known feasibility-dataset ISO2 set.
    Unknown codes fall back to 'GB'.
    """
    candidates = [
        req.args.get("cc", "").strip(),
        req.headers.get("cf-ipcountry", "").strip(),
    ]
    known = _known_country_codes()
    for raw in candidates:
        if not raw:
            continue
        cc = raw.upper()
        if not known or cc in known:
            return cc
    return "GB"


SUPPORTED_LOCALES = ("en", "hi")
# Locales whose script reads right-to-left. The /source-lens layout
# mirrors the source/viz panes for these so source always lands in
# the reading-first position.
RTL_LOCALES = frozenset({"ar", "he", "fa", "ur"})


def resolve_locale(req) -> str:
    """Resolve the requesting user's locale.

    Priority:
      1. ?lang= query param
      2. Accept-Language header (first supported tag wins)
      3. 'en' fallback
    """
    override = (req.args.get("lang") or "").strip().lower()
    if override[:2] in SUPPORTED_LOCALES:
        return override[:2]
    accept = (req.headers.get("Accept-Language") or "").lower()
    for tag in accept.split(","):
        tag = tag.split(";")[0].strip()[:2]
        if tag in SUPPORTED_LOCALES:
            return tag
    return "en"


def _autopilot_requested(req) -> bool:
    return (req.args.get("autopilot") or "").strip() == "1"


_SEARCH_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.I)


def _normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", _SEARCH_SANITIZE_RE.sub(" ", (value or "").lower())).strip()


def _search_score(query: str, candidate: str) -> int:
    q = _normalize_search_text(query)
    c = _normalize_search_text(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 300

    q_words = q.split()
    c_words = c.split()

    if len(q_words) == 1:
        if c.startswith(q):
            return 250
        for idx, word in enumerate(c_words):
            if word.startswith(q):
                return 200 - (idx * 5)
        return 0

    for start in range(max(0, len(c_words) - len(q_words) + 1)):
        if all(c_words[start + i].startswith(q_words[i]) for i in range(len(q_words))):
            return 220 - (start * 5)
    return 0


def _rank_member_rows(rows, query: str, limit: int = 10):
    scored = []
    for row in rows:
        score = max(
            _search_score(query, row["name"]),
            _search_score(query, row["constituency"]),
        )
        if score <= 0:
            continue
        scored.append((score, (row["name"] or "").lower(), row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [dict(row) for _, _, row in scored[:limit]]


def _lookup_postcode_mp(query: str):
    pc = (query or "").strip().replace(" ", "").upper()
    if not pc or not _POSTCODE_RE.fullmatch(pc):
        return None
    try:
        r = httpx.get(f"https://api.postcodes.io/postcodes/{pc}", timeout=5.0)
        if r.status_code != 200:
            return None
        data = r.json() or {}
        constituency = (data.get("result") or {}).get("parliamentary_constituency", "")
        if not constituency:
            return None

        conn = get_conn()
        row = conn.execute(
            "SELECT member_id, name, party, constituency FROM members WHERE lower(constituency) LIKE lower(?)",
            (f"%{constituency}%",),
        ).fetchone()
        conn.close()
        if row:
            return {
                "constituency": constituency,
                "mp": {"id": row["member_id"], "name": row["name"], "party": row["party"] or ""},
            }

        from parliament_client import search_members
        hits = search_members(constituency)
        if hits:
            m = hits[0]
            return {
                "constituency": constituency,
                "mp": {
                    "id": m.get("id"),
                    "name": m.get("nameDisplayAs", ""),
                    "party": (m.get("latestParty") or {}).get("name", ""),
                },
            }
    except Exception:
        return None
    return None


def resolve_dir(req) -> str:
    """Return 'rtl' if the request's locale (or ?lang= override) is
    right-to-left, else 'ltr'. Note we check both the supported-locale
    set AND the raw RTL list — so ?lang=ar still flips the layout
    even though we don't translate to Arabic yet."""
    raw = (req.args.get("lang") or "").strip().lower()[:2]
    if raw in RTL_LOCALES:
        return "rtl"
    accept = (req.headers.get("Accept-Language") or "").lower()
    for tag in accept.split(","):
        tag = tag.split(";")[0].strip()[:2]
        if tag in RTL_LOCALES:
            return "rtl"
        if tag in SUPPORTED_LOCALES:
            return "ltr"
    return "ltr"


# ── Bilingual copy dictionary (key surfaces only) ────────────────
# English is the source of truth; Hindi covers landing, welcome,
# global hero, nav labels, and a small set of stat / legend strings.
COPY = {
    "welcome_title": {
        "en": "Public records are public.",
        "hi": "सार्वजनिक रिकॉर्ड सार्वजनिक हैं।",
    },
    "welcome_subtitle": {
        "en": "Staying informed is a civic responsibility.",
        "hi": "जानकारी रखना एक नागरिक ज़िम्मेदारी है।",
    },
    "welcome_go": {
        "en": "Go now",
        "hi": "अभी जाएँ",
    },
    "welcome_skip": {
        "en": "Skip",
        "hi": "छोड़ें",
    },
    "start_in_my_country": {
        "en": "Start in my country",
        "hi": "मेरे देश से शुरू करें",
    },
    "back_to_mygov": {
        "en": "Back to YourGov",
        "hi": "YourGov पर वापस",
    },
    "open_source_lens": {
        "en": "Open YourGov",
        "hi": "सोर्स लेंस खोलें",
    },
    "open_global": {
        "en": "Open Global",
        "hi": "ग्लोबल खोलें",
    },
    "global_hero_subtitle": {
        "en": "Where can YourGov-style civic transparency be built today?",
        "hi": "YourGov-शैली की पारदर्शिता आज कहाँ बनाई जा सकती है?",
    },
    "global_hero_note": {
        "en": "Green/orange/red shows data buildability, not a government quality score.",
        "hi": "हरा/नारंगी/लाल डेटा निर्माण क्षमता दिखाता है, सरकार की गुणवत्ता का स्कोर नहीं।",
    },
    "stat_completed": {"en": "Live adapters", "hi": "लाइव एडाप्टर"},
    "stat_strong": {"en": "Strong candidates", "hi": "मज़बूत उम्मीदवार"},
    "stat_possible": {"en": "Possible with work", "hi": "प्रयास से संभव"},
    "stat_not_mapped": {"en": "Not yet mapped", "hi": "अभी मानचित्रित नहीं"},
    "legend_filter_label": {
        "en": "Click a colour to filter the list:",
        "hi": "सूची फ़िल्टर करने के लिए रंग पर क्लिक करें:",
    },
    "route_status_live": {
        "en": "Routing to your live YourGov view…",
        "hi": "आपके लाइव YourGov दृश्य पर भेज रहे हैं…",
    },
    "route_status_global": {
        "en": "Routing to the Global feasibility view for your country…",
        "hi": "आपके देश के लिए ग्लोबल व्यवहार्यता दृश्य पर भेज रहे हैं…",
    },
    # Onboarding tour (3 steps + nav buttons)
    "tour_step1_title": {
        "en": "Start here",
        "hi": "यहाँ से शुरू करें",
    },
    "tour_step1_body": {
        "en": "Pick a vote, MP, or party in the source panel.",
        "hi": "स्रोत पैनल में एक वोट, सांसद या पार्टी चुनें।",
    },
    "tour_step2_title": {
        "en": "Watch the map",
        "hi": "मानचित्र देखें",
    },
    "tour_step2_body": {
        "en": "The map colours your country by what you selected.",
        "hi": "आपके चयन के अनुसार मानचित्र आपके देश को रंगता है।",
    },
    "tour_step3_title": {
        "en": "Switch the view",
        "hi": "दृश्य बदलें",
    },
    "tour_step3_body": {
        "en": "Use the mode ring to compare Vote / Party / Gender / Rebel splits.",
        "hi": "वोट / पार्टी / लिंग / विद्रोह विभाजन की तुलना के लिए मोड रिंग का उपयोग करें।",
    },
    "tour_next": {"en": "Next", "hi": "आगे"},
    "tour_done": {"en": "Got it", "hi": "समझ गया"},
    "tour_skip": {"en": "Skip tour", "hi": "टूर छोड़ें"},
}


def t(key: str, locale: str) -> str:
    entry = COPY.get(key)
    if not entry:
        return key
    return entry.get(locale) or entry.get("en") or key


@app.context_processor
def _inject_i18n_helpers():
    """Expose t(key) / active_locale / active_cc / active_dir to every template."""
    locale = resolve_locale(request)
    return {
        "t": lambda key, loc=locale: t(key, loc),
        "active_locale": locale,
        "active_cc": resolve_country_code(request),
        "active_dir": resolve_dir(request),
    }


@app.route("/welcome")
def welcome():
    """Brief civic-responsibility transition page that auto-routes to /start."""
    locale = resolve_locale(request)
    cc = resolve_country_code(request)
    autopilot = _autopilot_requested(request)
    return render_template("welcome.html", locale=locale, cc=cc, autopilot=autopilot)


@app.route("/start")
def start_router():
    """Smart entry: resolve country + locale, redirect into the
    /source-lens shell with the correct initial source pre-loaded.

    Live countries (UK) open with the PublicWhip source so the user
    lands on the working data immediately. Non-live countries open
    with the Global feasibility source preselected to their country,
    inside the same shell — no separate page load.
    """
    return redirect(_global_entry_url(include_start_modal=True), code=302)


@app.route("/global")
def global_civic_lens():
    return render_template("global.html", asset_version=app.config["ASSET_VERSION"])


@app.route("/feedback")
def feedback():
    # Public feedback invitation. Three channels only: WhatsApp, Telegram,
    # Email. Links come from env/config; labels are always shown. This page
    # never collects data server-side — there is no form and no endpoint that
    # accepts public input. Messages are handled by the offline intake tool.
    return render_template(
        "feedback.html",
        asset_version=app.config["ASSET_VERSION"],
        whatsapp_url=os.environ.get("MYGOV_FEEDBACK_WHATSAPP_URL", ""),
        telegram_url=os.environ.get("MYGOV_FEEDBACK_TELEGRAM_URL", ""),
        feedback_email=os.environ.get("MYGOV_FEEDBACK_EMAIL", "yourgov@solvx.uk"),
    )


@app.route("/api/global/feasibility")
def api_global_feasibility():
    try:
        return jsonify(_load_global_feasibility())
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "Global feasibility data file is missing."}), 500
    except json.JSONDecodeError as exc:
        return jsonify({"ok": False, "error": f"Global feasibility data is invalid JSON: {exc}"}), 500

@app.route("/publicwhip")
def pw_home():
    conn = get_publicwhip_conn()
    recent = conn.execute(
        """
        SELECT v.division_id, v.title, v.division_date,
               v.aye_count, v.no_count,
               COUNT(DISTINCT v.member_id) AS mp_count
        FROM votes v
        GROUP BY v.division_id
        ORDER BY v.division_date DESC
        LIMIT 20
        """
    ).fetchall()
    conn.close()
    return render_template("pw_home.html", recent=recent, asset_version=app.config["ASSET_VERSION"])


@app.route("/publicwhip/divisions")
def pw_divisions():
    conn = get_publicwhip_conn()
    divisions = conn.execute(
        """
        SELECT v.division_id, v.title, v.division_date,
               v.aye_count, v.no_count,
               COUNT(DISTINCT v.member_id) AS mp_count
        FROM votes v
        GROUP BY v.division_id
        ORDER BY v.division_date DESC
        LIMIT 80
        """
    ).fetchall()
    conn.close()
    return render_template("pw_divisions.html", divisions=divisions, asset_version=app.config["ASSET_VERSION"])


@app.route("/publicwhip/mps")
def pw_mps():
    q = request.args.get("q", "").strip()
    conn = get_publicwhip_conn()
    if q:
        like = f"%{q}%"
        mps = conn.execute(
            """
            SELECT member_id, name, party, constituency
            FROM members
            WHERE constituency IS NOT NULL
              AND (name LIKE ? OR constituency LIKE ? OR party LIKE ?)
            ORDER BY name
            LIMIT 200
            """,
            (like, like, like),
        ).fetchall()
    else:
        mps = conn.execute(
            """
            SELECT member_id, name, party, constituency
            FROM members
            WHERE constituency IS NOT NULL
            ORDER BY name
            LIMIT 200
            """
        ).fetchall()
    conn.close()
    return render_template("pw_mps.html", mps=mps, q=q, asset_version=app.config["ASSET_VERSION"])


@app.route("/publicwhip/lords")
def pw_lords():
    return render_template("pw_lords.html", asset_version=app.config["ASSET_VERSION"])


@app.route("/publicwhip/msps")
def pw_msps():
    return render_template("pw_msps.html", asset_version=app.config["ASSET_VERSION"])


@app.route("/publicwhip/policies")
def pw_policies():
    q = request.args.get("q", "").strip()
    return render_template("pw_policies.html", q=q, asset_version=app.config["ASSET_VERSION"])


@app.route("/publicwhip/mp/<int:member_id>")
def pw_mp(member_id):
    conn = get_publicwhip_conn()
    mp = conn.execute(
        "SELECT * FROM members WHERE member_id=?", (member_id,)
    ).fetchone()
    if not mp:
        conn.close()
        abort(404)

    # Display the latest 100 for readability...
    votes = conn.execute(
        """
        SELECT division_id, division_date, title, voted_aye, aye_count, no_count
        FROM votes WHERE member_id=?
        ORDER BY division_date DESC
        LIMIT 100
        """,
        (member_id,),
    ).fetchall()
    # ...but compute every figure from the FULL recorded record, never the
    # displayed subset.
    all_votes = conn.execute(
        "SELECT division_id, voted_aye FROM votes WHERE member_id=? ORDER BY division_date DESC",
        (member_id,),
    ).fetchall()
    vote_by_division = {v["division_id"]: v["voted_aye"] for v in all_votes}

    # Rebellion detection across the FULL record in a SINGLE grouped query (no
    # per-division N+1): tally how the MP's party voted on every division the
    # member took part in, then flag divisions where they broke a >=60% party
    # majority. Indexed on votes(member_id) and votes(division_id).
    rebellions = set()
    if vote_by_division and mp["party"]:
        party_tally = {}  # division_id -> {0: n, 1: n}
        party_rows = conn.execute(
            """
            SELECT v.division_id AS division_id, v.voted_aye AS voted_aye, COUNT(*) AS cnt
            FROM votes v JOIN members m ON v.member_id = m.member_id
            WHERE m.party = ?
              AND v.division_id IN (SELECT division_id FROM votes WHERE member_id = ?)
            GROUP BY v.division_id, v.voted_aye
            """,
            (mp["party"], member_id),
        ).fetchall()
        for r in party_rows:
            party_tally.setdefault(r["division_id"], {})[r["voted_aye"]] = r["cnt"]
        for div_id, counts in party_tally.items():
            total = sum(counts.values())
            if total == 0:
                continue
            # Determine party majority position (require >=60% majority to flag rebel)
            if counts.get(1, 0) / total >= 0.6:
                party_majority = 1
            elif counts.get(0, 0) / total >= 0.6:
                party_majority = 0
            else:
                continue  # true split — skip
            mp_vote_aye = vote_by_division.get(div_id)
            if mp_vote_aye is not None and mp_vote_aye != party_majority:
                rebellions.add(div_id)

    conn.close()
    thumbnail = None
    try:
        posts = json.loads(mp["current_posts"] or "{}")
        thumbnail = posts.get("thumbnailUrl")
    except Exception:
        pass

    rebellion_count = len(rebellions)
    conn = get_conn()
    votes_taken = conn.execute("SELECT COUNT(*) FROM votes WHERE member_id=?", (member_id,)).fetchone()[0]
    conn.close()
    # Full-record tallies (not the displayed latest-100 subset).
    aye_count = sum(1 for v in all_votes if v["voted_aye"] == 1)
    no_count = sum(1 for v in all_votes if v["voted_aye"] == 0)

    return render_template(
        "pw_mp.html",
        mp=mp,
        votes=votes,
        rebellions=rebellions,
        rebellion_count=rebellion_count,
        votes_taken=votes_taken,
        aye_count=aye_count,
        no_count=no_count,
        thumbnail=thumbnail,
        party_colour=PARTY_COLOURS.get(mp["party"], "#8a97ab"),
        asset_version=app.config["ASSET_VERSION"],
    )


@app.route("/publicwhip/division/<int:division_id>")
def pw_division(division_id):
    conn = get_publicwhip_conn()
    # Get division metadata from any voter's row
    meta = conn.execute(
        "SELECT division_id, title, division_date, aye_count, no_count FROM votes WHERE division_id=? LIMIT 1",
        (division_id,),
    ).fetchone()
    if not meta:
        conn.close()
        abort(404)

    # All voters with member info
    voters = conn.execute(
        """
        SELECT v.member_id, v.voted_aye, m.name, m.party, m.constituency
        FROM votes v JOIN members m ON v.member_id = m.member_id
        WHERE v.division_id=?
        ORDER BY m.party, m.name
        """,
        (division_id,),
    ).fetchall()
    conn.close()

    # Party breakdown
    party_breakdown = {}
    for row in voters:
        p = row["party"] or "Unknown"
        if p not in party_breakdown:
            party_breakdown[p] = {"aye": 0, "no": 0}
        if row["voted_aye"] == 1:
            party_breakdown[p]["aye"] += 1
        else:
            party_breakdown[p]["no"] += 1

    ayes = [v for v in voters if v["voted_aye"] == 1]
    noes = [v for v in voters if v["voted_aye"] == 0]

    return render_template(
        "pw_division.html",
        meta=meta,
        ayes=ayes,
        noes=noes,
        party_breakdown=party_breakdown,
        party_colours=PARTY_COLOURS,
        asset_version=app.config["ASSET_VERSION"],
    )


@app.route("/publicwhip/search")
def pw_search():
    q = request.args.get("q", "").strip()
    conn = get_publicwhip_conn()
    mp_results = []
    division_results = []

    if q:
        like = f"%{q}%"
        mp_results = conn.execute(
            """
            SELECT member_id, name, party, constituency
            FROM members
            WHERE constituency IS NOT NULL
              AND (name LIKE ? OR constituency LIKE ? OR party LIKE ?)
            ORDER BY name LIMIT 30
            """,
            (like, like, like),
        ).fetchall()
        division_results = conn.execute(
            """
            SELECT division_id, title, division_date, aye_count, no_count
            FROM votes
            WHERE title LIKE ?
            GROUP BY division_id
            ORDER BY division_date DESC
            LIMIT 30
            """,
            (like,),
        ).fetchall()

    conn.close()
    return render_template(
        "pw_search.html",
        q=q,
        mp_results=mp_results,
        division_results=division_results,
        asset_version=app.config["ASSET_VERSION"],
    )


def _norm_title(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _normalise_division_map_mode(mode):
    raw = (mode or "vote-split").strip().lower().replace("_", "-")
    return MODE_ALIASES.get(raw)


def _vote_label(raw_vote):
    if raw_vote == 1:
        return "Aye"
    if raw_vote == 0:
        return "No"
    return "Absent/unknown"


def _member_gender_from_posts(raw_posts):
    gender = None
    try:
        posts = json.loads(raw_posts or "{}")
        if isinstance(posts, dict):
            gender = posts.get("gender")
    except Exception:
        gender = None

    if not isinstance(gender, str):
        return "Unknown"

    value = gender.strip().lower()
    if value in {"m", "male"}:
        return "M"
    if value in {"f", "female"}:
        return "F"
    return "Unknown"


def _party_majorities_for_division(rows):
    party_counts = {}
    for row in rows:
        raw_vote = row["voted_aye"]
        party = (row["party"] or "").strip()
        if raw_vote not in (0, 1) or not party or party.lower() == "independent":
            continue
        counts = party_counts.setdefault(party, {0: 0, 1: 0})
        counts[raw_vote] += 1

    party_majorities = {}
    for party, counts in party_counts.items():
        total = counts[0] + counts[1]
        if total <= 0:
            continue
        if counts[1] / total >= PARTY_MAJORITY_THRESHOLD:
            party_majorities[party] = 1
        elif counts[0] / total >= PARTY_MAJORITY_THRESHOLD:
            party_majorities[party] = 0
    return party_majorities


def _division_map_payload(division_id, mode="vote-split", source="publicwhip"):
    mode = _normalise_division_map_mode(mode)
    if mode not in DIVISION_MAP_MODES:
        return None

    conn = get_publicwhip_conn()
    meta = conn.execute(
        """
        SELECT division_id, title, division_date, aye_count, no_count
        FROM votes
        WHERE division_id=?
        LIMIT 1
        """,
        (division_id,),
    ).fetchone()
    if not meta:
        conn.close()
        return None

    selected_vote_rows = conn.execute(
        """
        SELECT
            v.member_id,
            v.voted_aye,
            m.party
        FROM votes v
        LEFT JOIN members m
            ON m.member_id = v.member_id
        WHERE v.division_id = ?
        """,
        (division_id,),
    ).fetchall()

    member_rows = conn.execute(
        """
        SELECT
            m.member_id,
            m.name,
            m.party,
            m.constituency,
            m.current_posts
        FROM members m
        WHERE m.constituency IS NOT NULL
        ORDER BY m.constituency
        """,
    ).fetchall()
    try:
        constituency_rows = conn.execute(
            """
            SELECT constituency_id, name, current_member_id
            FROM constituencies
            ORDER BY name
            """
        ).fetchall()
    except sqlite3.OperationalError:
        constituency_rows = []
    conn.close()

    selected_votes_by_member = {
        row["member_id"]: row["voted_aye"]
        for row in selected_vote_rows
    }
    selected_division_vote_rows = sum(
        1 for row in selected_vote_rows if row["voted_aye"] in (0, 1)
    )
    member_by_constituency = {
        row["constituency"]: row
        for row in member_rows
        if row["constituency"]
    }
    if constituency_rows:
        map_rows = [
            (
                constituency["name"],
                member_by_constituency.get(constituency["name"]),
                constituency["constituency_id"],
            )
            for constituency in constituency_rows
        ]
    else:
        map_rows = [
            (row["constituency"], row, None)
            for row in member_rows
            if row["constituency"]
        ]

    has_vacancies = any(row is None for _, row, _ in map_rows)
    current_member_rows = sum(1 for _, row, _ in map_rows if row is not None)
    map_constituency_rows = len(map_rows)
    map_data = {}
    votes = []
    counts = {"aye": 0, "no": 0, "unknown": 0, "vacant": 0}
    title = meta["title"] or "(division title not recorded)"
    party_majorities = _party_majorities_for_division(selected_vote_rows) if mode == "rebel-split" else {}

    if mode == "vote-split":
        legend = [
            {"key": "Aye", "label": "Aye", "color": VOTE_COLOURS["Aye"]},
            {"key": "No", "label": "No", "color": VOTE_COLOURS["No"]},
            {"key": "Absent/unknown", "label": "Absent/unknown", "color": VOTE_COLOURS["Absent/unknown"]},
        ]
        if has_vacancies:
            legend.append(
                {"key": "Vacant seat", "label": "Vacant seat", "color": VOTE_COLOURS["Vacant seat"]}
            )
    elif mode == "party-split":
        parties = sorted({(row["party"] or "Unknown").strip() or "Unknown" for row in member_rows})
        legend = [
            {"key": party, "label": party, "color": PARTY_COLOURS.get(party, "#8a97ab")}
            for party in parties
        ]
        legend.append(
            {"key": DID_NOT_VOTE_KEY, "label": "Did not vote on this division", "color": DID_NOT_VOTE_COLOUR}
        )
        if has_vacancies:
            legend.append({"key": "Vacant", "label": "Vacant", "color": PARTY_COLOURS.get("Vacant", "#8a97ab")})
    elif mode == "gender-split":
        legend = [
            {"key": "M", "label": "M", "color": GENDER_COLOURS["M"]},
            {"key": "F", "label": "F", "color": GENDER_COLOURS["F"]},
            {"key": "Unknown", "label": "Unknown gender", "color": GENDER_COLOURS["Unknown"]},
            {"key": DID_NOT_VOTE_KEY, "label": "Did not vote on this division", "color": DID_NOT_VOTE_COLOUR},
        ]
        if has_vacancies:
            legend.append(
                {"key": "No current MP", "label": "No current MP", "color": GENDER_COLOURS["No current MP"]}
            )
    else:
        legend = [
            {"key": key, "label": key.replace("_", " "), "color": colour}
            for key, colour in REBEL_COLOURS.items()
        ]

    for constituency, row, constituency_id in map_rows:
        if row is None:
            counts["vacant"] += 1
            vote = "Vacant seat"
            division_vote = "Vacant seat"
            party = "Vacant"
            majority = None
            gender = None
            rebel_status = None

            if mode == "vote-split":
                category = "Vacant seat"
                colour = VOTE_COLOURS["Vacant seat"]
                label = f"Vacant seat: {constituency} has no current MP for {title}"
            elif mode == "party-split":
                category = "Vacant"
                colour = PARTY_COLOURS.get("Vacant", "#8a97ab")
                label = f"Vacant seat: {constituency} has no current MP; no party vote on {title}"
            elif mode == "gender-split":
                gender = "No current MP"
                category = gender
                colour = GENDER_COLOURS["No current MP"]
                label = f"Vacant seat: {constituency} has no current MP; no gender vote on {title}"
            else:
                rebel_status = "vacant_seat"
                category = rebel_status
                colour = REBEL_COLOURS[rebel_status]
                label = f"Vacant seat: {constituency} has no current MP; no party-majority comparison on {title}"

            item = {
                "constituency": constituency,
                "constituency_id": constituency_id,
                "member_id": None,
                "name": "Vacant seat",
                "party": party,
                "vote": vote,
                "category": category,
                "legend_key": category,
                "color": colour,
                "label": label,
                "source": source,
                "mode": mode,
                "division_vote": division_vote,
                "is_vacant": True,
            }
            if gender is not None:
                item["gender"] = gender
            if rebel_status is not None:
                item["rebel_status"] = rebel_status
            votes.append(item)
            map_data[constituency] = dict(item)
            continue

        raw_vote = selected_votes_by_member.get(row["member_id"])
        division_vote = _vote_label(raw_vote)
        if division_vote == "Aye":
            counts["aye"] += 1
        elif division_vote == "No":
            counts["no"] += 1
        else:
            counts["unknown"] += 1

        party = (row["party"] or "Unknown").strip() or "Unknown"
        majority = None
        gender = None
        rebel_status = None

        vote = division_vote
        voted_in_division = raw_vote in (0, 1)
        if mode == "vote-split":
            category = division_vote
            colour = VOTE_COLOURS[vote]
            label = f"{vote}: {row['name']} on {title}"
        elif mode == "party-split":
            if voted_in_division:
                category = party
                colour = PARTY_COLOURS.get(party, "#8a97ab")
                label = f"{party}: {row['name']} voted {vote} on {title}"
            else:
                category = DID_NOT_VOTE_KEY
                colour = DID_NOT_VOTE_COLOUR
                label = f"Did not vote ({division_vote}): {row['name']} ({party}) on {title}"
        elif mode == "gender-split":
            gender = _member_gender_from_posts(row["current_posts"])
            gender_label = "Unknown gender" if gender == "Unknown" else gender
            if voted_in_division:
                category = gender
                colour = GENDER_COLOURS.get(gender, GENDER_COLOURS["Unknown"])
                label = f"Gender {gender_label}: {row['name']} voted {vote} on {title}"
            else:
                category = DID_NOT_VOTE_KEY
                colour = DID_NOT_VOTE_COLOUR
                label = f"Did not vote ({division_vote}): {row['name']} ({gender_label}) on {title}"
        else:
            if division_vote == "Absent/unknown":
                rebel_status = "absent_or_unknown"
            elif party == "Unknown" or party.lower() == "independent":
                rebel_status = "independent_or_no_party_grouping"
            else:
                majority = party_majorities.get(party)
                if majority is None:
                    rebel_status = "no_clear_party_majority"
                elif raw_vote == majority:
                    rebel_status = "with_party_majority"
                else:
                    rebel_status = "against_party_majority"
            category = rebel_status
            colour = REBEL_COLOURS[rebel_status]
            label = f"{rebel_status}: {row['name']} ({party}) voted {vote} on {title}"

        item = {
            "constituency": constituency,
            "constituency_id": constituency_id,
            "member_id": row["member_id"],
            "name": row["name"],
            "party": party,
            "vote": vote,
            "category": category,
            "legend_key": category,
            "color": colour,
            "label": label,
            "source": source,
            "mode": mode,
            "division_vote": division_vote,
            "is_vacant": False,
        }
        if gender is not None:
            item["gender"] = gender
        if rebel_status is not None:
            item["rebel_status"] = rebel_status
        if majority in (0, 1):
            item["party_majority_vote"] = _vote_label(majority)
        votes.append(item)
        map_data[constituency] = dict(item)

    source_url = f"/publicwhip/division/{meta['division_id']}"
    source_aye_count = int(meta["aye_count"] or 0)
    source_no_count = int(meta["no_count"] or 0)
    source_vote_count_total = source_aye_count + source_no_count
    mapped_recorded_vote_count = counts["aye"] + counts["no"]
    source_minus_mapped_vote_count = source_vote_count_total - mapped_recorded_vote_count

    return {
        "ok": True,
        "mode": mode,
        "map_mode": mode,
        "division_id": meta["division_id"],
        "title": meta["title"],
        "date": (meta["division_date"] or "")[:10],
        "aye_count": meta["aye_count"],
        "no_count": meta["no_count"],
        "match": {
            "method": "exact_local_division_id",
            "confidence": "high",
            "source": source,
        },
        "division": {
            "division_id": meta["division_id"],
            "title": meta["title"],
            "date": (meta["division_date"] or "")[:10],
            "aye_count": meta["aye_count"],
            "no_count": meta["no_count"],
            "source_url": source_url,
        },
        "counts": counts,
        "legend": legend,
        "map_data": map_data,
        "votes": votes,
        "source_links": [
            {"label": "PublicWhip division record", "url": source_url},
        ],
        "data_quality": {
            "division_scoped": True,
            "selected_division_id": meta["division_id"],
            "counts_basis": "official_constituencies_joined_to_current_members_and_selected_division_votes",
            "mapped_member_rows": current_member_rows,
            "current_member_rows": current_member_rows,
            "map_constituency_rows": map_constituency_rows,
            "vacant_constituency_rows": counts["vacant"],
            "selected_division_vote_rows": selected_division_vote_rows,
            "mapped_aye_count": counts["aye"],
            "mapped_no_count": counts["no"],
            "mapped_unknown_count": counts["unknown"],
            "mapped_vacant_count": counts["vacant"],
            "source_aye_count": source_aye_count,
            "source_no_count": source_no_count,
            "source_vote_count_total": source_vote_count_total,
            "mapped_recorded_vote_count": mapped_recorded_vote_count,
            "source_minus_mapped_vote_count": source_minus_mapped_vote_count,
            "source": source,
        },
        "caveat": (
            "This map describes recorded division data in the YourGov seed database. "
            "It does not infer motive, intent, wrongdoing, or absence of concern."
        ),
    }


def _division_payload(division_id, source="publicwhip"):
    payload = _division_map_payload(division_id, mode="vote-split", source=source)
    if payload:
        payload["map_mode"] = "votes"
    return payload


def _hex_lerp(a: str, b: str, t: float) -> str:
    a = (a or "#000000").lstrip("#")
    b = (b or "#000000").lstrip("#")
    if len(a) != 6 or len(b) != 6:
        return "#000000"
    t = max(0.0, min(1.0, float(t)))
    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    rr = int(ar + (br - ar) * t)
    rg = int(ag + (bg - ag) * t)
    rb = int(ab + (bb - ab) * t)
    return f"#{rr:02x}{rg:02x}{rb:02x}"


@app.route("/api/lens/map/party")
def api_lens_map_party():
    conn = get_publicwhip_conn()
    rows = conn.execute(
        """
        SELECT m.member_id, m.name, m.party, m.constituency
        FROM members m
        WHERE m.constituency IS NOT NULL
        ORDER BY m.constituency
        """
    ).fetchall()
    conn.close()
    map_data = {}
    for row in rows:
        party = row["party"] or "Unknown"
        colour = PARTY_COLOURS.get(party, "#8a97ab")
        constituency = row["constituency"]
        map_data[constituency] = {
            "color": colour,
            "label": f"{party}: {row['name']}",
            "vote": party,
            "member_id": row["member_id"],
            "name": row["name"],
            "party": party,
            "source": "members",
        }
    return jsonify(
        ok=True,
        map_mode="party",
        map_data=map_data,
        caveat="Party colours reflect the current MP party in the seed database. This is descriptive, not a ranking.",
    )


@app.route("/api/lens/map/gender")
def api_lens_map_gender():
    conn = get_publicwhip_conn()
    rows = conn.execute(
        """
        SELECT m.member_id, m.name, m.party, m.constituency, m.current_posts
        FROM members m
        WHERE m.constituency IS NOT NULL
        ORDER BY m.constituency
        """
    ).fetchall()
    conn.close()
    gender_colours = {"M": "#38bdf8", "F": "#f472b6"}
    map_data = {}
    for row in rows:
        constituency = row["constituency"]
        gender = None
        try:
            posts = json.loads(row["current_posts"] or "{}")
            gender = posts.get("gender")
        except Exception:
            gender = None
        g = (gender or "Unknown").strip() if isinstance(gender, str) else "Unknown"
        if g not in ("M", "F"):
            g = "Unknown"
        colour = gender_colours.get(g, "#6b7280")
        map_data[constituency] = {
            "color": colour,
            "label": f"Gender {g}: {row['name']}" if g in ("M", "F") else f"Gender unknown: {row['name']}",
            "vote": g,
            "member_id": row["member_id"],
            "name": row["name"],
            "party": row["party"] or "Unknown",
            "source": "members",
        }
    return jsonify(
        ok=True,
        map_mode="gender",
        map_data=map_data,
        caveat="Gender is taken from the Members API field stored in the seed database. Unknown means missing data, not a claim.",
    )


@app.route("/api/lens/map/rebel-rate")
def api_lens_map_rebel_rate():
    # Compute an approximate rebellion rate per MP over the most recent divisions in the local DB.
    limit_divisions = int(request.args.get("limit_divisions", "200") or "200")
    limit_divisions = max(25, min(600, limit_divisions))

    conn = get_publicwhip_conn()
    div_ids = [
        r["division_id"]
        for r in conn.execute(
            """
            SELECT DISTINCT division_id
            FROM votes
            ORDER BY division_date DESC, division_id DESC
            LIMIT ?
            """,
            (limit_divisions,),
        ).fetchall()
    ]
    if not div_ids:
        conn.close()
        return jsonify(ok=False, error="No vote data available for rebel-rate."), 422

    q_marks = ",".join(["?"] * len(div_ids))
    vote_rows = conn.execute(
        f"""
        SELECT v.division_id, v.member_id, v.voted_aye, m.party, m.name, m.constituency
        FROM votes v
        JOIN members m ON m.member_id = v.member_id
        WHERE v.division_id IN ({q_marks})
          AND m.constituency IS NOT NULL
          AND m.party IS NOT NULL
        """,
        tuple(div_ids),
    ).fetchall()
    conn.close()

    # First pass: party-majority by division (require >60% majority to count as party position).
    party_counts = {}
    for r in vote_rows:
        if r["voted_aye"] not in (0, 1):
            continue
        key = (r["division_id"], r["party"])
        if key not in party_counts:
            party_counts[key] = {0: 0, 1: 0}
        party_counts[key][r["voted_aye"]] += 1

    party_majority = {}
    for key, counts in party_counts.items():
        total = counts[0] + counts[1]
        if total <= 0:
            continue
        # require a clear majority to avoid mislabelling close splits
        if counts[1] / total >= 0.60:
            party_majority[key] = 1
        elif counts[0] / total >= 0.60:
            party_majority[key] = 0

    # Second pass: compute rebel rate per member.
    stats = {}
    for r in vote_rows:
        if r["voted_aye"] not in (0, 1):
            continue
        key = (r["division_id"], r["party"])
        maj = party_majority.get(key)
        if maj is None:
            continue
        mid = r["member_id"]
        if mid not in stats:
            stats[mid] = {
                "name": r["name"],
                "party": r["party"],
                "constituency": r["constituency"],
                "rebels": 0,
                "counted": 0,
            }
        stats[mid]["counted"] += 1
        if r["voted_aye"] != maj:
            stats[mid]["rebels"] += 1

    # Map colouring: single-hue intensity from grey -> amber.
    map_data = {}
    for mid, s in stats.items():
        counted = s["counted"] or 0
        if counted < 10:
            rate = None
        else:
            rate = s["rebels"] / counted
        if rate is None:
            colour = "#6b7280"
            label = f"Rebel rate: insufficient data ({counted} votes)"
        else:
            colour = _hex_lerp("#334155", "#f59e0b", min(1.0, rate * 2.0))
            label = f"Rebel rate: {int(rate*100)}% ({s['rebels']}/{counted})"
        map_data[s["constituency"]] = {
            "color": colour,
            "label": f"{label} — {s['name']}",
            "vote": "rebel_rate",
            "member_id": mid,
            "name": s["name"],
            "party": s["party"],
            "source": "votes",
        }

    return jsonify(
        ok=True,
        map_mode="rebel-rate",
        map_data=map_data,
        caveat=(
            "Rebel rate is computed from recorded divisions in the seed database over a recent window. "
            "Party position is inferred from party-majority (>60%) and can be noisy on close splits."
        ),
        window_divisions=len(div_ids),
    )


def _match_twf_url_to_division(url):
    match = re.search(r"/divisions/(pw-\d{4}-\d{2}-\d{2}-\d+-(?:commons|lords))", url)
    if not match:
        return {
            "ok": False,
            "error": "This is not a recognised TheyWorkForYou division URL.",
        }, 400

    slug = match.group(1)
    slug_match = re.match(r"pw-(\d{4}-\d{2}-\d{2})-(\d+)-(commons|lords)", slug)
    if not slug_match:
        return {"ok": False, "error": "Could not parse the TWFY division slug."}, 400

    date_text = slug_match.group(1)
    source_url = f"https://www.theyworkforyou.com/divisions/{slug}"
    try:
        resp = httpx.get(
            source_url,
            follow_redirects=True,
            timeout=12,
            headers={"User-Agent": "YourGov hackathon lens feasibility check"},
        )
        resp.raise_for_status()
    except Exception as exc:
        return {
            "ok": False,
            "error": f"TheyWorkForYou fetch failed from the server: {exc}",
            "source_url": source_url,
        }, 502

    html = resp.text
    title = None
    for pattern in (
        r'<meta property="og:title" content="([^"]+)"',
        r"<h1[^>]*>(.*?)</h1>",
        r"<title>(.*?)</title>",
    ):
        found = re.search(pattern, html, re.I | re.S)
        if found:
            title = re.sub(r"<[^>]+>", " ", found.group(1))
            title = re.sub(r"\s+", " ", title).strip()
            title = re.sub(r"\s*-\s*TheyWorkForYou\s*$", "", title)
            break

    if not title:
        return {
            "ok": False,
            "error": "Fetched TWFY page but could not extract a title.",
            "source_url": source_url,
        }, 422

    conn = get_publicwhip_conn()
    candidates = conn.execute(
        """
        SELECT division_id, title, division_date, aye_count, no_count
        FROM votes
        WHERE substr(division_date, 1, 10)=?
        GROUP BY division_id
        """,
        (date_text,),
    ).fetchall()
    conn.close()

    source_norm = _norm_title(title)
    best = None
    best_score = 0.0
    for candidate in candidates:
        score = SequenceMatcher(None, source_norm, _norm_title(candidate["title"])).ratio()
        if score > best_score:
            best = candidate
            best_score = score

    if not best or best_score < 0.86:
        return {
            "ok": False,
            "error": "Could not confidently match the TWFY page to a YourGov division.",
            "source_url": source_url,
            "extracted_title": title,
            "extracted_date": date_text,
            "best_score": round(best_score, 3),
            "confidence": "low",
        }, 422

    payload = _division_payload(best["division_id"], source="theyworkforyou-url")
    payload["match"] = {
        "method": "twfy_title_date_match",
        "confidence": "medium" if best_score < 0.94 else "high",
        "score": round(best_score, 3),
        "source": "theyworkforyou-url",
        "source_url": source_url,
        "extracted_title": title,
        "extracted_date": date_text,
    }
    payload["division"]["source_url"] = source_url
    return payload, 200


@app.route("/api/lens/source-divisions")
def api_lens_source_divisions():
    limit = min(int(request.args.get("limit", 50)), 200)
    conn = get_publicwhip_conn()
    rows = conn.execute(
        """
        SELECT DISTINCT division_id, title, division_date, aye_count, no_count
        FROM votes
        WHERE title IS NOT NULL AND aye_count > 0
        ORDER BY division_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return jsonify({
        "ok": True,
        "divisions": [
            {
                "division_id": r["division_id"],
                "title": r["title"],
                "date": (r["division_date"] or "")[:10],
                "aye_count": r["aye_count"],
                "no_count": r["no_count"],
                "source_url": f"/publicwhip/division/{r['division_id']}",
            }
            for r in rows
        ],
    })


def _mp_empty_record_status(party, current_posts=None):
    """Explain WHY an MP has no recorded division votes, so an empty list is never
    ambiguously read as 'data not loaded yet'."""
    normalised = (party or "").strip().lower()
    if normalised == "speaker":
        return {
            "code": "speaker",
            "message": (
                "By convention the Speaker does not vote in divisions except to "
                "break a tie, so there is no voting record to show."
            ),
        }
    posts_text = ""
    if current_posts:
        posts_text = (
            current_posts if isinstance(current_posts, str) else json.dumps(current_posts)
        ).lower()
    if "deputy speaker" in posts_text or "chairman of ways and means" in posts_text:
        return {
            "code": "deputy_speaker",
            "message": (
                "Deputy Speakers do not vote in divisions while they hold the Chair, "
                "so there is no voting record to show."
            ),
        }
    if normalised in {"sinn féin", "sinn fein"}:
        return {
            "code": "abstentionist",
            "message": (
                "Sinn Féin MPs follow a long-standing abstention policy: they do not "
                "take their seats or vote in House of Commons divisions, so there is "
                "no voting record to show."
            ),
        }
    return {
        "code": "no_recorded_votes",
        "message": (
            "No House of Commons divisions are recorded for this MP in the YourGov "
            "dataset yet."
        ),
    }


@app.route("/api/lens/mp/<int:member_id>/votes")
def api_lens_mp_votes(member_id):
    # Default to the full record; cap generously so a complete history can be
    # returned (and disclosed via total_votes) rather than silently truncated.
    limit = request.args.get("limit", default=2000, type=int)
    limit = max(1, min(limit or 2000, 2000))
    conn = get_publicwhip_conn()
    mp = conn.execute(
        "SELECT member_id, name, party, constituency, current_posts FROM members WHERE member_id=?",
        (member_id,),
    ).fetchone()
    if not mp:
        conn.close()
        return jsonify({"ok": False, "error": "MP not found in YourGov data."}), 404

    total_votes = conn.execute(
        "SELECT COUNT(*) AS n FROM votes WHERE member_id=?",
        (member_id,),
    ).fetchone()["n"]

    rows = conn.execute(
        """
        SELECT division_id, title, division_date, voted_aye, aye_count, no_count
        FROM votes
        WHERE member_id=?
        ORDER BY division_date DESC, division_id DESC
        LIMIT ?
        """,
        (member_id, limit),
    ).fetchall()
    conn.close()

    payload = {
        "ok": True,
        "mp": {
            "member_id": mp["member_id"],
            "name": mp["name"],
            "party": mp["party"] or "",
            "constituency": mp["constituency"] or "",
        },
        "total_votes": int(total_votes or 0),
        "returned_votes": len(rows),
        "truncated": len(rows) < int(total_votes or 0),
        "divisions": [
            {
                "division_id": row["division_id"],
                "title": row["title"] or "Untitled division",
                "date": (row["division_date"] or "")[:10],
                "vote": _vote_label(row["voted_aye"]),
                "voted_aye": row["voted_aye"],
                "aye_count": row["aye_count"] or 0,
                "no_count": row["no_count"] or 0,
                "source_url": f"/publicwhip/division/{row['division_id']}",
                "summary_url": f"/publicwhip/division/{row['division_id']}",
            }
            for row in rows
        ],
    }
    if not rows:
        payload["record_status"] = _mp_empty_record_status(mp["party"], mp["current_posts"])
    return jsonify(payload)


@app.route("/api/lens/division/<int:division_id>")
def api_lens_division(division_id):
    payload = _division_payload(division_id)
    if not payload:
        return jsonify({"ok": False, "error": "Division not found in YourGov data."}), 404
    return jsonify(payload)


@app.route("/api/lens/division/<int:division_id>/map")
def api_lens_division_map(division_id):
    mode = _normalise_division_map_mode(request.args.get("mode") or "vote-split")
    if not mode:
        return jsonify({"ok": False, "error": "Unsupported mode."}), 400

    payload = _division_map_payload(division_id, mode=mode)
    if not payload:
        return jsonify({"ok": False, "error": "Division not found in YourGov data."}), 404
    return jsonify(payload)


@app.route("/api/lens/recognise-url", methods=["POST"])
def api_lens_recognise_url():
    data = request.get_json(silent=True) or {}
    raw_url = (data.get("url") or "").strip()
    if not raw_url:
        return jsonify({"ok": False, "error": "URL is required."}), 400

    local_match = re.search(r"/publicwhip/division/(\d+)", raw_url)
    if local_match:
        payload = _division_payload(int(local_match.group(1)), source="mygov-publicwhip")
        if not payload:
            return jsonify({"ok": False, "error": "Division not found in YourGov data."}), 404
        return jsonify(payload)

    if "theyworkforyou.com" in raw_url.lower():
        payload, status = _match_twf_url_to_division(raw_url)
        return jsonify(payload), status

    return jsonify({
        "ok": False,
        "error": "Only YourGov PublicWhip division URLs and TheyWorkForYou division URLs are recognised in this POC.",
    }), 400


@app.route("/map/relay")
def map_relay():
    assets_dir = os.path.join(app.root_path, "static", "promap", "assets")
    js_asset_name = "index-uJtvkwRy.js"
    css_asset_name = "index-CvBPfDPn.css"
    try:
        js_candidates = sorted(
            [f for f in os.listdir(assets_dir) if f.startswith("index-") and f.endswith(".js")],
            key=lambda f: os.path.getmtime(os.path.join(assets_dir, f)),
            reverse=True,
        )
        css_candidates = sorted(
            [f for f in os.listdir(assets_dir) if f.startswith("index-") and f.endswith(".css")],
            key=lambda f: os.path.getmtime(os.path.join(assets_dir, f)),
            reverse=True,
        )
        if js_candidates:
            js_asset_name = js_candidates[0]
        if css_candidates:
            css_asset_name = css_candidates[0]
    except OSError:
        pass

    def versioned_promap_asset(filename):
        asset_url = f"/static/promap/assets/{filename}"
        try:
            version = os.stat(os.path.join(assets_dir, filename)).st_mtime_ns
        except OSError:
            return asset_url
        return f"{asset_url}?v={version}"

    js_asset = versioned_promap_asset(js_asset_name)
    css_asset = versioned_promap_asset(css_asset_name)
    return render_template("map_relay.html", promap_js=js_asset, promap_css=css_asset)


@app.route("/compare")
def compare():
    return render_template("compare.html")


@app.route("/ab_search_vs_lens")
@app.route("/ab_search_vs_panel")
def ab_legacy_redirect():
    return redirect("/source-lens", 302)


@app.route("/map")
def constituency_map():
    variant = request.args.get("variant", "A").upper()
    if variant not in ("A", "B"):
        variant = "A"
    return render_template("map.html", variant=variant)


@app.route("/map/pro")
@app.route("/map/pro/<path:subpath>")
def constituency_map_pro(subpath=""):
    from flask import send_from_directory
    return send_from_directory(
        os.path.join(app.root_path, "static", "promap"), "index.html"
    )


@app.route("/ab_map")
def ab_map():
    variant = request.args.get("variant", "a").lower()
    if variant not in ("a", "b"):
        variant = "a"
    return render_template("ab_map.html", variant=variant)


@app.route("/ab_map/<variant_id>")
def ab_map_variant(variant_id):
    v = (variant_id or "").lower()
    if v not in ("a", "b"):
        return redirect("/ab_map", 302)
    return redirect(f"/ab_map?variant={v}", 302)


@app.route("/api/telemetry", methods=["POST"])
def telemetry():
    data = request.get_json(silent=True) or {}
    event = (data.get("event") or "").strip()[:60]
    if not event:
        return jsonify({"ok": False}), 400
    payload = {
        "event": event,
        "ts": __import__("datetime").datetime.utcnow().isoformat(),
        "props": {k: v for k, v in data.items() if k != "event" and isinstance(v, (str, int, float, bool))}
    }
    try:
        log_path = os.path.join(os.path.dirname(__file__), "telemetry.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(__import__("json").dumps(payload) + "\n")
    except Exception:
        pass
    return jsonify({"ok": True})


# ── Agent Control API ─────────────────────────────────────────────
import hashlib
from functools import wraps
from datetime import datetime, timezone

_AGENT_API_TOKEN = os.environ.get("MYGOV_AGENT_API_TOKEN", "")
_agent_rate_store: dict = {}
_AGENT_RATE_WINDOW = 60.0
_AGENT_RATE_MAX = 60


def _agent_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_response(data=None, error=None, status=200):
    return jsonify({
        "ok": error is None,
        "data": data,
        "error": error,
        "ts": _agent_ts(),
    }), status


def _agent_check_rate(token_hash: str) -> bool:
    now = time.time()
    hits = _agent_rate_store.get(token_hash, [])
    hits = [t for t in hits if now - t < _AGENT_RATE_WINDOW]
    if len(hits) >= _AGENT_RATE_MAX:
        _agent_rate_store[token_hash] = hits
        return False
    hits.append(now)
    _agent_rate_store[token_hash] = hits
    return True


def require_agent_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _AGENT_API_TOKEN:
            return _agent_response(error="Agent API not configured on this server", status=503)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {_AGENT_API_TOKEN}":
            return _agent_response(error="Unauthorized", status=401)
        token_hash = hashlib.sha256(_AGENT_API_TOKEN.encode()).hexdigest()[:16]
        if not _agent_check_rate(token_hash):
            return _agent_response(error="Rate limit exceeded", status=429)
        return f(*args, **kwargs)
    return decorated


@app.route("/api/agent/health")
@require_agent_token
def agent_health():
    try:
        conn = get_publicwhip_conn()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False
    return _agent_response(data={
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "version": "1.0",
    })


@app.route("/api/agent/routes")
@require_agent_token
def agent_routes():
    return _agent_response(data={
        "routes": [
            {"path": "/", "description": "Search for an MP by name, postcode, or constituency"},
            {"path": "/source-lens", "description": "Interactive vote map and division browser (canonical UK view)"},
            {"path": "/global", "description": "Global civic feasibility map — country-adapter readiness"},
            {"path": "/mp/<id>", "description": "MP profile — votes, questions, issue spotlight"},
            {"path": "/api/agent/search_mps?q=<text>", "description": "Search MPs by name/party/constituency"},
            {"path": "/api/agent/map_payload?mode=<vote-split|party-split|gender-split|rebel-split>[&division_id=<id>]", "description": "Get map-ready selected-division payload for a map mode"},
            {"path": "/api/agent/global/countries[?status=green|orange|red&limit=<n>]", "description": "List countries from global feasibility dataset"},
            {"path": "/api/agent/global/country/<iso2>", "description": "Get one country feasibility record by ISO2"},
            {"path": "/api/agent/deeplink?target=<source-lens|global|mp|ab-map|publicwhip-division>", "description": "Build canonical in-app deep links for agent navigation"},
        ]
    })


@app.route("/api/agent/divisions")
@require_agent_token
def agent_divisions():
    limit = min(int(request.args.get("limit", 10)), 100)
    conn = get_publicwhip_conn()
    rows = conn.execute(
        """
        SELECT DISTINCT division_id, title, division_date, aye_count, no_count
        FROM votes
        WHERE title IS NOT NULL AND aye_count > 0
        ORDER BY division_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return _agent_response(data={
        "divisions": [
            {
                "division_id": r["division_id"],
                "title": r["title"],
                "date": (r["division_date"] or "")[:10],
                "aye_count": r["aye_count"],
                "no_count": r["no_count"],
            }
            for r in rows
        ]
    })


@app.route("/api/agent/division/<int:division_id>")
@require_agent_token
def agent_division(division_id):
    conn = get_publicwhip_conn()
    meta = conn.execute(
        "SELECT division_id, title, division_date, aye_count, no_count FROM votes WHERE division_id=? LIMIT 1",
        (division_id,),
    ).fetchone()
    if not meta:
        conn.close()
        return _agent_response(error="Division not found", status=404)

    voter_rows = conn.execute(
        """
        SELECT m.member_id, m.name, m.party, m.constituency, v.voted_aye
        FROM members m
        LEFT JOIN votes v ON v.member_id = m.member_id AND v.division_id = ?
        WHERE m.constituency IS NOT NULL
        ORDER BY m.name
        LIMIT 20
        """,
        (division_id,),
    ).fetchall()
    conn.close()

    voters = [
        {
            "member_id": r["member_id"],
            "name": r["name"],
            "party": r["party"],
            "constituency": r["constituency"],
            "vote": "Aye" if r["voted_aye"] == 1 else ("No" if r["voted_aye"] == 0 else "Unknown"),
        }
        for r in voter_rows
    ]

    return _agent_response(data={
        "division_id": meta["division_id"],
        "title": meta["title"],
        "date": (meta["division_date"] or "")[:10],
        "aye_count": meta["aye_count"],
        "no_count": meta["no_count"],
        "sample_voters": voters,
        "caveat": (
            "Sample voters only (first 20 alphabetically). "
            "Unknown means no recorded vote in this dataset — not guilt or absence of concern."
        ),
    })


@app.route("/api/agent/explain", methods=["POST"])
@require_agent_token
def agent_explain():
    body = request.get_json(silent=True) or {}
    division_id = body.get("division_id")
    member_id = body.get("member_id")
    if not isinstance(division_id, int) or not isinstance(member_id, int):
        return _agent_response(error="division_id and member_id must be integers", status=400)

    raw_level = body.get("level", 1)
    _level_str_map = {"skim": 0, "practical": 1, "detailed": 2, "full": 3}
    if isinstance(raw_level, str):
        level = _level_str_map.get(raw_level.lower(), 1)
    elif isinstance(raw_level, int) and raw_level in (0, 1, 2, 3):
        level = raw_level
    else:
        level = 1

    conn = get_conn()
    cached = conn.execute(
        "SELECT explanation FROM explanations WHERE division_id=? AND member_id=? AND level=? AND prompt_version=?",
        (division_id, member_id, level, EXPLAIN_PROMPT_VERSION),
    ).fetchone()
    if cached:
        conn.close()
        return _agent_response(data={
            "explanation": cached["explanation"],
            "cached": True,
            "caveat": "This record shows how this MP voted. It does not prove intent, motivation, or personal character.",
        })

    row = conn.execute(
        "SELECT title, voted_aye FROM votes WHERE division_id=? AND member_id=?",
        (division_id, member_id),
    ).fetchone()
    conn.close()

    if not row:
        return _agent_response(error="Vote record not found for this MP and division", status=404)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return _agent_response(data={
            "explanation": _LEVEL_FALLBACKS[level],
            "cached": False,
            "fallback": True,
            "caveat": "This record shows how this MP voted. It does not prove intent, motivation, or personal character.",
        })

    try:
        from openai import OpenAI as _OpenAI
        oa_client = _OpenAI(api_key=api_key)
        vote_direction = "Aye" if row["voted_aye"] else "No"
        system_prompt = _EXPLAIN_SYSTEM_PROMPT.format(
            level_name=_LEVEL_NAMES[level],
            level_instructions=_LEVEL_INSTRUCTIONS[level],
        )
        resp = oa_client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            max_tokens=_LEVEL_TOKENS[level],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _EXPLAIN_USER_TEMPLATE.format(
                    title=row["title"] or "(title not recorded)",
                    vote_direction=vote_direction,
                )},
            ],
        )
        explanation = resp.choices[0].message.content.strip()
    except Exception as e:
        return _agent_response(error=f"AI service error: {e}", status=500)

    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO explanations (division_id, member_id, level, prompt_version, explanation) VALUES (?,?,?,?,?)",
        (division_id, member_id, level, EXPLAIN_PROMPT_VERSION, explanation),
    )
    conn.commit()
    conn.close()

    return _agent_response(data={
        "explanation": explanation,
        "cached": False,
        "caveat": "This record shows how this MP voted. It does not prove intent, motivation, or personal character.",
    })


@app.route("/api/agent/mp/<int:member_id>")
@require_agent_token
def agent_mp(member_id):
    conn = get_conn()
    member = conn.execute(
        "SELECT member_id, name, party, constituency FROM members WHERE member_id=?",
        (member_id,),
    ).fetchone()
    if not member:
        conn.close()
        return _agent_response(error="MP not found", status=404)

    vote_count = conn.execute(
        "SELECT COUNT(*) FROM votes WHERE member_id=?", (member_id,)
    ).fetchone()[0]

    question_count = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE member_id=?", (member_id,)
    ).fetchone()[0]

    recent_votes = conn.execute(
        "SELECT division_id, title, division_date, voted_aye FROM votes WHERE member_id=? ORDER BY division_date DESC LIMIT 5",
        (member_id,),
    ).fetchall()
    conn.close()

    return _agent_response(data={
        "member_id": member["member_id"],
        "name": member["name"],
        "party": member["party"],
        "constituency": member["constituency"],
        "votes_recorded": vote_count,
        "questions_recorded": question_count,
        "recent_votes": [
            {
                "division_id": v["division_id"],
                "title": v["title"],
                "date": (v["division_date"] or "")[:10],
                "voted_aye": bool(v["voted_aye"]),
            }
            for v in recent_votes
        ],
    })


@app.route("/api/agent/search_mps")
@require_agent_token
def agent_search_mps():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return _agent_response(error="q must be at least 2 characters", status=400)

    limit = min(max(int(request.args.get("limit", 10)), 1), 50)
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT member_id, name, party, constituency
        FROM members
        WHERE constituency IS NOT NULL
          AND (name LIKE ? OR party LIKE ? OR constituency LIKE ?)
        ORDER BY name
        LIMIT ?
        """,
        (f"%{q}%", f"%{q}%", f"%{q}%", limit),
    ).fetchall()
    conn.close()
    return _agent_response(data={
        "query": q,
        "results": [
            {
                "member_id": r["member_id"],
                "name": r["name"],
                "party": r["party"],
                "constituency": r["constituency"],
                "profile_url": f"/mp/{r['member_id']}",
            }
            for r in rows
        ],
    })


@app.route("/api/agent/map_payload")
@require_agent_token
def agent_map_payload():
    mode = _normalise_division_map_mode(request.args.get("mode") or "vote-split")
    raw_division_id = request.args.get("division_id")
    division_id = None

    if not mode:
        return _agent_response(error="Unsupported mode", status=400)

    if "division_id" in request.args:
        raw_division_id = (raw_division_id or "").strip()
        if not raw_division_id:
            return _agent_response(error="division_id must be a positive integer", status=400)
        try:
            division_id = int(raw_division_id)
        except ValueError:
            return _agent_response(error="division_id must be a positive integer", status=400)
        if division_id <= 0:
            return _agent_response(error="division_id must be a positive integer", status=400)

    if division_id is None:
        conn = get_publicwhip_conn()
        latest = conn.execute(
            """
            SELECT DISTINCT division_id
            FROM votes
            WHERE title IS NOT NULL AND aye_count > 0
            ORDER BY division_date DESC
            LIMIT 1
            """
        ).fetchone()
        conn.close()
        if not latest:
            return _agent_response(error="No divisions available", status=404)
        division_id = int(latest["division_id"])

    payload = _division_map_payload(division_id, mode=mode)
    if not payload:
        return _agent_response(error="Division not found", status=404)
    if not payload.get("ok"):
        return _agent_response(error=payload.get("error", "Division payload failed"), status=404)
    return _agent_response(data=payload)


@app.route("/api/agent/global/countries")
@require_agent_token
def agent_global_countries():
    data = _load_global_feasibility()
    countries = data.get("countries", [])
    status_filter = (request.args.get("status") or "").strip().lower()
    if status_filter in {"green", "orange", "red"}:
        countries = [c for c in countries if (c.get("status") or "").lower() == status_filter]
    limit = min(max(int(request.args.get("limit", 25)), 1), 200)
    slim = [
        {
            "name": c.get("name"),
            "iso2": c.get("iso2"),
            "status": c.get("status"),
            "status_label": c.get("status_label"),
            "summary": c.get("summary"),
            "working_adapter": bool(c.get("working_adapter")),
        }
        for c in countries[:limit]
    ]
    return _agent_response(data={"countries": slim, "count": len(slim)})


@app.route("/api/agent/global/country/<iso2>")
@require_agent_token
def agent_global_country(iso2):
    cc = (iso2 or "").strip().upper()
    data = _load_global_feasibility()
    for c in data.get("countries", []):
        if (c.get("iso2") or "").upper() == cc:
            return _agent_response(data={"country": c})
    return _agent_response(error="Country not found", status=404)


@app.route("/api/agent/deeplink")
@require_agent_token
def agent_deeplink():
    target = (request.args.get("target") or "").strip().lower()

    if target == "source-lens":
        cc = (request.args.get("cc") or "").strip().upper() or "GB"
        lang = (request.args.get("lang") or "").strip().lower() or "en"
        source = (request.args.get("source") or "lens").strip().lower()
        return _agent_response(data={
            "target": "source-lens",
            "path": f"/source-lens?source={source}&cc={cc}&lang={lang}",
        })

    if target == "global":
        cc = (request.args.get("cc") or "").strip().upper() or "GB"
        lang = (request.args.get("lang") or "").strip().lower() or "en"
        return _agent_response(data={
            "target": "global",
            "path": f"/global?cc={cc}&lang={lang}",
        })

    if target == "mp":
        member_id = request.args.get("member_id", type=int)
        if not member_id:
            return _agent_response(error="member_id is required for target=mp", status=400)
        return _agent_response(data={
            "target": "mp",
            "path": f"/mp/{member_id}",
        })

    if target == "ab-map":
        variant = (request.args.get("variant") or "a").strip().lower()
        if variant not in {"a", "b"}:
            variant = "a"
        return _agent_response(data={
            "target": "ab-map",
            "path": f"/ab_map?variant={variant}",
        })

    if target == "publicwhip-division":
        division_id = request.args.get("division_id", type=int)
        if not division_id:
            return _agent_response(error="division_id is required for target=publicwhip-division", status=400)
        return _agent_response(data={
            "target": "publicwhip-division",
            "path": f"/publicwhip/division/{division_id}",
        })

    return _agent_response(
        error="Unsupported target. Use one of: source-lens, global, mp, ab-map, publicwhip-division",
        status=400,
    )


if __name__ == "__main__":
    app.run(debug=False, port=5050)
