"""Base entity for appliances behind a GTW-08 gateway."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import override

from gtw08_modbus import Gtw08Appliance, InvalidValueError, Zone
from modbus_connection import ModbusError

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Gtw08DataUpdateCoordinator, Gtw08RuntimeData, device_identifier


@dataclass(frozen=True, kw_only=True)
class Gtw08EntityDescription(EntityDescription):
    """Describe a GTW-08 entity."""

    component: str  # attribute name on Gtw08Appliance, e.g. 'appliance'
    zone: int | None = None  # None keeps the entity on the appliance


def zone_identifier(base: str, number: int) -> str:
    """The device registry identifier of a zone."""
    return f"{base}_zone_{number}"


def zone_of(device: Gtw08Appliance, number: int) -> Zone:
    """Zone ``number`` of the appliance."""
    return device.zone_slots[number]


class Gtw08Entity(CoordinatorEntity[Gtw08DataUpdateCoordinator]):
    """Defines a base GTW-08 entity."""

    _attr_has_entity_name = True
    entity_description: Gtw08EntityDescription

    def __init__(
        self,
        runtime_data: Gtw08RuntimeData,
        entity_description: Gtw08EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(runtime_data.coordinator_for(entity_description.component))
        self.entity_description = entity_description
        base = device_identifier(self.coordinator.config_entry)
        self._attr_unique_id = f"{base}_{entity_description.key}"
        self._runtime_data = runtime_data
        self._attr_device_info = self._device_info(runtime_data, base)

    def _device_info(
        self, runtime_data: Gtw08RuntimeData, base: str
    ) -> dr.DeviceInfo | dr.ChildDeviceInfo:
        """Place the entity on the appliance, or on the zone it belongs to."""
        if (number := self.entity_description.zone) is None:
            return self.coordinator.device_info
        return dr.ChildDeviceInfo(
            identifiers={(DOMAIN, zone_identifier(base, number))},
            parent_device_id=runtime_data.appliance_device_id,
            translation_key="zone",
            translation_placeholders={"number": str(number)},
        )

    @property
    @override
    def available(self) -> bool:
        """Whether this entity's component answered the most recent poll."""
        if not super().available:
            return False
        return self.entity_description.component not in self.coordinator.data.failed

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Run a write on the appliance, then refresh what it changed."""
        try:
            await write
        except InvalidValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err
        await self.coordinator.async_request_refresh()
        if self.entity_description.zone is not None:
            # Zone readings and settings show the same mode, from two
            # coordinators.
            for coordinator in (
                self._runtime_data.readings,
                self._runtime_data.settings,
            ):
                if coordinator is not self.coordinator:
                    await coordinator.async_request_refresh()
