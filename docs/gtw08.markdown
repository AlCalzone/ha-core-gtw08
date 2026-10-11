---
title: GTW-08 Modbus gateway
description: Instructions on how to integrate a Remeha, Brötje, De Dietrich or Baxi heat pump or boiler with Home Assistant through a GTW-08 Modbus gateway.
ha_category:
  - Climate
  - Energy
  - Modbus-controlled
ha_release: 2026.11
ha_iot_class: Local Polling
ha_codeowners:
  - '@AlCalzone'
ha_domain: gtw08
ha_platforms:
  - binary_sensor
  - climate
  - diagnostics
  - number
  - select
  - sensor
ha_config_flow: true
ha_integration_type: device
ha_quality_scale: bronze
---

The **GTW-08 Modbus gateway** {% term integration %} connects Home Assistant to a heat pump or boiler from the BDR Thermea group, sold under the Remeha, Brötje, De Dietrich and Baxi brands. The GTW-08 gateway plugs into the appliance's L-Bus and speaks Modbus RTU on RS-485. The integration reads temperatures, status, energy counters and errors, and controls the heating zones.

## Use cases

- Watching what the heat pump does. Flow and return temperatures, status, heat output and the coefficient of performance are live sensors.
- Tracking energy. The appliance counts the electricity it consumed and the heat it delivered, for heating, hot water and cooling, so both go straight into the Energy dashboard.
- Controlling the heating per room. Each heating zone is a thermostat with schedule, manual and off modes.
- Getting told about trouble. Low water pressure, a needed reset, a due service and board error codes are sensors that automations can act on.

## Supported devices

Appliances with an L-Bus that take a GTW-08 Modbus gateway:

- Heat pumps with an EHC control unit.
- Gas and oil boilers with a CU-GH or CU-OH control unit.
- Hybrid systems, and cascades of several appliances.

Zones driven by SCB expansion boards are supported too.

## Unsupported devices

Appliances without an L-Bus connection cannot take the GTW-08. The integration does not talk to the manufacturers' cloud services.

## Prerequisites

1. Have the GTW-08 Modbus gateway installed on the appliance's L-Bus.
2. Wire the gateway's Modbus terminals to an RS-485 adapter on the Home Assistant machine, or to an RS-485 to Ethernet converter.
3. Note the gateway's settings:
   - The rotary dial sets the unit ID. Position 0 is unit 100, the default. Position F is unit 115.
   - DIP switches 1 and 2 set the baud rate. Both off is 9600, the default.
   - DIP switches 3 and 4 set the parity. Both off is none, the default.

The gateway's LED is green while it works normally. Red means it has no Modbus communication. Orange means it has no L-Bus communication with the appliance.

{% include integrations/config_flow.md %}

The integration first asks how the gateway is connected:

- **RS-485 adapter on this machine**: a USB to RS-485 adapter or a serial port.
- **RS-485 to Ethernet converter, Modbus TCP**: a converter that translates Modbus RTU to Modbus TCP.
- **RS-485 to Ethernet converter, transparent**: a converter that passes the RS-485 traffic through unchanged.

{% configuration_basic %}
Serial port:
  description: "The RS-485 adapter the gateway is wired to."
Host:
  description: "The hostname or IP address of the RS-485 to Ethernet converter."
Port:
  description: "The TCP port of the converter."
Baud rate:
  description: "The baud rate set with DIP switches 1 and 2 on the gateway. The default is `9600`."
Parity:
  description: "The parity set with DIP switches 3 and 4 on the gateway. The default is none."
Unit ID:
  description: "100 plus the position of the gateway's rotary dial. The default is `100`."
{% endconfiguration_basic %}

{% note %}
Home Assistant can share a Modbus connection between integrations. Another integration that already talks to the same serial port or converter shares the connection instead of opening a second one. They have to use the same baud rate and parity.
{% endnote %}

## Reconfiguration

If the gateway moves to another serial port, converter or unit ID, you can update the settings without removing the integration:

1. Go to {% my integrations title="**Settings** > **Devices & services**" %} and find the **GTW-08 Modbus gateway** integration.
2. Select the three-dot menu {% icon "mdi:dots-vertical" %} and choose **Reconfigure**.
3. Update the settings, then select **Submit**.

When the appliance reports a serial number, the integration accepts the new settings only if they lead to the same appliance.

## Supported functionality

The appliance is one device. Each zone it serves gets its own device, such as **Zone 1**.

### Sensors

The appliance has these sensors. Sensors for something the appliance does not have, such as the flue gas temperature of a heat pump, are not created.

- **Outdoor temperature**, **Flow temperature**, **Return temperature**, **Flue gas temperature**, **Heat pump flow temperature**, **Heat pump return temperature** and **Hot water flow setpoint**.
- **Water pressure** of the primary circuit.
- **Status** and **Sub status**: what the appliance does, as its display shows it under AM012 and AM014.
- **Relative power**, **Heat output** and **Pump speed**.
- **Season**: winter, frost protection, summer neutral band or summer.
- **Coefficient of performance**, on heat pumps.
- **Energy consumed** and **Heat delivered**, in total and split by heating, hot water, cooling and backup.
- **Starts**, **Operating hours**, **Hours since service** and **Service notification**, as diagnostic sensors. The backup stage counters are disabled by default.
- **Board error code** and **Board error type** for each control board, as diagnostic sensors. The error code is `0` while the board reports no error.
- **Cascade flow temperature**, **Cascade return temperature**, **Cascade state**, **Cascade producers** and **Cascade requested power**, when the appliance is part of a cascade.

Each zone has **Flow temperature**, **Flow temperature setpoint**, **Activity** and **Operating mode** sensors. A hot water zone shows **Hot water temperature** instead of the flow temperature. A heating zone also has a **Room temperature setpoint** sensor.

### Binary sensors

- **Heat pump**, **Pump**, **Central heating**, **Hot water** and **Cooling**: what runs right now.
- **Flame**, **Backup stage 1**, **Backup stage 2** and **Hot water backup**, disabled by default.
- **Water pressure low**, **Reset needed**, **Service required** and **Error**: problems that need attention.

Each zone has a **Pump** binary sensor.

### Climate

Each zone that heats rooms is a thermostat:

- **Auto** follows the zone's time program.
- **Heat** holds the manual room temperature.
- **Off** keeps frost protection only.

Setting a temperature while the zone is on **Auto** switches it to **Heat**, so the zone holds the new temperature.

### Selects

- **Operating mode** of each zone: scheduling, manual or off. Hot water zones have this select instead of a thermostat.
- **Remote control** and **Remote heat demand**, disabled by default. See [Remote control of the heat demand](#remote-control-of-the-heat-demand).

### Numbers

- **Heating curve gradient**, **Heating curve footpoint** and **Fixed flow temperature** of each zone that is not a hot water zone. The fixed flow temperature is disabled by default.
- **Remote power request** and **Remote temperature request**, disabled by default.

### Remote control of the heat demand

The gateway can take over the heat demand of the whole system. While **Remote control** is set to anything other than **Monitoring only**, the appliance ignores its zones:

1. Set **Remote control** to **Power**, **Temperature** or **Temperature and power**. This has to happen first.
2. Set **Remote power request** and **Remote temperature request**.
3. Set **Remote heat demand** to **Heating** or **Cooling**.

Set **Remote control** back to **Monitoring only** to hand the heat demand back to the zones.

## Examples

### Lower the living room at night

{% raw %}

```yaml
alias: "Living room night setback"
triggers:
  - trigger: time
    at: "22:30:00"
actions:
  - action: climate.set_temperature
    target:
      entity_id: climate.gtw_08_ehc_04_zone_1
    data:
      temperature: 17
```

{% endraw %}

### Notify when the water pressure is low

{% raw %}

```yaml
alias: "Heating water pressure low"
triggers:
  - trigger: state
    entity_id: binary_sensor.gtw_08_ehc_04_water_pressure_low
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "The heating's water pressure is low. Top up the installation."
```

{% endraw %}

## Data updates

The integration polls the appliance every 30 seconds, and the remote control settings every 5 minutes. At 9600 baud, one poll takes a few seconds.

If one block of registers fails to read, only the entities from that block become unavailable.

## Known limitations

- The gateway documents no register for the room temperature, so the thermostats show no current temperature.
- The gateway documents no hot water temperature setpoint. Hot water zones have an operating mode select, but no thermostat.
- Zone numbers follow the gateway's zone list, which depends on the boards fitted. The manual's table 33 lists some registers of zones 7 to 12 at addresses that break the pattern of the other zones. The integration uses the pattern.
- The meaning of a board error code is in the appliance's service manual.

## Troubleshooting

### Failed to connect

- Check the wiring: A to A, B to B, and a common ground.
- Check that the baud rate, parity and unit ID match the gateway's DIP switches and rotary dial.
- Check the gateway's LED. Red means it receives no Modbus traffic. Orange means it has lost the appliance.

### The gateway reports no appliance behind it

The gateway answers, but sees no control board on its L-Bus. Check the L-Bus cable between the gateway and the appliance, and that the appliance is powered.

### Some entities are unavailable right after setup

The gateway reads a value from the appliance the first time it is asked for it, and answers "not yet read" until then. The entities fill in after the next poll.

## Removing the integration

This integration follows standard integration removal.

{% include integrations/remove_device_service_steps.md %}
