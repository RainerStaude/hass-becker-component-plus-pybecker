"""Tests for the becker cover entity."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    DOMAIN as COVER_DOMAIN,
    SERVICE_OPEN_COVER,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

ENTITY_ID = "cover.kitchen"


async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Set up the becker integration."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_becker")
async def test_position_updates_during_travel(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_config_entry_with_timed_cover: MockConfigEntry,
) -> None:
    """The reported position changes during travel, not only at the end."""
    await setup_integration(hass, mock_config_entry_with_timed_cover)

    # Cover starts closed (0 %).
    assert hass.states.get(ENTITY_ID).attributes[ATTR_CURRENT_POSITION] == 0

    await hass.services.async_call(
        COVER_DOMAIN,
        SERVICE_OPEN_COVER,
        {ATTR_ENTITY_ID: ENTITY_ID},
        blocking=True,
    )

    positions = []
    for _ in range(5):
        freezer.tick(timedelta(seconds=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        positions.append(hass.states.get(ENTITY_ID).attributes[ATTR_CURRENT_POSITION])

    # Over a 10 s travel, each 1 s tick should report a higher position.
    assert positions == [10, 20, 30, 40, 50]
