"""Support for GTW-08 selects."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import override

from gtw08_modbus import (
    Gtw08Appliance,
    RemoteControlMode,
    RemoteHeatDemand,
    SystemControl,
    ZoneMode,
)

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Gtw08ConfigEntry
from .entity import Gtw08Entity, Gtw08EntityDescription, zone_of

PARALLEL_UPDATES = 1

# A temporary override shows up in the zone mode but cannot be set.
SETTABLE_ZONE_MODES = (ZoneMode.SCHEDULING, ZoneMode.MANUAL, ZoneMode.OFF)


@dataclass(frozen=True, kw_only=True)
class Gtw08SelectDescription(SelectEntityDescription, Gtw08EntityDescription):
    """Describe a GTW-08 select."""

    choices: tuple[IntEnum, ...]
    value_fn: Callable[[Gtw08Appliance], IntEnum | None]
    write_fn: Callable[[Gtw08Appliance, IntEnum], Awaitable[None]]

    @property
    def option_names(self) -> list[str]:
        """The options, as Home Assistant shows them."""
        return [choice.name.lower() for choice in self.choices]


def _system_control(device: Gtw08Appliance) -> SystemControl:
    """The remote control block, which setup has found by the time this runs."""
    assert device.system_control is not None
    return device.system_control


SYSTEM_SELECTS: tuple[Gtw08SelectDescription, ...] = (
    Gtw08SelectDescription(
        key="remote_control_mode",
        translation_key="remote_control_mode",
        component="system_control",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        choices=tuple(RemoteControlMode),
        value_fn=lambda device: _system_control(device).mode,
        write_fn=lambda device, value: _system_control(device).write("mode", value),
    ),
    Gtw08SelectDescription(
        key="remote_heat_demand",
        translation_key="remote_heat_demand",
        component="system_control",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        choices=tuple(RemoteHeatDemand),
        value_fn=lambda device: _system_control(device).heat_demand,
        write_fn=lambda device, value: _system_control(device).write(
            "heat_demand", value
        ),
    ),
)


def zone_select(number: int) -> Gtw08SelectDescription:
    """The operating mode select of zone ``number``."""
    return Gtw08SelectDescription(
        key=f"zone_{number}_mode_setting",
        translation_key="zone_mode_setting",
        component="zone_settings",
        zone=number,
        choices=SETTABLE_ZONE_MODES,
        value_fn=lambda device: zone_of(device, number).mode_setting,
        write_fn=lambda device, value: zone_of(device, number).async_write_mode(
            ZoneMode(value)
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Gtw08ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the GTW-08 select platform."""
    runtime_data = entry.runtime_data
    served = runtime_data.served_components
    descriptions = [
        description for description in SYSTEM_SELECTS if description.component in served
    ]
    descriptions.extend(
        zone_select(number) for number in runtime_data.device.zone_slots
    )
    async_add_entities(
        Gtw08Select(runtime_data, description) for description in descriptions
    )


class Gtw08Select(Gtw08Entity, SelectEntity):
    """Defines a GTW-08 select."""

    entity_description: Gtw08SelectDescription

    @property
    @override
    def options(self) -> list[str]:
        return self.entity_description.option_names

    @property
    @override
    def current_option(self) -> str | None:
        value = self.entity_description.value_fn(self.coordinator.device)
        if value is None or value not in self.entity_description.choices:
            return None
        return value.name.lower()

    @override
    async def async_select_option(self, option: str) -> None:
        description = self.entity_description
        choice = description.choices[description.option_names.index(option)]
        await self._async_write(description.write_fn(self.coordinator.device, choice))
