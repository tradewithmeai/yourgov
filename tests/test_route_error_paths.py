"""Error / edge-path coverage for the DB-backed routes.

These exercise the "not found" early-returns that the connection-leak refactor
moved INSIDE the `with db_conn()/pw_conn()` blocks. A regression here (wrong
status, or a 500 from a leaked/!closed handle) is exactly what this guards.
Real-data success paths resolve a live division id from the seed at run time so
the tests stay valid as the data refreshes.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

# An id comfortably outside any real member/division range in the seed.
MISSING_ID = 999999999


@pytest.fixture
def client():
    return appmod.app.test_client()


def _agent_client(token="test-token"):
    appmod._AGENT_API_TOKEN = token
    return appmod.app.test_client(), {"Authorization": f"Bearer {token}"}


def _a_real_division_id(client):
    r = client.get("/api/lens/source-divisions?limit=1")
    assert r.status_code == 200
    divisions = r.get_json()["divisions"]
    if not divisions:
        pytest.skip("no divisions in seed")
    return divisions[0]["division_id"]


# ── public lens / publicwhip not-found paths ──────────────────────────────

def test_lens_mp_votes_missing_returns_404(client):
    r = client.get(f"/api/lens/mp/{MISSING_ID}/votes")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_publicwhip_mp_missing_returns_404(client):
    assert client.get(f"/publicwhip/mp/{MISSING_ID}").status_code == 404


def test_publicwhip_division_missing_returns_404(client):
    assert client.get(f"/publicwhip/division/{MISSING_ID}").status_code == 404


def test_mp_coverage_missing_member_reports_missing(client):
    r = client.get(f"/api/mp/{MISSING_ID}/coverage")
    assert r.status_code == 404
    body = r.get_json()
    assert body["coverage_status"] == "missing"
    assert body["votes_loaded"] == 0


# ── public lens / publicwhip success paths ────────────────────────────────

def test_lens_mp_votes_real_member_ok(client):
    # Resolve a real member from the division map payload, then fetch their votes.
    div_id = _a_real_division_id(client)
    detail = client.get(f"/api/lens/division/{div_id}").get_json()
    member_id = next(
        (cell.get("member_id") for cell in detail.get("map_data", {}).values() if cell.get("member_id")),
        None,
    )
    if not member_id:
        pytest.skip("no resolvable member id in division payload")
    r = client.get(f"/api/lens/mp/{member_id}/votes")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_publicwhip_division_real_ok(client):
    div_id = _a_real_division_id(client)
    assert client.get(f"/publicwhip/division/{div_id}").status_code == 200


def test_lens_source_divisions_ok(client):
    r = client.get("/api/lens/source-divisions?limit=5")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_lens_map_party_and_gender_ok(client):
    party = client.get("/api/lens/map/party")
    gender = client.get("/api/lens/map/gender")
    assert party.status_code == 200 and party.get_json()["ok"] is True
    assert gender.status_code == 200 and gender.get_json()["ok"] is True
    # Gender lens must classify real MPs, not collapse everyone to Unknown
    # (the bug the canonical normaliser fixed).
    votes = [v["vote"] for v in gender.get_json()["map_data"].values()]
    assert votes.count("M") + votes.count("F") > 0


# ── agent API (token-gated) paths ─────────────────────────────────────────

def test_agent_divisions_requires_token_then_ok():
    client, headers = _agent_client()
    assert client.get("/api/agent/divisions").status_code == 401
    r = client.get("/api/agent/divisions?limit=3", headers=headers)
    assert r.status_code == 200
    assert "divisions" in r.get_json()["data"]


def test_agent_division_missing_returns_404():
    client, headers = _agent_client()
    r = client.get(f"/api/agent/division/{MISSING_ID}", headers=headers)
    assert r.status_code == 404


def test_agent_division_real_ok():
    client, headers = _agent_client()
    div_id = _a_real_division_id(client)
    r = client.get(f"/api/agent/division/{div_id}", headers=headers)
    assert r.status_code == 200
    assert r.get_json()["data"]["division_id"] == div_id


def test_agent_mp_missing_returns_404():
    client, headers = _agent_client()
    r = client.get(f"/api/agent/mp/{MISSING_ID}", headers=headers)
    assert r.status_code == 404
