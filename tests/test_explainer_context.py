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
