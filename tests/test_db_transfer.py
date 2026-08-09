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
