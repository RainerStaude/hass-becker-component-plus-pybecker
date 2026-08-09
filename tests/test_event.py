"""Tests for the Becker remote event entity."""

import pytest

from custom_components.becker.event import decode_event_type


@pytest.mark.parametrize(
    ("command", "argument", "expected"),
    [
        (b"2", b"0", "up"),
        (b"4", b"0", "down"),
        (b"1", b"0", "halt"),
        (b"0", b"0", "release"),
        (b"2", b"4", "up_intermediate"),
        (b"4", b"4", "down_intermediate"),
        (b"2", b"1", "up"),  # non-zero argument nibble falls back to plain up
        (b"8", b"0", "unknown"),  # pair/train (0x80) is not in COMMANDS
    ],
    ids=[
        "up",
        "down",
        "halt",
        "release",
        "up-intermediate",
        "down-intermediate",
        "up-nonzero-arg",
        "unknown",
    ],
)
def test_decode_event_type(command: bytes, argument: bytes, expected: str) -> None:
    assert decode_event_type(command, argument) == expected
