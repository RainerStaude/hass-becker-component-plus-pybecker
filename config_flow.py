"""Config flow for the Becker integration."""

from datetime import timedelta
import logging
import shutil
from typing import Any

import voluptuous as vol

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_DEVICE,
    CONF_FILENAME,
    CONF_FRIENDLY_NAME,
    CONF_HOST,
    CONF_PORT,
    CONF_VALUE_TEMPLATE,
)
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, callback
from homeassistant.helpers.issue_registry import IssueSeverity, async_create_issue
from homeassistant.helpers.selector import (
    BooleanSelector,
    FileSelector,
    FileSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SerialPortSelector,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .const import (
    BACKUP_PREFIX,
    CHANNEL_PATTERN,
    CONF_CHANNEL,
    CONF_CONNECTION_TYPE,
    CONF_COVERS,
    CONF_INTERMEDIATE_DISABLE,
    CONF_INTERMEDIATE_POSITION,
    CONF_INTERMEDIATE_POSITION_DOWN,
    CONF_INTERMEDIATE_POSITION_UP,
    CONF_PAIR,
    CONF_REMOTE_ID,
    CONF_STATE_TEXT,
    CONF_TILT_BLIND,
    CONF_TILT_INTERMEDIATE,
    CONF_TILT_TIME_BLIND,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    CONF_UPLOAD,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_DB_FILENAME,
    DEFAULT_DEVICE,
    DEFAULT_TCP_PORT,
    DOMAIN,
    DOWNLOAD_LINK_TTL_MINUTES,
    DOWNLOAD_URL,
    INTERMEDIATE_POSITION,
    REMOTE_ID,
    SUBENTRY_TYPE_COVER,
    TILT_TIME,
    VENTILATION_POSITION,
)
from .pybecker.becker_helper import BeckerConnection, BeckerConnectionError

_LOGGER = logging.getLogger(__name__)

COVER_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FRIENDLY_NAME): TextSelector(),
        vol.Optional(CONF_VALUE_TEMPLATE): TemplateSelector(),
        vol.Optional(CONF_REMOTE_ID): TextSelector(),
        vol.Optional(CONF_TRAVELLING_TIME_DOWN): NumberSelector(
            NumberSelectorConfig(
                min=0, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
            )
        ),
        vol.Optional(CONF_TRAVELLING_TIME_UP): NumberSelector(
            NumberSelectorConfig(
                min=0, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
            )
        ),
        vol.Optional(CONF_INTERMEDIATE_POSITION, default=True): BooleanSelector(),
        vol.Optional(
            CONF_INTERMEDIATE_POSITION_UP, default=VENTILATION_POSITION
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=100, mode=NumberSelectorMode.BOX, unit_of_measurement="%"
            )
        ),
        vol.Optional(
            CONF_INTERMEDIATE_POSITION_DOWN, default=INTERMEDIATE_POSITION
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=100, mode=NumberSelectorMode.BOX, unit_of_measurement="%"
            )
        ),
        vol.Optional(CONF_TILT_INTERMEDIATE): BooleanSelector(),
        vol.Optional(CONF_TILT_BLIND, default=False): BooleanSelector(),
        vol.Optional(CONF_TILT_TIME_BLIND, default=TILT_TIME): NumberSelector(
            NumberSelectorConfig(
                min=0, step=0.1, mode=NumberSelectorMode.BOX, unit_of_measurement="s"
            )
        ),
    }
)

COVER_ADD_SCHEMA = vol.Schema(
    {vol.Required(CONF_CHANNEL): TextSelector()}
).extend(COVER_OPTIONS_SCHEMA.schema)

PAIR_SCHEMA = vol.Schema(
    {vol.Required(CONF_PAIR, default=True): BooleanSelector()}
)


def _test_connection(device: str) -> None:
    """Open and close the connection to validate the device (blocking)."""
    BeckerConnection(device).close()


def _validate_cover_input(
    user_input: dict[str, Any], require_channel: bool
) -> dict[str, str]:
    """Validate cover subentry user input."""
    errors: dict[str, str] = {}
    if require_channel and not CHANNEL_PATTERN.match(user_input[CONF_CHANNEL]):
        errors[CONF_CHANNEL] = "invalid_channel"
    remote_id = user_input.get(CONF_REMOTE_ID)
    if remote_id and not REMOTE_ID.search(remote_id.upper()):
        errors[CONF_REMOTE_ID] = "invalid_remote_id"
    return errors


def _import_cover_data(slug: str, cover_config: dict[str, Any]) -> dict[str, Any]:
    """Map a validated YAML cover config onto subentry data."""
    data: dict[str, Any] = {CONF_CHANNEL: cover_config[CONF_CHANNEL]}
    for key in (
        CONF_FRIENDLY_NAME,
        CONF_REMOTE_ID,
        CONF_TRAVELLING_TIME_DOWN,
        CONF_TRAVELLING_TIME_UP,
        CONF_INTERMEDIATE_POSITION_UP,
        CONF_INTERMEDIATE_POSITION_DOWN,
        CONF_TILT_INTERMEDIATE,
        CONF_TILT_BLIND,
        CONF_TILT_TIME_BLIND,
    ):
        if key in cover_config:
            data[key] = cover_config[key]
    data.setdefault(CONF_FRIENDLY_NAME, slug)
    # Templates are not JSON serializable - store the template string
    if (template := cover_config.get(CONF_VALUE_TEMPLATE)) is not None:
        data[CONF_VALUE_TEMPLATE] = template.template
    # Collapse the deprecated intermediate_position_disable key
    intermediate_disable = cover_config.get(CONF_INTERMEDIATE_DISABLE, False)
    data[CONF_INTERMEDIATE_POSITION] = (
        cover_config.get(CONF_INTERMEDIATE_POSITION, True) and not intermediate_disable
    )
    return data


class BeckerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Becker Centronic stick."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_COVER: CoverSubentryFlowHandler}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the import/export options flow."""
        return BeckerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the connection type."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[CONNECTION_TYPE_SERIAL, CONNECTION_TYPE_NETWORK],
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a locally connected Centronic stick."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device = user_input[CONF_DEVICE]
            await self.async_set_unique_id(device)
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(_test_connection, device)
            except BeckerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Becker ({device.rsplit('/', 1)[-1]})",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                        CONF_DEVICE: device,
                        CONF_FILENAME: user_input.get(
                            CONF_FILENAME, DEFAULT_DB_FILENAME
                        ),
                    },
                )

        schema = vol.Schema(
            {vol.Required(CONF_DEVICE, default=DEFAULT_DEVICE): SerialPortSelector()}
        )
        if self.show_advanced_options:
            schema = schema.extend(
                {
                    vol.Optional(
                        CONF_FILENAME, default=DEFAULT_DB_FILENAME
                    ): TextSelector()
                }
            )
        return self.async_show_form(
            step_id=CONNECTION_TYPE_SERIAL, data_schema=schema, errors=errors
        )

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a stick reachable through a serial-to-TCP bridge."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            # pybecker resolves "host:port" to socket://host:port itself
            device = f"{host}:{port}"
            await self.async_set_unique_id(f"socket://{device}")
            self._abort_if_unique_id_configured()
            try:
                await self.hass.async_add_executor_job(_test_connection, device)
            except BeckerConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Becker ({device})",
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
                        CONF_DEVICE: device,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_FILENAME: user_input.get(
                            CONF_FILENAME, DEFAULT_DB_FILENAME
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): TextSelector(),
                vol.Required(CONF_PORT, default=DEFAULT_TCP_PORT): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=65535, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Coerce(int),
                ),
            }
        )
        if self.show_advanced_options:
            schema = schema.extend(
                {
                    vol.Optional(
                        CONF_FILENAME, default=DEFAULT_DB_FILENAME
                    ): TextSelector()
                }
            )
        return self.async_show_form(
            step_id=CONNECTION_TYPE_NETWORK, data_schema=schema, errors=errors
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import the YAML cover platform configuration."""
        async_create_issue(
            self.hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            breaks_in_ha_version="2026.12.0",
            is_fixable=False,
            issue_domain=DOMAIN,
            severity=IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={
                "domain": DOMAIN,
                "integration_title": "Becker",
            },
        )

        device = import_data.get(CONF_DEVICE) or DEFAULT_DEVICE
        # Mirror pybecker's device detection to derive the connection type
        if "/" in device or device.upper().startswith("COM"):
            connection_type = CONNECTION_TYPE_SERIAL
            unique_id = device
            data: dict[str, Any] = {
                CONF_CONNECTION_TYPE: connection_type,
                CONF_DEVICE: device,
            }
        else:
            connection_type = CONNECTION_TYPE_NETWORK
            host, _, port = device.partition(":")
            port_number = int(port) if port else DEFAULT_TCP_PORT
            device = f"{host}:{port_number}"
            unique_id = f"socket://{device}"
            data = {
                CONF_CONNECTION_TYPE: connection_type,
                CONF_DEVICE: device,
                CONF_HOST: host,
                CONF_PORT: port_number,
            }
        data[CONF_FILENAME] = import_data.get(CONF_FILENAME) or DEFAULT_DB_FILENAME

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        # Connection is intentionally not tested here: if the stick is
        # offline during a restart, entry setup retries via
        # ConfigEntryNotReady instead of dropping the YAML covers.
        subentries = []
        for slug, cover_config in import_data[CONF_COVERS].items():
            cover_data = _import_cover_data(slug, cover_config)
            subentries.append(
                {
                    "subentry_type": SUBENTRY_TYPE_COVER,
                    "data": cover_data,
                    "title": cover_data[CONF_FRIENDLY_NAME],
                    "unique_id": cover_data[CONF_CHANNEL],
                }
            )

        return self.async_create_entry(
            title="Becker", data=data, subentries=subentries
        )


class CoverSubentryFlowHandler(ConfigSubentryFlow):
    """Handle adding and reconfiguring covers."""

    def __init__(self) -> None:
        """Init the cover subentry flow."""
        self._cover_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new cover."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_cover_input(user_input, require_channel=True)
            channel = user_input[CONF_CHANNEL]
            if not errors:
                for subentry in self._get_entry().subentries.values():
                    if subentry.unique_id == channel:
                        errors[CONF_CHANNEL] = "already_configured"
                        break
            if not errors:
                self._cover_input = user_input
                return await self.async_step_pair()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                COVER_ADD_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Optionally pair the receiver before creating the cover."""
        channel = self._cover_input[CONF_CHANNEL]

        if user_input is not None:
            entry = self._get_entry()
            if user_input[CONF_PAIR] and entry.state is ConfigEntryState.LOADED:
                await entry.runtime_data.pair(channel)
            return self.async_create_entry(
                title=self._cover_input.get(CONF_FRIENDLY_NAME)
                or f"Channel {channel}",
                data=self._cover_input,
                unique_id=channel,
            )

        return self.async_show_form(
            step_id="pair",
            data_schema=PAIR_SCHEMA,
            description_placeholders={CONF_CHANNEL: channel},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an existing cover. The channel is immutable."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_cover_input(user_input, require_channel=False)
            if not errors:
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=user_input.get(CONF_FRIENDLY_NAME) or subentry.title,
                    data_updates={
                        **user_input,
                        CONF_CHANNEL: subentry.data[CONF_CHANNEL],
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                COVER_OPTIONS_SCHEMA, user_input or subentry.data
            ),
            description_placeholders={CONF_CHANNEL: subentry.data[CONF_CHANNEL]},
            errors=errors,
        )


class BeckerOptionsFlow(OptionsFlow):
    """Import and export the shutter database from the UI."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the import/export menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["export_json", "import_json", "export_db", "import_db"],
        )

    def _download_url(self, fmt: str) -> str:
        """Build a short-lived signed download URL for the given format."""
        path = DOWNLOAD_URL.format(entry_id=self.config_entry.entry_id, fmt=fmt)
        return async_sign_path(
            self.hass, path, timedelta(minutes=DOWNLOAD_LINK_TTL_MINUTES)
        )

    async def _db_path(self) -> str:
        """Resolve the database file path for this entry."""
        from . import _resolve_db_path

        return await self.hass.async_add_executor_job(
            _resolve_db_path,
            self.hass.config.config_dir,
            self.config_entry.data.get(CONF_FILENAME),
        )

    async def async_step_export_json(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the JSON state as a download link and inline copy."""
        if user_input is not None:
            return self.async_abort(reason="export_done")

        from .db_transfer import dump_state_json, read_units

        db_path = await self._db_path()
        units = await self.hass.async_add_executor_job(read_units, db_path)
        inline = dump_state_json(units, dt_util.now().isoformat())
        return self.async_show_form(
            step_id="export_json",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_STATE_TEXT, default=inline): TextSelector(
                        TextSelectorConfig(
                            multiline=True, type=TextSelectorType.TEXT
                        )
                    )
                }
            ),
            description_placeholders={"download_url": self._download_url("json")},
        )

    async def async_step_export_db(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the raw .db file as a download link."""
        if user_input is not None:
            return self.async_abort(reason="export_done")
        return self.async_show_form(
            step_id="export_db",
            data_schema=vol.Schema({}),
            description_placeholders={"download_url": self._download_url("db")},
        )

    def _backup_path(self, suffix: str) -> str:
        """Return a timestamped backup file path in the config directory."""
        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
        return self.hass.config.path(f"{BACKUP_PREFIX}{stamp}{suffix}")

    async def async_step_import_json(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Upload and apply a JSON state export."""
        from .db_transfer import (
            StateFormatError,
            StateJSONError,
            apply_units,
            dump_state_json,
            parse_state_json,
            read_units,
        )

        errors: dict[str, str] = {}
        if user_input is not None:
            with process_uploaded_file(self.hass, user_input[CONF_UPLOAD]) as path:
                raw = await self.hass.async_add_executor_job(path.read_bytes)
            try:
                rows = parse_state_json(raw)
            except StateJSONError:
                errors["base"] = "invalid_json"
            except StateFormatError:
                errors["base"] = "invalid_format"
            if not errors:
                db_path = await self._db_path()
                current = await self.hass.async_add_executor_job(read_units, db_path)
                backup = self._backup_path(".json")
                await self.hass.async_add_executor_job(
                    _write_text, backup, dump_state_json(current, dt_util.now().isoformat())
                )
                await self.hass.async_add_executor_job(apply_units, db_path, rows)
                return self.async_abort(reason="import_done")

        return self.async_show_form(
            step_id="import_json",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPLOAD): FileSelector(
                        FileSelectorConfig(accept=".json,application/json")
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_import_db(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Upload and swap in a raw .db file."""
        from pathlib import Path

        from .db_transfer import consistent_copy, is_valid_becker_db

        errors: dict[str, str] = {}
        if user_input is not None:
            with process_uploaded_file(self.hass, user_input[CONF_UPLOAD]) as path:
                valid = await self.hass.async_add_executor_job(
                    is_valid_becker_db, path
                )
                if not valid:
                    errors["base"] = "invalid_db"
                else:
                    db_path = await self._db_path()
                    backup = self._backup_path(".db")
                    await self.hass.async_add_executor_job(
                        _swap_db, Path(db_path), path, Path(backup)
                    )
            if not errors:
                self.hass.config_entries.async_schedule_reload(
                    self.config_entry.entry_id
                )
                return self.async_abort(reason="import_done")

        return self.async_show_form(
            step_id="import_db",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPLOAD): FileSelector(
                        FileSelectorConfig(accept=".db,application/octet-stream")
                    )
                }
            ),
            errors=errors,
        )


def _write_text(path: str, text: str) -> None:
    """Write text to a file (blocking, run in executor)."""
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def _swap_db(db_path, uploaded, backup) -> None:
    """Back up the current db, then copy the uploaded db over it."""
    if db_path.exists():
        shutil.copy2(db_path, backup)
    shutil.copy2(uploaded, db_path)
