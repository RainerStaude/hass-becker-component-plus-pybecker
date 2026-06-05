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
