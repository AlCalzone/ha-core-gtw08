"""Tests for the GTW-08 config flow."""

from typing import Any
from unittest.mock import MagicMock, patch

from modbus_connection import (
    GatewayPathUnavailableError,
    GatewayTargetError,
    ModbusSerialParams,
    ModbusTcpParams,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest

from homeassistant.components.gtw08.config_flow import (
    SECTION_MORE_OPTIONS,
    create_modbus_params,
)
from homeassistant.components.gtw08.const import (
    CONF_BAUDRATE,
    CONF_PARITY,
    CONF_UNIT_ID,
    DOMAIN,
    TYPE_RTU_OVER_TCP,
    TYPE_SERIAL,
    TYPE_TCP,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from . import MOCK_ENTRY_DATA, MOCK_TITLE, SERIAL_NUMBER, seed_appliance

from tests.common import MockConfigEntry

SERIAL_INPUT = {
    CONF_DEVICE: "/dev/ttyUSB0",
    CONF_BAUDRATE: "9600",
    CONF_PARITY: "none",
    SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 100},
}


class _RaisingTemporaryUnit:
    """Stand in for a temporary-unit context whose __aenter__ raises."""

    def __init__(self, error: Exception) -> None:
        """Initialize with the error to raise on entry."""
        self._error = error

    async def __aenter__(self) -> None:
        raise self._error

    async def __aexit__(self, *args: object) -> None:
        """No cleanup: entry never succeeded."""


async def _start(hass: HomeAssistant, step: str) -> str:
    """Open the flow and pick a connection type from the menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": step}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == step
    return result["flow_id"]


@pytest.mark.parametrize(
    ("step", "user_input", "params", "data"),
    [
        pytest.param(
            TYPE_SERIAL,
            {**SERIAL_INPUT, CONF_BAUDRATE: "19200", CONF_PARITY: "even"},
            ModbusSerialParams(device="/dev/ttyUSB0", baudrate=19200, parity="E"),
            {
                CONF_TYPE: TYPE_SERIAL,
                CONF_DEVICE: "/dev/ttyUSB0",
                CONF_BAUDRATE: 19200,
                CONF_PARITY: "even",
                CONF_UNIT_ID: 100,
            },
            id="serial",
        ),
        pytest.param(
            TYPE_TCP,
            {
                CONF_HOST: "Gateway.local",
                CONF_PORT: 502,
                SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 100},
            },
            ModbusTcpParams(host="gateway.local", port=502),
            {
                CONF_TYPE: TYPE_TCP,
                CONF_HOST: "gateway.local",
                CONF_PORT: 502,
                CONF_UNIT_ID: 100,
            },
            id="tcp",
        ),
        pytest.param(
            TYPE_RTU_OVER_TCP,
            {
                CONF_HOST: "192.168.1.60",
                CONF_PORT: 8899,
                CONF_BAUDRATE: "9600",
                CONF_PARITY: "odd",
                SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 100},
            },
            ModbusSerialParams(
                device="socket://192.168.1.60:8899", baudrate=9600, parity="O"
            ),
            {
                CONF_TYPE: TYPE_RTU_OVER_TCP,
                CONF_HOST: "192.168.1.60",
                CONF_PORT: 8899,
                CONF_BAUDRATE: 9600,
                CONF_PARITY: "odd",
                CONF_UNIT_ID: 100,
            },
            id="rtu_over_tcp",
        ),
    ],
)
@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow(
    hass: HomeAssistant,
    mock_temporary_unit: MagicMock,
    step: str,
    user_input: dict[str, Any],
    params: ModbusSerialParams | ModbusTcpParams,
    data: dict[str, Any],
) -> None:
    """Test each link type probes the appliance and creates an entry."""
    flow_id = await _start(hass, step)
    result = await hass.config_entries.flow.async_configure(flow_id, user_input)

    mock_temporary_unit.assert_called_once_with(hass, params, 100)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_TITLE
    assert result["data"] == data
    assert result["result"].unique_id == str(SERIAL_NUMBER)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(ModbusTimeoutError(), "cannot_connect", id="timeout"),
        pytest.param(
            GatewayPathUnavailableError(), "cannot_connect", id="no_appliance_on_bus"
        ),
        pytest.param(HomeAssistantError("in use"), "cannot_connect", id="in_use"),
    ],
)
@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_user_flow_cannot_connect(
    hass: HomeAssistant, error: Exception, expected: str
) -> None:
    """Test a failed probe shows an error and the flow recovers."""
    flow_id = await _start(hass, TYPE_SERIAL)
    with patch(
        "homeassistant.components.gtw08.config_flow.async_get_temporary_unit",
        return_value=_RaisingTemporaryUnit(error),
    ):
        result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_user_flow_no_appliance(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a gateway that reports no board behind it is refused."""
    mock_unit.holding[128] = 0
    flow_id = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_appliance"}

    mock_unit.holding[128] = 2
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_user_flow_gateway_not_ready(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a gateway without a board count yet shows an error until it has one."""
    mock_unit.holding[128] = 0xFF
    flow_id = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_unit.holding[128] = 2
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test an appliance that is already set up aborts the flow."""
    mock_config_entry.add_to_hass(hass)
    flow_id = await _start(hass, TYPE_TCP)
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_HOST: "192.168.1.60",
            CONF_PORT: 502,
            SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 100},
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_user_flow_same_link_without_serial_number(
    hass: HomeAssistant, mock_connection: MockModbusConnection
) -> None:
    """Test a second entry on the same link aborts without a serial number."""
    for unit_id in (100, 101):
        unit = mock_connection.for_unit(unit_id)
        seed_appliance(unit)
        unit.holding[7228] = [0, 0]
    MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA).add_to_hass(hass)
    flow_id = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    flow_id = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {**SERIAL_INPUT, SECTION_MORE_OPTIONS: {CONF_UNIT_ID: 101}}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id is None


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_reconfigure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test reconfiguring moves the entry to another port."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SERIAL_INPUT, CONF_DEVICE: "/dev/ttyUSB1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_DEVICE] == "/dev/ttyUSB1"


@pytest.mark.usefixtures("mock_temporary_unit")
async def test_reconfigure_line_settings_of_a_loaded_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a loaded entry lets go of its link while the new settings are probed."""
    result = await init_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SERIAL_INPUT, CONF_BAUDRATE: "19200"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_BAUDRATE] == 19200
    assert init_integration.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_temporary_unit")
async def test_reconfigure_other_appliance(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_unit: MockModbusUnit,
) -> None:
    """Test reconfiguring onto another appliance aborts and keeps the entry."""
    mock_unit.holding[7228] = [0, 1]
    result = await init_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SERIAL_INPUT, CONF_BAUDRATE: "19200"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert init_integration.data[CONF_BAUDRATE] == 9600
    assert init_integration.state is ConfigEntryState.LOADED


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_reconfigure_cannot_connect(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test a failed probe while reconfiguring shows an error."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    with patch(
        "homeassistant.components.gtw08.config_flow.async_get_temporary_unit",
        return_value=_RaisingTemporaryUnit(ModbusTimeoutError()),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], SERIAL_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], SERIAL_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_user_flow_serial_number_still_pending(
    hass: HomeAssistant, mock_unit: MockModbusUnit
) -> None:
    """Test a serial number the gateway is still fetching asks to try again."""
    mock_unit.fail_read(7228, GatewayTargetError())
    flow_id = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_ready"}

    mock_unit.fail_read(7228, None)
    result = await hass.config_entries.flow.async_configure(flow_id, SERIAL_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == str(SERIAL_NUMBER)


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_same_link_aborts_before_probing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_temporary_unit: MagicMock,
) -> None:
    """Test a link already in use aborts without touching the bus."""
    mock_config_entry.add_to_hass(hass)
    flow_id = await _start(hass, TYPE_SERIAL)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {**SERIAL_INPUT, CONF_BAUDRATE: "19200"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_temporary_unit.assert_not_called()


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_reconfigure_an_entry_without_a_serial_number(
    hass: HomeAssistant,
) -> None:
    """Test an entry set up without a serial number can be reconfigured."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, title=MOCK_TITLE)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SERIAL_INPUT, CONF_DEVICE: "/dev/ttyUSB1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DEVICE] == "/dev/ttyUSB1"
    assert entry.unique_id is None


def test_rtu_over_tcp_to_an_ipv6_host() -> None:
    """Test an IPv6 converter address gets brackets in the socket URL."""
    params = create_modbus_params(
        {
            CONF_TYPE: TYPE_RTU_OVER_TCP,
            CONF_HOST: "fd00::60",
            CONF_PORT: 8899,
            CONF_BAUDRATE: 9600,
            CONF_PARITY: "none",
        }
    )
    assert params == ModbusSerialParams(device="socket://[fd00::60]:8899")


@pytest.mark.usefixtures("mock_setup_entry", "mock_temporary_unit")
async def test_reconfigure_onto_another_entrys_link(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test reconfiguring onto the link and unit of another entry aborts."""
    mock_config_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_ENTRY_DATA, CONF_DEVICE: "/dev/ttyUSB1"},
        title=MOCK_TITLE,
    )
    other.add_to_hass(hass)
    result = await other.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], SERIAL_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
