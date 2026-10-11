# GTW-08 integration for Home Assistant core

The `gtw08` integration for [Home Assistant core](https://github.com/home-assistant/core), staged here until it is submitted. It connects a heat pump or boiler from the BDR Thermea group (Remeha, Brötje, De Dietrich, Baxi) through a GTW-08 Modbus gateway, using the device library [gtw08-modbus](https://github.com/AlCalzone/gtw08-modbus).

The layout mirrors core's, so the files copy straight across:

```text
homeassistant/components/gtw08/   the integration
tests/components/gtw08/           its tests and snapshots
docs/gtw08.markdown               the page for home-assistant.io
```

## What it does

- A config flow with three link types: an RS-485 adapter, an RS-485 to Ethernet converter speaking Modbus TCP, and a transparent converter carrying RTU over TCP. Baud rate, parity and unit ID default to the gateway's factory settings: 9600 baud, no parity, unit 100.
- Two coordinators: readings every 30 seconds, and the zone and remote control settings every minute.
- Sensors for temperatures, water pressure, status, power, COP, energy counters, service state, board errors and the cascade. Sensors the appliance has no value for are not created.
- Binary sensors for what runs and for problems such as low water pressure.
- A child device per zone. Room heating zones get a climate entity, other zones an operating mode select. Every zone that is not a hot water zone gets heating curve numbers.
- Two admin-only actions for the gateway's remote control of the heat demand, and a binary sensor that shows when it is on. The actions go through the library's `async_request()` and `async_stop()`, which write the registers in order and roll back on failure.
- A reload when a block or zone the gateway was still fetching at startup answers, so its entities appear.
- Diagnostics with the raw register dump. The serial number registers, the host and the serial port are left out.

It takes its Modbus unit from core's `modbus` integration with `async_get_unit`, so it shares the serial port or converter with any other integration on the same bus.

The config entry's unique ID is the producer serial number in register 7228 when the appliance reports one. Without it the entry has no unique ID, and the flow refuses a second entry on the same link and unit ID.

## Trying it in a core checkout

```bash
script/install-into-core.sh ../core
```

The script copies the integration and its tests into the checkout and adds it to `.strict-typing`. When the checkout has a `.venv`, it also regenerates the translations, `CODEOWNERS`, the generated config flow list, `mypy.ini` and `requirements_all.txt`.

Until `gtw08-modbus` is on PyPI, install it from git into core's venv:

```bash
uv pip install --python ../core/.venv/bin/python "gtw08-modbus @ git+https://github.com/AlCalzone/gtw08-modbus@main"
```

Then run the tests from the core checkout:

```bash
.venv/bin/python -m pytest tests/components/gtw08
```

CI does the same against core's `dev` branch on every push and once a week.

## Before submitting

- Publish `gtw08-modbus` 0.1.0 to PyPI. The manifest pins it. `dependency-transparency` stays `todo` until then.
- Add the brand to [home-assistant/brands](https://github.com/home-assistant/brands). Until then hassfest fails the `brands` rule of the Bronze tier, which every new integration has to reach. Remeha, Brötje, De Dietrich and Baxi could each become a virtual integration that points to `gtw08`.
- Open the documentation pull request on home-assistant.io with `docs/gtw08.markdown`.
- Test against a real gateway. The register map comes from the manufacturer's configuration manual 7854678, version 01 of 15 September 2023, and has only been tested against the mock.
