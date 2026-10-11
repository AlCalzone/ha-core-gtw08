"""Tests for the GTW-08 diagnostics."""

from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry
from tests.components.diagnostics import get_diagnostics_for_config_entry
from tests.typing import ClientSessionGenerator


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test diagnostics hold the raw dump without the serial number."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    assert diagnostics == snapshot
    assert "7228" not in diagnostics["raw"]["holding"]


async def test_diagnostics_read_error(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test diagnostics still answer when the raw read fails."""
    mock_unit.fail_requests(ModbusTimeoutError())
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )
    assert diagnostics["read_error"] == "ModbusTimeoutError"
    assert diagnostics["raw"] is None
