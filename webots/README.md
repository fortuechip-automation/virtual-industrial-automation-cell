# Webots Simulation

This folder contains the repo-native Webots simulation for the virtual
industrial automation cell.

## Design Direction

The MVP is physics-first:

- the conveyor is a Webots `Track` driven by a `LinearMotor`
- the carton is a physical `Solid` with `boundingObject` and `Physics`
- belt/carton friction is configured with `ContactProperties`
- entry, station, and exit photoeyes are Webots `DistanceSensor` devices
- the supervisor does not move the carton during normal operation

The controller supports two control modes:

- `demo` - local Webots demo mode. The conveyor auto-runs and reloads cartons.
- `plc` - PLC boundary mode. Webots waits for external I/O commands and does
  not make production sequencing decisions.

The intended control architecture is:

```text
TwinCAT PLC VM <-> simulated I/O protocol <-> Webots physics plant VM
```

Webots should act like the physical plant, while TwinCAT owns the control
logic. In PLC mode, Webots should expose sensor inputs and accept actuator
outputs instead of making sequencing decisions itself.

The supervisor is currently still used for:

- driving the belt motor
- reading photoeye values
- resetting/reloading the carton to the infeed position
- publishing state to the gateway over TCP

## Files

- `worlds/industrial_cell_mvp.wbt` - physical conveyor, carton, rails, stops, and photoeyes.
- `controllers/industrial_cell_supervisor/industrial_cell_supervisor.py` - belt motor control, sensor reads, reset, and TCP publisher.

## Run In Demo Mode

Open this world on the `webots-sim` VM:

```text
webots/worlds/industrial_cell_mvp.wbt
```

With the Webots window focused:

- `S` starts the conveyor.
- `T` stops the conveyor.
- `R` resets the carton and clears faults.
- `F` triggers a manual fault.

The default mode is `demo`, so this is equivalent to:

```bash
WEBOTS_CELL_MODE=demo webots webots/worlds/industrial_cell_mvp.wbt
```

## Run In PLC Mode

PLC mode keeps the physical simulation alive but stops Webots from owning the
machine sequence.

```bash
WEBOTS_CELL_MODE=plc webots webots/worlds/industrial_cell_mvp.wbt
```

Current PLC mode behaviour:

- photoeyes still report real Webots `DistanceSensor` states
- the carton still has physical `Solid` / `Physics` behaviour
- the TCP publisher still exposes state on port `9000`
- the conveyor remains stopped until future external I/O commands are added
- demo-only auto counting and auto reload are disabled

## Gateway Integration

The controller listens on:

```text
0.0.0.0:9000
```

It publishes newline-delimited JSON about every 100 ms. This keeps the existing
gateway path intact while replacing the old supervisor-driven part motion with
real belt/contact physics.

Planned PLC I/O integration:

- PLC reads: `PE_ENTRY`, `PE_STATION`, `PE_EXIT`, motor feedback, jam/fault state.
- PLC writes: conveyor run command, speed command, reset, feed carton, fault inject.
- First target protocol: Modbus TCP as a simple simulated remote I/O rack.
- Later target protocol: ADS once TwinCAT AMS routes are configured between VMs.
