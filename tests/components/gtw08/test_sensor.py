"""Tests for the GTW-08 sensor platform."""

from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.gtw08.const import SCAN_INTERVAL
from homeassistant.const import STATE_UNKNOWN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, async_fire_time_changed, snapshot_platform

PREFIX = "sensor.gtw_08_ehc_04"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the sensor platform only."""
    return [Platform.SENSOR]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the sensor entities and their states."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.usefixtures("init_integration")
async def test_board_error(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a board error shows up in the board's sensors."""
    mock_unit.holding[532] = [531, 6, 0xFFFE, 0]
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(f"{PREFIX}_board_1_ehc_04_error_code").state == "531"
    assert hass.states.get(f"{PREFIX}_board_1_ehc_04_error_type").state == "warning"
    assert hass.states.get(f"{PREFIX}_board_2_scb_04_error_code").state == STATE_UNKNOWN


async def test_cascade(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a cascade with producers gets its sensors."""
    mock_unit.holding.update({7101: 6010, 7102: 3, 7151: [0, 245], 7159: 3, 7164: 5020})
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.gtw08.PLATFORMS", [Platform.SENSOR]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(f"{PREFIX}_cascade_flow_temperature").state == "60.1"
    assert hass.states.get(f"{PREFIX}_cascade_return_temperature").state == "50.2"
    assert hass.states.get(f"{PREFIX}_cascade_state").state == "generator_ch"
    assert hass.states.get(f"{PREFIX}_cascade_requested_power").state == "24.5"
