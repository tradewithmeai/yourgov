"""First-party site-metrics tests: privacy-safe beacon ingest, PERSISTENT
SQLite counter storage, server-side aggregation (funnel / pages / referrers),
the token-gated admin view, and the distinct-row cap.
"""
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod

_DB_SEQ = 0


def _client_with_metrics(token="test-metrics-key", persistent=True):
    """Point metrics at a fresh temp SQLite DB and return a test client."""
    global _DB_SEQ
    _DB_SEQ += 1
    path = os.path.join(tempfile.gettempdir(), f"yg_metrics_unit_{_DB_SEQ}.db")
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS metric_counts "
        "(day TEXT, event TEXT, dim TEXT, key TEXT, count INTEGER, "
        "PRIMARY KEY(day, event, dim, key))"
    )
    con.commit()
    con.close()
    appmod._METRICS_DB = path
    appmod._METRICS_PERSISTENT = persistent
    appmod._METRICS_TOKEN = token
    appmod._METRICS_MAX_ROWS = 50000
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_beacon_ingest_and_funnel_aggregation():
    c = _client_with_metrics()
    for b in [
        {"event": "pageview", "path": "/source-lens", "referrer": "https://twitter.com/x/1"},
        {"event": "pageview", "path": "/source-lens", "referrer": ""},
        {"event": "search", "kind": "postcode"},
        {"event": "mp_view", "party": "Labour"},
        {"event": "contact_click", "via": "writetothem"},
    ]:
        assert c.post("/api/telemetry", json=b).status_code == 200

    agg = c.get("/admin/metrics?key=test-metrics-key&format=json").get_json()
    assert dict(agg["funnel"]) == {"pageview": 2, "search": 1, "mp_view": 1, "contact_click": 1}
    assert dict(agg["top_pages"])["/source-lens"] == 2
    assert "twitter.com" in dict(agg["top_referrers"])
    assert agg["total_events"] == 5  # one 'total' row per beacon
    assert agg["persistent"] is True


def test_metrics_persist_across_simulated_restart():
    # The whole point of this change: data survives the process going away.
    c = _client_with_metrics()
    db_path = appmod._METRICS_DB
    for _ in range(3):
        c.post("/api/telemetry", json={"event": "pageview", "path": "/home", "referrer": ""})
    # Simulate a restart: nothing in memory carries over, but the on-disk DB does.
    # (Re-point at the SAME file, as a fresh process would by resolving the path.)
    appmod._METRICS_DB = db_path
    agg = c.get("/admin/metrics?key=test-metrics-key&format=json").get_json()
    assert dict(agg["funnel"])["pageview"] == 3
    assert dict(agg["top_pages"])["/home"] == 3


def test_no_pii_stored_query_string_and_same_origin_referrer_stripped():
    c = _client_with_metrics()
    c.post("/api/telemetry", json={
        "event": "pageview",
        "path": "/source-lens?q=SW1A1AA&token=secret",
        "referrer": "https://yourgov.solvx.uk/start",
    })
    # The stored path key must have no query string (no postcode/search term).
    con = sqlite3.connect(appmod._METRICS_DB)
    keys = [r[0] for r in con.execute("SELECT key FROM metric_counts WHERE dim='path'")]
    con.close()
    assert keys == ["/source-lens"]
    assert not any("SW1A1AA" in k or "secret" in k or "?" in k for k in keys)
    # Same-origin referrer dropped (no external source recorded).
    agg = c.get("/admin/metrics?key=test-metrics-key&format=json").get_json()
    assert agg["top_referrers"] == []


def test_junk_referrer_rejected():
    c = _client_with_metrics()
    # A referrer that isn't a plausible domain must not be stored.
    c.post("/api/telemetry", json={"event": "pageview", "path": "/", "referrer": "not a url"})
    c.post("/api/telemetry", json={"event": "pageview", "path": "/", "referrer": "javascript:alert(1)"})
    agg = c.get("/admin/metrics?key=test-metrics-key&format=json").get_json()
    assert agg["top_referrers"] == []


def test_empty_event_rejected():
    c = _client_with_metrics()
    assert c.post("/api/telemetry", json={"event": ""}).status_code == 400


def test_admin_metrics_is_token_gated():
    c = _client_with_metrics(token="secret-key")
    assert c.get("/admin/metrics").status_code == 404            # no key
    assert c.get("/admin/metrics?key=wrong").status_code == 404  # wrong key
    assert c.get("/admin/metrics?key=secret-key").status_code == 200
    assert c.get("/admin/metrics", headers={"X-Metrics-Token": "secret-key"}).status_code == 200


def test_admin_metrics_404_when_token_unset():
    c = _client_with_metrics(token="")
    assert c.get("/admin/metrics?key=").status_code == 404


def test_distinct_row_cap_blocks_new_keys_but_keeps_counting():
    c = _client_with_metrics()
    appmod._METRICS_MAX_ROWS = 2  # tiny cap to force the limit
    # First two distinct event keys create rows; a third new key is dropped, but
    # an existing key keeps incrementing.
    c.post("/api/telemetry", json={"event": "pageview", "path": "/a"})  # rows: total/pageview, pageview/path:/a
    # Already 2 rows -> new distinct keys dropped, existing increment.
    c.post("/api/telemetry", json={"event": "pageview", "path": "/a"})  # increments existing
    c.post("/api/telemetry", json={"event": "search"})                  # new key dropped (over cap)
    con = sqlite3.connect(appmod._METRICS_DB)
    nrows = con.execute("SELECT COUNT(*) FROM metric_counts").fetchone()[0]
    con.close()
    assert nrows <= 2  # cap held
    appmod._METRICS_MAX_ROWS = 50000


def test_resolve_metrics_db_prefers_persistent_over_tmp(monkeypatch, tmp_path):
    # The persistent (beside-app) path must win over /tmp when both are writable.
    monkeypatch.delenv("MYGOV_METRICS_DB", raising=False)
    path, persistent = appmod._resolve_metrics_db()
    # On any dev/host where the app-parent dir is writable, this is persistent and
    # NOT under /tmp.
    assert persistent is True
    assert not path.startswith("/tmp")
