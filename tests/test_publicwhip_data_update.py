import importlib.util
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_publicwhip_data.py"


def _load_update_script():
    spec = importlib.util.spec_from_file_location("update_publicwhip_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        params = dict(params or {})
        self.calls.append((url, params))

        if url.endswith("/Members/Search"):
            assert "Name" not in params
            skip = int(params["skip"])
            pages = {
                0: [
                    {"value": _member(1, "Ada Example", "Labour", "Example North")},
                    {"value": _member(2, "Ben Example", "Conservative", "Example South")},
                ],
                2: [
                    {"value": _member(3, "Cara Example", "Liberal Democrat", "Example East")},
                ],
            }
            return _FakeResponse({"items": pages.get(skip, [])})

        if url.endswith("/Location/Constituency/Search"):
            skip = int(params["skip"])
            pages = {
                0: [
                    {"value": _constituency(101, "Example North", 1)},
                    {"value": _constituency(102, "Example South", 2)},
                ],
                2: [
                    {"value": _constituency(103, "Example East", 3)},
                    {"value": _constituency(104, "Example Vacancy", None)},
                ],
            }
            return _FakeResponse({"items": pages.get(skip, []), "totalResults": 4})

        if url.endswith("/divisions.json/search"):
            return _FakeResponse(
                [
                    {
                        "DivisionId": 2372,
                        "Date": "2026-06-10T18:56:00",
                        "Title": "Railways Bill: Third Reading",
                        "AyeCount": 2,
                        "NoCount": 1,
                    }
                ]
            )

        if url.endswith("/division/2372.json"):
            return _FakeResponse(_division_detail())

        raise AssertionError(f"unexpected URL {url}")


class _CappedMembersHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        params = dict(params or {})
        self.calls.append((url, params))
        assert url.endswith("/Members/Search")
        assert "Name" not in params

        skip = int(params["skip"])
        pages = {
            0: [_member(i, f"Member {i}", "Labour", f"Seat {i}") for i in range(1, 21)],
            20: [_member(i, f"Member {i}", "Labour", f"Seat {i}") for i in range(21, 41)],
            40: [_member(i, f"Member {i}", "Labour", f"Seat {i}") for i in range(41, 46)],
        }
        return _FakeResponse(
            {
                "items": [{"value": member} for member in pages.get(skip, [])],
                "totalResults": 45,
            }
        )


class _MixedCurrentMembersHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        params = dict(params or {})
        self.calls.append((url, params))
        active = _member(1, "Ada Current", "Labour", "Example North")
        ended = _member(2, "Ben Former", "Conservative", "Old Example")
        ended["latestHouseMembership"]["membershipEndDate"] = "2024-05-30T00:00:00"
        return _FakeResponse(
            {
                "items": [
                    {"value": active},
                    {"value": ended},
                ],
                "totalResults": 2,
            }
        )


def _member(member_id, name, party, constituency):
    return {
        "id": member_id,
        "nameDisplayAs": name,
        "latestParty": {"name": party},
        "latestHouseMembership": {
            "house": 1,
            "membershipFrom": constituency,
            "membershipEndDate": None,
        },
        "gender": "M",
    }


def _constituency(constituency_id, name, current_member_id):
    current_representation = None
    if current_member_id is not None:
        current_representation = {
            "member": {
                "value": {
                    "id": current_member_id,
                    "nameDisplayAs": f"Member {current_member_id}",
                },
            },
            "representation": {
                "membershipFrom": name,
                "membershipFromId": constituency_id,
                "house": 1,
            },
        }
    return {
        "id": constituency_id,
        "name": name,
        "startDate": "2024-05-31T00:00:00",
        "endDate": None,
        "currentRepresentation": current_representation,
    }


def _vote_member(member_id, name, party, constituency):
    return {
        "MemberId": member_id,
        "Name": name,
        "Party": party,
        "MemberFrom": constituency,
    }


def _division_detail():
    return {
        "DivisionId": 2372,
        "Date": "2026-06-10T18:56:00",
        "Title": "Railways Bill: Third Reading",
        "FriendlyTitle": None,
        "AyeCount": 2,
        "NoCount": 1,
        "Ayes": [_vote_member(1, "Ada Example", "Labour", "Example North")],
        "AyeTellers": [_vote_member(4, "Dina Teller", "Labour", "Example West")],
        "Noes": [_vote_member(2, "Ben Example", "Conservative", "Example South")],
        "NoTellers": [_vote_member(5, "Eli Teller", "Conservative", "Example Central")],
    }


def test_upserts_vote_rows_from_full_division_detail_including_tellers(tmp_path):
    updater = _load_update_script()
    db_path = tmp_path / "votes.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    updater.prepare_database(conn)

    rows_changed = updater.upsert_division_detail(conn, _division_detail())

    assert rows_changed == 4
    rows = conn.execute(
        "SELECT member_id, title, voted_aye, aye_count, no_count FROM votes ORDER BY member_id"
    ).fetchall()
    assert [row["member_id"] for row in rows] == [1, 2, 4, 5]
    assert {row["member_id"]: row["voted_aye"] for row in rows} == {
        1: 1,
        2: 0,
        4: 1,
        5: 0,
    }
    assert all(row["title"] == "Railways Bill: Third Reading" for row in rows)
    assert all(row["aye_count"] == 2 for row in rows)
    assert all(row["no_count"] == 1 for row in rows)


def test_fetch_current_commons_members_paginates_without_empty_name_filter():
    updater = _load_update_script()
    fake_client = _FakeHttpClient()

    members = updater.fetch_current_commons_members(fake_client, page_size=2)

    assert [member["id"] for member in members] == [1, 2, 3]
    member_calls = [params for url, params in fake_client.calls if url.endswith("/Members/Search")]
    assert member_calls == [
        {"House": 1, "IsCurrentMember": "true", "skip": 0, "take": 2},
        {"House": 1, "IsCurrentMember": "true", "skip": 2, "take": 2},
    ]


def test_fetch_current_commons_members_continues_when_api_caps_page_size():
    updater = _load_update_script()
    fake_client = _CappedMembersHttpClient()

    members = updater.fetch_current_commons_members(fake_client, page_size=100)

    assert len(members) == 45
    member_calls = [params for _url, params in fake_client.calls]
    assert member_calls == [
        {"House": 1, "IsCurrentMember": "true", "skip": 0, "take": 100},
        {"House": 1, "IsCurrentMember": "true", "skip": 20, "take": 100},
        {"House": 1, "IsCurrentMember": "true", "skip": 40, "take": 100},
    ]


def test_fetch_current_commons_members_filters_ended_memberships():
    updater = _load_update_script()
    fake_client = _MixedCurrentMembersHttpClient()

    members = updater.fetch_current_commons_members(fake_client, page_size=20)

    assert [member["id"] for member in members] == [1]


def test_fetch_constituencies_paginates_and_keeps_vacancies():
    updater = _load_update_script()
    fake_client = _FakeHttpClient()

    constituencies = updater.fetch_constituencies(fake_client, page_size=2)

    assert [seat["name"] for seat in constituencies] == [
        "Example North",
        "Example South",
        "Example East",
        "Example Vacancy",
    ]
    assert updater._constituency_current_member_id(constituencies[-1]) is None
    constituency_calls = [
        params
        for url, params in fake_client.calls
        if url.endswith("/Location/Constituency/Search")
    ]
    assert constituency_calls == [
        {"skip": 0, "take": 2},
        {"skip": 2, "take": 2},
    ]


def test_update_database_refreshes_members_and_latest_divisions(tmp_path):
    updater = _load_update_script()
    db_path = tmp_path / "refresh.db"
    fake_client = _FakeHttpClient()

    summary = updater.update_database(
        db_path,
        client=fake_client,
        latest_take=5,
        member_page_size=2,
        constituency_page_size=2,
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    latest = conn.execute("SELECT MAX(division_id) AS latest_id FROM votes").fetchone()
    members = conn.execute("SELECT COUNT(*) AS total FROM members").fetchone()
    constituencies = conn.execute("SELECT COUNT(*) AS total FROM constituencies").fetchone()
    vacancies = conn.execute(
        "SELECT COUNT(*) AS total FROM constituencies WHERE current_member_id IS NULL"
    ).fetchone()
    votes = conn.execute("SELECT COUNT(*) AS total FROM votes").fetchone()

    assert summary.local_latest_after == 2372
    assert summary.members_seen == 3
    assert summary.constituencies_seen == 4
    assert summary.vacant_constituencies == 1
    assert summary.divisions_seen == 1
    assert summary.vote_rows_upserted == 4
    assert latest["latest_id"] == 2372
    assert members["total"] == 3
    assert constituencies["total"] == 4
    assert vacancies["total"] == 1
    assert votes["total"] == 4
