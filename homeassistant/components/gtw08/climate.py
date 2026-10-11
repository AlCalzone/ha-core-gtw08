"""Support for GTW-08 heating zones as climate entities."""

from dataclasses import dataclass
from typing import Any, override

from gtw08_modbus import HydraulicStatus, Zone, ZoneMode

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Gtw08ConfigEntry, Gtw08RuntimeData
from .entity import Gtw08Entity, Gtw08EntityDescription, zone_of

PARALLEL_UPDATES = 1

# Display code CM19X reports room temperature setpoints from 5 to 30 °C.
MIN_TEMPERATURE = 5.0
MAX_TEMPERATURE = 30.0

HVAC_MODES = {
    ZoneMode.SCHEDULING: HVACMode.AUTO,
    ZoneMode.TEMPORARY: HVACMode.AUTO,
    ZoneMode.MANUAL: HVACMode.HEAT,
    ZoneMode.OFF: HVACMode.OFF,
}
ZONE_MODES = {
    HVACMode.AUTO: ZoneMode.SCHEDULING,
    HVACMode.HEAT: ZoneMode.MANUAL,
    HVACMode.OFF: ZoneMode.OFF,
}


@dataclass(frozen=True, kw_only=True)
class Gtw08ClimateDescription(ClimateEntityDescription, Gtw08EntityDescription):
    """Describe a zone's climate entity."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Gtw08ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a climate entity for every zone that heats rooms."""
    runtime_data = entry.runtime_data
    async_add_entities(
        Gtw08Climate(
            runtime_data,
            Gtw08ClimateDescription(
                key=f"zone_{number}_climate",
                component="zones",
                zone=number,
                name=None,
            ),
        )
        for number, zone in runtime_data.device.zone_slots.items()
        if zone.function is not None and zone.function.is_room_heating
    )


class Gtw08Climate(Gtw08Entity, ClimateEntity):
    """A zone that heats rooms.

    Auto follows the zone's time program, heat holds the manual setpoint and
    off keeps frost protection only.
    """

    entity_description: Gtw08ClimateDescription

    _attr_hvac_modes = list(ZONE_MODES)
    _attr_max_temp = MAX_TEMPERATURE
    _attr_min_temp = MIN_TEMPERATURE
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        runtime_data: Gtw08RuntimeData,
        entity_description: Gtw08ClimateDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(runtime_data, entity_description)
        assert entity_description.zone is not None
        self._number = entity_description.zone

    @property
    def _zone(self) -> Zone:
        return zone_of(self.coordinator.device, self._number)

    @property
    @override
    def hvac_mode(self) -> HVACMode | None:
        mode = self._zone.mode
        return None if mode is None else HVAC_MODES[mode]

    @property
    @override
    def hvac_action(self) -> HVACAction | None:
        zone = self._zone
        if zone.mode is ZoneMode.OFF:
            return HVACAction.OFF
        if zone.pump_running is None:
            return None
        if not zone.pump_running:
            return HVACAction.IDLE
        hydraulics = self.coordinator.device.system_status.hydraulic_status
        if hydraulics is not None and HydraulicStatus.COOLING_ACTIVE in hydraulics:
            return HVACAction.COOLING
        return HVACAction.HEATING

    @property
    @override
    def native_target_temperature(self) -> float | None:
        return self._zone.room_setpoint

    @override
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._async_write(self._zone.async_write_mode(ZONE_MODES[hvac_mode]))

    @override
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the manual temperature and the mode passed along with it.

        Without a mode, a scheduled zone switches to manual so it holds the
        new temperature.
        """
        zone = self._zone
        await self._async_write(
            zone.async_write_room_setpoint(kwargs[ATTR_TEMPERATURE])
        )
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self._async_write(zone.async_write_mode(ZONE_MODES[hvac_mode]))
        elif zone.mode is not ZoneMode.MANUAL:
            await self._async_write(zone.async_write_mode(ZoneMode.MANUAL))

    @override
    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.AUTO)

    @override
    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
