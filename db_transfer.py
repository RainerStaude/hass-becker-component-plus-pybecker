"""Serialization and validation helpers for shutter-database import/export.

Pure logic with no Home Assistant imports so it can be unit-tested directly.
"""

import json
import sqlite3
from pathlib import Path

from .pybecker.database import Database

STATE_VERSION = 1
KNOWN_UNIT_CODES = ("1737b", "1737c", "1737d", "1737e", "1737f")


class StateJSONError(Exception):
    """Raised when the uploaded text is not valid JSON."""


class StateFormatError(Exception):
    """Raised when the JSON does not match the expected state format."""


def build_state(units: list[dict], exported_at: str) -> dict:
    """Build the export document from unit rows."""
    return {"version": STATE_VERSION, "exported_at": exported_at, "units": units}


def dump_state_json(units: list[dict], exported_at: str) -> str:
    """Serialize unit rows to a pretty JSON string."""
    return json.dumps(build_state(units, exported_at), indent=2)


def parse_state_json(raw: str | bytes) -> list[dict]:
    """Parse and validate uploaded JSON, returning normalized unit rows.

    Raises StateJSONError for non-JSON input and StateFormatError when the
    structure, unit codes, or values are invalid.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as err:
        raise StateJSONError from err

    if not isinstance(data, dict) or not isinstance(data.get("units"), list):
        raise StateFormatError
    if not data["units"]:
        raise StateFormatError

    rows: list[dict] = []
    for item in data["units"]:
        if not isinstance(item, dict) or item.get("code") not in KNOWN_UNIT_CODES:
            raise StateFormatError
        try:
            increment = int(item["increment"])
            configured = int(item["configured"])
        except (KeyError, ValueError, TypeError) as err:
            raise StateFormatError from err
        if increment < 0 or configured not in (0, 1):
            raise StateFormatError
        rows.append(
            {"code": item["code"], "increment": increment, "configured": configured}
        )
    return rows


def read_units(db_path: str) -> list[dict]:
    """Open the database at db_path and return all unit rows."""
    db = Database(db_path)
    try:
        return db.export_units()
    finally:
        db.conn.close()


def apply_units(db_path: str, rows: list[dict]) -> None:
    """Open the database at db_path and apply the given unit rows."""
    db = Database(db_path)
    try:
        db.import_units(rows)
    finally:
        db.conn.close()


def is_valid_becker_db(path: Path) -> bool:
    """Return True if path is a SQLite database containing a 'unit' table."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='unit'"
        )
        return cur.fetchone() is not None
    except sqlite3.DatabaseError:
        return False
    finally:
        con.close()


def consistent_copy(src_path: Path, dst_path: Path) -> None:
    """Write a transactionally consistent copy of the db via the backup API."""
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
