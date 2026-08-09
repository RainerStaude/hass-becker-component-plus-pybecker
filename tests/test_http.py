"""Tests for the Becker database download view."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import ClientSession
import pytest

from homeassistant.const import CONF_DEVICE, CONF_FILENAME
from homeassistant.core import HomeAssistant

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
    """Create a real sqlite db file with a known increment."""
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


async def test_download_json(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    hass_client: Callable[[], Awaitable[ClientSession]],
) -> None:
    """The json download returns the current state as an attachment."""
    entry = await _setup(hass, real_db, mock_becker)
    client = await hass_client()

    resp = await client.get(f"/api/becker/download/{entry.entry_id}/json")

    assert resp.status == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    body = await resp.json()
    assert body["version"] == 1
    unit = next(u for u in body["units"] if u["code"] == "1737b")
    assert unit["increment"] == 77


async def test_download_db(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    hass_client: Callable[[], Awaitable[ClientSession]],
) -> None:
    """The db download returns a binary sqlite attachment."""
    entry = await _setup(hass, real_db, mock_becker)
    client = await hass_client()

    resp = await client.get(f"/api/becker/download/{entry.entry_id}/db")

    assert resp.status == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    assert (await resp.read())[:16].startswith(b"SQLite format 3")


async def test_download_unknown_entry(
    hass: HomeAssistant,
    mock_becker,
    real_db: str,
    hass_client: Callable[[], Awaitable[ClientSession]],
) -> None:
    """An unknown entry id returns 404."""
    await _setup(hass, real_db, mock_becker)
    client = await hass_client()

    resp = await client.get("/api/becker/download/does-not-exist/json")

    assert resp.status == 404
