"""Integrate heating appliances behind a GTW-08 Modbus gateway."""

from typing import TYPE_CHECKING

from gtw08_modbus import Gtw08Appliance

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import device_registry as dr

from .config_flow import create_modbus_params
from .const import CONF_UNIT_ID, DOMAIN, SCAN_INTERVAL, SETTINGS_SCAN_INTERVAL
from .coordinator import (
    Gtw08ConfigEntry,
    Gtw08DataUpdateCoordinator,
    Gtw08RuntimeData,
    device_identifier,
)
from .entity import zone_identifier

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: Gtw08ConfigEntry) -> bool:
    """Set up a GTW-08 gateway from a config entry."""
    try:
        unit = async_get_unit(
            hass, entry, create_modbus_params(entry.data), entry.data[CONF_UNIT_ID]
        )
    except HomeAssistantError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="link_settings_in_use",
            translation_placeholders={"error": str(err)},
        ) from err
    device = Gtw08Appliance(unit)

    readings = Gtw08DataUpdateCoordinator(
        hass, entry, device, device.async_update_readings, SCAN_INTERVAL
    )
    settings = Gtw08DataUpdateCoordinator(
        hass, entry, device, device.async_update_settings, SETTINGS_SCAN_INTERVAL
    )
    # The first readings poll also finds the boards and zones and settles
    # which blocks this appliance serves.
    await readings.async_config_entry_first_refresh()
    await settings.async_refresh()

    # Register the appliance first, because each zone links to its id.
    appliance = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **readings.device_info
    )
    entry.runtime_data = Gtw08RuntimeData(readings, settings, appliance.id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: Gtw08ConfigEntry,
    device_entry: dr.AnyDeviceEntry,
) -> bool:
    """Allow removing a zone the appliance no longer reports."""
    if config_entry.state is not ConfigEntryState.LOADED:
        return False
    if TYPE_CHECKING:
        assert config_entry.runtime_data is not None
    base = device_identifier(config_entry)
    current = {(DOMAIN, base)} | {
        (DOMAIN, zone_identifier(base, number))
        for number in config_entry.runtime_data.device.zone_slots
    }
    return not current & device_entry.identifiers


async def async_unload_entry(hass: HomeAssistant, entry: Gtw08ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
