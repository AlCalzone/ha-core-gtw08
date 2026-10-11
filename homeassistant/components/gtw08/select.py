"""Support for GTW-08 selects."""

from dataclasses import dataclass
from typing import override

from gtw08_modbus import ZoneMode

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Gtw08ConfigEntry, Gtw08RuntimeData
from .entity import Gtw08Entity, Gtw08EntityDescription, zone_of

PARALLEL_UPDATES = 1

# A temporary override shows up in the zone mode but cannot be set.
SETTABLE_ZONE_MODES = (ZoneMode.SCHEDULING, ZoneMode.MANUAL, ZoneMode.OFF)


@dataclass(frozen=True, kw_only=True)
class Gtw08SelectDescription(SelectEntityDescription, Gtw08EntityDescription):
    """Describe a GTW-08 select."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Gtw08ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add an operating mode select for each zone without a climate entity."""
    runtime_data = entry.runtime_data
    async_add_entities(
        Gtw08ZoneModeSelect(runtime_data, number)
        for number, zone in runtime_data.device.zone_slots.items()
        if zone.function is None or not zone.function.is_room_heating
    )


class Gtw08ZoneModeSelect(Gtw08Entity, SelectEntity):
    """The operating mode of a zone, such as a hot water tank."""

    _attr_options = [mode.name.lower() for mode in SETTABLE_ZONE_MODES]
    entity_description: Gtw08SelectDescription

    def __init__(self, runtime_data: Gtw08RuntimeData, number: int) -> None:
        """Initialize the entity."""
        super().__init__(
            runtime_data,
            Gtw08SelectDescription(
                key=f"zone_{number}_mode_setting",
                translation_key="zone_mode_setting",
                component="zone_settings",
                zone=number,
            ),
        )
        self._number = number

    @property
    @override
    def current_option(self) -> str | None:
        mode = zone_of(self.coordinator.device, self._number).mode_setting
        if mode not in SETTABLE_ZONE_MODES:
            return None
        return mode.name.lower()

    @override
    async def async_select_option(self, option: str) -> None:
        zone = zone_of(self.coordinator.device, self._number)
        await self._async_write(zone.async_write_mode(ZoneMode[option.upper()]))
