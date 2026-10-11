"""Tests for the GTW-08 select platform."""

from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the select platform only."""
    return [Platform.SELECT]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the select entities and their states."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "option", "address", "expected"),
    [
        pytest.param(
            "select.gtw_08_ehc_04_zone_2_operating_mode",
            "scheduling",
            1161,
            0,
            id="zone_mode",
        ),
        pytest.param(
            "select.gtw_08_ehc_04_remote_control",
            "temperature",
            258,
            2,
            id="remote_control_mode",
        ),
        pytest.param(
            "select.gtw_08_ehc_04_remote_heat_demand",
            "heating",
            259,
            7,
            id="remote_heat_demand",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_select_option(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    entity_id: str,
    option: str,
    address: int,
    expected: int,
) -> None:
    """Test selecting an option writes its register."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        blocking=True,
    )
    assert mock_unit.holding[address] == expected
