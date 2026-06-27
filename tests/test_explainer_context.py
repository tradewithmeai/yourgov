"""Tests for the explainer grounding + context assembly (Phase 1).

Covers the division-summary builder (precise DB lookup), the directly-injected
grounding docs, the click-focus decay in the assembled system prompt, history
sanitising, and the /api/explain-selection envelope.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as appmod  # noqa: E402
import explainer_context as ec  # noqa: E402


def _latest_division_id():
    conn = appmod.get_publicwhip_conn()
    try:
        row = conn.execute("SELECT MAX(division_id) AS d FROM votes WHERE aye_count > 0").fetchone()
        return int(row["d"])
    finally:
        conn.close()


def test_build_division_summary_is_structured_and_precise():
    division_id = _latest_division_id()
    conn = appmod.get_publicwhip_conn()
    try:
        summary = ec.build_division_summary(conn, division_id)
    finally:
        conn.close()

    assert summary is not None
    assert summary["division_id"] == division_id
    assert isinstance(summary["title"], str) and summary["title"]
    assert summary["outcome"] in ("passed", "rejected", "tied")
    assert isinstance(summary["aye_count"], int)
    assert isinstance(summary["no_count"], int)
    assert summary["total_recorded"] == summary["aye_count"] + summary["no_count"]
    # A real, contested division has at least one party with a recorded split.
    assert summary["party_breakdown"], "expected a per-party breakdown"
    for p in summary["party_breakdown"]:
        assert set(p) == {"party", "aye", "no"}
    assert isinstance(summary["rebel_count"], int)
    assert len(summary["notable_rebels"]) <= 8


def test_build_division_summary_returns_none_for_missing_division():
    conn = appmod.get_publicwhip_conn()
    try:
        assert ec.build_division_summary(conn, 99999999) is None
    finally:
        conn.close()


def test_render_division_summary_text_and_compact():
    summary = {
        "division_id": 2355,
        "title": "Example Bill: Third Reading",
        "date": "2026-06-01",
        "aye_count": 307,
        "no_count": 171,
        "outcome": "passed",
        "total_recorded": 478,
        "party_breakdown": [
            {"party": "Labour", "aye": 300, "no": 2},
            {"party": "Conservative", "aye": 1, "no": 100},
        ],
        "rebel_count": 2,
        "notable_rebels": [
            {"name": "A B", "party": "Labour", "voted": "No"},
            {"name": "C D", "party": "Conservative", "voted": "Aye"},
        ],
    }
    text = ec.render_division_summary(summary)
    assert "Example Bill: Third Reading" in text
    assert "PASSED" in text
    assert "Ayes 307" in text and "Noes 171" in text
    assert "Labour 300-2" in text
    assert "A B (Labour, voted No)" in text

    compact = ec.render_division_summary(summary, compact=True)
    assert "Example Bill: Third Reading" in compact
    assert "Labour 300-2" not in compact  # compact omits the party detail


def test_load_grounding_docs_includes_both_corpora():
    ec.clear_grounding_cache()
    grounding = ec.load_grounding_docs(ROOT)
    assert grounding, "grounding docs should be present"
    low = grounding.lower()
    assert "yourgov" in low
    assert "glossary" in low
    assert "division" in low
    # The two docs are joined; expect content from each.
    assert "self-knowledge" in low
    assert "wikipedia.org" in low  # glossary links


def test_assemble_system_prompt_click_focus_then_decay():
    grounding = "GROUNDING_MARKER"
    div = "Division 2382 — \"X\" (2026-06-17). Result: PASSED (Ayes 5, Noes 3)."
    click = '"Aye on the National Security Bill"'

    # Turn 0: the click and division lead.
    opening = ec.assemble_system_prompt(
        "PRACTICAL", "Write 2-3 sentences.", grounding, div, click, turn_index=0
    )
    assert "CURRENT FOCUS" in opening
    assert "DIVISION IN CONTEXT" in opening
    assert "GROUNDING_MARKER" in opening
    assert "began from" not in opening.lower()

    # Turn 3+: the click decays to background, grounding/history lead.
    later = ec.assemble_system_prompt(
        "PRACTICAL", "Write 2-3 sentences.", grounding, div, click, turn_index=3
    )
    assert "CURRENT FOCUS" not in later
    assert "began from" in later.lower() or "broadened" in later.lower()
    assert "background" in later.lower()
    assert "GROUNDING_MARKER" in later  # grounding stays available throughout

    # Safety rules are pinned in both.
    assert "Never infer intent" in opening
    assert "Never infer intent" in later


def test_normalise_history_filters_trims_and_limits():
    raw = [
        {"role": "user", "content": "  hi  "},
        {"role": "assistant", "content": "hello"},
        {"role": "system", "content": "should be dropped"},
        {"role": "user", "content": ""},
        {"role": "user"},
        "not a dict",
        {"role": "user", "content": "x" * 5000},
    ]
    out = ec.normalise_history(raw, limit=10)
    roles = [m["role"] for m in out]
    assert "system" not in roles
    assert out[0] == {"role": "user", "content": "hi"}
    assert all(len(m["content"]) <= 2000 for m in out)
    # Empty / malformed entries dropped.
    assert all(m["content"] for m in out)
    # Limit trims to most recent.
    big = [{"role": "user", "content": str(i)} for i in range(30)]
    assert len(ec.normalise_history(big, limit=12)) == 12


def test_explain_selection_envelope_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    resp = client.post("/api/explain-selection", json={
        "target_text": "Sir Keir Starmer voted Aye",
        "surrounding_text": "Division on the National Security Bill",
        "level": 1,
        "metadata": {"division_id": _latest_division_id()},
    })
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("clicked", "meaning", "source_support", "does_not_prove", "followups"):
        assert key in data
    assert isinstance(data["followups"], list)


def test_division_summary_text_helper_resolves_from_yourgov_state():
    division_id = _latest_division_id()
    text = appmod._division_summary_text_for(
        {"yourgov_state": {"selected_division": {"division_id": division_id}}}
    )
    assert text and f"Division {division_id}" in text
    # No division in context -> empty (so the explainer just uses grounding).
    assert appmod._division_summary_text_for({}) == ""


# ── Cost guards ────────────────────────────────────────────────────────────

def test_is_cacheable_turn():
    assert ec.is_cacheable_turn("", []) is True          # opening click
    assert ec.is_cacheable_turn("why?", []) is False      # follow-up question
    assert ec.is_cacheable_turn("", [{"role": "user", "content": "x"}]) is False  # has history


def test_selection_cache_key_stable_and_part_sensitive():
    a = ec.selection_cache_key(["div", 1, 2382, "144-244", "division"])
    b = ec.selection_cache_key(["div", 1, 2382, "144-244", "division"])
    assert a == b  # deterministic
    # A changed vote fingerprint must invalidate the cached explanation.
    assert a != ec.selection_cache_key(["div", 1, 2382, "200-100", "division"])
    # Level and element type are part of the key.
    assert a != ec.selection_cache_key(["div", 2, 2382, "144-244", "division"])
    assert a != ec.selection_cache_key(["div", 1, 2382, "144-244", "vote"])


def test_division_vote_cache_key_is_member_and_text_specific():
    # Regression for cross-user cache poisoning / cross-member collision: a coarse
    # division-only key (level, division, fingerprint, type) let the first caller's
    # attacker-controllable text be cached and served to every later user on the
    # same division, and collided MP A's vote row with MP B's. The key must change
    # when the member OR the clicked text changes; identical clicks must still share.
    base = ["sel", 1, "vote", 2, "307-57"]
    a = ec.selection_cache_key(base + ["8",    "MP A voted Aye", "", "", ""])
    b = ec.selection_cache_key(base + ["4532", "MP B voted No",  "", "", ""])
    poison = ec.selection_cache_key(base + ["8", "POISON_MARKER", "", "", ""])
    assert a != b          # different member + text -> separate cache entries
    assert a != poison     # different clicked text -> separate entry (no poisoning)
    # An identical click still shares (legitimate caching preserved).
    assert a == ec.selection_cache_key(base + ["8", "MP A voted Aye", "", "", ""])


def test_selection_cache_key_unambiguous_serialization():
    # The parts must serialize injectively (a free-text "|" must not let two
    # different part-lists collide).
    assert ec.selection_cache_key(["a|b", "c"]) != ec.selection_cache_key(["a", "b|c"])


def test_normalise_explain_type_collapses_to_fixed_set():
    assert ec.normalise_explain_type("division-row") == "division"
    assert ec.normalise_explain_type("division") == "division"
    assert ec.normalise_explain_type("vote") == "vote"
    assert ec.normalise_explain_type("mp") == "mp"
    # Anything else (including attacker free text or a non-string) → "other",
    # so the cache key can only take a few values.
    assert ec.normalise_explain_type("whatever-xyz") == "other"
    assert ec.normalise_explain_type(None) == "other"
    assert ec.normalise_explain_type(123) == "other"


def test_sliding_window_allow_enforces_max():
    store = {}
    allows = [ec.sliding_window_allow(store, "ip", 1000.0, 60.0, 3) for _ in range(5)]
    assert allows == [True, True, True, False, False]
    # A later timestamp past the window frees the allowance again.
    assert ec.sliding_window_allow(store, "ip", 1000.0 + 61, 60.0, 3) is True


def test_budget_reserve_enforces_daily_ceiling():
    conn = appmod.get_conn()
    appmod._ensure_explainer_tables(conn)
    day = "test-day-2099-01-01"
    conn.execute("DELETE FROM explainer_budget WHERE day=?", (day,))
    conn.commit()
    try:
        reserved = [appmod._explainer_budget_reserve(conn, day, 3) for _ in range(5)]
        assert reserved == [True, True, True, False, False]
        assert appmod._explainer_budget_reserve(conn, "test-day-zero", 0) is False
    finally:
        conn.execute("DELETE FROM explainer_budget WHERE day IN (?, ?)", (day, "test-day-zero"))
        conn.commit()
        conn.close()


def test_cache_round_trip_and_ttl_expiry():
    conn = appmod.get_conn()
    appmod._ensure_explainer_tables(conn)
    key = "test-cache-key-abc"
    payload = {"clicked": "x", "meaning": "m", "source_support": "s",
               "does_not_prove": "d", "followups": []}
    conn.execute("DELETE FROM selection_cache WHERE key=?", (key,))
    conn.commit()
    try:
        appmod._explainer_cache_put(conn, key, payload)
        assert appmod._explainer_cache_get(conn, key, ttl=3600) == payload
        # Age the row beyond the TTL -> miss.
        conn.execute("UPDATE selection_cache SET created_at = ? WHERE key = ?",
                     (1.0, key))
        conn.commit()
        assert appmod._explainer_cache_get(conn, key, ttl=10) is None
    finally:
        conn.execute("DELETE FROM selection_cache WHERE key=?", (key,))
        conn.commit()
        conn.close()


def test_ip_store_is_bounded_against_spoofed_ip_flood(monkeypatch):
    monkeypatch.setattr(appmod, "_EXPLAINER_IP_STORE_CAP", 100)
    appmod._EXPLAINER_IP_STORE.clear()
    now = 1_000_000.0
    # Simulate a flood of distinct (stale) IPs well past the cap.
    for i in range(500):
        appmod._EXPLAINER_IP_STORE[f"ip{i}:m"] = [now - 100_000]  # all older than a day
    appmod._prune_ip_store(now)
    assert len(appmod._EXPLAINER_IP_STORE) <= 100  # bounded, stale entries dropped
    appmod._EXPLAINER_IP_STORE.clear()


def _client_with_fake_key(monkeypatch):
    # A syntactically-fake key reaches the guard logic; if a guard wrongly lets a
    # request through it would 401 (an error envelope), failing the test loudly
    # without a real charge.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-for-tests")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_endpoint_falls_back_when_budget_exhausted(monkeypatch):
    client = _client_with_fake_key(monkeypatch)
    monkeypatch.setattr(appmod, "_EXPLAINER_DAILY_BUDGET", 0)  # nothing allowed
    appmod._EXPLAINER_IP_STORE.clear()
    resp = client.post("/api/explain-selection", json={
        "target_text": "Some clicked element", "level": 1, "metadata": {},
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "error" not in data  # never reached OpenAI
    assert data["meaning"] == appmod._LEVEL_FALLBACKS[1]  # the safe fallback


def test_endpoint_falls_back_when_rate_limited(monkeypatch):
    client = _client_with_fake_key(monkeypatch)
    monkeypatch.setattr(appmod, "_EXPLAINER_RATE_PER_MIN", 0)  # block at the per-minute cap
    monkeypatch.setattr(appmod, "_EXPLAINER_DAILY_BUDGET", 10_000)
    appmod._EXPLAINER_IP_STORE.clear()
    resp = client.post("/api/explain-selection", json={
        "target_text": "Some clicked element", "level": 1, "metadata": {},
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "error" not in data
    assert data["meaning"] == appmod._LEVEL_FALLBACKS[1]


def test_endpoint_serves_cache_hit_without_calling_openai(monkeypatch):
    client = _client_with_fake_key(monkeypatch)
    monkeypatch.setattr(appmod, "_EXPLAINER_RATE_PER_MIN", 1000)
    monkeypatch.setattr(appmod, "_EXPLAINER_RATE_PER_DAY", 1000)
    monkeypatch.setattr(appmod, "_EXPLAINER_DAILY_BUDGET", 10_000)
    appmod._EXPLAINER_IP_STORE.clear()

    target = "Cache-hit probe element"
    # No division/member (metadata={}); the endpoint binds the full answer context
    # into the key: [sel, level, ntype, division_id, division_fp, member_id,
    # target_text, surrounding, source_links, url]. Match it exactly.
    key = ec.selection_cache_key(["sel", 1, "other", "", "", "", target, "", "", ""])
    seeded = {"clicked": target, "meaning": "SEEDED ANSWER", "source_support": "s",
              "does_not_prove": "d", "followups": ["q1"]}
    conn = appmod.get_conn()
    appmod._ensure_explainer_tables(conn)
    appmod._explainer_cache_put(conn, key, seeded)
    conn.close()
    try:
        resp = client.post("/api/explain-selection", json={
            "target_text": target, "level": 1, "metadata": {},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["meaning"] == "SEEDED ANSWER"  # served from cache, not OpenAI
        assert data.get("cached") is True
    finally:
        conn = appmod.get_conn()
        conn.execute("DELETE FROM selection_cache WHERE key=?", (key,))
        conn.commit()
        conn.close()


def test_endpoint_never_500s_on_hostile_request_bodies(monkeypatch):
    # No API key -> the endpoint must coerce wrong-typed fields and return the
    # safe envelope, never an unhandled 500. (No key also means no OpenAI call.)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    hostile_bodies = [
        {"target_text": "hi", "metadata": "not-a-dict"},
        {"target_text": "hi", "metadata": [1, 2, 3]},
        {"target_text": 5},
        {"target_text": ["a", "b"]},
        {"target_text": "hi", "surrounding_text": ["x"]},
        {"target_text": "hi", "source_links": [1, 2, 3]},
        {"target_text": "hi", "source_links": {"a": 1}},
        {"target_text": "hi", "level": True},
        {"target_text": "hi", "messages": "not-a-list"},
        ["this", "is", "a", "list", "body"],
        "a bare string body",
    ]
    for body in hostile_bodies:
        resp = client.post("/api/explain-selection", json=body)
        # Either a clean 400 (missing target_text) or a 200 safe envelope — never 500.
        assert resp.status_code in (200, 400), f"{body!r} -> {resp.status_code}"
        data = resp.get_json()
        if resp.status_code == 200:
            for k in ("clicked", "meaning", "source_support", "does_not_prove", "followups"):
                assert k in data, f"{body!r} missing key {k}"
