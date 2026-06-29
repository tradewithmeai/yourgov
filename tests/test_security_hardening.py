"""Regression tests for the 2026-06 security review Pass-2 (mygov) hardening:
constant-time agent-token compare, no 500 on bad query params, generic error
bodies (no exception-text leak), and pinned dependencies.
"""
import os
import sys
import pathlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_bad_limit_query_param_does_not_500():
    # Unauthenticated lens endpoint: a non-numeric ?limit must degrade to the
    # default, never raise an unhandled 500 (was bare int(...) before).
    c = _client()
    for q in ("abc", "", "9e9", "-1", "999999"):
        r = c.get(f"/api/lens/source-divisions?limit={q}")
        assert r.status_code != 500, f"limit={q!r} -> {r.status_code}"


def test_agent_token_uses_constant_time_compare():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in src
    # The non-constant-time `auth != f\"Bearer ...` compare must be gone.
    assert 'auth != f"Bearer' not in src


def test_agent_endpoint_rejects_wrong_token_without_500(monkeypatch):
    monkeypatch.setattr(appmod, "_AGENT_API_TOKEN", "the-real-token")
    c = _client()
    r = c.get("/api/agent/global/countries", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_error_bodies_do_not_leak_exception_text():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    # The exception-interpolating error bodies were replaced with generic text.
    assert "TheyWorkForYou fetch failed from the server: {exc}" not in src
    assert "AI service error: {e}" not in src
    assert "invalid JSON: {exc}" not in src


def test_requirements_are_pinned():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pkg_lines = [l.strip() for l in reqs.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert pkg_lines, "no requirement lines found"
    for line in pkg_lines:
        assert "==" in line, f"dependency not pinned: {line!r}"
        assert ">=" not in line, f"floating lower bound still present: {line!r}"
