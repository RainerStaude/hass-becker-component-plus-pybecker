"""Tests for the becker config flow."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_DEVICE, CONF_FILENAME, CONF_HOST, CONF_PORT
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir

from custom_components.becker.const import (
    CONF_CHANNEL,
    CONF_CONNECTION_TYPE,
    CONF_INTERMEDIATE_DISABLE,
    CONF_INTERMEDIATE_POSITION,
    CONF_REMOTE_ID,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_DB_FILENAME,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
)
from custom_components.becker.pybecker.becker_helper import BeckerConnectionError

TEST_DEVICE = "/dev/ttyUSB0"


async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Set up the becker integration."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_setup_entry", "mock_test_connection")
async def test_user_serial_flow(hass: HomeAssistant) -> None:
    """Test the serial happy path."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_SERIAL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == CONNECTION_TYPE_SERIAL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: TEST_DEVICE}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Becker (ttyUSB0)"
    assert result["data"] == {
        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        CONF_DEVICE: TEST_DEVICE,
        CONF_FILENAME: DEFAULT_DB_FILENAME,
    }
    assert result["result"].unique_id == TEST_DEVICE


@pytest.mark.usefixtures("mock_setup_entry", "mock_test_connection")
async def test_user_network_flow(hass: HomeAssistant) -> None:
    """Test the network happy path."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_NETWORK}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == CONNECTION_TYPE_NETWORK

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.20", CONF_PORT: 5000}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Becker (192.168.1.20:5000)"
    assert result["data"] == {
        CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        CONF_DEVICE: "192.168.1.20:5000",
        CONF_HOST: "192.168.1.20",
        CONF_PORT: 5000,
        CONF_FILENAME: DEFAULT_DB_FILENAME,
    }
    assert result["result"].unique_id == "socket://192.168.1.20:5000"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_serial_cannot_connect(
    hass: HomeAssistant, mock_test_connection: MagicMock
) -> None:
    """Test error handling and recovery on connection failure."""
    mock_test_connection.side_effect = BeckerConnectionError("no stick")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_SERIAL}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: TEST_DEVICE}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_test_connection.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: TEST_DEVICE}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry", "mock_test_connection")
async def test_user_serial_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the same stick cannot be added twice."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": CONNECTION_TYPE_SERIAL}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE: TEST_DEVICE}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_import_flow(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Test importing a YAML platform configuration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={
            CONF_DEVICE: TEST_DEVICE,
            "covers": {
                "kitchen": {
                    CONF_CHANNEL: "1",
                    "friendly_name": "Kitchen",
                    CONF_TRAVELLING_TIME_DOWN: 20.0,
                    CONF_TRAVELLING_TIME_UP: 22.0,
                    CONF_INTERMEDIATE_POSITION: True,
                },
                "living_room": {
                    CONF_CHANNEL: "2:1",
                    CONF_INTERMEDIATE_POSITION: True,
                    CONF_INTERMEDIATE_DISABLE: True,
                },
            },
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        CONF_DEVICE: TEST_DEVICE,
        CONF_FILENAME: DEFAULT_DB_FILENAME,
    }

    subentries = list(result["result"].subentries.values())
    assert len(subentries) == 2
    kitchen = next(s for s in subentries if s.unique_id == "1")
    assert kitchen.title == "Kitchen"
    assert kitchen.data[CONF_TRAVELLING_TIME_DOWN] == 20.0
    living = next(s for s in subentries if s.unique_id == "2:1")
    assert living.title == "living_room"
    # The deprecated intermediate_position_disable key is collapsed
    assert CONF_INTERMEDIATE_DISABLE not in living.data
    assert living.data[CONF_INTERMEDIATE_POSITION] is False

    assert issue_registry.async_get_issue(
        HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}"
    )


@pytest.mark.usefixtures("mock_setup_entry")
async def test_import_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a repeated import aborts."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_DEVICE: TEST_DEVICE, "covers": {}},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_becker")
async def test_subentry_add_cover(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test adding a cover subentry, including channel validation."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, SUBENTRY_TYPE_COVER),
        context={"source": SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHANNEL: "9",
            CONF_INTERMEDIATE_POSITION: True,
            "intermediate_position_up": 25,
            "intermediate_position_down": 75,
            "tilt_blind": False,
            "tilt_time_blind": 0.3,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CHANNEL: "invalid_channel"}

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHANNEL: "2:1",
            "friendly_name": "Living room",
            CONF_REMOTE_ID: "12345:2",
            CONF_INTERMEDIATE_POSITION: True,
            "intermediate_position_up": 25,
            "intermediate_position_down": 75,
            "tilt_blind": False,
            "tilt_time_blind": 0.3,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert len(mock_config_entry.subentries) == 1
    subentry = next(iter(mock_config_entry.subentries.values()))
    assert subentry.unique_id == "2:1"
    assert subentry.title == "Living room"
    assert subentry.data[CONF_REMOTE_ID] == "12345:2"


@pytest.mark.usefixtures("mock_becker")
async def test_subentry_add_duplicate_channel(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Test that two covers cannot share a channel."""
    await setup_integration(hass, mock_config_entry_with_cover)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry_with_cover.entry_id, SUBENTRY_TYPE_COVER),
        context={"source": SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_CHANNEL: "1",
            CONF_INTERMEDIATE_POSITION: True,
            "intermediate_position_up": 25,
            "intermediate_position_down": 75,
            "tilt_blind": False,
            "tilt_time_blind": 0.3,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CHANNEL: "already_configured"}


@pytest.mark.usefixtures("mock_becker")
async def test_subentry_reconfigure(
    hass: HomeAssistant, mock_config_entry_with_cover: MockConfigEntry
) -> None:
    """Test reconfiguring a cover keeps the channel."""
    await setup_integration(hass, mock_config_entry_with_cover)
    subentry = next(iter(mock_config_entry_with_cover.subentries.values()))

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry_with_cover.entry_id, SUBENTRY_TYPE_COVER),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "friendly_name": "Kitchen window",
            CONF_TRAVELLING_TIME_DOWN: 18.5,
            CONF_TRAVELLING_TIME_UP: 19.5,
            CONF_INTERMEDIATE_POSITION: True,
            "intermediate_position_up": 25,
            "intermediate_position_down": 75,
            "tilt_blind": False,
            "tilt_time_blind": 0.3,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    subentry = mock_config_entry_with_cover.subentries[subentry.subentry_id]
    assert subentry.data[CONF_CHANNEL] == "1"
    assert subentry.data[CONF_TRAVELLING_TIME_DOWN] == 18.5
    assert subentry.title == "Kitchen window"


async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_becker: MagicMock,
    mock_config_entry_with_cover: MockConfigEntry,
) -> None:
    """Test the entry sets up the cover and unload closes the connection."""
    await setup_integration(hass, mock_config_entry_with_cover)

    mock_becker.init_unconfigured_unit.assert_awaited_once_with("1", name="Kitchen")
    state = hass.states.get("cover.kitchen")
    assert state is not None

    assert await hass.config_entries.async_unload(
        mock_config_entry_with_cover.entry_id
    )
    await hass.async_block_till_done()
    mock_becker.close.assert_called_once()
