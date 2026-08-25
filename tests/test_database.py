"""Regression tests for the bundled pybecker database."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from custom_components.becker.pybecker.database import Database


def test_connection_usable_across_threads(tmp_path: Path) -> None:
    """The connection is created in the executor but used on the event loop.

    async_setup_entry builds the Becker (and therefore the sqlite
    connection) in a worker thread via async_add_executor_job, while every
    later database call runs as a coroutine on the event loop thread.
    Regression test for the ProgrammingError this raised when the
    connection was bound to its creating thread.
    """
    db_file = str(tmp_path / "centronic-stick.db")

    with ThreadPoolExecutor(max_workers=1) as executor:
        database = executor.submit(Database, db_file).result()

    # Access from a different (here: the main) thread must not raise.
    assert database.get_all_units() == []
    assert database.get_unit(1) == ["1737b", 0, 0]


def test_export_units_returns_all_rows(tmp_path: Path) -> None:
    """export_units returns every unit row, not just configured ones."""
    db_file = str(tmp_path / "centronic-stick.db")
    db = Database(db_file)
    db.import_units([{"code": "1737b", "increment": 42, "configured": 1}])

    rows = db.export_units()

    assert len(rows) == 5  # the five seeded units
    first = next(r for r in rows if r["code"] == "1737b")
    assert first == {"code": "1737b", "increment": 42, "configured": 1}
    db.conn.close()


def test_import_units_updates_matching_codes_only(tmp_path: Path) -> None:
    """import_units updates increment+configured for the given codes only."""
    db_file = str(tmp_path / "centronic-stick.db")
    db = Database(db_file)

    db.import_units([{"code": "1737c", "increment": 7, "configured": 1}])

    rows = {r["code"]: r for r in db.export_units()}
    assert rows["1737c"] == {"code": "1737c", "increment": 7, "configured": 1}
    assert rows["1737b"] == {"code": "1737b", "increment": 0, "configured": 0}
    db.conn.close()
