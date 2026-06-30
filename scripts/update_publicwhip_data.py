#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import init_db  # noqa: E402


DEFAULT_DB_PATH = ROOT / "yourgov.db"
MEMBERS_SEARCH_URL = "https://members-api.parliament.uk/api/Members/Search"
CONSTITUENCY_SEARCH_URL = (
    "https://members-api.parliament.uk/api/Location/Constituency/Search"
)
COMMONS_VOTES_BASE_URL = "https://commonsvotes-api.parliament.uk/data"
DIVISIONS_SEARCH_URL = f"{COMMONS_VOTES_BASE_URL}/divisions.json/search"
TIMEOUT_SECONDS = 30.0
USER_AGENT = "YourGov data updater"
# Stored member rows include up to four tellers that the announced Aye/No tally
# excludes, and a handful of voters can be missing from the current member list, so
# a division is treated as complete when it stores at least (aye+no - tolerance) rows.
COMPLETENESS_TELLER_TOLERANCE = 6


class UpdateSummary:
    def __init__(
        self,
        *,
        db_path: Path,
        local_latest_before: int | None,
        local_latest_after: int | None,
        members_seen: int,
        members_upserted: int,
        members_deactivated: int,
        constituencies_seen: int,
        constituencies_upserted: int,
        constituencies_with_current_member: int,
        vacant_constituencies: int,
        divisions_seen: int,
        divisions_upserted: int,
        vote_rows_upserted: int,
        divisions_skipped: int = 0,
    ) -> None:
        self.db_path = db_path
        self.local_latest_before = local_latest_before
        self.local_latest_after = local_latest_after
        self.members_seen = members_seen
        self.members_upserted = members_upserted
        self.members_deactivated = members_deactivated
        self.constituencies_seen = constituencies_seen
        self.constituencies_upserted = constituencies_upserted
        self.constituencies_with_current_member = constituencies_with_current_member
        self.vacant_constituencies = vacant_constituencies
        self.divisions_seen = divisions_seen
        self.divisions_upserted = divisions_upserted
        self.vote_rows_upserted = vote_rows_upserted
        self.divisions_skipped = divisions_skipped

    def as_dict(self) -> dict[str, Any]:
        return {
            "db_path": str(self.db_path),
            "local_latest_before": self.local_latest_before,
            "local_latest_after": self.local_latest_after,
            "members_seen": self.members_seen,
            "members_upserted": self.members_upserted,
            "members_deactivated": self.members_deactivated,
            "constituencies_seen": self.constituencies_seen,
            "constituencies_upserted": self.constituencies_upserted,
            "constituencies_with_current_member": self.constituencies_with_current_member,
            "vacant_constituencies": self.vacant_constituencies,
            "divisions_seen": self.divisions_seen,
            "divisions_upserted": self.divisions_upserted,
            "divisions_skipped": self.divisions_skipped,
            "vote_rows_upserted": self.vote_rows_upserted,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_value(row: sqlite3.Row | tuple | None, key: str, index: int = 0):
    if row is None:
        return None
    try:
        return row[key]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        return row[index]  # type: ignore[index]


def _safe_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_current_commons_member(member: dict[str, Any]) -> bool:
    membership = member.get("latestHouseMembership") or {}
    if not isinstance(membership, dict):
        return False
    return (
        _safe_int(membership.get("house")) == 1
        and not membership.get("membershipEndDate")
        and bool(membership.get("membershipFrom"))
    )


def prepare_database(conn: sqlite3.Connection) -> None:
    init_db(conn)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_votes_member_id ON votes(member_id);
        CREATE INDEX IF NOT EXISTS idx_votes_division_id ON votes(division_id);
        CREATE INDEX IF NOT EXISTS idx_votes_title ON votes(title);
        CREATE INDEX IF NOT EXISTS idx_members_constituency ON members(constituency);
        CREATE TABLE IF NOT EXISTS constituencies (
            constituency_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            current_member_id INTEGER,
            current_member_name TEXT,
            raw_json TEXT,
            fetched_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_constituencies_name ON constituencies(name);
        CREATE INDEX IF NOT EXISTS idx_constituencies_current_member_id
            ON constituencies(current_member_id);
        """
    )
    conn.commit()


def latest_local_division_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        """
        SELECT MAX(division_id) AS latest_id
        FROM votes
        WHERE title IS NOT NULL
          AND aye_count > 0
        """
    ).fetchone()
    return _safe_int(_row_value(row, "latest_id"))


def _get_json(client, url: str, params: dict[str, Any] | None = None):
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def fetch_current_commons_members(client, page_size: int = 100) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    skip = 0

    while True:
        params = {
            "House": 1,
            "IsCurrentMember": "true",
            "skip": skip,
            "take": page_size,
        }
        payload = _get_json(client, MEMBERS_SEARCH_URL, params=params)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        page_members = [
            item.get("value")
            for item in items
            if isinstance(item, dict) and isinstance(item.get("value"), dict)
            and _is_current_commons_member(item["value"])
        ]
        members.extend(page_members)

        received = len(items)
        if received == 0:
            break

        skip += received
        total_results = _safe_int(payload.get("totalResults")) if isinstance(payload, dict) else None
        if total_results is not None and skip >= total_results:
            break
        if total_results is None and received < page_size:
            break

    if not members:
        raise RuntimeError("Members API returned no current Commons members.")
    return members


def fetch_constituencies(client, page_size: int = 100) -> list[dict[str, Any]]:
    constituencies: list[dict[str, Any]] = []
    skip = 0

    while True:
        params = {
            "skip": skip,
            "take": page_size,
        }
        payload = _get_json(client, CONSTITUENCY_SEARCH_URL, params=params)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        page_constituencies = [
            item.get("value")
            for item in items
            if isinstance(item, dict) and isinstance(item.get("value"), dict)
        ]
        constituencies.extend(page_constituencies)

        received = len(items)
        if received == 0:
            break

        skip += received
        total_results = _safe_int(payload.get("totalResults")) if isinstance(payload, dict) else None
        if total_results is not None and skip >= total_results:
            break
        if total_results is None and received < page_size:
            break

    if not constituencies:
        raise RuntimeError("Constituency API returned no constituencies.")
    return constituencies


def _constituency_current_member_id(constituency: dict[str, Any]) -> int | None:
    representation = constituency.get("currentRepresentation") or {}
    if not isinstance(representation, dict):
        return None
    member = representation.get("member") or {}
    if not isinstance(member, dict):
        return None
    value = member.get("value") or {}
    if not isinstance(value, dict):
        return None
    return _safe_int(value.get("id"))


def _constituency_current_member_name(constituency: dict[str, Any]) -> str | None:
    representation = constituency.get("currentRepresentation") or {}
    if not isinstance(representation, dict):
        return None
    member = representation.get("member") or {}
    if not isinstance(member, dict):
        return None
    value = member.get("value") or {}
    if not isinstance(value, dict):
        return None
    name = value.get("nameDisplayAs")
    return str(name) if name else None


def upsert_constituencies(conn: sqlite3.Connection, constituencies: list[dict[str, Any]]) -> tuple[int, int, int]:
    fetched_at = _now()
    constituency_ids: list[int] = []
    upserted = 0
    represented = 0

    for constituency in constituencies:
        constituency_id = _safe_int(constituency.get("id"))
        name = str(constituency.get("name") or "").strip()
        if constituency_id is None or not name:
            continue

        current_member_id = _constituency_current_member_id(constituency)
        current_member_name = _constituency_current_member_name(constituency)
        if current_member_id is not None:
            represented += 1
        constituency_ids.append(constituency_id)
        conn.execute(
            """
            INSERT INTO constituencies (
                constituency_id, name, current_member_id,
                current_member_name, raw_json, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(constituency_id) DO UPDATE SET
                name=excluded.name,
                current_member_id=excluded.current_member_id,
                current_member_name=excluded.current_member_name,
                raw_json=excluded.raw_json,
                fetched_at=excluded.fetched_at
            """,
            (
                constituency_id,
                name,
                current_member_id,
                current_member_name,
                json.dumps(constituency, sort_keys=True, separators=(",", ":")),
                fetched_at,
            ),
        )
        upserted += 1

    if not constituency_ids:
        raise RuntimeError("Constituency API returned rows, but none had usable ids.")

    placeholders = ",".join("?" for _ in constituency_ids)
    conn.execute(
        f"DELETE FROM constituencies WHERE constituency_id NOT IN ({placeholders})",
        constituency_ids,
    )
    conn.commit()
    return upserted, represented, upserted - represented


def _member_fields(member: dict[str, Any]) -> tuple[int | None, str, str | None, str | None, int | None, str]:
    member_id = _safe_int(member.get("id") or member.get("member_id"))
    party = member.get("latestParty") or {}
    membership = member.get("latestHouseMembership") or {}
    return (
        member_id,
        str(member.get("nameDisplayAs") or member.get("name") or ""),
        party.get("name") if isinstance(party, dict) else None,
        membership.get("membershipFrom") if isinstance(membership, dict) else None,
        _safe_int(membership.get("house")) if isinstance(membership, dict) else None,
        json.dumps(member, sort_keys=True, separators=(",", ":")),
    )


def upsert_current_members(conn: sqlite3.Connection, members: list[dict[str, Any]]) -> tuple[int, int]:
    fetched_at = _now()
    current_ids: list[int] = []
    upserted = 0

    for member in members:
        if not _is_current_commons_member(member):
            continue
        member_id, name, party, constituency, house, current_posts = _member_fields(member)
        if member_id is None or not name:
            continue
        current_ids.append(member_id)
        conn.execute(
            """
            INSERT INTO members (
                member_id, name, party, constituency, house, current_posts, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(member_id) DO UPDATE SET
                name=excluded.name,
                party=excluded.party,
                constituency=excluded.constituency,
                house=excluded.house,
                current_posts=excluded.current_posts,
                fetched_at=excluded.fetched_at
            """,
            (
                member_id,
                name,
                party,
                constituency,
                house,
                current_posts,
                fetched_at,
            ),
        )
        upserted += 1

    if not current_ids:
        raise RuntimeError("Members API returned rows, but none had usable member ids.")

    placeholders = ",".join("?" for _ in current_ids)
    cursor = conn.execute(
        f"""
        UPDATE members
        SET constituency = NULL,
            fetched_at = ?
        WHERE constituency IS NOT NULL
          AND member_id NOT IN ({placeholders})
        """,
        [fetched_at, *current_ids],
    )
    conn.commit()
    return upserted, max(cursor.rowcount, 0)


def fetch_recent_divisions(client, take: int = 80) -> list[dict[str, Any]]:
    divisions: list[dict[str, Any]] = []
    skip = 0
    page_size = 25

    while len(divisions) < take:
        page_take = min(page_size, take - len(divisions))
        payload = _get_json(
            client,
            DIVISIONS_SEARCH_URL,
            params={
                "queryParameters.skip": skip,
                "queryParameters.take": page_take,
            },
        )
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        page = [row for row in rows if isinstance(row, dict)]
        if not page:
            break
        divisions.extend(page)
        skip += len(page)
        if len(page) < page_take:
            break

    if not divisions:
        raise RuntimeError("Commons Votes API returned no recent divisions.")
    return divisions


def fetch_all_divisions(
    client,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    page_size: int = 25,
) -> list[dict[str, Any]]:
    """Page through the ENTIRE Commons Votes division list (optionally bounded by
    date), newest first. Used for historical backfill, unlike fetch_recent_divisions
    which only returns the most recent `take` divisions."""
    divisions: list[dict[str, Any]] = []
    skip = 0

    while True:
        params: dict[str, Any] = {
            "queryParameters.skip": skip,
            "queryParameters.take": page_size,
        }
        if start_date:
            params["queryParameters.startDate"] = start_date
        if end_date:
            params["queryParameters.endDate"] = end_date
        payload = _get_json(client, DIVISIONS_SEARCH_URL, params=params)
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        page = [row for row in rows if isinstance(row, dict)]
        if not page:
            break
        divisions.extend(page)
        skip += len(page)
        if len(page) < page_size:
            break

    return divisions


def _division_is_complete(
    conn: sqlite3.Connection,
    division_id: int,
    tolerance: int = COMPLETENESS_TELLER_TOLERANCE,
) -> bool:
    """True when the local DB already stores a full member set for this division, so
    a backfill re-run can skip it and only spend API calls on the genuine gaps."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS stored, MAX(aye_count) AS aye_count, MAX(no_count) AS no_count
        FROM votes
        WHERE division_id = ?
        """,
        (division_id,),
    ).fetchone()
    stored = _safe_int(_row_value(row, "stored")) or 0
    if stored <= 0:
        return False
    reported = (_safe_int(_row_value(row, "aye_count", 1)) or 0) + (
        _safe_int(_row_value(row, "no_count", 2)) or 0
    )
    return stored >= reported - tolerance


def fetch_division_detail(client, division_id: int) -> dict[str, Any]:
    payload = _get_json(client, f"{COMMONS_VOTES_BASE_URL}/division/{division_id}.json")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Division {division_id} detail payload was not an object.")
    return payload


def _division_id(division: dict[str, Any]) -> int:
    division_id = _safe_int(
        division.get("DivisionId")
        or division.get("divisionId")
        or division.get("division_id")
    )
    if division_id is None:
        raise ValueError(f"Division payload missing DivisionId: {division}")
    return division_id


def _division_vote_members(division: dict[str, Any]):
    for key, voted_aye in (
        ("Ayes", 1),
        ("AyeTellers", 1),
        ("Noes", 0),
        ("NoTellers", 0),
    ):
        members = division.get(key) or []
        if not isinstance(members, list):
            continue
        for member in members:
            if isinstance(member, dict):
                yield member, voted_aye


def upsert_division_detail(conn: sqlite3.Connection, division: dict[str, Any]) -> int:
    division_id = _division_id(division)
    title = str(division.get("FriendlyTitle") or division.get("Title") or "")
    division_date = str(division.get("Date") or "")
    aye_count = _safe_int(division.get("AyeCount"))
    no_count = _safe_int(division.get("NoCount"))
    fetched_at = _now()

    vote_by_member: dict[int, int] = {}
    for member, voted_aye in _division_vote_members(division):
        member_id = _safe_int(member.get("MemberId"))
        if member_id is None:
            continue
        vote_by_member[member_id] = voted_aye

    if not vote_by_member:
        raise RuntimeError(f"Division {division_id} contained no Aye/No member rows.")

    for member_id, voted_aye in sorted(vote_by_member.items()):
        conn.execute(
            """
            INSERT INTO votes (
                division_id, member_id, division_date, title,
                voted_aye, aye_count, no_count, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(division_id, member_id) DO UPDATE SET
                division_date=excluded.division_date,
                title=excluded.title,
                voted_aye=excluded.voted_aye,
                aye_count=excluded.aye_count,
                no_count=excluded.no_count,
                fetched_at=excluded.fetched_at
            """,
            (
                division_id,
                member_id,
                division_date,
                title,
                voted_aye,
                aye_count,
                no_count,
                fetched_at,
            ),
        )

    conn.commit()
    return len(vote_by_member)


def update_database(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    client=None,
    latest_take: int = 80,
    member_page_size: int = 100,
    constituency_page_size: int = 100,
    backfill: bool = False,
    backfill_start_date: str | None = None,
    backfill_end_date: str | None = None,
    skip_complete: bool | None = None,
) -> UpdateSummary:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            prepare_database(conn)
            local_latest_before = latest_local_division_id(conn)

            constituencies = fetch_constituencies(
                client,
                page_size=constituency_page_size,
            )
            (
                constituencies_upserted,
                constituencies_with_current_member,
                vacant_constituencies,
            ) = upsert_constituencies(conn, constituencies)

            members = fetch_current_commons_members(client, page_size=member_page_size)
            members_upserted, members_deactivated = upsert_current_members(conn, members)

            # Backfill walks the full division history; the daily path only refreshes
            # the most recent divisions. When backfilling we skip divisions already
            # stored in full so an interrupted run resumes cheaply.
            if skip_complete is None:
                skip_complete = backfill
            if backfill:
                divisions = fetch_all_divisions(
                    client,
                    start_date=backfill_start_date,
                    end_date=backfill_end_date,
                )
            else:
                divisions = fetch_recent_divisions(client, take=latest_take)

            divisions_upserted = 0
            divisions_skipped = 0
            vote_rows_upserted = 0
            for division in divisions:
                division_id = _division_id(division)
                if skip_complete and _division_is_complete(conn, division_id):
                    divisions_skipped += 1
                    continue
                detail = fetch_division_detail(client, division_id)
                vote_rows_upserted += upsert_division_detail(conn, detail)
                divisions_upserted += 1

            local_latest_after = latest_local_division_id(conn)
        finally:
            conn.close()
    finally:
        if owns_client:
            client.close()

    return UpdateSummary(
        db_path=path,
        local_latest_before=local_latest_before,
        local_latest_after=local_latest_after,
        members_seen=len(members),
        members_upserted=members_upserted,
        members_deactivated=members_deactivated,
        constituencies_seen=len(constituencies),
        constituencies_upserted=constituencies_upserted,
        constituencies_with_current_member=constituencies_with_current_member,
        vacant_constituencies=vacant_constituencies,
        divisions_seen=len(divisions),
        divisions_upserted=divisions_upserted,
        divisions_skipped=divisions_skipped,
        vote_rows_upserted=vote_rows_upserted,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh YourGov's bundled PublicWhip-family SQLite data.",
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database to update. Defaults to the repo yourgov.db seed.",
    )
    parser.add_argument(
        "--latest-take",
        type=int,
        default=80,
        help="Number of recent Commons divisions to refresh.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Backfill the FULL division history (idempotent), not just the latest "
            "divisions. Skips divisions already stored in full so it resumes cheaply."
        ),
    )
    parser.add_argument(
        "--backfill-start-date",
        default=None,
        help="Optional ISO date (YYYY-MM-DD) lower bound for --backfill.",
    )
    parser.add_argument(
        "--backfill-end-date",
        default=None,
        help="Optional ISO date (YYYY-MM-DD) upper bound for --backfill.",
    )
    parser.add_argument(
        "--no-skip-complete",
        action="store_true",
        help="During --backfill, re-fetch even divisions already stored in full.",
    )
    parser.add_argument(
        "--member-page-size",
        type=int,
        default=100,
        help="Members API page size.",
    )
    parser.add_argument(
        "--constituency-page-size",
        type=int,
        default=100,
        help="Constituency API page size.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the update summary as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = update_database(
        args.db_path,
        latest_take=args.latest_take,
        member_page_size=args.member_page_size,
        constituency_page_size=args.constituency_page_size,
        backfill=args.backfill,
        backfill_start_date=args.backfill_start_date,
        backfill_end_date=args.backfill_end_date,
        skip_complete=False if args.no_skip_complete else None,
    )

    if args.json:
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    else:
        print("YourGov data refresh complete")
        for key, value in summary.as_dict().items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
