import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_QUALITY_FIELDS = {
    "division_scoped",
    "selected_division_id",
    "counts_basis",
    "mapped_member_rows",
    "selected_division_vote_rows",
    "mapped_aye_count",
    "mapped_no_count",
    "mapped_unknown_count",
    "source_aye_count",
    "source_no_count",
    "source_vote_count_gap",
}


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
    assert {
        "division_id",
        "title",
        "date",
        "aye_count",
        "no_count",
        "source_url",
    }.issubset(payload["division"])
    assert payload["division"]["division_id"] == 2355
    assert payload["division"]["title"]
    assert payload["division"]["date"]
    assert isinstance(payload["division"]["aye_count"], int)
    assert isinstance(payload["division"]["no_count"], int)
    assert payload["division"]["source_url"]
    assert set(payload["counts"]) == {"aye", "no", "unknown"}
    assert payload["legend"]
    assert payload["map_data"]
    assert payload["votes"]
    assert len(payload["votes"]) == len(payload["map_data"])
    assert payload["source_links"]
    data_quality = payload["data_quality"]
    assert DATA_QUALITY_FIELDS.issubset(data_quality)
    assert "counts_from_selected_division" not in data_quality
    assert data_quality["division_scoped"] is True
    assert data_quality["selected_division_id"] == 2355
    assert data_quality["counts_basis"] == "current_constituency_members_joined_to_selected_division_votes"
    assert data_quality["mapped_member_rows"] == len(payload["map_data"])
    assert payload["counts"]["aye"] == data_quality["mapped_aye_count"]
    assert payload["counts"]["no"] == data_quality["mapped_no_count"]
    assert payload["counts"]["unknown"] == data_quality["mapped_unknown_count"]
    assert data_quality["selected_division_vote_rows"] == (
        data_quality["mapped_aye_count"] + data_quality["mapped_no_count"]
    )
    assert data_quality["source_aye_count"] == payload["division"]["aye_count"]
    assert data_quality["source_no_count"] == payload["division"]["no_count"]
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

    vote_sample = payload["votes"][0]
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
    }.issubset(vote_sample)
    assert vote_sample["mode"] == mode


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


def test_division_2355_documents_source_count_gap():
    client = _client()

    payload = _division_map_payload(client, 2355, "vote-split")

    assert payload["counts"] == {"aye": 305, "no": 165, "unknown": 177}
    assert payload["division"]["aye_count"] == 307
    assert payload["division"]["no_count"] == 171
    assert payload["data_quality"]["source_aye_count"] == 307
    assert payload["data_quality"]["source_no_count"] == 171
    assert payload["data_quality"]["selected_division_vote_rows"] == 470
    assert payload["data_quality"]["mapped_member_rows"] == 647
    assert payload["data_quality"]["source_vote_count_gap"] == 8


def test_legacy_division_endpoint_keeps_vote_map_compatibility():
    client = _client()

    response = client.get("/api/lens/division/2355")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "vote-split"
    assert payload["map_mode"] == "votes"
    assert payload["data_quality"]["division_scoped"] is True
