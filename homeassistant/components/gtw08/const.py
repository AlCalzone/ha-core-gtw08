"""Constants for the GTW-08 integration."""

from datetime import timedelta
from typing import Final, Literal

DOMAIN: Final = "gtw08"

DEFAULT_NAME: Final = "GTW-08"

CONF_BAUDRATE: Final = "baudrate"
CONF_PARITY: Final = "parity"
CONF_UNIT_ID: Final = "unit_id"

TYPE_SERIAL: Final = "serial"
TYPE_TCP: Final = "tcp"
TYPE_RTU_OVER_TCP: Final = "rtu_over_tcp"

# The gateway's factory settings: 9600 baud, no parity, unit 100.
DEFAULT_BAUDRATE: Final = 9600
DEFAULT_PARITY: Final = "none"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT_ID: Final = 100

BAUDRATES: Final = (9600, 19200, 38400, 57600)
# PARITIES maps the form's parity names to the serial line's letters.
PARITIES: Final[dict[str, Literal["N", "O", "E"]]] = {
    "none": "N",
    "odd": "O",
    "even": "E",
}

# A poll takes a few seconds at 9600 baud. Heating moves slowly.
SCAN_INTERVAL: Final = timedelta(seconds=30)
# Zone settings change from the appliance's own display too.
SETTINGS_SCAN_INTERVAL: Final = timedelta(minutes=1)
