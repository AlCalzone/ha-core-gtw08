"""Fixtures for the GTW-08 integration tests."""

from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from modbus_connection import ModbusSerialParams, ModbusTcpParams
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest

from homeassistant.components.gtw08.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import MOCK_ENTRY_DATA, MOCK_TITLE, SERIAL_NUMBER, seed_appliance

from tests.common import MockConfigEntry


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        "homeassistant.components.gtw08.async_setup_entry",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry


@pytest.fixture(autouse=True)
def no_retry_delay() -> Generator[None]:
    """Let the library ask again without waiting."""
    with (
        patch("homeassistant.components.gtw08.RETRY_DELAY", 0),
        patch("homeassistant.components.gtw08.config_flow.RETRY_DELAY", 0),
    ):
        yield


@pytest.fixture
def mock_connection() -> MockModbusConnection:
    """A fake Modbus link with an appliance behind the gateway."""
    connection = MockModbusConnection()
    seed_appliance(connection.for_unit(100))
    return connection


@pytest.fixture
def mock_unit(mock_connection: MockModbusConnection) -> MockModbusUnit:
    """The gateway's unit on the mock connection."""
    return mock_connection.for_unit(100)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Mock a GTW-08 config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(SERIAL_NUMBER),
        data=MOCK_ENTRY_DATA,
        title=MOCK_TITLE,
    )


@pytest.fixture
def mock_get_unit(mock_connection: MockModbusConnection) -> Generator[MagicMock]:
    """Hand out units on the mock connection when the entry sets up."""
    with patch(
        "homeassistant.components.gtw08.async_get_unit",
        side_effect=lambda hass, entry, params, unit_id: mock_connection.for_unit(
            unit_id
        ),
    ) as mock_get_unit:
        yield mock_get_unit


@pytest.fixture
def mock_temporary_unit(
    mock_connection: MockModbusConnection,
) -> Generator[MagicMock]:
    """Hand out units on the mock connection for the config flow and removal."""

    @asynccontextmanager
    async def _get_temporary_unit(
        hass: HomeAssistant,
        params: ModbusSerialParams | ModbusTcpParams,
        unit_id: int,
    ) -> AsyncIterator[MockModbusUnit]:
        yield mock_connection.for_unit(unit_id)

    with (
        patch(
            "homeassistant.components.gtw08.config_flow.async_get_temporary_unit",
            side_effect=_get_temporary_unit,
        ) as mock_temporary_unit,
        patch(
            "homeassistant.components.gtw08.async_get_temporary_unit",
            side_effect=_get_temporary_unit,
        ),
    ):
        yield mock_temporary_unit


@pytest.fixture
def platforms() -> list[Platform]:
    """The platforms to set up; all of them unless a test narrows it."""
    return [
        Platform.BINARY_SENSOR,
        Platform.CLIMATE,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
    ]


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_get_unit: MagicMock,
    platforms: list[Platform],
) -> MockConfigEntry:
    """Set up the GTW-08 integration for testing."""
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.gtw08.PLATFORMS", platforms):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    return mock_config_entry
