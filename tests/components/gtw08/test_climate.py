"""Tests for the GTW-08 climate platform."""

from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from gtw08_modbus import InvalidValueError
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    HVACAction,
    HVACMode,
)
from homeassistant.components.gtw08.const import SCAN_INTERVAL
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform

ZONE_1 = "climate.gtw_08_ehc_04_zone_1"
ZONE_3 = "climate.gtw_08_ehc_04_zone_3"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the climate platform only."""
    return [Platform.CLIMATE]


async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test a climate entity per room heating zone, and none for hot water."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("service", "data", "expected"),
    [
        pytest.param(
            SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.HEAT}, 1, id="heat"
        ),
        pytest.param(
            SERVICE_SET_HVAC_MODE, {ATTR_HVAC_MODE: HVACMode.OFF}, 2, id="off"
        ),
        pytest.param(SERVICE_TURN_OFF, {}, 2, id="turn_off"),
        pytest.param(SERVICE_TURN_ON, {}, 0, id="turn_on"),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_set_mode(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    service: str,
    data: dict[str, str],
    expected: int,
) -> None:
    """Test the HVAC modes write the zone's operating mode."""
    mock_unit.holding[649] = 1
    await hass.services.async_call(
        CLIMATE_DOMAIN, service, {ATTR_ENTITY_ID: ZONE_1, **data}, blocking=True
    )
    assert mock_unit.holding[649] == expected


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_switches_to_manual(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test setting a temperature on a scheduled zone holds it in manual."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ZONE_1, ATTR_TEMPERATURE: 22.5},
        blocking=True,
    )
    assert mock_unit.holding[664] == 225
    assert mock_unit.holding[649] == 1


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_keeps_manual(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test setting a temperature on a manual zone writes only the setpoint."""
    mock_unit.holding[2132] = 1  # zone 3 runs in manual
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ZONE_3).state == HVACMode.HEAT

    mock_unit.fail_write(1673, ModbusTimeoutError())
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ZONE_3, ATTR_TEMPERATURE: 19},
        blocking=True,
    )
    assert mock_unit.holding[1688] == 190


@pytest.mark.usefixtures("init_integration")
async def test_write_failure(hass: HomeAssistant, mock_unit: MockModbusUnit) -> None:
    """Test a refused write raises a translated error."""
    mock_unit.fail_write(649, ModbusTimeoutError())
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: ZONE_1, ATTR_HVAC_MODE: HVACMode.OFF},
            blocking=True,
        )
    assert err.value.translation_key == "write_failed"


@pytest.mark.usefixtures("init_integration")
async def test_invalid_value(hass: HomeAssistant) -> None:
    """Test a value the library refuses raises a translated validation error."""
    with (
        patch(
            "homeassistant.components.gtw08.climate.Zone.async_write_mode",
            side_effect=InvalidValueError("no"),
        ),
        pytest.raises(ServiceValidationError) as err,
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: ZONE_1, ATTR_HVAC_MODE: HVACMode.OFF},
            blocking=True,
        )
    assert err.value.translation_key == "invalid_value"


@pytest.mark.parametrize(
    ("hvac_mode", "expected"),
    [
        pytest.param(HVACMode.OFF, 2, id="off"),
        pytest.param(HVACMode.HEAT, 1, id="heat"),
    ],
)
@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_a_mode(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    hvac_mode: HVACMode,
    expected: int,
) -> None:
    """Test a mode passed with the temperature is the mode written."""
    mock_unit.holding[649] = 1
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ZONE_1, ATTR_TEMPERATURE: 18, ATTR_HVAC_MODE: hvac_mode},
        blocking=True,
    )
    assert mock_unit.holding[664] == 180
    assert mock_unit.holding[649] == expected


@pytest.mark.usefixtures("init_integration")
async def test_cooling_action(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a running zone pump shows cooling while the appliance cools."""
    assert hass.states.get(ZONE_1).attributes["hvac_action"] == HVACAction.HEATING

    mock_unit.holding[280] = 0b1000001  # pump on, cooling active
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(ZONE_1).attributes["hvac_action"] == HVACAction.COOLING


@pytest.mark.usefixtures("init_integration")
async def test_a_mode_write_refreshes_the_settings_too(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a climate write also refreshes the zone settings coordinator."""
    mock_unit.read_events.clear()
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ZONE_1, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )
    await hass.async_block_till_done()

    starts = {event.address for event in mock_unit.read_events}
    assert {648, 1107} <= starts


@pytest.mark.parametrize("hvac_mode", [HVACMode.COOL, HVACMode.AUTO])
@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_with_an_unsupported_mode(
    hass: HomeAssistant, mock_unit: MockModbusUnit, hvac_mode: HVACMode
) -> None:
    """Test a mode a temperature cannot go with is refused before any write."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: ZONE_1, ATTR_TEMPERATURE: 20, ATTR_HVAC_MODE: hvac_mode},
            blocking=True,
        )
    assert err.value.translation_key == "temperature_mode_unsupported"
    assert writes == []


@pytest.mark.usefixtures("init_integration")
async def test_set_temperature_keeps_an_off_zone_off(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a temperature set on a zone that is off leaves it off."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ZONE_3, ATTR_TEMPERATURE: 21},
        blocking=True,
    )
    assert mock_unit.holding[1688] == 210
    assert mock_unit.holding[1673] == 2
