import importlib


def _appmod():
    return importlib.import_module("app")


def test_search_score_respects_word_boundaries():
    appmod = _appmod()

    assert appmod._search_score("water", "Waterloo") > 0
    assert appmod._search_score("water", "stormwater") == 0
    assert appmod._search_score("davey", "Ed Davey") > 0


def test_rank_member_rows_prefers_clean_prefix_matches():
    appmod = _appmod()
    rows = [
        {"member_id": 1, "name": "Stormwater Hill", "party": "", "constituency": "Somewhere"},
        {"member_id": 2, "name": "Waterloo Example", "party": "", "constituency": "Somewhere"},
        {"member_id": 3, "name": "Water Lane", "party": "", "constituency": "Somewhere"},
    ]

    ranked = appmod._rank_member_rows(rows, "water", limit=3)
    assert [r["member_id"] for r in ranked] == [3, 2]


def test_publicwhip_mp_shows_total_vote_count():
    appmod = _appmod()
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    conn = appmod.get_publicwhip_conn()
    try:
        total_votes = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE member_id = ?",
            (5362,),
        ).fetchone()[0]
    finally:
        conn.close()

    r = client.get("/publicwhip/mp/5362")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f">{total_votes}<" in body
    assert f"Showing the latest 100 of {total_votes} recorded votes." in body


def test_publicwhip_mps_lists_only_current_constituency_members():
    appmod = _appmod()
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    r = client.get("/publicwhip/mps")

    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "<td class=\"pw-muted\">--</td>" not in body


def test_api_mps_search_returns_postcode_match(monkeypatch):
    appmod = _appmod()
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    def fake_lookup(query):
        assert query == "SW1A 1AA"
        return {
            "constituency": "Tottenham",
            "mp": {"id": 206, "name": "David Lammy", "party": "Labour"},
        }

    monkeypatch.setattr(appmod, "_lookup_postcode_mp", fake_lookup)

    response = client.get("/api/mps/search?q=SW1A%201AA")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["results"][0] == {
        "id": 206,
        "name": "David Lammy",
        "party": "Labour",
        "constituency": "Tottenham",
        "match_type": "postcode",
    }


def test_lens_mp_votes_returns_mp_scoped_division_history():
    appmod = _appmod()
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    response = client.get("/api/lens/mp/5362/votes?limit=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["mp"]["member_id"] == 5362
    assert payload["mp"]["name"]
    assert payload["mp"]["constituency"]
    assert 1 <= len(payload["divisions"]) <= 5
    first = payload["divisions"][0]
    assert {
        "division_id",
        "title",
        "date",
        "vote",
        "aye_count",
        "no_count",
        "source_url",
        "summary_url",
    }.issubset(first)
    assert first["source_url"].startswith("/publicwhip/division/")
    assert first["summary_url"].startswith("/publicwhip/division/")


if __name__ == "__main__":
    raise SystemExit(0)
