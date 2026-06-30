"""YourGov data layer.

Owns the SQLite schema, idempotent migrations, and the upsert CRUD used by the
ingest pipeline (see parliament_client.py). The database is a **read-mostly seed
snapshot**: the live web app overwhelmingly reads it; the only writes are this
ingest path (refreshing MPs/votes/questions) and the explainer's answer cache.
"""
import os
import sqlite3
import json
from datetime import datetime, timezone

_SEED_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yourgov.db")
# On the live host (Krystal/Passenger) the app directory is READ-ONLY, so any
# writable DB copy must live in /tmp. Locally (no /tmp) we use the repo seed.
DB_PATH = "/tmp/yourgov.db" if os.path.exists("/tmp") else _SEED_DB


_migration_done = False


def get_conn() -> sqlite3.Connection:
    """Open a Row-factory SQLite connection.

    Runs the explanations-table migration exactly ONCE per process (guarded by
    the module-level `_migration_done` flag) so the first request after a
    redeploy self-heals an older on-disk schema, without paying the check on
    every connection. Callers are responsible for closing the connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    global _migration_done
    if not _migration_done:
        _migrate_explanations(conn)
        _migration_done = True
    return conn


def _migrate_pw_indexes(conn: sqlite3.Connection) -> None:
    """Add indexes on votes(member_id), votes(division_id), votes(title) for PW queries."""
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)")
        conn.commit()
        already = conn.execute(
            "SELECT 1 FROM _migrations WHERE name='pw_indexes_v1'"
        ).fetchone()
        if already:
            return
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_votes_member_id ON votes(member_id);
            CREATE INDEX IF NOT EXISTS idx_votes_division_id ON votes(division_id);
            CREATE INDEX IF NOT EXISTS idx_votes_title ON votes(title);
        """)
        conn.execute("INSERT INTO _migrations VALUES ('pw_indexes_v1')")
        conn.commit()
    except Exception as e:
        print(f"[db] migration warning: {e}")


def _migrate_activity_fetched(conn: sqlite3.Connection) -> None:
    """Add activity_fetched_at column to members — tracks when votes/questions were last pulled."""
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)")
        conn.commit()
        already = conn.execute(
            "SELECT 1 FROM _migrations WHERE name='members_activity_fetched_v1'"
        ).fetchone()
        if already:
            return
        conn.execute("ALTER TABLE members ADD COLUMN activity_fetched_at TEXT")
        conn.execute("INSERT INTO _migrations VALUES ('members_activity_fetched_v1')")
        conn.commit()
    except Exception as e:
        print(f"[db] migration warning: {e}")


def _migrate_explanations(conn: sqlite3.Connection) -> None:
    """Migrate old single-level explanations table to composite-key v2 schema."""
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY)")
        conn.commit()
        already = conn.execute(
            "SELECT 1 FROM _migrations WHERE name='explanations_v2'"
        ).fetchone()
        if already:
            return
        # Check old table exists
        old = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='explanations'"
        ).fetchone()
        if old:
            conn.executescript("""
                ALTER TABLE explanations RENAME TO explanations_old;
                CREATE TABLE explanations (
                    division_id   INTEGER NOT NULL,
                    member_id     INTEGER NOT NULL,
                    level         INTEGER NOT NULL,
                    prompt_version TEXT   NOT NULL,
                    explanation   TEXT    NOT NULL,
                    created_at    TEXT    DEFAULT (datetime('now')),
                    PRIMARY KEY (division_id, member_id, level, prompt_version)
                );
                INSERT INTO explanations
                    SELECT division_id, abs(member_id), 2, 'v1', explanation, created_at
                    FROM explanations_old;
                DROP TABLE explanations_old;
            """)
        else:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS explanations (
                    division_id   INTEGER NOT NULL,
                    member_id     INTEGER NOT NULL,
                    level         INTEGER NOT NULL,
                    prompt_version TEXT   NOT NULL,
                    explanation   TEXT    NOT NULL,
                    created_at    TEXT    DEFAULT (datetime('now')),
                    PRIMARY KEY (division_id, member_id, level, prompt_version)
                );
            """)
        conn.execute("INSERT INTO _migrations VALUES ('explanations_v2')")
        conn.commit()
    except Exception as e:
        print(f"[db] migration warning: {e}")


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables from scratch (used by ingest and tests). Live databases
    instead evolve incrementally through the `_migrate_*` helpers, so this is the
    greenfield path, not the upgrade path."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            member_id     INTEGER PRIMARY KEY,
            name          TEXT NOT NULL,
            party         TEXT,
            constituency  TEXT,
            house         INTEGER,
            current_posts TEXT,
            fetched_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS votes (
            division_id   INTEGER NOT NULL,
            member_id     INTEGER NOT NULL,
            division_date TEXT NOT NULL,
            title         TEXT,
            voted_aye     INTEGER,
            aye_count     INTEGER,
            no_count      INTEGER,
            fetched_at    TEXT NOT NULL,
            PRIMARY KEY (division_id, member_id)
        );

        CREATE TABLE IF NOT EXISTS questions (
            question_id   INTEGER PRIMARY KEY,
            member_id     INTEGER NOT NULL,
            question_text TEXT,
            date_tabled   TEXT,
            answering_body TEXT,
            fetched_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS constituencies (
            constituency_id INTEGER PRIMARY KEY,
            name            TEXT NOT NULL UNIQUE,
            current_member_id INTEGER,
            current_member_name TEXT,
            raw_json        TEXT,
            fetched_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS explanations (
            division_id   INTEGER NOT NULL,
            member_id     INTEGER NOT NULL,
            level         INTEGER NOT NULL,
            prompt_version TEXT   NOT NULL,
            explanation   TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (division_id, member_id, level, prompt_version)
        );
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_member(conn: sqlite3.Connection, member_id: int, data: dict) -> None:
    """Insert/update one MP. Flattens the nested Members-API shape
    (`latestParty.name`, `latestHouseMembership.membershipFrom`) into columns and
    stashes the full raw record as JSON in `current_posts` for later use."""
    party = data.get("latestParty", {}).get("name")
    constituency = data.get("latestHouseMembership", {}).get("membershipFrom")
    house = data.get("latestHouseMembership", {}).get("house")
    conn.execute(
        """
        INSERT INTO members (member_id, name, party, constituency, house, current_posts, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(member_id) DO UPDATE SET
            name=excluded.name, party=excluded.party,
            constituency=excluded.constituency, house=excluded.house,
            current_posts=excluded.current_posts, fetched_at=excluded.fetched_at
        """,
        (
            member_id,
            data.get("nameDisplayAs", ""),
            party,
            constituency,
            house,
            json.dumps(data),
            _now(),
        ),
    )
    conn.commit()


def upsert_votes(conn: sqlite3.Connection, member_id: int, votes: list[dict]) -> int:
    # NB: the Commons Votes API uses PascalCase (PublishedDivision, DivisionId,
    # MemberVotedAye, AyeCount) — unlike the Members API's camelCase used in
    # upsert_member. This shape difference is easy to trip over when tracing data
    # flow, so the two upserts deliberately read different key casings.
    count = 0
    for v in votes:
        div = v.get("PublishedDivision", {})
        division_id = div.get("DivisionId")
        if not division_id:
            continue
        voted_aye = 1 if v.get("MemberVotedAye") else 0
        conn.execute(
            """
            INSERT INTO votes (division_id, member_id, division_date, title, voted_aye, aye_count, no_count, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(division_id, member_id) DO UPDATE SET
                division_date=excluded.division_date, title=excluded.title,
                voted_aye=excluded.voted_aye, aye_count=excluded.aye_count,
                no_count=excluded.no_count, fetched_at=excluded.fetched_at
            """,
            (
                division_id,
                member_id,
                div.get("Date", ""),
                div.get("FriendlyTitle") or div.get("Title", ""),
                voted_aye,
                div.get("AyeCount"),
                div.get("NoCount"),
                _now(),
            ),
        )
        count += 1
    conn.commit()
    return count


def upsert_questions(conn: sqlite3.Connection, member_id: int, questions: list[dict]) -> int:
    count = 0
    for q in questions:
        question_id = q.get("id")
        if not question_id:
            continue
        answering_body = q.get("answeringBody", {})
        if isinstance(answering_body, dict):
            body_name = answering_body.get("name", "")
        else:
            body_name = ""
        conn.execute(
            """
            INSERT INTO questions (question_id, member_id, question_text, date_tabled, answering_body, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                question_text=excluded.question_text, date_tabled=excluded.date_tabled,
                answering_body=excluded.answering_body, fetched_at=excluded.fetched_at
            """,
            (
                question_id,
                member_id,
                q.get("questionText", ""),
                q.get("dateTabled", ""),
                body_name,
                _now(),
            ),
        )
        count += 1
    conn.commit()
    return count


def print_summary(conn: sqlite3.Connection, member_id: int) -> None:
    row = conn.execute(
        "SELECT name, party, constituency FROM members WHERE member_id = ?", (member_id,)
    ).fetchone()
    if not row:
        print(f"  No member record for ID {member_id}")
        return

    print(f"\n{'='*60}")
    print(f"  {row['name']}  |  {row['party']}  |  {row['constituency']}")
    print(f"{'='*60}")

    votes = conn.execute(
        "SELECT division_date, title, voted_aye FROM votes WHERE member_id = ? ORDER BY division_date DESC LIMIT 10",
        (member_id,),
    ).fetchall()
    print(f"\n  VOTES ({len(votes)} most recent shown):")
    for v in votes:
        aye_str = "AYE" if v["voted_aye"] else "NO "
        date = (v["division_date"] or "")[:10]
        title = (v["title"] or "")[:60]
        print(f"    {date}  [{aye_str}]  {title}")

    questions = conn.execute(
        "SELECT date_tabled, answering_body, question_text FROM questions WHERE member_id = ? ORDER BY date_tabled DESC LIMIT 5",
        (member_id,),
    ).fetchall()
    print(f"\n  WRITTEN QUESTIONS ({len(questions)} most recent shown):")
    for q in questions:
        date = (q["date_tabled"] or "")[:10]
        body = (q["answering_body"] or "")[:30]
        text = (q["question_text"] or "")[:70]
        print(f"    {date}  [{body}]  {text}...")
    print()
