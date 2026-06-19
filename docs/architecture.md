# System Architecture

This project is a virtual industrial automation cell deployed across multiple virtual machines on a Proxmox VE host.

The purpose of the architecture is to demonstrate a realistic automation system using simulation, PLC-style control, industrial communication, SCADA visualisation, and historian logging.

## High-Level Architecture

```text
Proxmox VE Host
│
├── twincat-eng
│   └── TwinCAT engineering / PLC logic
│
├── webots-sim
│   └── Simulated machine / conveyor / automation cell
│
├── gateway
│   └── Python services, OPC UA, MQTT, protocol bridging
│
├── automation-ignition-scada
│   └── Ignition SCADA dashboards, tags, alarms, trends
│
└── postgres-historian
    └── PostgreSQL historian database
```

## Data Flow

```text
Webots Simulation
        │
        │ simulated sensors, actuators, machine state
        ▼
Gateway VM
Python / OPC UA / MQTT
        │
        ├──► Ignition SCADA
        │       dashboards, operator controls, alarms, trends
        │
        ├──► PostgreSQL Historian
        │       telemetry, events, alarms, production counts
        │
        └──► TwinCAT Engineering VM
                PLC logic, sequencing, control testing
```

## VM Roles

| VM                          |      IP Address | Role                                                                     |
| --------------------------- | --------------: | ------------------------------------------------------------------------ |
| `twincat-eng`               | `192.168.1.181` | TwinCAT engineering and PLC/runtime testing                              |
| `webots-sim`                | `192.168.1.182` | Webots simulation of the virtual automation cell                         |
| `automation-ignition-scada` | `192.168.1.183` | Ignition SCADA server for dashboards, alarms, and trends                 |
| `postgres-historian`        | `192.168.1.184` | PostgreSQL historian for telemetry and event storage                     |
| `gateway`                   | `192.168.1.187` | Python-based protocol gateway for OPC UA, MQTT, and database integration |

## Architecture Layers

For the control responsibility model between Webots, TwinCAT, Ignition,
gateway services, and the historian, see
[`control-architecture.md`](control-architecture.md).

### 1. Simulation Layer

The `webots-sim` VM provides the virtual plant. It will simulate a manufacturing automation cell with objects such as conveyors, sensors, actuators, machine states, and faults.

The simulation layer represents the physical process that would normally exist on a factory floor.

### 2. Control and Integration Layer

The `gateway` VM provides the integration layer between the simulation, SCADA, historian, and PLC environment.

The gateway will initially expose test values using OPC UA. Later it will connect Webots simulation values to Ignition and PostgreSQL.

Planned gateway responsibilities include:

* OPC UA server/client services
* MQTT bridge services
* Python data processing
* Historian inserts into PostgreSQL
* Command handling between SCADA and simulation
* Future TwinCAT integration

### 3. PLC / Engineering Layer

The `twincat-eng` VM provides the Beckhoff TwinCAT engineering environment.

TwinCAT will be used to demonstrate PLC-style automation concepts such as:

* Machine sequencing
* Start/stop/reset control
* Manual and automatic modes
* Interlocks
* Fault handling
* Production counters
* Structured tags and control logic

### 4. SCADA Layer

The `automation-ignition-scada` VM provides the operator interface using Ignition.

Ignition will be used for:

* Machine status displays
* Operator controls
* OPC UA tag browsing
* Alarm display
* Trend charts
* Production counters
* System overview screens

### 5. Historian Layer

The `postgres-historian` VM provides the PostgreSQL historian database.

The historian stores:

* Machine telemetry
* Machine events
* Alarm records
* Production counts

The initial project database is named `industrial_cell`.

## Current Network Phase

The first phase uses the main LAN with static DHCP reservations configured in the main OPNsense router.

```text
Main OPNsense Router
192.168.1.1
        │
        ▼
Proxmox Host
        │
        ├── twincat-eng               192.168.1.181
        ├── webots-sim                192.168.1.182
        ├── automation-ignition-scada 192.168.1.183
        ├── postgres-historian        192.168.1.184
        └── gateway                   192.168.1.187
```

This simple network layout is being used first to reduce routing complexity while the core automation system is built.

## Future Network Phase

A later phase may introduce a virtual OPNsense firewall and an isolated OT lab subnet.

This would allow the project to demonstrate:

* Industrial network segmentation
* Firewall rules
* Controlled access between home LAN and lab network
* OT/IT separation concepts
* Lab DMZ design

Example future layout:

```text
Main OPNsense Router
        │
        ▼
Virtual OPNsense
        │
        ▼
Industrial Automation Lab Network
```

## First Integration Milestone

The first major integration milestone is:

```text
Gateway OPC UA Server
        │
        ▼
Ignition OPC UA Client
        │
        ▼
Live test tag displayed in Ignition
```

This milestone proves that the SCADA communication backbone is working.

After that, the next milestone is:

```text
Webots simulated value
        │
        ▼
Gateway OPC UA tag
        │
        ▼
Ignition dashboard
        │
        ▼
PostgreSQL historian
```

## Portfolio Purpose

This architecture is designed to demonstrate practical industrial automation knowledge across multiple layers:

* PLC engineering
* Simulation
* SCADA
* OPC UA
* Database/historian design
* Linux services
* Proxmox deployment
* Industrial network planning

The project forms part of an Industrial Automation and Digital Systems portfolio.
