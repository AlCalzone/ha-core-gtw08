"""Tests for the GTW-08 binary sensor platform."""

from unittest.mock import MagicMock, patch

from modbus_connection import IllegalDataAddressError
from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the binary sensor platform only."""
    return [Platform.BINARY_SENSOR]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the binary sensor entities and their states."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_heat_pump_entities_on_a_heat_pump(hass: HomeAssistant) -> None:
    """Test a heat pump gets the heat pump and cooling sensors, and no flame."""
    assert hass.states.get("binary_sensor.gtw_08_ehc_04_heat_pump") is not None
    assert hass.states.get("binary_sensor.gtw_08_ehc_04_cooling") is not None
    assert hass.states.get("binary_sensor.gtw_08_ehc_04_flame") is None


async def test_burner_entities_on_a_boiler(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a gas boiler gets an enabled flame sensor and no heat pump sensors."""
    mock_unit.holding[129] = 0x0008  # CU-GH08
    mock_unit.fail_read(9230, IllegalDataAddressError())
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.gtw08.PLATFORMS", [Platform.BINARY_SENSOR]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    prefix = "binary_sensor.gtw_08_ehc_04"
    assert hass.states.get(f"{prefix}_flame").state == "off"
    assert hass.states.get(f"{prefix}_heat_pump") is None
    assert hass.states.get(f"{prefix}_cooling") is None
