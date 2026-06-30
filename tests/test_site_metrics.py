"""First-party site-metrics tests: privacy-safe beacon ingest, server-side
aggregation (funnel / pages / referrers), and the token-gated admin view.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod


def _client_with_metrics(tmp_path, token="test-metrics-key"):
    appmod._METRICS_FILE = str(tmp_path)
    appmod._METRICS_TOKEN = token
    open(appmod._METRICS_FILE, "w").close()
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _tmpfile():
    return os.path.join(tempfile.gettempdir(), "yg_metrics_unit.jsonl")


def test_beacon_ingest_and_funnel_aggregation():
    c = _client_with_metrics(_tmpfile())
    for b in [
        {"event": "pageview", "path": "/source-lens", "referrer": "https://twitter.com/x/1"},
        {"event": "pageview", "path": "/source-lens", "referrer": ""},
        {"event": "search", "kind": "postcode"},
        {"event": "mp_view", "party": "Labour"},
        {"event": "contact_click", "via": "writetothem"},
    ]:
        assert c.post("/api/telemetry", json=b).status_code == 200

    agg = c.get("/admin/metrics?key=test-metrics-key&format=json").get_json()
    funnel = dict(agg["funnel"])
    assert funnel == {"pageview": 2, "search": 1, "mp_view": 1, "contact_click": 1}
    assert dict(agg["top_pages"])["/source-lens"] == 2
    assert "twitter.com" in dict(agg["top_referrers"])


def test_no_pii_stored_query_string_and_same_origin_referrer_stripped():
    c = _client_with_metrics(_tmpfile())
    # A path with a query string (could carry a postcode/search term) and a
    # same-origin referrer must both be reduced to nothing identifying.
    c.post("/api/telemetry", json={
        "event": "pageview",
        "path": "/source-lens?q=SW1A1AA&token=secret",
        "referrer": "https://yourgov.solvx.uk/start",
    })
    raw = open(appmod._METRICS_FILE, encoding="utf-8").read()
    assert "SW1A1AA" not in raw and "secret" not in raw and "?" not in raw
    # Same-origin referrer dropped (no external source recorded).
    agg = c.get("/admin/metrics?key=test-metrics-key&format=json").get_json()
    assert agg["top_referrers"] == []


def test_empty_event_rejected():
    c = _client_with_metrics(_tmpfile())
    assert c.post("/api/telemetry", json={"event": ""}).status_code == 400


def test_admin_metrics_is_token_gated():
    c = _client_with_metrics(_tmpfile(), token="secret-key")
    assert c.get("/admin/metrics").status_code == 404            # no key
    assert c.get("/admin/metrics?key=wrong").status_code == 404  # wrong key
    assert c.get("/admin/metrics?key=secret-key").status_code == 200
    # Header token also works.
    assert c.get("/admin/metrics", headers={"X-Metrics-Token": "secret-key"}).status_code == 200


def test_admin_metrics_404_when_token_unset():
    c = _client_with_metrics(_tmpfile(), token="")
    # With no token configured the endpoint must not be exposed at all.
    assert c.get("/admin/metrics?key=").status_code == 404


def test_metrics_file_size_cap_blocks_runaway_append():
    c = _client_with_metrics(_tmpfile())
    appmod._METRICS_MAX_BYTES = 1  # force "already too big" on the next write
    with open(appmod._METRICS_FILE, "w", encoding="utf-8") as f:
        f.write("x" * 50)
    # Endpoint still 200s (never errors the beacon) but does not append.
    before = os.path.getsize(appmod._METRICS_FILE)
    assert c.post("/api/telemetry", json={"event": "pageview", "path": "/"}).status_code == 200
    assert os.path.getsize(appmod._METRICS_FILE) == before  # nothing appended
    appmod._METRICS_MAX_BYTES = 8 * 1024 * 1024  # restore for other tests
