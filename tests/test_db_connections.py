"""Tests for the always-closing DB connection context managers.

`db_conn()` and `pw_conn()` exist so a query exception can never leak the
SQLite handle (the connection-leak refactor). These tests pin the contract the
~30 migrated routes rely on: the connection is usable inside the block and
ALWAYS closed on the way out — including when the body raises.
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod


def _is_closed(conn) -> bool:
    """A closed sqlite3.Connection raises ProgrammingError on any use."""
    try:
        conn.execute("SELECT 1")
        return False
    except sqlite3.ProgrammingError:
        return True


def test_db_conn_yields_usable_connection_and_closes_after():
    with appmod.db_conn() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
        captured = conn
    assert _is_closed(captured), "db_conn() must close the handle when the block exits"


def test_pw_conn_yields_usable_connection_and_closes_after():
    with appmod.pw_conn() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
        captured = conn
    assert _is_closed(captured), "pw_conn() must close the handle when the block exits"


def test_db_conn_closes_on_exception():
    captured = {}
    with pytest.raises(RuntimeError):
        with appmod.db_conn() as conn:
            captured["conn"] = conn
            raise RuntimeError("boom")
    assert _is_closed(captured["conn"]), "db_conn() must close even when the body raises"


def test_pw_conn_closes_on_exception():
    captured = {}
    with pytest.raises(RuntimeError):
        with appmod.pw_conn() as conn:
            captured["conn"] = conn
            raise RuntimeError("boom")
    assert _is_closed(captured["conn"]), "pw_conn() must close even when the body raises"


def test_pw_conn_is_read_only_seed():
    # The PublicWhip seed is opened read-only; a write must fail rather than
    # silently mutate the shipped snapshot.
    with appmod.pw_conn() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE _should_not_exist (x INTEGER)")
