"""Config flow for appliances behind a GTW-08 Modbus gateway."""

from collections.abc import Mapping
from typing import Any, override

from gtw08_modbus import Gtw08Appliance, NoApplianceError
from modbus_connection import ModbusError, ModbusSerialParams, ModbusTcpParams
import probatio

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.data_entry_flow import AbortFlow, section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)

from .const import (
    BAUDRATES,
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_UNIT_ID,
    DEFAULT_BAUDRATE,
    DEFAULT_NAME,
    DEFAULT_PARITY,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    PARITIES,
    TYPE_RTU_OVER_TCP,
    TYPE_SERIAL,
    TYPE_TCP,
)

SECTION_MORE_OPTIONS = "more_options"

# The rotary dial on the gateway sets the unit ID. It is rarely moved off 0.
MORE_OPTIONS = {
    probatio.Required(SECTION_MORE_OPTIONS): section(
        probatio.Schema(
            {
                probatio.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): probatio.All(
                    NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=247, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    probatio.Coerce(int),
                ),
            }
        ),
        {"collapsed": True},
    )
}

LINE_SETTINGS = {
    probatio.Required(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): SelectSelector(
        SelectSelectorConfig(
            options=[str(baudrate) for baudrate in BAUDRATES],
            mode=SelectSelectorMode.DROPDOWN,
        )
    ),
    probatio.Required(CONF_PARITY, default=DEFAULT_PARITY): SelectSelector(
        SelectSelectorConfig(
            options=list(PARITIES),
            mode=SelectSelectorMode.DROPDOWN,
            translation_key=CONF_PARITY,
        )
    ),
}

HOST_AND_PORT = {
    probatio.Required(CONF_HOST): TextSelector(),
    probatio.Required(CONF_PORT, default=DEFAULT_PORT): probatio.All(
        NumberSelector(
            NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
        ),
        probatio.Coerce(int),
    ),
}

SCHEMAS = {
    TYPE_SERIAL: probatio.Schema(
        {
            probatio.Required(CONF_DEVICE): SerialPortSelector(),
            **LINE_SETTINGS,
            **MORE_OPTIONS,
        }
    ),
    TYPE_TCP: probatio.Schema({**HOST_AND_PORT, **MORE_OPTIONS}),
    TYPE_RTU_OVER_TCP: probatio.Schema(
        {**HOST_AND_PORT, **LINE_SETTINGS, **MORE_OPTIONS}
    ),
}


def create_modbus_params(
    data: Mapping[str, Any],
) -> ModbusSerialParams | ModbusTcpParams:
    """Build the Modbus link parameters from config entry data.

    A transparent RS-485 to Ethernet converter passes RTU frames through.
    That makes it a serial port reached over a socket.
    """
    if data[CONF_TYPE] == TYPE_TCP:
        return ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])
    device = (
        data[CONF_DEVICE]
        if data[CONF_TYPE] == TYPE_SERIAL
        else f"socket://{data[CONF_HOST]}:{data[CONF_PORT]}"
    )
    return ModbusSerialParams(
        device=device,
        baudrate=data[CONF_BAUDRATE],
        parity=PARITIES[data[CONF_PARITY]],
    )


def _flatten(connection_type: str, user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the sectioned form input into config entry data."""
    data = {CONF_TYPE: connection_type, **user_input}
    data[CONF_UNIT_ID] = data.pop(SECTION_MORE_OPTIONS)[CONF_UNIT_ID]
    if CONF_BAUDRATE in data:
        data[CONF_BAUDRATE] = int(data[CONF_BAUDRATE])
    if CONF_HOST in data:
        # Lower-case the host because one connection is shared per host and port
        data[CONF_HOST] = data[CONF_HOST].lower()
    return data


def _sectioned(data: Mapping[str, Any]) -> dict[str, Any]:
    """Shape config entry data back into the sectioned form input."""
    form = {
        key: value
        for key, value in data.items()
        if key not in (CONF_TYPE, CONF_UNIT_ID)
    }
    if CONF_BAUDRATE in form:
        form[CONF_BAUDRATE] = str(form[CONF_BAUDRATE])
    form[SECTION_MORE_OPTIONS] = {CONF_UNIT_ID: data[CONF_UNIT_ID]}
    return form


def _link(data: Mapping[str, Any]) -> tuple[Any, ...]:
    """What tells two entries apart when neither has a serial number."""
    return (*create_modbus_params(data).endpoint, data[CONF_UNIT_ID])


def _title(appliance: Gtw08Appliance) -> str:
    """Name the entry after the appliance's main control board."""
    if appliance.model is None:
        return DEFAULT_NAME
    return f"{DEFAULT_NAME} {appliance.model}"


class Gtw08ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a GTW-08 config flow."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how the gateway is reached."""
        return self.async_show_menu(
            step_id="user", menu_options=[TYPE_SERIAL, TYPE_TCP, TYPE_RTU_OVER_TCP]
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway wired to a serial port on this machine."""
        return await self._async_step_link(TYPE_SERIAL, user_input)

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway behind a converter that speaks Modbus TCP."""
        return await self._async_step_link(TYPE_TCP, user_input)

    async def async_step_rtu_over_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a gateway behind a converter that passes RTU frames through."""
        return await self._async_step_link(TYPE_RTU_OVER_TCP, user_input)

    async def _async_step_link(
        self, connection_type: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Ask for the link settings, then probe the appliance behind them."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            data = _flatten(connection_type, user_input)
            appliance, errors, placeholders = await self._async_validate(data)
            if appliance is not None:
                if appliance.serial_number is not None:
                    await self.async_set_unique_id(str(appliance.serial_number))
                    self._abort_if_unique_id_configured()
                self._abort_if_link_configured(data)
                return self.async_create_entry(title=_title(appliance), data=data)

        return self.async_show_form(
            step_id=connection_type,
            data_schema=self.add_suggested_values_to_schema(
                SCHEMAS[connection_type], user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _abort_if_link_configured(self, data: Mapping[str, Any]) -> None:
        """Abort when an entry already reaches the same gateway and unit."""
        for entry in self._async_current_entries(include_ignore=False):
            if _link(entry.data) == _link(data):
                raise AbortFlow("already_configured")

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a change of how the gateway is reached."""
        entry = self._get_reconfigure_entry()
        connection_type = entry.data[CONF_TYPE]
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            data = _flatten(connection_type, user_input)
            # Release the entry's hold on the old link first, because the
            # shared connection refuses other settings for the same endpoint.
            relinking = False
            if _needs_relink(entry, data):
                relinking = await self.hass.config_entries.async_unload(entry.entry_id)

            appliance, errors, placeholders = await self._async_validate(data)
            probed = (
                None
                if appliance is None or appliance.serial_number is None
                else str(appliance.serial_number)
            )
            same_appliance = appliance is not None and probed == entry.unique_id

            if relinking and not same_appliance:
                await self.hass.config_entries.async_setup(entry.entry_id)

            if appliance is not None:
                if not same_appliance:
                    return self.async_abort(reason="unique_id_mismatch")
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMAS[connection_type], user_input or _sectioned(entry.data)
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_validate(
        self, data: Mapping[str, Any]
    ) -> tuple[Gtw08Appliance | None, dict[str, str], dict[str, str]]:
        """Probe the appliance, returning it or the errors to show instead."""
        try:
            async with async_get_temporary_unit(
                self.hass, create_modbus_params(data), data[CONF_UNIT_ID]
            ) as unit:
                appliance = await Gtw08Appliance.async_detect(unit)
        except NoApplianceError:
            return None, {"base": "no_appliance"}, {}
        except (ModbusError, HomeAssistantError) as err:
            return None, {"base": "cannot_connect"}, {"error": str(err)}
        return appliance, {}, {}


def _needs_relink(entry: ConfigEntry, data: Mapping[str, Any]) -> bool:
    """Whether probing these settings clashes with the connection the entry holds.

    An entry waiting to retry counts as holding it, because the retry would
    set it up on the old settings while the probe runs on the new ones.
    """
    if entry.state not in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_RETRY):
        return False
    current = create_modbus_params(entry.data)
    new = create_modbus_params(data)
    return new.endpoint == current.endpoint and new != current
