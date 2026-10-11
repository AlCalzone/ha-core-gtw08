"""Tests for the GTW-08 remote control actions."""

from typing import Any

from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest

from homeassistant.components.gtw08.const import DOMAIN
from homeassistant.components.gtw08.services import (
    SERVICE_REQUEST_HEAT_DEMAND,
    SERVICE_STOP_REMOTE_CONTROL,
)
from homeassistant.const import ATTR_CONFIG_ENTRY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from tests.common import MockConfigEntry

REMOTE_CONTROL = "binary_sensor.gtw_08_ehc_04_remote_control"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the binary sensor platform only."""
    return [Platform.BINARY_SENSOR]


async def _call(
    hass: HomeAssistant, entry: MockConfigEntry, service: str, **data: Any
) -> None:
    await hass.services.async_call(
        DOMAIN,
        service,
        {ATTR_CONFIG_ENTRY_ID: entry.entry_id, **data},
        blocking=True,
    )


async def test_request_and_stop(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a request writes the mode first, and stopping hands control back."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)
    assert hass.states.get(REMOTE_CONTROL).state == "off"

    await _call(
        hass,
        init_integration,
        SERVICE_REQUEST_HEAT_DEMAND,
        mode="temperature",
        heat_demand="heating",
        temperature=55,
    )

    assert [write.address for write in writes] == [258, 257, 259]
    assert mock_unit.holding[257] == 5500
    assert hass.states.get(REMOTE_CONTROL).state == "on"

    await _call(hass, init_integration, SERVICE_STOP_REMOTE_CONTROL)

    assert mock_unit.holding[258] == 3
    assert hass.states.get(REMOTE_CONTROL).state == "off"


async def test_a_failed_request_falls_back_to_monitoring(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a write that fails puts the gateway back to monitoring only."""
    mock_unit.fail_write(259, ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _call(
            hass,
            init_integration,
            SERVICE_REQUEST_HEAT_DEMAND,
            mode="power",
            heat_demand="heating",
            power=60,
        )

    assert err.value.translation_key == "write_failed"
    assert mock_unit.holding[258] == 3


async def test_a_request_without_its_setpoint(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a mode without the value it needs is refused before any write."""
    writes: list[WriteEvent] = []
    mock_unit.on_write(writes.append)

    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            init_integration,
            SERVICE_REQUEST_HEAT_DEMAND,
            mode="temperature",
            heat_demand="heating",
        )

    assert err.value.translation_key == "invalid_value"
    assert writes == []


async def test_a_failed_stop(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a stop that cannot be written raises a translated error."""
    mock_unit.fail_write(258, ModbusTimeoutError())

    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, init_integration, SERVICE_STOP_REMOTE_CONTROL)
    assert err.value.translation_key == "write_failed"


async def test_a_gateway_without_remote_control(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: Any,
    mock_unit: MockModbusUnit,
) -> None:
    """Test the actions refuse a gateway that does not serve remote control."""
    mock_unit.fail_read(256, IllegalDataAddressError())
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, mock_config_entry, SERVICE_STOP_REMOTE_CONTROL)
    assert err.value.translation_key == "remote_control_unsupported"
