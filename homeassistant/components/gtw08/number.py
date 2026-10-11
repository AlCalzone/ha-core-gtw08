"""Support for GTW-08 numbers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from gtw08_modbus import Gtw08Appliance, Gtw08Component

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Gtw08ConfigEntry
from .entity import Gtw08Entity, Gtw08EntityDescription, zone_of

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class Gtw08NumberDescription(NumberEntityDescription, Gtw08EntityDescription):
    """Describe a GTW-08 number."""

    target_fn: Callable[[Gtw08Appliance], Gtw08Component]
    field: str


def _system_control(device: Gtw08Appliance) -> Gtw08Component:
    """The remote control block, which setup has found by the time this runs."""
    assert device.system_control is not None
    return device.system_control


SYSTEM_NUMBERS: tuple[Gtw08NumberDescription, ...] = (
    Gtw08NumberDescription(
        key="remote_power",
        translation_key="remote_power",
        component="system_control",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.BOX,
        target_fn=_system_control,
        field="power",
    ),
    Gtw08NumberDescription(
        key="remote_temperature",
        translation_key="remote_temperature",
        component="system_control",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=0,
        native_max_value=90,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        target_fn=_system_control,
        field="temperature",
    ),
)


def zone_numbers(number: int) -> list[Gtw08NumberDescription]:
    """The heating curve and fixed flow setpoint of zone ``number``."""
    return [
        Gtw08NumberDescription(
            key=f"zone_{number}_heating_curve_gradient",
            translation_key="heating_curve_gradient",
            component="zone_settings",
            zone=number,
            entity_category=EntityCategory.CONFIG,
            native_min_value=0,
            native_max_value=4,
            native_step=0.1,
            mode=NumberMode.BOX,
            target_fn=lambda device: zone_of(device, number).settings,
            field="heating_curve_gradient",
        ),
        Gtw08NumberDescription(
            key=f"zone_{number}_heating_curve_footpoint",
            translation_key="heating_curve_footpoint",
            component="zone_settings",
            zone=number,
            entity_category=EntityCategory.CONFIG,
            device_class=NumberDeviceClass.TEMPERATURE,
            native_min_value=15,
            native_max_value=90,
            native_step=0.5,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            mode=NumberMode.BOX,
            target_fn=lambda device: zone_of(device, number).settings,
            field="heating_curve_footpoint",
        ),
        Gtw08NumberDescription(
            key=f"zone_{number}_flow_setpoint_fixed",
            translation_key="flow_setpoint_fixed",
            component="zone_settings",
            zone=number,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
            device_class=NumberDeviceClass.TEMPERATURE,
            native_min_value=0,
            native_max_value=90,
            native_step=0.5,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            mode=NumberMode.BOX,
            target_fn=lambda device: zone_of(device, number).settings,
            field="flow_setpoint_fixed",
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Gtw08ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the GTW-08 number platform."""
    runtime_data = entry.runtime_data
    served = runtime_data.served_components
    descriptions = [
        description for description in SYSTEM_NUMBERS if description.component in served
    ]
    descriptions.extend(
        description
        for number, zone in runtime_data.device.zone_slots.items()
        if zone.function is not None and not zone.function.is_dhw
        for description in zone_numbers(number)
    )
    async_add_entities(
        Gtw08Number(runtime_data, description) for description in descriptions
    )


class Gtw08Number(Gtw08Entity, NumberEntity):
    """Defines a GTW-08 number."""

    entity_description: Gtw08NumberDescription

    @property
    @override
    def native_value(self) -> float | None:
        description = self.entity_description
        value: float | None = getattr(
            description.target_fn(self.coordinator.device), description.field
        )
        return value

    @override
    async def async_set_native_value(self, value: float) -> None:
        description = self.entity_description
        target = description.target_fn(self.coordinator.device)
        await self._async_write(target.write(description.field, value))
