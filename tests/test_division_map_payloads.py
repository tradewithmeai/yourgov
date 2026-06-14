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
    "current_member_rows",
    "map_constituency_rows",
    "vacant_constituency_rows",
    "selected_division_vote_rows",
    "mapped_aye_count",
    "mapped_no_count",
    "mapped_unknown_count",
    "mapped_vacant_count",
    "source_aye_count",
    "source_no_count",
    "source_vote_count_total",
    "mapped_recorded_vote_count",
    "source_minus_mapped_vote_count",
}


def _client():
    appmod = importlib.import_module("app")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _division_map_payload(client, division_id, mode):
    response = client.get(f"/api/lens/division/{division_id}/map?mode={mode}")
    assert response.status_code == 200
    return response.get_json()


def _assert_all_rows_match_legend_and_mode(payload, mode):
    legend_colours = {entry["key"]: entry["color"] for entry in payload["legend"]}
    required_keys = {
        "category",
        "legend_key",
        "color",
        "vote",
        "division_vote",
        "label",
        "mode",
    }

    for item in payload["map_data"].values():
        assert required_keys.issubset(item)
        assert item["legend_key"] == item["category"]
        assert item["division_vote"] in {"Aye", "No", "Absent/unknown", "Vacant seat"}
        assert item["division_vote"] in item["label"]
        assert item["mode"] == mode
        assert item["legend_key"] in legend_colours
        assert item["color"] == legend_colours[item["legend_key"]]

        if item.get("is_vacant"):
            assert item["member_id"] is None
            assert item["name"] == "Vacant seat"
            assert item["party"] == "Vacant"
            assert item["vote"] == "Vacant seat"
            assert item["division_vote"] == "Vacant seat"
        elif mode == "vote-split":
            assert item["category"] == item["vote"] == item["division_vote"]
        elif mode == "party-split":
            # Division-scoped: voters carry their party; MPs who did not record an
            # Aye/No on this division are shown as "Did not vote".
            if item["division_vote"] in {"Aye", "No"}:
                assert item["category"] == item["party"]
            else:
                assert item["category"] == "Did not vote"
            assert item["vote"] == item["division_vote"]
        elif mode == "gender-split":
            if item["division_vote"] in {"Aye", "No"}:
                assert item["category"] in {"M", "F", "Unknown"}
            else:
                assert item["category"] == "Did not vote"
            assert item["vote"] == item["division_vote"]
        else:
            assert item["category"] == item["rebel_status"]
            assert item["vote"] == item["division_vote"]

    for item in payload["votes"]:
        assert required_keys.issubset(item)
        map_item = payload["map_data"][item["constituency"]]
        assert item["category"] == map_item["category"]
        assert item["legend_key"] == map_item["legend_key"]
        assert item["color"] == map_item["color"]
        assert item["division_vote"] == map_item["division_vote"]


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
    assert set(payload["counts"]) == {"aye", "no", "unknown", "vacant"}
    assert payload["legend"]
    assert payload["map_data"]
    assert payload["votes"]
    assert len(payload["votes"]) == len(payload["map_data"])
    assert payload["source_links"]
    data_quality = payload["data_quality"]
    assert DATA_QUALITY_FIELDS.issubset(data_quality)
    assert "counts_from_selected_division" not in data_quality
    assert "source_vote_count_gap" not in data_quality
    assert data_quality["division_scoped"] is True
    assert data_quality["selected_division_id"] == 2355
    assert data_quality["counts_basis"] == "official_constituencies_joined_to_current_members_and_selected_division_votes"
    assert data_quality["map_constituency_rows"] == len(payload["map_data"])
    assert data_quality["mapped_member_rows"] == data_quality["current_member_rows"]
    assert (
        data_quality["current_member_rows"] + data_quality["vacant_constituency_rows"]
        == data_quality["map_constituency_rows"]
    )
    assert payload["counts"]["aye"] == data_quality["mapped_aye_count"]
    assert payload["counts"]["no"] == data_quality["mapped_no_count"]
    assert payload["counts"]["unknown"] == data_quality["mapped_unknown_count"]
    assert payload["counts"]["vacant"] == data_quality["mapped_vacant_count"]
    assert data_quality["selected_division_vote_rows"] == (
        data_quality["mapped_aye_count"] + data_quality["mapped_no_count"]
    )
    assert data_quality["source_aye_count"] == payload["division"]["aye_count"]
    assert data_quality["source_no_count"] == payload["division"]["no_count"]
    assert data_quality["source_vote_count_total"] == (
        data_quality["source_aye_count"] + data_quality["source_no_count"]
    )
    assert data_quality["mapped_recorded_vote_count"] == (
        data_quality["mapped_aye_count"] + data_quality["mapped_no_count"]
    )
    assert data_quality["source_minus_mapped_vote_count"] == (
        data_quality["source_vote_count_total"] - data_quality["mapped_recorded_vote_count"]
    )
    assert "motive" in payload["caveat"].lower()
    assert "wrongdoing" in payload["caveat"].lower()

    _assert_all_rows_match_legend_and_mode(payload, mode)


def test_division_map_payload_includes_explicit_vacant_constituencies():
    client = _client()

    payload = _division_map_payload(client, 2372, "vote-split")

    assert payload["data_quality"]["map_constituency_rows"] == 650
    assert payload["data_quality"]["current_member_rows"] == 647
    assert payload["data_quality"]["vacant_constituency_rows"] == 3
    assert payload["counts"]["vacant"] == 3
    for constituency in (
        "Aberdeen South",
        "Arbroath and Broughty Ferry",
        "Makerfield",
    ):
        row = payload["map_data"][constituency]
        assert row["is_vacant"] is True
        assert row["member_id"] is None
        assert row["name"] == "Vacant seat"
        assert row["party"] == "Vacant"
        assert row["division_vote"] == "Vacant seat"


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
    counts = payload["counts"]
    data_quality = payload["data_quality"]

    assert payload["division"]["aye_count"] == 307
    assert payload["division"]["no_count"] == 171
    assert data_quality["source_aye_count"] == payload["division"]["aye_count"]
    assert data_quality["source_no_count"] == payload["division"]["no_count"]
    assert data_quality["mapped_aye_count"] == counts["aye"]
    assert data_quality["mapped_no_count"] == counts["no"]
    assert data_quality["mapped_unknown_count"] == counts["unknown"]
    assert data_quality["map_constituency_rows"] == sum(counts.values())
    assert data_quality["mapped_member_rows"] == (
        counts["aye"] + counts["no"] + counts["unknown"]
    )
    assert data_quality["mapped_vacant_count"] == counts["vacant"]
    assert data_quality["selected_division_vote_rows"] == data_quality["mapped_recorded_vote_count"]
    assert "source_vote_count_gap" not in data_quality
    assert (
        data_quality["source_vote_count_total"]
        == data_quality["source_aye_count"] + data_quality["source_no_count"]
    )
    assert (
        data_quality["source_minus_mapped_vote_count"]
        == data_quality["source_vote_count_total"]
        - data_quality["mapped_recorded_vote_count"]
    )


@pytest.mark.parametrize("mode", ["party-split", "gender-split"])
def test_party_and_gender_split_are_division_derived(mode):
    """Regression for the bug where party/gender split produced a constant national
    map (byte-identical across divisions). Colouring must change with the selected
    division, driven by who actually voted on it."""
    client = _client()
    divisions = client.get("/api/lens/source-divisions?limit=6").get_json()["divisions"]
    first, second = divisions[0]["division_id"], divisions[5]["division_id"]

    a = _division_map_payload(client, first, mode)["map_data"]
    b = _division_map_payload(client, second, mode)["map_data"]

    shared = set(a) & set(b)
    differing = sum(1 for k in shared if a[k]["category"] != b[k]["category"])
    assert differing > 0, (
        f"{mode} produced identical categories across divisions {first} and {second}; "
        "the map is not division-derived"
    )

    # "Did not vote" must be a real, legend-backed category for non-voters.
    legend_keys = {entry["key"] for entry in _division_map_payload(client, first, mode)["legend"]}
    assert "Did not vote" in legend_keys
    assert any(item["category"] == "Did not vote" for item in a.values())


def test_legacy_division_endpoint_keeps_vote_map_compatibility():
    client = _client()

    response = client.get("/api/lens/division/2355")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "vote-split"
    assert payload["map_mode"] == "votes"
    assert payload["data_quality"]["division_scoped"] is True
