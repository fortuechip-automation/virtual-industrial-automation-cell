# Build Log

## Baseline Infrastructure

The initial VM infrastructure for the virtual industrial automation cell has been created on Proxmox.

### VM Stack

| VM                          |      IP Address | Purpose                     |
| --------------------------- | --------------: | --------------------------- |
| `twincat-eng`               | `192.168.1.181` | TwinCAT engineering/runtime |
| `webots-sim`                | `192.168.1.182` | Webots simulation           |
| `automation-ignition-scada` | `192.168.1.183` | Ignition SCADA              |
| `postgres-historian`        | `192.168.1.184` | PostgreSQL historian        |
| `gateway`                   | `192.168.1.187` | OPC UA/MQTT/Python gateway  |

### Completed Setup

* Created all five project VMs in Proxmox.
* Configured static DHCP reservations in the main OPNsense router.
* Confirmed SSH access to all Linux VMs.
* Configured NoMachine access for the Windows TwinCAT engineering VM.
* Installed and launched Webots on the `webots-sim` VM.
* Installed PostgreSQL 16 on the `postgres-historian` VM.
* Created the `industrial_cell` database.
* Created the initial historian schema for telemetry, events, alarms, and production counts.

### Current Project Phase

The project is currently in the software installation and integration phase.

The next major milestone is to create a simple OPC UA server on the `gateway` VM and connect Ignition SCADA to it as an OPC UA client.


## Gateway OPC UA Test Server

A Python-based OPC UA test server has been created on the `gateway` VM.

The server exposes simulated machine tags for the virtual industrial automation cell:

- `MachineState`
- `ConveyorRunning`
- `ConveyorSpeed`
- `EntrySensor`
- `ExitSensor`
- `PartCount`
- `FaultActive`

The server runs on:

```text
opc.tcp://192.168.1.187:4840/industrial-cell/server/
```

## Ignition OPC UA Connection

Ignition has been connected to the Python OPC UA test server running on the `gateway` VM.

### OPC UA Endpoint

```text
opc.tcp://192.168.1.187:4840/industrial-cell/server/
```

### OPC UA Server Structure

The Python OPC UA test server exposes machine simulation tags under:

```text
Objects
└── Cell_01
    ├── MachineState
    ├── ConveyorRunning
    ├── ConveyorSpeed
    ├── EntrySensor
    ├── ExitSensor
    ├── FaultActive
    └── PartCount
```

### Imported OPC Tags

The following OPC UA tags are exposed under `Objects > Cell_01`:

* `MachineState`
* `ConveyorRunning`
* `ConveyorSpeed`
* `EntrySensor`
* `ExitSensor`
* `FaultActive`
* `PartCount`

`PartCount` was successfully imported into the Ignition default tag provider and confirmed updating live.

### Current Integration Status

```text
gateway OPC UA server → Ignition OPC UA client → live Ignition tag
```

This confirms that the first industrial communication path between the gateway layer and SCADA layer is working.


## Ignition Perspective Dashboard

A basic Ignition Perspective dashboard has been created for the virtual industrial automation cell.

The dashboard displays live OPC UA values from the `gateway` VM and converts raw boolean values into operator-friendly text.

### Displayed Values

- `MachineState`
- `PartCount`
- `ConveyorSpeed`
- `ConveyorRunning`
- `EntrySensor`
- `ExitSensor`
- `FaultActive`

### Operator-Friendly Display

Boolean values are displayed as readable status text:

| Tag | False State | True State |
|---|---|---|
| `ConveyorRunning` | `Stopped` | `Running` |
| `EntrySensor` | `Clear` | `Detected` |
| `ExitSensor` | `Clear` | `Detected` |
| `FaultActive` | `Normal` | `Fault` |

### Integration Path

```text
Python OPC UA test server
        ↓
Ignition OPC UA connection
        ↓
Ignition tag provider
        ↓
Perspective dashboard
```


## Physics-First Webots MVP

A fresh Webots MVP has been added under `webots/` and should be treated as the
active simulation source.

### Added Files

* `webots/worlds/industrial_cell_mvp.wbt`
* `webots/controllers/industrial_cell_supervisor/industrial_cell_supervisor.py`
* `webots/README.md`

### Simulation Behaviour

The MVP includes:

* Webots `Track` conveyor driven by a `LinearMotor`
* Physical carton `Solid` with `boundingObject` and `Physics`
* Belt/carton friction configured with `ContactProperties`
* Entry, station, and exit `DistanceSensor` photoeyes
* TCP state publishing on port `9000`
* Manual keyboard controls for start, stop, reset, and fault injection

The supervisor no longer moves the carton during normal operation. It drives the
belt motor and reads physical sensor devices. Reset still uses supervisor access
to place the carton back at the infeed.

### Gateway Interface

The Webots supervisor listens on TCP port `9000` and publishes newline-delimited
JSON about every 100 ms. This matches the gateway bridge in
`src/gateway/opcua_server.py`.

Current intended runtime path:

```text
Webots supervisor 192.168.1.182:9000
        ↓
Gateway OPC UA server 192.168.1.187:4840
        ↓
Ignition Perspective dashboard
```
