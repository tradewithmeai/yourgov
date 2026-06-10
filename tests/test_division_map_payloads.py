import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client():
    appmod = importlib.import_module("app")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _division_map_payload(client, division_id, mode):
    response = client.get(f"/api/lens/division/{division_id}/map?mode={mode}")
    assert response.status_code == 200
    return response.get_json()


@pytest.mark.parametrize("mode", ["vote-split", "party-split", "gender-split", "rebel-split"])
def test_division_map_payload_contract(mode):
    client = _client()

    payload = _division_map_payload(client, 2355, mode)

    assert payload["ok"] is True
    assert payload["mode"] == mode
    assert payload["map_mode"] == mode
    assert payload["division"]["division_id"] == 2355
    assert payload["division"]["source_url"]
    assert set(payload["counts"]) == {"aye", "no", "unknown"}
    assert payload["legend"]
    assert payload["map_data"]
    assert payload["source_links"]
    assert payload["data_quality"]["division_scoped"] is True
    assert "motive" in payload["caveat"].lower()
    assert "wrongdoing" in payload["caveat"].lower()

    sample = next(iter(payload["map_data"].values()))
    assert {
        "constituency",
        "member_id",
        "name",
        "party",
        "vote",
        "color",
        "label",
        "source",
        "mode",
    }.issubset(sample)
    assert sample["mode"] == mode
    assert sample["vote"] in sample["label"]


@pytest.mark.parametrize("mode", ["party-split", "gender-split", "rebel-split"])
def test_non_vote_modes_include_selected_division_context(mode):
    client = _client()

    first = _division_map_payload(client, 2355, mode)
    second = _division_map_payload(client, 2356, mode)

    assert first["division"]["division_id"] != second["division"]["division_id"]

    first_label = next(iter(first["map_data"].values()))["label"]
    second_label = next(iter(second["map_data"].values()))["label"]

    assert first["division"]["title"] in first_label
    assert second["division"]["title"] not in first_label
    assert second["division"]["title"] in second_label
    assert first["division"]["title"] not in second_label


def test_rebel_rate_alias_returns_division_scoped_rebel_split():
    client = _client()

    response = client.get("/api/lens/division/2355/map?mode=rebel-rate")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "rebel-split"
    assert payload["division"]["division_id"] == 2355


def test_legacy_division_endpoint_keeps_vote_map_compatibility():
    client = _client()

    response = client.get("/api/lens/division/2355")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "vote-split"
    assert payload["map_mode"] == "votes"
    assert payload["data_quality"]["division_scoped"] is True
