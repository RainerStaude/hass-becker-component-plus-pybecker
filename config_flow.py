"""Config flow for the Becker integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
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
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SerialPortSelector,
    TemplateSelector,
    TextSelector,
)

from .const import (
    CHANNEL_PATTERN,
    CONF_CHANNEL,
    CONF_CONNECTION_TYPE,
    CONF_COVERS,
    CONF_INTERMEDIATE_DISABLE,
    CONF_INTERMEDIATE_POSITION,
    CONF_INTERMEDIATE_POSITION_DOWN,
    CONF_INTERMEDIATE_POSITION_UP,
    CONF_REMOTE_ID,
    CONF_TILT_BLIND,
    CONF_TILT_INTERMEDIATE,
    CONF_TILT_TIME_BLIND,
    CONF_TRAVELLING_TIME_DOWN,
    CONF_TRAVELLING_TIME_UP,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_DB_FILENAME,
    DEFAULT_DEVICE,
    DEFAULT_TCP_PORT,
    DOMAIN,
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
                return self.async_create_entry(
                    title=user_input.get(CONF_FRIENDLY_NAME)
                    or f"Channel {channel}",
                    data=user_input,
                    unique_id=channel,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                COVER_ADD_SCHEMA, user_input
            ),
            errors=errors,
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
