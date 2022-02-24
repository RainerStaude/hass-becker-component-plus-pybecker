"""Handling of the Becker USB device."""

import logging
import os

import voluptuous as vol
from .pybecker.becker import Becker
from .pybecker.database import FILE_PATH, SQL_DB_FILE

from .const import CONF_CHANNEL, CONF_UNIT, DOMAIN, RECEIVE_MESSAGE

_LOGGER = logging.getLogger(__name__)

PAIR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHANNEL): vol.All(int, vol.Range(min=1, max=7)),
        vol.Optional(CONF_UNIT): vol.All(int, vol.Range(min=1, max=5)),
    }
)


class PyBecker:
    """Manages a (single, global) pybecker Becker instance."""

    becker = None

    @classmethod
    def setup(cls, hass, device=None, filename=None):
        """Initiate becker instance."""
        # Validate filename
        if filename is None:
            filename = SQL_DB_FILE
        if not os.path.isfile(filename):
            file = os.path.basename(filename)
            path = os.path.dirname(filename)
            if path == '':
                # file in HA config folder
                if os.path.isfile(os.path.join(hass.config.config_dir, file)):
                    filename = os.path.join(hass.config.config_dir, file)
                # file in pybecker folder
                elif os.path.isfile(os.path.join(FILE_PATH, file)):
                    # move file to config folder once
                    filename = os.path.join(hass.config.config_dir, file)
                    _LOGGER.debug("Move file to %s", filename)
                    os.rename(os.path.join(FILE_PATH, file), filename)
                else:
                    # create a new file in HA config folder
                    _LOGGER.warning("Filename %s does not exist. Create a new file.", file)
                    filename = os.path.join(hass.config.config_dir, file)
            else:
                assert os.path.exists(path), f"Path of filename {filename} invalid or does not exist!"
                # create a new file
                _LOGGER.warning("Filename %s does not exist. Create a new file.", filename)
        _LOGGER.debug("Use filename: %s", filename)
        # Setup callback function
        callback = lambda packet: cls.callback(hass, packet)
        # Setup Becker
        cls.becker = Becker(device_name=device, init_dummy=False, db_filename=filename, callback=callback)

    @classmethod
    async def async_register_services(cls, hass):
        """Register component services."""

        hass.services.async_register(DOMAIN, "pair", cls.handle_pair, PAIR_SCHEMA)
        hass.services.async_register(DOMAIN, "log_units", cls.handle_log_units)

    @classmethod
    async def handle_pair(cls, call):
        """Service to pair with a cover receiver."""

        channel = call.data.get(CONF_CHANNEL)
        unit = call.data.get(CONF_UNIT, 1)
        await cls.becker.pair(f"{unit}:{channel}")

    @classmethod
    async def handle_log_units(cls, call):
        """Service that logs all paired units."""
        units = await cls.becker.list_units()

        # Apparently the SQLite results are implicitly returned in unit id
        # order. This seems pretty dirty to rely on.
        unit_id = 1
        _LOGGER.info("Configured Becker centronic units:")
        for row in units:
            unit_code, increment = row[0:2]
            _LOGGER.info(
                "Unit id %d, unit code %s, increment %d", unit_id, unit_code, increment
            )
            unit_id += 1

    @staticmethod
    def callback(hass, packet):
        """Handle Becker device callback for received packets."""
        _LOGGER.debug("Received packet for dispatcher")
        hass.helpers.dispatcher.dispatcher_send(f"{DOMAIN}.{RECEIVE_MESSAGE}", packet)
