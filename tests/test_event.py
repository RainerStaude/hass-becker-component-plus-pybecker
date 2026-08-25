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


import re

from homeassistant.const import (
    CONF_DEVICE,
    CONF_FILENAME,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.becker import signal_for_entry
from custom_components.becker.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SERIAL,
    DOMAIN,
)
from custom_components.becker.pybecker.becker_helper import MESSAGE


def _make_packet(unit_id: str, channel: str, command: str, argument: str) -> re.Match[bytes]:
    """Build a real MESSAGE match for a received packet."""
    body = (
        b"0000000002010B"  # CODE_PREFIX
        + b"0001"  # increment (4 hex)
        + b"000000"  # CODE_SUFFIX
        + unit_id.encode()  # unit_id (5 hex)
        + b"000000"  # 6 hex filler
        + channel.encode()  # channel (1 hex)
        + b"00"
        + command.encode()  # command (1 hex)
        + argument.encode()  # argument (1 hex)
        + b"00"  # 2 hex trailer
    )
    match = MESSAGE.search(b"\x02" + body + b"\x03")
    assert match is not None
    return match


async def _setup(hass: HomeAssistant, mock_becker) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_DEVICE: "/dev/ttyUSB0",
            CONF_FILENAME: "centronic-stick.db",
        },
        unique_id="/dev/ttyUSB0",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_remote_event_entity_fires(hass: HomeAssistant, mock_becker) -> None:
    entry = await _setup(hass, mock_becker)
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id("event", DOMAIN, f"{entry.entry_id}_remote")
    assert entity_id is not None
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    async_dispatcher_send(
        hass,
        signal_for_entry(entry.entry_id),
        _make_packet("1737B", "1", "2", "0"),
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "up"
    assert state.attributes["unit_id"] == "1737B"
    assert state.attributes["channel"] == "1"


async def test_remote_event_unknown_command(hass: HomeAssistant, mock_becker) -> None:
    entry = await _setup(hass, mock_becker)
    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id("event", DOMAIN, f"{entry.entry_id}_remote")

    async_dispatcher_send(
        hass,
        signal_for_entry(entry.entry_id),
        _make_packet("1737C", "2", "8", "0"),  # 0x80 pair/train -> unknown
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "unknown"
    assert state.attributes["unit_id"] == "1737C"
    assert state.attributes["command_code"] == "80"
