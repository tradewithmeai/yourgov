"""Regression tests for db.upsert_member's handling of the Members-API shape.

The Members API can return an EXPLICIT null for nested objects (latestParty,
latestHouseMembership) — e.g. a member with no current party. `.get(key, {})`
only substitutes the default for a MISSING key, so an explicit null used to
flow through as None and crash with AttributeError, 500ing the whole MP profile
on the on-demand ingest path. These pin the `(... or {})` fix.
"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db as dbmod


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    dbmod.init_db(c)
    yield c
    c.close()


def _row(conn, member_id):
    return conn.execute("SELECT * FROM members WHERE member_id=?", (member_id,)).fetchone()


def test_upsert_member_with_explicit_null_nested_objects(conn):
    # The exact shape that crashed: nested objects present but null.
    data = {
        "nameDisplayAs": "No Party Member",
        "latestParty": None,
        "latestHouseMembership": None,
    }
    dbmod.upsert_member(conn, 4856, data)  # must not raise
    row = _row(conn, 4856)
    assert row is not None
    assert row["party"] is None
    assert row["constituency"] is None


def test_upsert_member_with_missing_nested_objects(conn):
    # Keys absent entirely — also must not crash.
    dbmod.upsert_member(conn, 1, {"nameDisplayAs": "Sparse Member"})
    assert _row(conn, 1) is not None


def test_upsert_member_with_full_nested_objects(conn):
    data = {
        "nameDisplayAs": "Full Member",
        "latestParty": {"name": "Labour"},
        "latestHouseMembership": {"membershipFrom": "Anytown", "house": 1},
    }
    dbmod.upsert_member(conn, 2, data)
    row = _row(conn, 2)
    assert row["party"] == "Labour"
    assert row["constituency"] == "Anytown"
