"""The becker component."""
import logging

from .rf_device import PyBecker

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass, config):
    """Initiate becker component for home assistant."""

    # Register this component's services
    await PyBecker.async_register_services(hass)

    return True
