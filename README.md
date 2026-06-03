# Virtual Industrial Automation Cell

This project demonstrates a simulated industrial automation cell using Webots, TwinCAT, OPC UA, Ignition SCADA, and PostgreSQL, deployed across multiple virtual machines on Proxmox.

## Project Objective

The objective is to build a realistic industrial automation portfolio project that demonstrates:

- PLC-style machine sequencing
- Sensors and actuators
- Start, stop, reset, manual and auto modes
- Fault handling and interlocks
- OPC UA communication
- SCADA visualisation with Ignition
- PostgreSQL historian logging
- Proxmox-based OT lab deployment
- Clear engineering documentation

## Technology Stack

| Layer | Technology |
|---|---|
| Virtualisation | Proxmox VE |
| PLC / Control | Beckhoff TwinCAT |
| Simulation | Webots |
| Protocol Gateway | Python, OPC UA, MQTT |
| SCADA | Ignition |
| Historian | PostgreSQL |
| Documentation | Markdown, diagrams, GitHub |

## VM Layout

| VM | IP Address | Purpose |
|---|---:|---|
| `twincat-eng` | `192.168.1.181` | TwinCAT engineering/runtime |
| `webots-sim` | `192.168.1.182` | Webots simulation |
| `automation-ignition-scada` | `192.168.1.183` | Ignition SCADA |
| `postgres-historian` | `192.168.1.184` | PostgreSQL historian |
| `gateway` | `192.168.1.187` | OPC UA/MQTT/Python gateway |

## Planned Architecture

```text
Webots Simulation
        |
        v
Python Gateway
OPC UA / MQTT
        |
        +----> Ignition SCADA
        |
        +----> PostgreSQL Historian
        |
        +----> TwinCAT PLC Logic


        
## Current Status

* [x] Proxmox VM stack created
* [x] Static DHCP reservations configured in main OPNsense
* [x] SSH access tested on Linux VMs
* [x] NoMachine access configured for Windows TwinCAT VM
* [x] Webots installed and launched on `webots-sim`
* [x] PostgreSQL installed on `postgres-historian`
* [x] `industrial_cell` database created
* [x] Initial historian schema created
* [ ] Ignition installed
* [ ] Gateway OPC UA server created
* [ ] Ignition connected to OPC UA gateway
* [ ] Webots simulation connected to gateway
* [ ] TwinCAT logic integrated
* [ ] Historian logging connected to gateway
