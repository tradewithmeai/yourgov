"""Regression tests for mp_profile's auto-ingest path.

A connection-leak refactor once made mp_profile hold a read connection open
*across* the _auto_ingest() call. _auto_ingest opens its OWN connection and
commits a write; on the read-only live host, an overlapping reader connection
made that write raise "database is locked", so every not-yet-ingested MP
profile 500'd. These tests pin the fix:

  1. the not-ingestable path returns a clean 404 (not 500), and
  2. _auto_ingest is never invoked while a db_conn() is held open.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

MISSING_ID = 999999999


@pytest.fixture
def client():
    return appmod.app.test_client()


def test_missing_member_that_cannot_ingest_returns_404(client, monkeypatch):
    # Simulate an MP absent from the seed whose ingest also finds nothing.
    monkeypatch.setattr(appmod, "_auto_ingest", lambda member_id: False)
    r = client.get(f"/mp/{MISSING_ID}")
    assert r.status_code == 404


def test_auto_ingest_runs_with_no_connection_held_open(client, monkeypatch):
    # The real failure mode: a write inside _auto_ingest contends with a reader
    # connection mp_profile left open. Assert no db_conn() is open when
    # _auto_ingest is called, by detecting overlap via a depth counter wrapped
    # around the real context manager.
    depth = {"now": 0, "max_during_ingest": 0}
    real_db_conn = appmod.db_conn

    from contextlib import contextmanager

    @contextmanager
    def counting_db_conn():
        depth["now"] += 1
        try:
            with real_db_conn() as conn:
                yield conn
        finally:
            depth["now"] -= 1

    monkeypatch.setattr(appmod, "db_conn", counting_db_conn)

    def fake_ingest(member_id):
        # Record how many db_conn()s are open at ingest time; must be 0.
        depth["max_during_ingest"] = max(depth["max_during_ingest"], depth["now"])
        return False  # not ingestable -> mp_profile should 404 cleanly

    monkeypatch.setattr(appmod, "_auto_ingest", fake_ingest)

    r = client.get(f"/mp/{MISSING_ID}")
    assert r.status_code == 404
    assert depth["max_during_ingest"] == 0, (
        "mp_profile must not hold a db_conn() open across _auto_ingest "
        f"(saw depth {depth['max_during_ingest']})"
    )


def test_mp_profile_source_does_not_call_ingest_inside_with_block():
    """Belt-and-braces source check: in mp_profile, no _auto_ingest call sits
    inside a `with db_conn()` block."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    start = src.index("def mp_profile(")
    end = src.index("\ndef ", start + 1)
    body = src[start:end]
    # Walk line by line tracking whether we're inside a `with db_conn()` block by
    # indentation; assert _auto_ingest only appears at the function's base indent.
    in_with = False
    with_indent = None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())
        if in_with and indent <= with_indent:
            in_with = False
        if "_auto_ingest(" in stripped and not stripped.startswith("#"):
            assert not in_with, "_auto_ingest must not be called inside a `with db_conn()` block"
        if re.match(r"with db_conn\(\)", stripped) or re.match(r"with .*db_conn\(\)", stripped):
            in_with = True
            with_indent = indent
