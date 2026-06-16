"""The full-history seed DB ships gzipped (mygov.db.gz) because the raw file is
~280MB — over GitHub's 100MB limit and heavy for the FTPS deploy. These tests
protect that contract: the archive is present, is a valid SQLite database with
the expected vote data, and the app exposes the runtime decompression hook.
"""

import gzip
import importlib
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SEED_GZ = ROOT / "mygov.db.gz"


def test_seed_archive_is_present_and_small_enough_for_github():
    assert SEED_GZ.exists(), "mygov.db.gz seed archive is missing"
    size_mb = SEED_GZ.stat().st_size / 1e6
    # GitHub hard-rejects files over 100MB; stay comfortably under.
    assert size_mb < 95, f"seed archive {size_mb:.1f}MB exceeds the safe GitHub limit"


def test_seed_archive_decompresses_to_a_valid_full_history_db():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "seed.db")
        with gzip.open(SEED_GZ, "rb") as fsrc, open(out, "wb") as fdst:
            fdst.write(fsrc.read())
        conn = sqlite3.connect(out)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert {"members", "votes", "constituencies"}.issubset(tables)
            vote_rows = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
            divisions = conn.execute(
                "SELECT COUNT(DISTINCT division_id) FROM votes"
            ).fetchone()[0]
        finally:
            conn.close()
        # Full-history backfill: far beyond the old recent-only ~165k rows.
        assert vote_rows > 900_000, f"only {vote_rows} vote rows — backfill not shipped"
        assert divisions > 2_000, f"only {divisions} divisions — backfill not shipped"


def test_app_exposes_seed_decompression_hook():
    appmod = importlib.import_module("app")
    assert hasattr(appmod, "_ensure_seed_db")
    assert appmod._SEED_GZ.endswith("mygov.db.gz")
    # The resolved seed path must point at a real SQLite file the app can read.
    conn = appmod.get_publicwhip_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    finally:
        conn.close()
    assert count > 900_000
