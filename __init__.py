"""The becker component."""

import codecs
from functools import partial
import logging
import os

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_FILENAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.typing import ConfigType

from .const import (
    COMMANDS,
    CONF_CHANNEL,
    CONF_UNIT,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
    RECEIVE_MESSAGE,
    REMOTE_PACKET_EVENT,
    SUBENTRY_TYPE_COVER,
)
from .pybecker.becker import Becker
from .pybecker.becker_helper import BeckerConnectionError
from .pybecker.database import FILE_PATH, SQL_DB_FILE

_LOGGER = logging.getLogger(__name__)

type BeckerConfigEntry = ConfigEntry[Becker]

PAIR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHANNEL): vol.All(int, vol.Range(min=1, max=7)),
        vol.Optional(CONF_UNIT): vol.All(int, vol.Range(min=1, max=5)),
    }
)


def signal_for_entry(entry_id: str) -> str:
    """Return the dispatcher signal carrying received packets of one stick."""
    return f"{DOMAIN}_{RECEIVE_MESSAGE}_{entry_id}"


def _resolve_db_path(config_dir: str, filename: str | None) -> str:
    """Resolve the sqlite database path (blocking, run in executor)."""
    if filename is None:
        filename = SQL_DB_FILE
    if os.path.isfile(filename):
        return filename
    file = os.path.basename(filename)
    path = os.path.dirname(filename)
    if path == "":
        # file in HA config folder
        if os.path.isfile(os.path.join(config_dir, file)):
            return os.path.join(config_dir, file)
        # file in pybecker folder (legacy location, move it once)
        if os.path.isfile(os.path.join(FILE_PATH, file)):
            filename = os.path.join(config_dir, file)
            _LOGGER.debug("Move database file to %s", filename)
            os.rename(os.path.join(FILE_PATH, file), filename)
            return filename
        # create a new file in HA config folder
        _LOGGER.warning("Database file %s does not exist. Creating a new file", file)
        return os.path.join(config_dir, file)
    assert os.path.exists(path), f"Path of filename {filename} invalid or does not exist!"
    _LOGGER.warning("Database file %s does not exist. Creating a new file", filename)
    return filename


def _packet_callback(hass: HomeAssistant, entry_id: str, packet) -> None:
    """Forward a received RF packet (runs in the communicator thread)."""
    _LOGGER.debug("Received packet for dispatcher")
    dispatcher_send(hass, signal_for_entry(entry_id), packet)

    # Also fire an explicit event that external applications can listen to
    # if that is of use to them.
    data = {
        "unit": codecs.decode(packet.group("unit_id"), "ascii"),
        "channel": codecs.decode(packet.group("channel"), "ascii"),
    }
    command = packet.group("command") + b"0"
    command_name = [nm for nm, cmd in COMMANDS.items() if cmd == command]
    if command_name:
        data["command"] = command_name[0]
    hass.bus.fire(f"{DOMAIN}_{REMOTE_PACKET_EVENT}", data)


def _get_becker(hass: HomeAssistant) -> Becker:
    """Return the Becker instance of the loaded config entry."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("No loaded Becker configuration entry found")
    if len(entries) > 1:
        _LOGGER.warning(
            "Multiple Becker entries are configured. The service uses the first one"
        )
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the becker services."""

    async def handle_pair(call: ServiceCall) -> None:
        """Pair with a cover receiver."""
        channel = call.data[CONF_CHANNEL]
        unit = call.data.get(CONF_UNIT, 1)
        await _get_becker(hass).pair(f"{unit}:{channel}")

    async def handle_log_units(call: ServiceCall) -> None:
        """Log all paired units."""
        units = await _get_becker(hass).list_units()
        # Apparently the SQLite results are implicitly returned in unit id
        # order. This seems pretty dirty to rely on.
        _LOGGER.info("Configured Becker centronic units:")
        for unit_id, row in enumerate(units, start=1):
            unit_code, increment = row[0:2]
            _LOGGER.info(
                "Unit id %d, unit code %s, increment %d", unit_id, unit_code, increment
            )

    hass.services.async_register(DOMAIN, "pair", handle_pair, PAIR_SCHEMA)
    hass.services.async_register(DOMAIN, "log_units", handle_log_units)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BeckerConfigEntry) -> bool:
    """Set up a Becker Centronic stick from a config entry."""
    filename = await hass.async_add_executor_job(
        _resolve_db_path, hass.config.config_dir, entry.data.get(CONF_FILENAME)
    )
    _LOGGER.debug("Using database file %s", filename)

    try:
        becker = await hass.async_add_executor_job(
            partial(
                Becker,
                device_name=entry.data[CONF_DEVICE],
                init_dummy=False,
                db_filename=filename,
                callback=partial(_packet_callback, hass, entry.entry_id),
            )
        )
    except BeckerConnectionError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to Becker stick on {entry.data[CONF_DEVICE]}: {err}"
        ) from err
    entry.runtime_data = becker

    # Initialize all units of configured covers in the db file and send a
    # stop command for sync. Sequential on purpose: RF commands must not
    # overlap and pybecker paces them with sleeps.
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_COVER:
            continue
        await becker.init_unconfigured_unit(
            subentry.data[CONF_CHANNEL], name=subentry.title
        )

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        name="Centronic stick",
        model="Centronic USB stick",
    )

    entry.async_on_unload(entry.add_update_listener(_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BeckerConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Stops the communicator thread (blocking join) and closes the db
        await hass.async_add_executor_job(entry.runtime_data.close)
    return unload_ok


async def _update_listener(hass: HomeAssistant, entry: BeckerConfigEntry) -> None:
    """Reload the entry when subentries change."""
    hass.config_entries.async_schedule_reload(entry.entry_id)
