"""Tests for the Becker import/export options flow."""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

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
from custom_components.becker.db_transfer import apply_units, dump_state_json, read_units
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


async def _open_import(hass: HomeAssistant, entry: MockConfigEntry, step: str) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_import_json_applies_and_backs_up(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    uploaded_file: Path,
    mock_process_uploaded_file: MagicMock,
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    uploaded_file.write_text(
        dump_state_json(
            [{"code": "1737b", "increment": 500, "configured": 1}],
            "2026-08-03T10:00:00",
        )
    )
    form = await _open_import(hass, entry, "import_json")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"upload": str(uuid4())}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "import_done"
    rows = {r["code"]: r for r in read_units(real_db)}
    assert rows["1737b"]["increment"] == 500
    backups = list(Path(hass.config.config_dir).glob("becker_db_backup_*.json"))
    assert len(backups) == 1


async def test_import_json_rejects_bad_json(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    uploaded_file: Path,
    mock_process_uploaded_file: MagicMock,
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    uploaded_file.write_text("definitely not json {{{")
    form = await _open_import(hass, entry, "import_json")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"upload": str(uuid4())}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_json"}


async def test_import_db_swaps_file_and_backs_up(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    tmp_path: Path,
    uploaded_file: Path,
    mock_process_uploaded_file: MagicMock,
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    # Build a valid replacement db with a distinct increment
    replacement = tmp_path / "replacement.db"
    Database(str(replacement)).conn.close()
    apply_units(str(replacement), [{"code": "1737b", "increment": 900, "configured": 1}])
    uploaded_file.write_bytes(replacement.read_bytes())

    form = await _open_import(hass, entry, "import_db")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"upload": str(uuid4())}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "import_done"
    rows = {r["code"]: r for r in read_units(real_db)}
    assert rows["1737b"]["increment"] == 900
    backups = list(Path(hass.config.config_dir).glob("becker_db_backup_*.db"))
    assert len(backups) == 1


async def test_import_db_rejects_non_sqlite(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    uploaded_file: Path,
    mock_process_uploaded_file: MagicMock,
) -> None:
    entry = await _setup(hass, real_db, mock_becker)
    uploaded_file.write_bytes(b"not a database")
    form = await _open_import(hass, entry, "import_db")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"upload": str(uuid4())}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_db"}
