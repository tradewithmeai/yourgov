"""Regression tests for the division-click -> map-repaint contract.

The map iframe (templates/map_relay.html) only repaints when its `_applySetMode`
handler recognises the `mode` string the parent page forwards. The parent forwards
`payload.map_mode`, which the /api/lens/division/<id>/map endpoint sets to one of the
four `*-split` mode names. A previous build shipped a relay that handled only the
legacy ('votes', 'party', ...) names, so every division click was silently dropped
while the relay still posted `yourgov:map:applied` ("Map updated") on a frozen map.

These tests lock both halves of that contract:
  1. the endpoint emits each `*-split` map_mode, and
  2. the relay handles each one and only reports success when a paint happened.
"""

import importlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DIVISION_MAP_MODES = ("vote-split", "party-split", "gender-split", "rebel-split")


def _client():
    appmod = importlib.import_module("app")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _latest_division_id(client):
    response = client.get("/api/lens/source-divisions?limit=1")
    assert response.status_code == 200
    divisions = response.get_json()["divisions"]
    assert divisions, "no source divisions available to test the map contract"
    return divisions[0]["division_id"]


def _relay_set_mode_body():
    html = (
        open(os.path.join(ROOT, "templates", "map_relay.html"), encoding="utf-8")
        .read()
    )
    match = re.search(
        r"function _applySetMode\(msg\)\s*\{(.*?)\n    \}",
        html,
        re.DOTALL,
    )
    assert match, "could not locate _applySetMode in map_relay.html"
    return match.group(1)


def test_division_map_endpoint_emits_each_split_mode():
    client = _client()
    division_id = _latest_division_id(client)
    for mode in DIVISION_MAP_MODES:
        payload = client.get(
            f"/api/lens/division/{division_id}/map?mode={mode}"
        ).get_json()
        assert payload["map_mode"] == mode, (
            f"endpoint emitted map_mode={payload['map_mode']!r} for requested {mode!r}; "
            "the relay matches on this exact string"
        )


def test_relay_handles_every_split_mode():
    body = _relay_set_mode_body()
    for mode in DIVISION_MAP_MODES:
        assert f"'{mode}'" in body, (
            f"map_relay.html _applySetMode has no branch for {mode!r}; "
            "a division click in this mode would be silently dropped"
        )
    assert "setConstituencyColours" in body


def test_relay_only_reports_applied_after_a_paint():
    """The 'Map updated' signal must be gated on an actual paint, so a dropped
    mode can never masquerade as success (the original silent-failure bug)."""
    body = _relay_set_mode_body()
    assert "var applied = false" in body, (
        "relay should track whether a paint happened before posting yourgov:map:applied"
    )
    applied_index = body.index("yourgov:map:applied")
    guard = body[:applied_index]
    assert re.search(r"if\s*\(\s*applied", guard), (
        "yourgov:map:applied must be guarded by the `applied` flag so an unhandled "
        "mode does not falsely report success"
    )
