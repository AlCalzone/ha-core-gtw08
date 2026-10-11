"""Tests for setting up and unloading the GTW-08 integration."""

from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import (
    GatewayPathUnavailableError,
    GatewayTargetError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit
import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.gtw08.const import DOMAIN, SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from . import MOCK_ENTRY_DATA, SERIAL_NUMBER

from tests.common import MockConfigEntry, async_fire_time_changed
from tests.typing import WebSocketGenerator

OUTDOOR = "sensor.gtw_08_ehc_04_outdoor_temperature"
ZONE_1_FLOW = "sensor.gtw_08_ehc_04_zone_1_flow_temperature"


@pytest.fixture
def platforms() -> list[Platform]:
    """Set up the sensor platform only."""
    return [Platform.SENSOR]


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the entry loads and unloads."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get(OUTDOOR).state == "-3.5"

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_devices(
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the appliance and its zones register as devices."""
    appliance = device_registry.async_get_device_by_identifier(
        (DOMAIN, str(SERIAL_NUMBER)), init_integration.entry_id
    )
    assert appliance == snapshot(name="appliance")
    zones = [
        device_registry.async_get_child_device_by_identifier(
            (DOMAIN, f"{SERIAL_NUMBER}_zone_{number}"), init_integration.entry_id
        )
        for number in (1, 2, 3)
    ]
    assert [zone.parent_device_id for zone in zones] == [appliance.id] * 3
    assert [zone.name for zone in zones] == ["Zone 1", "Zone 2", "Zone 3"]


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ModbusTimeoutError(), id="timeout"),
        pytest.param(GatewayPathUnavailableError(), id="no_appliance_on_bus"),
        pytest.param(GatewayTargetError(), id="still_fetching"),
    ],
)
async def test_setup_retries_when_the_gateway_does_not_answer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
    error: Exception,
) -> None:
    """Test a gateway that does not answer puts the entry into retry."""
    mock_unit.fail_requests(error)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retries_without_boards(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a gateway that reports no board puts the entry into retry."""
    mock_unit.holding[128] = 0
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retries_without_a_board_count(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
) -> None:
    """Test a gateway that has not read the board count yet puts the entry into retry."""
    mock_unit.holding[128] = 0xFF
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_when_the_link_is_in_use(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a port held with other line settings fails the entry."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.gtw08.async_get_unit",
        side_effect=HomeAssistantError("in use"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_entities_follow_their_component(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a component that stops answering takes only its own entities along."""
    mock_unit.fail_read(1100, GatewayTargetError())
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(ZONE_1_FLOW).state == STATE_UNAVAILABLE
    assert hass.states.get(OUTDOOR).state == "-3.5"
    assert "zones failed to refresh and is unavailable" in caplog.text

    mock_unit.fail_read(1100, None)
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(ZONE_1_FLOW).state == "34.8"
    assert "zones is available again" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(ModbusTimeoutError(), id="timeout"),
        pytest.param(GatewayTargetError(), id="every_block_refused"),
    ],
)
async def test_everything_unavailable_when_nothing_answers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
    error: Exception,
) -> None:
    """Test a poll that gets no answer at all marks every entity unavailable."""
    mock_unit.fail_requests(error)
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(OUTDOOR).state == STATE_UNAVAILABLE


async def test_remove_stale_zone(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Test a zone the appliance no longer reports can be removed, a current one not."""
    appliance = device_registry.async_get_device_by_identifier(
        (DOMAIN, str(SERIAL_NUMBER)), init_integration.entry_id
    )
    assert appliance is not None
    stale = device_registry.async_get_or_create_child(
        config_entry_id=init_integration.entry_id,
        identifiers={(DOMAIN, f"{SERIAL_NUMBER}_zone_9")},
        parent_device_id=appliance.id,
    )
    current = device_registry.async_get_child_device_by_identifier(
        (DOMAIN, f"{SERIAL_NUMBER}_zone_1"), init_integration.entry_id
    )
    assert current is not None
    assert await async_setup_component(hass, "config", {})
    client = await hass_ws_client(hass)

    for device, removable in ((current, False), (stale, True)):
        await client.send_json_auto_id(
            {
                "type": "config/device_registry/remove",
                "device_id": device.id,
            }
        )
        response = await client.receive_json()
        assert response["success"] is removable


async def test_entry_without_serial_number(
    hass: HomeAssistant,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test an entry without a serial number keys its devices by entry ID."""
    mock_unit.holding[7228] = [0, 0]
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, title="GTW-08")
    entry.add_to_hass(hass)
    with patch("homeassistant.components.gtw08.PLATFORMS", [Platform.SENSOR]):
        await hass.config_entries.async_setup(entry.entry_id)

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    assert device.serial_number is None


async def test_reload_when_a_pending_block_answers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    mock_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a block the gateway was still fetching gets its entities later."""
    cop = "sensor.gtw_08_ehc_04_coefficient_of_performance"
    mock_unit.fail_read(9230, GatewayTargetError())
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.gtw08.PLATFORMS", [Platform.SENSOR]):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(cop) is None

        mock_unit.fail_read(9230, None)
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(cop).state == "4.21"
