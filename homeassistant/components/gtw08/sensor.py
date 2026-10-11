"""Support for GTW-08 sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import override

from gtw08_modbus import (
    ApplianceStatus,
    ApplianceSubStatus,
    Cascade,
    ErrorType,
    Gtw08Appliance,
    HeatPumpPerformance,
    SeasonMode,
    ServiceNotification,
    ZoneActivity,
    ZoneMode,
)

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import Gtw08ConfigEntry
from .entity import (
    KIND_BURNER,
    KIND_HEAT_PUMP,
    Gtw08Entity,
    Gtw08EntityDescription,
    appliance_kinds,
    zone_of,
)

PARALLEL_UPDATES = 0

type ValueFn = Callable[[Gtw08Appliance], StateType | IntEnum]


def _enum_options(enum_type: type[IntEnum]) -> list[str]:
    """The sensor options a device enum maps to."""
    return [member.name.lower() for member in enum_type]


def _heat_pump(device: Gtw08Appliance) -> HeatPumpPerformance:
    """The COP block, which setup has found when its sensors are added."""
    assert device.heat_pump is not None
    return device.heat_pump


def _cascade(device: Gtw08Appliance) -> Cascade:
    """The cascade block, which setup has found when its sensors are added."""
    assert device.cascade is not None
    return device.cascade


@dataclass(frozen=True, kw_only=True)
class Gtw08SensorDescription(SensorEntityDescription, Gtw08EntityDescription):
    """Describe a GTW-08 sensor."""

    value_fn: ValueFn


def _temperature(
    key: str,
    component: str,
    value_fn: ValueFn,
    *,
    translation_key: str | None = None,
    zone: int | None = None,
    kind: str | None = None,
) -> Gtw08SensorDescription:
    """A temperature sensor, in °C."""
    return Gtw08SensorDescription(
        key=key,
        translation_key=translation_key or key,
        component=component,
        zone=zone,
        kind=kind,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=value_fn,
    )


def _energy(key: str, value_fn: ValueFn) -> Gtw08SensorDescription:
    """An energy counter, in kWh."""
    return Gtw08SensorDescription(
        key=key,
        translation_key=key,
        component="appliance",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=value_fn,
    )


def _hours(
    key: str,
    component: str,
    value_fn: ValueFn,
    *,
    enabled: bool = True,
    translation_key: str | None = None,
    zone: int | None = None,
) -> Gtw08SensorDescription:
    """An hour counter."""
    return Gtw08SensorDescription(
        key=key,
        translation_key=translation_key or key,
        component=component,
        zone=zone,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        value_fn=value_fn,
    )


def _count(
    key: str,
    component: str,
    value_fn: ValueFn,
    *,
    enabled: bool = True,
    translation_key: str | None = None,
    zone: int | None = None,
) -> Gtw08SensorDescription:
    """A start counter."""
    return Gtw08SensorDescription(
        key=key,
        translation_key=translation_key or key,
        component=component,
        zone=zone,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        value_fn=value_fn,
    )


APPLIANCE_SENSORS: tuple[Gtw08SensorDescription, ...] = (
    _temperature(
        "outdoor_temperature",
        "system_status",
        lambda device: device.system_status.outdoor_temperature,
    ),
    _temperature(
        "flow_temperature",
        "appliance",
        lambda device: device.appliance.flow_temperature,
    ),
    _temperature(
        "return_temperature",
        "appliance",
        lambda device: device.appliance.return_temperature,
    ),
    _temperature(
        "flue_gas_temperature",
        "appliance",
        lambda device: device.appliance.flue_gas_temperature,
        kind=KIND_BURNER,
    ),
    _temperature(
        "heat_pump_flow_temperature",
        "appliance",
        lambda device: device.appliance.heat_pump_flow_temperature,
        kind=KIND_HEAT_PUMP,
    ),
    _temperature(
        "heat_pump_return_temperature",
        "appliance",
        lambda device: device.appliance.heat_pump_return_temperature,
        kind=KIND_HEAT_PUMP,
    ),
    _temperature(
        "dhw_setpoint",
        "appliance",
        lambda device: device.appliance.dhw_setpoint,
    ),
    Gtw08SensorDescription(
        key="water_pressure",
        translation_key="water_pressure",
        component="appliance",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.appliance.water_pressure,
    ),
    Gtw08SensorDescription(
        key="status",
        translation_key="status",
        component="appliance",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(ApplianceStatus),
        value_fn=lambda device: device.appliance.status,
    ),
    Gtw08SensorDescription(
        key="sub_status",
        translation_key="sub_status",
        component="appliance",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(ApplianceSubStatus),
        value_fn=lambda device: device.appliance.sub_status,
    ),
    Gtw08SensorDescription(
        key="relative_power",
        translation_key="relative_power",
        component="appliance",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.appliance.relative_power,
    ),
    Gtw08SensorDescription(
        key="actual_power",
        translation_key="actual_power",
        component="appliance",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.appliance.actual_power,
    ),
    Gtw08SensorDescription(
        key="pump_speed",
        translation_key="pump_speed",
        component="appliance",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.appliance.pump_speed,
    ),
    Gtw08SensorDescription(
        key="system_power",
        translation_key="system_power",
        component="system_status",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.system_status.system_power,
    ),
    Gtw08SensorDescription(
        key="season_mode",
        translation_key="season_mode",
        component="system_status",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(SeasonMode),
        value_fn=lambda device: device.system_status.season_mode,
    ),
    Gtw08SensorDescription(
        key="cop",
        translation_key="cop",
        component="heat_pump",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda device: _heat_pump(device).cop,
    ),
    _energy(
        "energy_consumed_total",
        lambda device: device.appliance.energy_consumed_total,
    ),
    _energy(
        "energy_consumed_ch",
        lambda device: device.appliance.energy_consumed_ch,
    ),
    _energy(
        "energy_consumed_dhw",
        lambda device: device.appliance.energy_consumed_dhw,
    ),
    _energy(
        "energy_consumed_cooling",
        lambda device: device.appliance.energy_consumed_cooling,
    ),
    _energy(
        "energy_consumed_backup",
        lambda device: device.appliance.energy_consumed_backup,
    ),
    _energy(
        "energy_delivered_total",
        lambda device: device.appliance.energy_delivered_total,
    ),
    _energy(
        "energy_delivered_ch",
        lambda device: device.appliance.energy_delivered_ch,
    ),
    _energy(
        "energy_delivered_dhw",
        lambda device: device.appliance.energy_delivered_dhw,
    ),
    _energy(
        "energy_delivered_cooling",
        lambda device: device.appliance.energy_delivered_cooling,
    ),
    _energy(
        "energy_delivered_backup",
        lambda device: device.appliance.energy_delivered_backup,
    ),
    _count(
        "generator_starts",
        "appliance",
        lambda device: device.appliance.generator_starts,
    ),
    _hours(
        "generator_hours",
        "appliance",
        lambda device: device.appliance.generator_hours,
    ),
    _count(
        "backup_1_starts",
        "appliance",
        lambda device: device.appliance.backup_1_starts,
        enabled=False,
    ),
    _hours(
        "backup_1_hours",
        "appliance",
        lambda device: device.appliance.backup_1_hours,
        enabled=False,
    ),
    _count(
        "backup_2_starts",
        "appliance",
        lambda device: device.appliance.backup_2_starts,
        enabled=False,
    ),
    _hours(
        "backup_2_hours",
        "appliance",
        lambda device: device.appliance.backup_2_hours,
        enabled=False,
    ),
    _hours(
        "mains_hours",
        "appliance",
        lambda device: device.appliance.mains_hours,
        enabled=False,
    ),
    Gtw08SensorDescription(
        key="service_notification",
        translation_key="service_notification",
        component="service",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(ServiceNotification),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.service.notification,
    ),
    _hours(
        "hours_since_service",
        "service",
        lambda device: device.service.hours_since_service,
    ),
    _hours(
        "hours_producing_since_service",
        "service",
        lambda device: device.service.hours_producing_since_service,
        enabled=False,
    ),
    _count(
        "starts_since_service",
        "service",
        lambda device: device.service.starts_since_service,
        enabled=False,
    ),
)

CASCADE_SENSORS: tuple[Gtw08SensorDescription, ...] = (
    _temperature(
        "cascade_flow_temperature",
        "cascade",
        lambda device: _cascade(device).flow_temperature,
    ),
    _temperature(
        "cascade_return_temperature",
        "cascade",
        lambda device: _cascade(device).return_temperature,
    ),
    Gtw08SensorDescription(
        key="cascade_state",
        translation_key="cascade_state",
        component="cascade",
        device_class=SensorDeviceClass.ENUM,
        options=_enum_options(ApplianceStatus),
        value_fn=lambda device: _cascade(device).state,
    ),
    Gtw08SensorDescription(
        key="cascade_producer_count",
        translation_key="cascade_producer_count",
        component="cascade",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: _cascade(device).producer_count,
    ),
    Gtw08SensorDescription(
        key="cascade_requested_power",
        translation_key="cascade_requested_power",
        component="cascade",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: _cascade(device).requested_power,
    ),
)


def _board_error_type(device: Gtw08Appliance, number: int) -> StateType | IntEnum:
    """The board's error type, ``none`` without an error, unknown if unreachable."""
    board = device.board_list[number - 1]
    if not board.is_available:
        return None
    if board.error_code is None:
        return "none"
    return board.error_type


def board_sensors(number: int, model: str | None) -> list[Gtw08SensorDescription]:
    """The error sensors of board ``number``."""
    placeholders = {"number": str(number), "model": model or "?"}

    def board_error_code(device: Gtw08Appliance) -> StateType:
        board = device.board_list[number - 1]
        if not board.is_available:
            return None
        return board.error_code or 0

    return [
        Gtw08SensorDescription(
            key=f"board_{number}_error_code",
            translation_key="board_error_code",
            translation_placeholders=placeholders,
            component="boards",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=board_error_code,
        ),
        Gtw08SensorDescription(
            key=f"board_{number}_error_type",
            translation_key="board_error_type",
            translation_placeholders=placeholders,
            component="boards",
            device_class=SensorDeviceClass.ENUM,
            options=["none", *_enum_options(ErrorType)],
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda device: _board_error_type(device, number),
        ),
    ]


def zone_sensors(device: Gtw08Appliance, number: int) -> list[Gtw08SensorDescription]:
    """The sensors of zone ``number``."""
    function = zone_of(device, number).function
    is_dhw = function is not None and function.is_dhw
    sensors = [
        _temperature(
            f"zone_{number}_flow_temperature",
            "zones",
            lambda device: zone_of(device, number).flow_temperature,
            translation_key=("dhw_temperature" if is_dhw else "zone_flow_temperature"),
            zone=number,
        ),
        _temperature(
            f"zone_{number}_flow_setpoint",
            "zones",
            lambda device: zone_of(device, number).flow_setpoint,
            translation_key="zone_flow_setpoint",
            zone=number,
        ),
        Gtw08SensorDescription(
            key=f"zone_{number}_activity",
            translation_key="zone_activity",
            component="zones",
            zone=number,
            device_class=SensorDeviceClass.ENUM,
            options=_enum_options(ZoneActivity),
            value_fn=lambda device: zone_of(device, number).activity,
        ),
        Gtw08SensorDescription(
            key=f"zone_{number}_mode",
            translation_key="zone_mode",
            component="zones",
            zone=number,
            device_class=SensorDeviceClass.ENUM,
            options=_enum_options(ZoneMode),
            value_fn=lambda device: zone_of(device, number).mode,
        ),
        _hours(
            f"zone_{number}_pump_hours",
            "zones",
            lambda device: zone_of(device, number).pump_hours,
            enabled=False,
            translation_key="zone_pump_hours",
            zone=number,
        ),
        _count(
            f"zone_{number}_pump_starts",
            "zones",
            lambda device: zone_of(device, number).pump_starts,
            enabled=False,
            translation_key="zone_pump_starts",
            zone=number,
        ),
    ]
    if function is not None and function.is_room_heating:
        sensors.append(
            _temperature(
                f"zone_{number}_room_setpoint",
                "zones",
                lambda device: zone_of(device, number).room_setpoint,
                translation_key="zone_room_setpoint",
                zone=number,
            )
        )
    return sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Gtw08ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the GTW-08 sensor platform."""
    runtime_data = entry.runtime_data
    device = runtime_data.device
    served = runtime_data.served_components
    kinds = appliance_kinds(device)

    descriptions = [
        description
        for description in (*APPLIANCE_SENSORS, *CASCADE_SENSORS)
        if description.component in served
        and (description.kind is None or description.kind in kinds)
    ]
    descriptions.extend(
        description
        for board in device.board_list
        for description in board_sensors(board.number, board.model)
    )
    descriptions.extend(
        description
        for number in device.zone_slots
        for description in zone_sensors(device, number)
    )
    async_add_entities(
        Gtw08Sensor(runtime_data, description) for description in descriptions
    )


class Gtw08Sensor(Gtw08Entity, SensorEntity):
    """Defines a GTW-08 sensor."""

    entity_description: Gtw08SensorDescription

    @property
    @override
    def native_value(self) -> StateType:
        value = self.entity_description.value_fn(self.coordinator.device)
        if isinstance(value, IntEnum):
            return value.name.lower()
        return value
