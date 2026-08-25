"""Tests for the db_transfer serialization/validation helpers."""

import json

import pytest

from custom_components.becker.db_transfer import (
    StateFormatError,
    StateJSONError,
    dump_state_json,
    parse_state_json,
)

UNITS = [
    {"code": "1737b", "increment": 42, "configured": 1},
    {"code": "1737c", "increment": 0, "configured": 0},
]


def test_dump_state_json_roundtrips() -> None:
    raw = dump_state_json(UNITS, "2026-08-03T10:00:00")
    data = json.loads(raw)
    assert data["version"] == 1
    assert data["exported_at"] == "2026-08-03T10:00:00"
    assert data["units"] == UNITS


def test_parse_state_json_returns_normalized_rows() -> None:
    rows = parse_state_json(dump_state_json(UNITS, "2026-08-03T10:00:00"))
    assert rows == UNITS


def test_parse_state_json_rejects_non_json() -> None:
    with pytest.raises(StateJSONError):
        parse_state_json("not json {{{")


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 1, "units": "nope"},
        {"version": 1, "units": []},
        {"version": 1, "units": [{"code": "9999z", "increment": 1, "configured": 1}]},
        {"version": 1, "units": [{"code": "1737b", "increment": -1, "configured": 1}]},
        {"version": 1, "units": [{"code": "1737b", "increment": 1, "configured": 2}]},
        {"version": 1, "units": [{"code": "1737b", "configured": 1}]},
    ],
    ids=["units-not-list", "empty", "unknown-code", "negative", "bad-configured", "missing-key"],
)
def test_parse_state_json_rejects_bad_structure(payload: dict) -> None:
    with pytest.raises(StateFormatError):
        parse_state_json(json.dumps(payload))


from pathlib import Path

from custom_components.becker.db_transfer import (
    apply_units,
    consistent_copy,
    is_valid_becker_db,
    read_units,
)
from custom_components.becker.pybecker.database import Database


def _make_db(tmp_path: Path) -> str:
    path = str(tmp_path / "centronic-stick.db")
    Database(path).conn.close()
    return path


def test_read_units_reads_all_rows(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    rows = read_units(path)
    assert len(rows) == 5
    assert {r["code"] for r in rows} == set("1737b 1737c 1737d 1737e 1737f".split())


def test_apply_units_persists_changes(tmp_path: Path) -> None:
    path = _make_db(tmp_path)
    apply_units(path, [{"code": "1737b", "increment": 99, "configured": 1}])
    rows = {r["code"]: r for r in read_units(path)}
    assert rows["1737b"] == {"code": "1737b", "increment": 99, "configured": 1}


def test_is_valid_becker_db_true_for_real_db(tmp_path: Path) -> None:
    assert is_valid_becker_db(Path(_make_db(tmp_path))) is True


def test_is_valid_becker_db_false_for_garbage(tmp_path: Path) -> None:
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a sqlite database")
    assert is_valid_becker_db(junk) is False


def test_is_valid_becker_db_false_for_wrong_schema(tmp_path: Path) -> None:
    import sqlite3

    other = tmp_path / "other.db"
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE something (x INTEGER)")
    con.commit()
    con.close()
    assert is_valid_becker_db(other) is False


def test_consistent_copy_produces_valid_db(tmp_path: Path) -> None:
    src = _make_db(tmp_path)
    apply_units(src, [{"code": "1737b", "increment": 5, "configured": 1}])
    dst = tmp_path / "copy.db"
    consistent_copy(Path(src), dst)
    assert is_valid_becker_db(dst) is True
    assert {r["code"]: r for r in read_units(str(dst))}["1737b"]["increment"] == 5
