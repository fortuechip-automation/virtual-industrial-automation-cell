# Control Architecture

This project is structured as a virtual industrial cell with clear separation
between physical simulation, PLC control, SCADA, gateway services, and historian
logging.

## Layered View

```text
Operator / HMI
    |
Ignition SCADA
    |
TwinCAT PLC
    |
Simulated I/O protocol
    |
Webots physical plant
```

## Webots: Physical Simulation

Webots is the machine body.

It should simulate:

- conveyor physics
- cartons
- photoeyes
- jams
- motor behaviour
- mechanical delays
- faults

Webots should not decide production logic in PLC mode. It should expose
simulated sensors and accept actuator commands.

Example:

```text
PLC writes: conveyor run command
Webots responds: belt motor moves
Webots reports: entry sensor blocked
```

## TwinCAT PLC: Real Control Logic

TwinCAT is the machine brain.

It should handle:

- start/stop sequence
- interlocks
- part counting
- fault detection
- reset sequence
- mode handling
- timers
- alarms

The PLC should decide:

```text
Should the conveyor run?
Did a carton take too long to reach exit?
Is this a jam?
Should the system fault?
```

## Ignition: HMI / SCADA

Ignition should not directly control Webots physics. It should talk to the PLC
or gateway layer.

Ignition handles:

- operator screens
- start/stop/reset buttons
- alarm display
- trends
- dashboards
- manual mode commands
- production counters

Ignition sends operator intent, not raw physics commands.

Example:

```text
Operator clicks Start in Ignition
Ignition writes Start request to PLC
PLC checks permissives
PLC commands conveyor output
Webots moves conveyor
```

## Gateway: Protocol Bridge / Data Normalizer

The gateway sits between systems that speak different protocols.

Possible jobs:

- read Webots TCP, Modbus, or ADS data
- expose clean OPC UA tags to Ignition
- normalize tag names
- buffer state
- publish MQTT later if needed
- isolate Webots from SCADA details

In the final version, the gateway may sit between:

```text
TwinCAT -> OPC UA -> Ignition
Webots -> Modbus/ADS/TCP -> TwinCAT or gateway
Gateway -> Historian
```

The gateway should not become the PLC. It should translate and publish data,
not own machine sequencing.

## Historian: Long-Term Memory of the Plant

The historian records what happened.

It stores:

- sensor changes
- motor states
- counts
- alarms
- faults
- cycle times
- simulated process values
- operator actions

The historian should not control anything. It is for analysis, replay,
dashboards, and proof of behaviour.

Example useful historian data:

```text
carton cycle time
entry-to-exit time
jam frequency
motor run hours
fault count by type
operator reset count
```

## Recommended Repository Structure

```text
webots/
  worlds/
  controllers/
  README.md

plc/
  twincat/
  io-map/
  docs/

ignition/
  perspective/
  tags/
  gateway-backups/

gateway/
  opcua/
  modbus_bridge/
  config/

historian/
  schema/
  queries/
  dashboards/

docs/
  architecture.md
  control-architecture.md
  io-map.md
  build-log.md
  network-layout.md
```

## Recommended Data Flow For The First Real Version

```text
Webots physics plant
    <-> Modbus TCP simulated I/O
TwinCAT PLC
    <-> OPC UA / ADS
Ignition HMI
    |
Historian
```

## First Target

Keep the first target simple:

1. Webots exposes simulated I/O over Modbus TCP.
2. TwinCAT reads and writes that I/O.
3. TwinCAT owns all logic.
4. Ignition talks to TwinCAT or the gateway for HMI.
5. Historian logs the final tag and state stream.

This gives the project a realistic automation stack without mixing
responsibilities.

## Current Phase 2 Boundary

The Webots controller now has an explicit mode boundary:

```text
WEBOTS_CELL_MODE=demo
WEBOTS_CELL_MODE=plc
```

In `demo` mode, Webots keeps the known-good behaviour: the conveyor runs,
cartons are automatically reloaded, and local counting is available for
simulation verification.

In `plc` mode, Webots stops making production decisions. It still reports
physical sensor state and publishes machine state, but the conveyor remains
stopped until an external I/O protocol is added. This is the staging point for
the next phase: Modbus TCP simulated I/O.
