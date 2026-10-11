"""Diagnostics support for GTW-08."""

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_DEVICE, CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import Gtw08ConfigEntry

TO_REDACT = {CONF_HOST, CONF_DEVICE, "serial_number"}

_SERIAL_NUMBER_REGISTERS = (7228, 7229)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Gtw08ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    device = runtime_data.device
    raw = read_error = None
    try:
        raw = await device.async_read_raw()
    except ModbusError as err:
        read_error = type(err).__name__
    if raw is not None and (holding := raw.get("holding")) is not None:
        for address in _SERIAL_NUMBER_REGISTERS:
            holding.pop(address, None)

    return async_redact_data(
        {
            "entry_data": dict(entry.data),
            "model": device.model,
            "serial_number": device.serial_number,
            "boards": [board.model for board in device.board_list],
            "zones": {
                number: zone.function.name.lower() if zone.function else None
                for number, zone in device.zone_slots.items()
            },
            "readings_components": device.readings_components,
            "settings_components": device.settings_components,
            "failed": {
                name: type(error).__name__
                for coordinator in (runtime_data.readings, runtime_data.settings)
                if coordinator.data is not None
                for name, error in coordinator.data.failed.items()
            },
            "read_error": read_error,
            "raw": raw,
        },
        TO_REDACT,
    )
