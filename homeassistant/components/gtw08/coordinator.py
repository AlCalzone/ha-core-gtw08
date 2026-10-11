"""Data update coordinator for appliances behind a GTW-08 gateway."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import override

from gtw08_modbus import Gtw08Appliance, Gtw08Error, NoApplianceError, UpdateReport
from modbus_connection import ModbusError
from propcache.api import cached_property

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class Gtw08DataUpdateCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Run one of the appliance's update methods on its own interval."""

    config_entry: Gtw08ConfigEntry
    device: Gtw08Appliance

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Gtw08ConfigEntry,
        device: Gtw08Appliance,
        poll: Callable[[], Awaitable[UpdateReport]],
        interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.title,
            update_interval=interval,
        )
        self.device = device
        self._poll = poll
        self._failing: set[str] = set()

    @cached_property
    def device_info(self) -> dr.DeviceInfo:
        """Return device information."""
        device = self.device
        return dr.DeviceInfo(
            identifiers={(DOMAIN, device_identifier(self.config_entry))},
            name=self.config_entry.title,
            model=device.model,
            serial_number=(
                None if device.serial_number is None else str(device.serial_number)
            ),
        )

    @override
    async def _async_update_data(self) -> UpdateReport:
        try:
            report = await self._poll()
        except NoApplianceError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="no_appliance",
            ) from err
        except (Gtw08Error, ModbusError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="modbus_error",
                translation_placeholders={"error": str(err) or type(err).__name__},
            ) from err
        if report.failed and not report.updated:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="no_component_answered",
            ) from ExceptionGroup(
                "all components failed to refresh", list(report.failed.values())
            )

        for name, cause in report.failed.items():
            if name not in self._failing:
                _LOGGER.warning(
                    "%s: %s failed to refresh and is unavailable: %s",
                    self.name,
                    name,
                    cause,
                )
        for name in self._failing & report.updated:
            _LOGGER.info("%s: %s is available again", self.name, name)
        self._failing = (self._failing - report.updated) | set(report.failed)
        return report


def device_identifier(entry: ConfigEntry) -> str:
    """The identifier everything in this entry derives from.

    It is the serial number where the appliance reports one. Otherwise it is
    the entry ID.
    """
    return entry.unique_id or entry.entry_id


@dataclass
class Gtw08RuntimeData:
    """Class to hold runtime data."""

    readings: Gtw08DataUpdateCoordinator
    settings: Gtw08DataUpdateCoordinator
    appliance_device_id: str

    @property
    def device(self) -> Gtw08Appliance:
        """The appliance both coordinators poll."""
        return self.readings.device

    @property
    def served_components(self) -> frozenset[str]:
        """Component names this appliance polls, answered or not."""
        return frozenset(self.device.readings_components) | frozenset(
            self.device.settings_components
        )

    def coordinator_for(self, component: str) -> Gtw08DataUpdateCoordinator:
        """Which coordinator owns a given component's data."""
        if component in self.device.settings_components:
            return self.settings
        return self.readings


type Gtw08ConfigEntry = ConfigEntry[Gtw08RuntimeData]
