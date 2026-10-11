"""Actions for the GTW-08 integration."""

from gtw08_modbus import (
    Gtw08Error,
    InvalidValueError,
    RemoteControlMode,
    RemoteHeatDemand,
    SystemControl,
)
from modbus_connection import ModbusError
import probatio

from homeassistant.const import ATTR_CONFIG_ENTRY_ID, ATTR_MODE, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import (
    async_get_config_entry,
    async_register_admin_service,
)

from .const import DOMAIN
from .coordinator import Gtw08ConfigEntry

SERVICE_REQUEST_HEAT_DEMAND = "request_heat_demand"
SERVICE_STOP_REMOTE_CONTROL = "stop_remote_control"

ATTR_HEAT_DEMAND = "heat_demand"
ATTR_POWER = "power"

MODES = {
    "power": RemoteControlMode.POWER,
    "temperature": RemoteControlMode.TEMPERATURE,
    "temperature_and_power": RemoteControlMode.TEMPERATURE_AND_POWER,
}
HEAT_DEMANDS = {
    "standby": RemoteHeatDemand.STANDBY,
    "heating": RemoteHeatDemand.HEATING,
    "cooling": RemoteHeatDemand.COOLING,
}

_ENTRY_SCHEMA = probatio.Schema({probatio.Required(ATTR_CONFIG_ENTRY_ID): str})

# The selectors in services.yaml bound only the UI. This bounds scripted calls.
REQUEST_HEAT_DEMAND_SCHEMA = _ENTRY_SCHEMA.extend(
    {
        probatio.Required(ATTR_MODE): probatio.In(list(MODES)),
        probatio.Required(ATTR_HEAT_DEMAND): probatio.In(list(HEAT_DEMANDS)),
        probatio.Optional(ATTR_POWER): probatio.All(
            probatio.Coerce(int), probatio.Range(min=0, max=100)
        ),
        probatio.Optional(ATTR_TEMPERATURE): probatio.All(
            probatio.Coerce(float), probatio.Range(min=0, max=90)
        ),
    }
)


def _system_control(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[Gtw08ConfigEntry, SystemControl]:
    """Return a loaded entry and its remote control block."""
    entry: Gtw08ConfigEntry = async_get_config_entry(
        hass, DOMAIN, call.data[ATTR_CONFIG_ENTRY_ID]
    )
    control = entry.runtime_data.device.system_control
    if control is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="remote_control_unsupported",
            translation_placeholders={"title": entry.title},
        )
    return entry, control


async def _async_finish(entry: Gtw08ConfigEntry) -> None:
    """Show the new remote control state at once."""
    await entry.runtime_data.settings.async_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the GTW-08 actions."""

    async def _handle_request_heat_demand(call: ServiceCall) -> None:
        entry, control = _system_control(hass, call)
        try:
            await control.async_request(
                MODES[call.data[ATTR_MODE]],
                HEAT_DEMANDS[call.data[ATTR_HEAT_DEMAND]],
                power=call.data.get(ATTR_POWER),
                temperature=call.data.get(ATTR_TEMPERATURE),
            )
        except InvalidValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except (ModbusError, Gtw08Error) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err
        await _async_finish(entry)

    async def _handle_stop_remote_control(call: ServiceCall) -> None:
        entry, control = _system_control(hass, call)
        try:
            await control.async_stop()
        except (ModbusError, Gtw08Error) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err
        await _async_finish(entry)

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_REQUEST_HEAT_DEMAND,
        _handle_request_heat_demand,
        schema=REQUEST_HEAT_DEMAND_SCHEMA,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_STOP_REMOTE_CONTROL,
        _handle_stop_remote_control,
        schema=_ENTRY_SCHEMA,
    )
