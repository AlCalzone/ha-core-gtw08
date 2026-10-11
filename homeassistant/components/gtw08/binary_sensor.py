"""Support for GTW-08 binary sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntFlag
from typing import override

from gtw08_modbus import (
    GeneratorStatus,
    Gtw08Appliance,
    HydraulicStatus,
    RemoteControlMode,
)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Gtw08ConfigEntry
from .entity import Gtw08Entity, Gtw08EntityDescription, zone_of

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class Gtw08BinarySensorDescription(
    BinarySensorEntityDescription, Gtw08EntityDescription
):
    """Describe a GTW-08 binary sensor."""

    value_fn: Callable[[Gtw08Appliance], bool | None]


def _has(flags: IntFlag | None, flag: IntFlag) -> bool | None:
    """Whether ``flag`` is set, or ``None`` without a reading."""
    return None if flags is None else flag in flags


def _remote_control_active(device: Gtw08Appliance) -> bool | None:
    """Whether the gateway has taken over the heat demand from the zones."""
    control = device.system_control
    if control is None or control.mode is None:
        return None
    return control.mode is not RemoteControlMode.MONITORING_ONLY


def _generator(
    key: str,
    flag: GeneratorStatus,
    device_class: BinarySensorDeviceClass | None = None,
    *,
    enabled: bool = True,
) -> Gtw08BinarySensorDescription:
    """A bit of register 279."""
    return Gtw08BinarySensorDescription(
        key=key,
        translation_key=key,
        component="system_status",
        device_class=device_class,
        entity_registry_enabled_default=enabled,
        value_fn=lambda device: _has(device.system_status.generator_status, flag),
    )


def _hydraulic(
    key: str,
    flag: HydraulicStatus,
    device_class: BinarySensorDeviceClass | None = None,
    *,
    enabled: bool = True,
) -> Gtw08BinarySensorDescription:
    """A bit of register 280."""
    return Gtw08BinarySensorDescription(
        key=key,
        translation_key=key,
        component="system_status",
        device_class=device_class,
        entity_registry_enabled_default=enabled,
        value_fn=lambda device: _has(device.system_status.hydraulic_status, flag),
    )


APPLIANCE_BINARY_SENSORS: tuple[Gtw08BinarySensorDescription, ...] = (
    _generator("flame", GeneratorStatus.FLAME_ON, enabled=False),
    _generator(
        "heat_pump", GeneratorStatus.HEAT_PUMP_ON, BinarySensorDeviceClass.RUNNING
    ),
    _generator(
        "backup_1",
        GeneratorStatus.BACKUP_1_ON,
        BinarySensorDeviceClass.RUNNING,
        enabled=False,
    ),
    _generator(
        "backup_2",
        GeneratorStatus.BACKUP_2_ON,
        BinarySensorDeviceClass.RUNNING,
        enabled=False,
    ),
    _generator(
        "dhw_backup",
        GeneratorStatus.DHW_BACKUP_ON,
        BinarySensorDeviceClass.RUNNING,
        enabled=False,
    ),
    _generator(
        "reset_needed", GeneratorStatus.RESET_NEEDED, BinarySensorDeviceClass.PROBLEM
    ),
    _generator(
        "water_pressure_low",
        GeneratorStatus.WATER_PRESSURE_LOW,
        BinarySensorDeviceClass.PROBLEM,
    ),
    _hydraulic("pump", HydraulicStatus.PUMP_ON, BinarySensorDeviceClass.RUNNING),
    _hydraulic("dhw_active", HydraulicStatus.DHW_ACTIVE),
    _hydraulic("ch_active", HydraulicStatus.CH_ACTIVE),
    _hydraulic("cooling_active", HydraulicStatus.COOLING_ACTIVE),
    Gtw08BinarySensorDescription(
        key="service_required",
        translation_key="service_required",
        component="service",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda device: device.service.service_required,
    ),
    Gtw08BinarySensorDescription(
        key="remote_control",
        translation_key="remote_control",
        component="system_control",
        value_fn=_remote_control_active,
    ),
    Gtw08BinarySensorDescription(
        key="error",
        translation_key="error",
        component="summary",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.summary.any_error,
    ),
)


def zone_binary_sensors(number: int) -> list[Gtw08BinarySensorDescription]:
    """The binary sensors of zone ``number``."""
    return [
        Gtw08BinarySensorDescription(
            key=f"zone_{number}_pump",
            translation_key="pump",
            component="zones",
            zone=number,
            device_class=BinarySensorDeviceClass.RUNNING,
            value_fn=lambda device: zone_of(device, number).pump_running,
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Gtw08ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the GTW-08 binary sensor platform."""
    runtime_data = entry.runtime_data
    served = runtime_data.served_components
    descriptions = [
        description
        for description in APPLIANCE_BINARY_SENSORS
        if description.component in served
    ]
    descriptions.extend(
        description
        for number in runtime_data.device.zone_slots
        for description in zone_binary_sensors(number)
    )
    async_add_entities(
        Gtw08BinarySensor(runtime_data, description) for description in descriptions
    )


class Gtw08BinarySensor(Gtw08Entity, BinarySensorEntity):
    """Defines a GTW-08 binary sensor."""

    entity_description: Gtw08BinarySensorDescription

    @property
    @override
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.device)
