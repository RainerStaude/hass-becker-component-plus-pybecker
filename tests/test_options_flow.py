"""Tests for the Becker import/export options flow."""

from pathlib import Path

import pytest

from homeassistant.const import CONF_DEVICE, CONF_FILENAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.becker.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SERIAL,
    DOMAIN,
)
from custom_components.becker.db_transfer import apply_units
from custom_components.becker.pybecker.database import Database


@pytest.fixture
def real_db(tmp_path: Path) -> str:
    path = str(tmp_path / "centronic-stick.db")
    Database(path).conn.close()
    apply_units(path, [{"code": "1737b", "increment": 77, "configured": 1}])
    return path


async def _setup(hass: HomeAssistant, db_path: str, mock_becker) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_DEVICE: "/dev/ttyUSB0",
            CONF_FILENAME: db_path,
        },
        unique_id="/dev/ttyUSB0",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_menu_lists_actions(
    hass: HomeAssistant, mock_becker, real_db: str
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {
        "export_json",
        "import_json",
        "export_db",
        "import_db",
    }


async def test_export_json_offers_download_link(
    hass: HomeAssistant, mock_becker, real_db: str
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "export_json"}
    )
    assert result["type"] is FlowResultType.FORM
    url = result["description_placeholders"]["download_url"]
    assert f"/api/becker/download/{entry.entry_id}/json" in url
    # submitting closes the flow without changing anything
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "export_done"


async def test_export_db_offers_download_link(
    hass: HomeAssistant, mock_becker, real_db: str
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "export_db"}
    )
    assert result["type"] is FlowResultType.FORM
    assert (
        f"/api/becker/download/{entry.entry_id}/db"
        in result["description_placeholders"]["download_url"]
    )
