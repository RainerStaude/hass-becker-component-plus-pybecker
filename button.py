"""Button platform for the Becker integration."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_FRIENDLY_NAME, EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_CHANNEL, DOMAIN, MANUFACTURER, SUBENTRY_TYPE_COVER


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up a pair button for each configured cover."""
    becker = entry.runtime_data
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_COVER:
            continue
        channel = subentry.data[CONF_CHANNEL]
        name = subentry.data.get(CONF_FRIENDLY_NAME) or f"Channel {channel}"
        async_add_entities(
            [BeckerPairButton(becker, entry.entry_id, channel, name)],
            config_subentry_id=subentry_id,
        )


class BeckerPairButton(ButtonEntity):
    """Button that teaches a shutter receiver this stick's channel."""

    _attr_has_entity_name = True
    _attr_translation_key = "pair"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, becker, entry_id, channel, name):
        """Init the pair button."""
        self._becker = becker
        self._channel = channel
        self._attr_unique_id = f"{channel}_pair"
        # Share the cover's device so the button shows up on the cover. The
        # name is set here too because platforms set up concurrently and the
        # button may register before the cover names the device.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{channel}")},
            name=name,
            manufacturer=MANUFACTURER,
            via_device=(DOMAIN, entry_id),
        )

    async def async_press(self):
        """Send the pairing (TRAIN) signal on the cover's channel."""
        await self._becker.pair(self._channel)
