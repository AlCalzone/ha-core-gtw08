"""Tests for the GTW-08 number platform."""

from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from tests.common import MockConfigEntry, snapshot_platform


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the number platform only."""
    return [Platform.NUMBER]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the number entities and their states."""
    await snapshot_platform(hass, entity_registry, snapshot, init_integration.entry_id)


@pytest.mark.parametrize(
    ("entity_id", "value", "address", "expected"),
    [
        pytest.param(
            "number.gtw_08_ehc_04_zone_3_heating_curve_gradient",
            0.9,
            1698,
            9,
            id="gradient",
        ),
        pytest.param(
            "number.gtw_08_ehc_04_zone_1_heating_curve_footpoint",
            22,
            675,
            220,
            id="footpoint",
        ),
        pytest.param(
            "number.gtw_08_ehc_04_zone_1_fixed_flow_temperature",
            45,
            648,
            4500,
            id="fixed_flow",
        ),
    ],
)
@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_set_value(
    hass: HomeAssistant,
    mock_unit: MockModbusUnit,
    entity_id: str,
    value: float,
    address: int,
    expected: int,
) -> None:
    """Test setting a value writes its register."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        blocking=True,
    )
    assert mock_unit.holding[address] == expected
