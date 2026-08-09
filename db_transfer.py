"""Serialization and validation helpers for shutter-database import/export.

Pure logic with no Home Assistant imports so it can be unit-tested directly.
"""

import json

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
